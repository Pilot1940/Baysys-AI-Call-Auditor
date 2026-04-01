"""Tests for the SyncCallLogsView API endpoint."""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from baysys_call_audit.auth import MockUser
from baysys_call_audit.views import SyncCallLogsView


class SyncCallLogsViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = SyncCallLogsView.as_view()

    def _post(self, data=None, role_id=1):
        request = self.factory.post(
            "/audit/recordings/sync/",
            data=data or {},
            format="json",
        )
        request.user = MockUser(role_id=role_id)
        return self.view(request)

    @patch("baysys_call_audit.views.run_sync_for_date")
    def test_admin_can_sync(self, mock_sync):
        mock_sync.return_value = {
            "fetched": 100, "created": 90, "skipped_dedup": 5,
            "skipped_validation": 3, "unknown_agents": 2, "errors": 0,
            "duration_seconds": 1.5,
        }
        response = self._post(role_id=1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ok")
        self.assertEqual(response.data["created"], 90)
        mock_sync.assert_called_once()

    @patch("baysys_call_audit.views.run_sync_for_date")
    def test_supervisor_can_sync(self, mock_sync):
        mock_sync.return_value = {
            "fetched": 0, "created": 0, "skipped_dedup": 0,
            "skipped_validation": 0, "unknown_agents": 0, "errors": 0,
            "duration_seconds": 0.1,
        }
        response = self._post(role_id=4)
        self.assertEqual(response.status_code, 200)

    def test_manager_forbidden(self):
        response = self._post(role_id=2)
        self.assertEqual(response.status_code, 403)
        self.assertIn("Insufficient permissions", response.data["error"])

    def test_agent_forbidden(self):
        response = self._post(role_id=3)
        self.assertEqual(response.status_code, 403)

    def test_invalid_date_returns_400(self):
        response = self._post(data={"date": "not-a-date"}, role_id=1)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid date", response.data["error"])

    @patch("baysys_call_audit.views.run_sync_for_date")
    def test_no_body_defaults(self, mock_sync):
        mock_sync.return_value = {
            "fetched": 0, "created": 0, "skipped_dedup": 0,
            "skipped_validation": 0, "unknown_agents": 0, "errors": 0,
            "duration_seconds": 0.1,
        }
        response = self._post(data={}, role_id=1)
        self.assertEqual(response.status_code, 200)
        # Should call with target_date=None (defaults to yesterday inside run_sync_for_date)
        call_kwargs = mock_sync.call_args[1]
        self.assertIsNone(call_kwargs["target_date"])

    @patch("baysys_call_audit.views.run_sync_for_date")
    def test_dry_run(self, mock_sync):
        mock_sync.return_value = {
            "fetched": 10, "created": 10, "skipped_dedup": 0,
            "skipped_validation": 0, "unknown_agents": 0, "errors": 0,
            "duration_seconds": 0.1,
        }
        response = self._post(data={"dry_run": True}, role_id=1)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["dry_run"])
        call_kwargs = mock_sync.call_args[1]
        self.assertTrue(call_kwargs["dry_run"])

    @patch("baysys_call_audit.views.run_sync_for_date")
    def test_response_includes_duration(self, mock_sync):
        mock_sync.return_value = {
            "fetched": 0, "created": 0, "skipped_dedup": 0,
            "skipped_validation": 0, "unknown_agents": 0, "errors": 0,
            "duration_seconds": 3.7,
        }
        response = self._post(role_id=1)
        self.assertEqual(response.data["duration_seconds"], 3.7)

    @patch("baysys_call_audit.views.run_sync_for_date")
    def test_custom_date_and_batch_size(self, mock_sync):
        mock_sync.return_value = {
            "fetched": 0, "created": 0, "skipped_dedup": 0,
            "skipped_validation": 0, "unknown_agents": 0, "errors": 0,
            "duration_seconds": 0.1,
        }
        response = self._post(
            data={"date": "2026-03-30", "batch_size": 1000},
            role_id=1,
        )
        self.assertEqual(response.status_code, 200)
        from datetime import date
        call_kwargs = mock_sync.call_args[1]
        self.assertEqual(call_kwargs["target_date"], date(2026, 3, 30))
        self.assertEqual(call_kwargs["batch_size"], 1000)
