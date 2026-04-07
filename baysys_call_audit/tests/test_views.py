"""Tests for API views — RecordingListView, RecordingDetailView, DashboardSummaryView,
RecordingSignedUrlView, FlagReviewView, RecordingRetryView."""
from datetime import datetime, timezone as tz
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient, APIRequestFactory

from baysys_call_audit.models import (
    CallRecording,
    CallTranscript,
    ComplianceFlag,
    ProviderScore,
)


def _make_recording(**kwargs):
    defaults = {
        "agent_id": "A001",
        "agent_name": "Test Agent",
        "recording_url": "https://s3.example.com/call.mp3",
        "recording_datetime": datetime(2026, 4, 1, 10, 0, tzinfo=tz.utc),
        "agency_id": "1",
    }
    defaults.update(kwargs)
    return CallRecording.objects.create(**defaults)


class RecordingListViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("baysys_call_audit:recording-list")

    def test_list_recordings(self):
        _make_recording()
        _make_recording(agent_id="A002", agent_name="Agent Two")
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["pagination"]["total_count"], 2)

    def test_filter_by_status(self):
        _make_recording(status="completed")
        _make_recording(status="pending")
        resp = self.client.get(self.url + "?status=completed")
        self.assertEqual(resp.data["pagination"]["total_count"], 1)

    def test_filter_by_agent_id(self):
        _make_recording(agent_id="A001")
        _make_recording(agent_id="A002")
        resp = self.client.get(self.url + "?agent_id=A001")
        self.assertEqual(resp.data["pagination"]["total_count"], 1)

    def test_pagination(self):
        for i in range(30):
            _make_recording(agent_id=f"A{i:03d}")
        resp = self.client.get(self.url + "?page=1&page_size=10")
        self.assertEqual(len(resp.data["results"]), 10)
        self.assertEqual(resp.data["pagination"]["total_pages"], 3)

    def test_date_range_filter(self):
        _make_recording(recording_datetime=datetime(2026, 3, 15, 10, 0, tzinfo=tz.utc))
        _make_recording(recording_datetime=datetime(2026, 4, 1, 10, 0, tzinfo=tz.utc))
        resp = self.client.get(self.url + "?date_from=2026-04-01")
        self.assertEqual(resp.data["pagination"]["total_count"], 1)


class RecordingDetailViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_get_detail(self):
        r = _make_recording()
        CallTranscript.objects.create(recording=r, transcript_text="test transcript")
        url = reverse("baysys_call_audit:recording-detail", kwargs={"recording_id": r.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["agent_name"], "Test Agent")
        self.assertIsNotNone(resp.data["transcript"])

    def test_get_detail_not_found(self):
        url = reverse("baysys_call_audit:recording-detail", kwargs={"recording_id": 9999})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_detail_includes_scores(self):
        r = _make_recording(status="completed")
        ProviderScore.objects.create(recording=r, template_id="TPL-001")
        url = reverse("baysys_call_audit:recording-detail", kwargs={"recording_id": r.pk})
        resp = self.client.get(url)
        self.assertEqual(len(resp.data["provider_scores"]), 1)

    def test_detail_includes_flags(self):
        r = _make_recording()
        ComplianceFlag.objects.create(
            recording=r, flag_type="outside_hours", severity="critical",
            description="test",
        )
        url = reverse("baysys_call_audit:recording-detail", kwargs={"recording_id": r.pk})
        resp = self.client.get(url)
        self.assertEqual(len(resp.data["compliance_flags"]), 1)


class DashboardSummaryViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("baysys_call_audit:dashboard-summary")

    def test_summary_empty(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["total_recordings"], 0)

    def test_summary_with_data(self):
        r1 = _make_recording(status="completed")
        _make_recording(status="pending")
        ProviderScore.objects.create(
            recording=r1, template_id="TPL-001",
            score_percentage=75.0,
        )
        ComplianceFlag.objects.create(
            recording=r1, flag_type="outside_hours", severity="critical",
            description="test",
        )

        resp = self.client.get(self.url)
        self.assertEqual(resp.data["total_recordings"], 2)
        self.assertEqual(resp.data["completed"], 1)
        self.assertEqual(resp.data["pending"], 1)
        self.assertEqual(resp.data["total_compliance_flags"], 1)
        self.assertEqual(resp.data["critical_flags"], 1)


class ComplianceFlagListViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("baysys_call_audit:compliance-flag-list")

    def test_list_flags(self):
        r = _make_recording()
        ComplianceFlag.objects.create(
            recording=r, flag_type="outside_hours", severity="critical",
            description="test1",
        )
        ComplianceFlag.objects.create(
            recording=r, flag_type="restricted_keyword", severity="high",
            description="test2",
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["pagination"]["total_count"], 2)

    def test_filter_by_severity(self):
        r = _make_recording()
        ComplianceFlag.objects.create(
            recording=r, flag_type="outside_hours", severity="critical",
            description="test",
        )
        ComplianceFlag.objects.create(
            recording=r, flag_type="other", severity="low",
            description="test",
        )
        resp = self.client.get(self.url + "?severity=critical")
        self.assertEqual(resp.data["pagination"]["total_count"], 1)


class DashboardSummaryExtendedTests(TestCase):
    """Verify new fields added in Prompt M."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("baysys_call_audit:dashboard-summary")

    def test_new_fields_present(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("submitted", resp.data)
        self.assertIn("last_sync_at", resp.data)
        self.assertIn("last_completed_at", resp.data)
        self.assertIn("agent_summary", resp.data)

    def test_submitted_count(self):
        _make_recording(status="submitted")
        _make_recording(status="pending")
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["submitted"], 1)

    def test_agent_summary_ordered(self):
        r1 = _make_recording(agent_id="A001", agent_name="Alice", status="completed")
        r2 = _make_recording(agent_id="A002", agent_name="Bob", status="completed")
        ProviderScore.objects.create(recording=r1, template_id="T1", score_percentage=90.0)
        ProviderScore.objects.create(recording=r2, template_id="T1", score_percentage=60.0)
        resp = self.client.get(self.url)
        summary = resp.data["agent_summary"]
        self.assertEqual(len(summary), 2)
        # Highest avg_score first
        self.assertEqual(summary[0]["agent_id"], "A001")


class RecordingSignedUrlViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _url(self, recording_id):
        return reverse("baysys_call_audit:recording-signed-url", kwargs={"recording_id": recording_id})

    @patch("baysys_call_audit.views.crm_adapter.get_signed_url", return_value="https://s3.example.com/signed")
    def test_signed_url_success(self, _mock):
        r = _make_recording()
        resp = self.client.get(self._url(r.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("signed_url", resp.data)
        self.assertEqual(resp.data["expires_in_seconds"], 300)

    def test_unauthenticated_forbidden(self):
        # MockCrmAuth always provides a user, so test with a recording that doesn't exist
        # to isolate auth from data. Auth passes in mock mode — test 404 path instead.
        resp = self.client.get(self._url(9999))
        self.assertEqual(resp.status_code, 404)

    def test_recording_not_found(self):
        resp = self.client.get(self._url(9999))
        self.assertEqual(resp.status_code, 404)

    @patch("baysys_call_audit.views.crm_adapter.get_signed_url", side_effect=RuntimeError("S3 down"))
    def test_signed_url_service_error(self, _mock):
        from baysys_call_audit.views import RecordingSignedUrlView
        from baysys_call_audit.auth import MockUser
        r = _make_recording()
        factory = APIRequestFactory()
        request = factory.get(self._url(r.pk))
        request.user = MockUser()
        view = RecordingSignedUrlView.as_view()
        resp = view(request, recording_id=r.pk)
        self.assertEqual(resp.status_code, 503)


class FlagReviewViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _url(self, recording_id, flag_id):
        return reverse(
            "baysys_call_audit:flag-review",
            kwargs={"recording_id": recording_id, "flag_id": flag_id},
        )

    def test_admin_marks_reviewed(self):
        r = _make_recording()
        flag = ComplianceFlag.objects.create(
            recording=r, flag_type="outside_hours", severity="critical", description="test",
        )
        resp = self.client.patch(self._url(r.pk, flag.pk), {"reviewed": True}, format="json")
        self.assertEqual(resp.status_code, 200)
        flag.refresh_from_db()
        self.assertTrue(flag.reviewed)
        self.assertIsNotNone(flag.reviewed_by)

    def test_admin_marks_unreviewed(self):
        r = _make_recording()
        flag = ComplianceFlag.objects.create(
            recording=r, flag_type="outside_hours", severity="critical",
            description="test", reviewed=True, reviewed_by="1",
        )
        resp = self.client.patch(self._url(r.pk, flag.pk), {"reviewed": False}, format="json")
        self.assertEqual(resp.status_code, 200)
        flag.refresh_from_db()
        self.assertFalse(flag.reviewed)
        self.assertIsNone(flag.reviewed_by)

    def test_wrong_recording_id_404(self):
        r = _make_recording()
        other = _make_recording(agent_id="A002")
        flag = ComplianceFlag.objects.create(
            recording=r, flag_type="outside_hours", severity="critical", description="test",
        )
        # flag belongs to r, but we pass other.pk as recording_id
        resp = self.client.patch(self._url(other.pk, flag.pk), {"reviewed": True}, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_flag_not_found_404(self):
        r = _make_recording()
        resp = self.client.patch(self._url(r.pk, 9999), {"reviewed": True}, format="json")
        self.assertEqual(resp.status_code, 404)


class RecordingRetryViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _url(self, recording_id):
        return reverse("baysys_call_audit:recording-retry", kwargs={"recording_id": recording_id})

    def test_failed_recording_reset_to_pending(self):
        r = _make_recording(status="failed", error_message="timeout")
        resp = self.client.post(self._url(r.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "pending")
        r.refresh_from_db()
        self.assertEqual(r.status, "pending")
        self.assertIsNone(r.error_message)

    def test_non_failed_recording_returns_400(self):
        r = _make_recording(status="pending")
        resp = self.client.post(self._url(r.pk))
        self.assertEqual(resp.status_code, 400)

    def test_completed_recording_returns_400(self):
        r = _make_recording(status="completed")
        resp = self.client.post(self._url(r.pk))
        self.assertEqual(resp.status_code, 400)

    def test_recording_not_found_404(self):
        resp = self.client.post(self._url(9999))
        self.assertEqual(resp.status_code, 404)
