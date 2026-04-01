"""Tests for API views — RecordingListView, RecordingDetailView, DashboardSummaryView."""
from datetime import datetime, timezone as tz

from django.test import TestCase
from rest_framework.test import APIClient

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

    def test_list_recordings(self):
        _make_recording()
        _make_recording(agent_id="A002", agent_name="Agent Two")
        resp = self.client.get("/audit/recordings/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["pagination"]["total_count"], 2)

    def test_filter_by_status(self):
        _make_recording(status="completed")
        _make_recording(status="pending")
        resp = self.client.get("/audit/recordings/?status=completed")
        self.assertEqual(resp.data["pagination"]["total_count"], 1)

    def test_filter_by_agent_id(self):
        _make_recording(agent_id="A001")
        _make_recording(agent_id="A002")
        resp = self.client.get("/audit/recordings/?agent_id=A001")
        self.assertEqual(resp.data["pagination"]["total_count"], 1)

    def test_pagination(self):
        for i in range(30):
            _make_recording(agent_id=f"A{i:03d}")
        resp = self.client.get("/audit/recordings/?page=1&page_size=10")
        self.assertEqual(len(resp.data["results"]), 10)
        self.assertEqual(resp.data["pagination"]["total_pages"], 3)

    def test_date_range_filter(self):
        _make_recording(recording_datetime=datetime(2026, 3, 15, 10, 0, tzinfo=tz.utc))
        _make_recording(recording_datetime=datetime(2026, 4, 1, 10, 0, tzinfo=tz.utc))
        resp = self.client.get("/audit/recordings/?date_from=2026-04-01")
        self.assertEqual(resp.data["pagination"]["total_count"], 1)


class RecordingDetailViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_get_detail(self):
        r = _make_recording()
        CallTranscript.objects.create(recording=r, transcript_text="test transcript")
        resp = self.client.get(f"/audit/recordings/{r.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["agent_name"], "Test Agent")
        self.assertIsNotNone(resp.data["transcript"])

    def test_get_detail_not_found(self):
        resp = self.client.get("/audit/recordings/9999/")
        self.assertEqual(resp.status_code, 404)

    def test_detail_includes_scores(self):
        r = _make_recording(status="completed")
        ProviderScore.objects.create(recording=r, template_id="TPL-001")
        resp = self.client.get(f"/audit/recordings/{r.pk}/")
        self.assertEqual(len(resp.data["provider_scores"]), 1)

    def test_detail_includes_flags(self):
        r = _make_recording()
        ComplianceFlag.objects.create(
            recording=r, flag_type="outside_hours", severity="critical",
            description="test",
        )
        resp = self.client.get(f"/audit/recordings/{r.pk}/")
        self.assertEqual(len(resp.data["compliance_flags"]), 1)


class DashboardSummaryViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_summary_empty(self):
        resp = self.client.get("/audit/dashboard/summary/")
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

        resp = self.client.get("/audit/dashboard/summary/")
        self.assertEqual(resp.data["total_recordings"], 2)
        self.assertEqual(resp.data["completed"], 1)
        self.assertEqual(resp.data["pending"], 1)
        self.assertEqual(resp.data["total_compliance_flags"], 1)
        self.assertEqual(resp.data["critical_flags"], 1)


class ComplianceFlagListViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

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
        resp = self.client.get("/audit/compliance-flags/")
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
        resp = self.client.get("/audit/compliance-flags/?severity=critical")
        self.assertEqual(resp.data["pagination"]["total_count"], 1)
