"""Tests for the provider webhook receiver view."""
from datetime import datetime, timezone as tz

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
        "category_data": [
            {"audit_parameter_name": "Conversation Category", "answer": ["Request"]},
        ],
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

    def test_webhook_success(self):
        _make_recording()
        resp = self.client.post(self.url, SAMPLE_WEBHOOK_PAYLOAD, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "ok")

        recording = CallRecording.objects.get(provider_resource_id="RES-100")
        self.assertEqual(recording.status, "completed")

    def test_webhook_creates_transcript(self):
        _make_recording()
        self.client.post(self.url, SAMPLE_WEBHOOK_PAYLOAD, format="json")

        transcript = CallTranscript.objects.get(recording__provider_resource_id="RES-100")
        self.assertIn("Test Agent", transcript.transcript_text)
        self.assertEqual(transcript.detected_language, "en")
        self.assertEqual(transcript.total_call_duration, 203)
        self.assertEqual(transcript.summary, "Agent greeted customer.")
        self.assertEqual(transcript.next_actionable, "Follow up in 2 days.")

    def test_webhook_creates_provider_score(self):
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

    def test_webhook_restricted_keywords_creates_flag(self):
        _make_recording()
        payload = {**SAMPLE_WEBHOOK_PAYLOAD, "detected_restricted_keyword": True, "restricted_keywords": ["threat"]}
        self.client.post(self.url, payload, format="json")

        flags = ComplianceFlag.objects.filter(recording__provider_resource_id="RES-100")
        self.assertTrue(flags.filter(flag_type="restricted_keyword").exists())

    def test_webhook_outside_hours_creates_flag(self):
        _make_recording(
            recording_datetime=datetime(2026, 4, 1, 6, 0, tzinfo=tz.utc),
            provider_resource_id="RES-EARLY",
        )
        payload = {**SAMPLE_WEBHOOK_PAYLOAD, "resource_insight_id": "RES-EARLY"}
        self.client.post(self.url, payload, format="json")

        flags = ComplianceFlag.objects.filter(recording__provider_resource_id="RES-EARLY")
        self.assertTrue(flags.filter(flag_type="outside_hours").exists())
