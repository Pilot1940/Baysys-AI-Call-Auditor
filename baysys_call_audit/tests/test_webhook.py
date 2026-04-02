"""Tests for the provider webhook receiver view."""
from datetime import datetime, timezone as tz
from unittest.mock import patch

from django.test import TestCase, override_settings
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
        "status": "submitted",
        "provider_resource_id": "RES-100",
    }
    defaults.update(kwargs)
    return CallRecording.objects.create(**defaults)


SAMPLE_WEBHOOK_PAYLOAD = {
    "resource_insight_id": "RES-100",
    "transcript": "Agent: Hello, this is Test Agent. Customer: Hi.",
    "detected_language": "en",
    "total_call_duration": 203,
    "total_non_speech_duration": 49,
    "customer_talk_duration": 36,
    "agent_talk_duration": 110,
    "audit_compliance_score": 3,
    "max_compliance_score": 4,
    "customer_sentiment": "Neutral",
    "agent_sentiment": "Neutral",
    "detected_restricted_keyword": False,
    "restricted_keywords": [],
    "insights": {
        "category_data": [],
        "subjective_data": [
            {"audit_parameter_name": "Summary", "answer": "Agent greeted customer."},
            {"audit_parameter_name": "Next Actionable", "answer": "Follow up in 2 days."},
        ],
    },
}


@override_settings(SPEECH_PROVIDER_TEMPLATE_ID="TPL-001")
class ProviderWebhookViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/audit/webhook/provider/"

    @patch("baysys_call_audit.compliance.load_compliance_rules", return_value={"provider_rules": []})
    @patch("baysys_call_audit.compliance.load_fatal_level_rules", return_value={})
    def test_webhook_success(self, _fl, _cr):
        _make_recording()
        resp = self.client.post(self.url, SAMPLE_WEBHOOK_PAYLOAD, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "ok")

        recording = CallRecording.objects.get(provider_resource_id="RES-100")
        self.assertEqual(recording.status, "completed")

    @patch("baysys_call_audit.compliance.load_compliance_rules", return_value={"provider_rules": []})
    @patch("baysys_call_audit.compliance.load_fatal_level_rules", return_value={})
    def test_webhook_creates_transcript(self, _fl, _cr):
        _make_recording()
        self.client.post(self.url, SAMPLE_WEBHOOK_PAYLOAD, format="json")

        transcript = CallTranscript.objects.get(recording__provider_resource_id="RES-100")
        self.assertIn("Test Agent", transcript.transcript_text)
        self.assertEqual(transcript.detected_language, "en")
        self.assertEqual(transcript.total_call_duration, 203)
        self.assertEqual(transcript.summary, "Agent greeted customer.")
        self.assertEqual(transcript.next_actionable, "Follow up in 2 days.")

    @patch("baysys_call_audit.compliance.load_compliance_rules", return_value={"provider_rules": []})
    @patch("baysys_call_audit.compliance.load_fatal_level_rules", return_value={})
    def test_webhook_creates_provider_score(self, _fl, _cr):
        _make_recording()
        self.client.post(self.url, SAMPLE_WEBHOOK_PAYLOAD, format="json")

        score = ProviderScore.objects.get(recording__provider_resource_id="RES-100")
        self.assertEqual(score.audit_compliance_score, 3)
        self.assertEqual(score.max_compliance_score, 4)
        self.assertEqual(score.score_percentage, 75.00)

    def test_webhook_empty_payload(self):
        resp = self.client.post(self.url, {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_webhook_unknown_resource_id(self):
        resp = self.client.post(
            self.url,
            {"resource_insight_id": "UNKNOWN"},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_webhook_idempotent(self):
        r = _make_recording(status="completed")
        resp = self.client.post(self.url, SAMPLE_WEBHOOK_PAYLOAD, format="json")
        self.assertEqual(resp.status_code, 200)
        # Should not create duplicate transcript
        self.assertEqual(CallTranscript.objects.filter(recording=r).count(), 0)

    @patch("baysys_call_audit.compliance.load_compliance_rules", return_value={"provider_rules": []})
    @patch("baysys_call_audit.compliance.load_fatal_level_rules", return_value={})
    def test_webhook_restricted_keywords_creates_flag(self, _fl, _cr):
        _make_recording()
        payload = {**SAMPLE_WEBHOOK_PAYLOAD, "detected_restricted_keyword": True, "restricted_keywords": ["threat"]}
        self.client.post(self.url, payload, format="json")

        flags = ComplianceFlag.objects.filter(recording__provider_resource_id="RES-100")
        self.assertTrue(flags.filter(flag_type="restricted_keyword").exists())

    @patch("baysys_call_audit.compliance.load_compliance_rules", return_value={"provider_rules": []})
    @patch("baysys_call_audit.compliance.load_fatal_level_rules", return_value={})
    def test_webhook_outside_hours_creates_flag(self, _fl, _cr):
        """Outside-hours is now a metadata rule checked at ingestion, not webhook.
        Verify no outside_hours flag from webhook processing."""
        _make_recording(
            recording_datetime=datetime(2026, 4, 1, 6, 0, tzinfo=tz.utc),
            provider_resource_id="RES-EARLY",
        )
        payload = {**SAMPLE_WEBHOOK_PAYLOAD, "resource_insight_id": "RES-EARLY"}
        self.client.post(self.url, payload, format="json")

        flags = ComplianceFlag.objects.filter(recording__provider_resource_id="RES-EARLY")
        # No outside_hours from webhook — that's a metadata rule now
        self.assertFalse(flags.filter(flag_type="outside_hours").exists())


class ProviderWebhookIPAllowlistTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/audit/webhook/provider/"

    @override_settings(SPEECH_PROVIDER_WEBHOOK_ALLOWED_IPS="203.0.113.10,203.0.113.11")
    def test_allowed_ip_via_remote_addr(self):
        """Request from a whitelisted IP is passed through (hits 400 for empty payload, not 403)."""
        resp = self.client.post(
            self.url, {}, format="json",
            REMOTE_ADDR="203.0.113.10",
        )
        self.assertEqual(resp.status_code, 400)

    @override_settings(SPEECH_PROVIDER_WEBHOOK_ALLOWED_IPS="203.0.113.10,203.0.113.11")
    def test_allowed_ip_via_x_forwarded_for(self):
        """First IP in X-Forwarded-For is checked against the allowlist."""
        resp = self.client.post(
            self.url, {}, format="json",
            HTTP_X_FORWARDED_FOR="203.0.113.11, 10.0.0.1",
        )
        self.assertEqual(resp.status_code, 400)

    @override_settings(SPEECH_PROVIDER_WEBHOOK_ALLOWED_IPS="203.0.113.10")
    def test_blocked_ip_returns_403(self):
        """Request from an IP not in the allowlist is rejected with 403."""
        resp = self.client.post(
            self.url, {}, format="json",
            REMOTE_ADDR="1.2.3.4",
        )
        self.assertEqual(resp.status_code, 403)

    @override_settings(SPEECH_PROVIDER_WEBHOOK_ALLOWED_IPS="")
    def test_empty_setting_allows_all(self):
        """Empty allowlist setting permits any IP (returns 400 for empty payload, not 403)."""
        resp = self.client.post(
            self.url, {}, format="json",
            REMOTE_ADDR="1.2.3.4",
        )
        self.assertEqual(resp.status_code, 400)
