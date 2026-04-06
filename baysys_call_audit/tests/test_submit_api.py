"""Tests for SubmitRecordingsView and PollStuckRecordingsView."""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from baysys_call_audit.auth import MockCrmAuth, MockUser
from baysys_call_audit.views import PollStuckRecordingsView, SubmitRecordingsView

_SUBMIT_RESULT = {"submitted": 5, "failed": 0, "skipped": 0}
_POLL_RESULT = {
    "polled": 3,
    "recovered": 2,
    "still_processing": 1,
    "errors": 0,
    "dry_run": False,
    "threshold_minutes": 30,
}


class SubmitRecordingsViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = SubmitRecordingsView.as_view()

    def _post(self, role_id=1):
        request = self.factory.post("/audit/recordings/submit/", format="json")
        request.user = MockUser(role_id=role_id)
        return self.view(request)

    @patch("baysys_call_audit.views.submit_pending_recordings", return_value=_SUBMIT_RESULT)
    def test_admin_submit_returns_200(self, mock_submit):
        response = self._post(role_id=1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["submitted"], 5)
        self.assertEqual(response.data["failed"], 0)
        mock_submit.assert_called_once()

    def test_agent_forbidden(self):
        response = self._post(role_id=3)
        self.assertEqual(response.status_code, 403)

    @patch("baysys_call_audit.views.submit_pending_recordings", side_effect=RuntimeError("boom"))
    def test_submit_exception_returns_500(self, _):
        response = self._post(role_id=1)
        self.assertEqual(response.status_code, 500)
        self.assertIn("error", response.data)

    @patch.object(MockCrmAuth, "authenticate", return_value=None)
    def test_unauthenticated_returns_403(self, _):
        # DRF coerces NotAuthenticated → 403 when no WWW-Authenticate header is provided
        request = self.factory.post("/audit/recordings/submit/", format="json")
        response = self.view(request)
        self.assertEqual(response.status_code, 403)


class PollStuckRecordingsViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = PollStuckRecordingsView.as_view()

    def _post(self, data=None, role_id=1):
        request = self.factory.post(
            "/audit/recordings/poll/",
            data=data or {},
            format="json",
        )
        request.user = MockUser(role_id=role_id)
        return self.view(request)

    @patch("baysys_call_audit.views.run_poll_stuck_recordings", return_value=_POLL_RESULT)
    def test_admin_poll_returns_200_with_summary_keys(self, mock_poll):
        response = self._post(role_id=1)
        self.assertEqual(response.status_code, 200)
        for key in ("polled", "recovered", "still_processing", "errors", "dry_run", "threshold_minutes"):
            self.assertIn(key, response.data)
        mock_poll.assert_called_once()

    @patch("baysys_call_audit.views.run_poll_stuck_recordings")
    def test_dry_run_true_in_body_and_response(self, mock_poll):
        mock_poll.return_value = {**_POLL_RESULT, "dry_run": True}
        response = self._post(data={"dry_run": True}, role_id=1)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["dry_run"])
        _, kwargs = mock_poll.call_args
        self.assertTrue(kwargs.get("dry_run", False))

    def test_agent_forbidden(self):
        response = self._post(role_id=3)
        self.assertEqual(response.status_code, 403)

    @patch.object(MockCrmAuth, "authenticate", return_value=None)
    def test_unauthenticated_returns_403(self, _):
        # DRF coerces NotAuthenticated → 403 when no WWW-Authenticate header is provided
        request = self.factory.post("/audit/recordings/poll/", format="json")
        response = self.view(request)
        self.assertEqual(response.status_code, 403)

    @patch("baysys_call_audit.views.run_poll_stuck_recordings", side_effect=RuntimeError("poll boom"))
    def test_poll_exception_returns_500(self, _):
        response = self._post(role_id=1)
        self.assertEqual(response.status_code, 500)
        self.assertIn("error", response.data)

    @patch("baysys_call_audit.views.run_poll_stuck_recordings", return_value=_POLL_RESULT)
    def test_manager_can_poll(self, mock_poll):
        response = self._post(role_id=2)
        self.assertEqual(response.status_code, 200)
        mock_poll.assert_called_once()

    @patch("baysys_call_audit.views.run_poll_stuck_recordings", return_value=_POLL_RESULT)
    def test_custom_batch_size_passed_to_service(self, mock_poll):
        self._post(data={"batch_size": 10}, role_id=1)
        _, kwargs = mock_poll.call_args
        self.assertEqual(kwargs.get("batch_size"), 10)
