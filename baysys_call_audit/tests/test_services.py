"""Tests for services.py — ingestion pipeline, scoring, compliance."""
from datetime import datetime, timezone as tz
from unittest.mock import patch

from django.test import TestCase, override_settings

from baysys_call_audit.models import (
    CallRecording,
    CallTranscript,
    ProviderScore,
)
from baysys_call_audit.services import (
    process_provider_webhook,
    run_own_llm_scoring,
    submit_pending_recordings,
)


def _make_recording(**kwargs):
    defaults = {
        "agent_id": "A001",
        "agent_name": "Test Agent",
        "recording_url": "https://s3.example.com/call.mp3",
        "recording_datetime": datetime(2026, 4, 1, 10, 0, tzinfo=tz.utc),
    }
    defaults.update(kwargs)
    return CallRecording.objects.create(**defaults)


@override_settings(
    SPEECH_PROVIDER_TEMPLATE_ID="TPL-001",
    SPEECH_PROVIDER_CALLBACK_URL="https://example.com/webhook/",
)
class SubmitPendingRecordingsTests(TestCase):
    @patch("baysys_call_audit.services.speech_provider.submit_recording")
    def test_submit_pending_success(self, mock_submit):
        mock_submit.return_value = "RES-001"
        _make_recording()

        result = submit_pending_recordings(batch_size=10)
        self.assertEqual(result["submitted"], 1)
        self.assertEqual(result["failed"], 0)

        r = CallRecording.objects.first()
        self.assertEqual(r.status, "submitted")
        self.assertEqual(r.provider_resource_id, "RES-001")

    @patch("baysys_call_audit.services.speech_provider.submit_recording")
    def test_submit_pending_failure(self, mock_submit):
        from baysys_call_audit.speech_provider import ProviderError
        mock_submit.side_effect = ProviderError("API error", status_code=500)
        _make_recording()

        result = submit_pending_recordings(batch_size=10)
        self.assertEqual(result["failed"], 1)

        r = CallRecording.objects.first()
        self.assertEqual(r.status, "failed")
        self.assertEqual(r.retry_count, 1)

    def test_submit_skips_no_url(self):
        _make_recording(recording_url="")
        result = submit_pending_recordings(batch_size=10)
        self.assertEqual(result["skipped"], 1)

    @patch("baysys_call_audit.services.speech_provider.submit_recording")
    def test_submit_only_pending(self, mock_submit):
        mock_submit.return_value = "RES-002"
        _make_recording(status="completed", provider_resource_id="RES-DONE")
        _make_recording(status="pending")

        result = submit_pending_recordings(batch_size=10)
        self.assertEqual(result["submitted"], 1)

    @patch("baysys_call_audit.services.speech_provider.submit_recording")
    def test_batch_size_limit(self, mock_submit):
        counter = {"n": 0}

        def _unique_id(*args, **kwargs):
            counter["n"] += 1
            return f"RES-BATCH-{counter['n']}"

        mock_submit.side_effect = _unique_id
        for i in range(5):
            _make_recording(agent_id=f"A{i:03d}")

        result = submit_pending_recordings(batch_size=3)
        self.assertEqual(result["submitted"], 3)


@override_settings(SPEECH_PROVIDER_TEMPLATE_ID="TPL-001")
class ProcessProviderWebhookTests(TestCase):
    @patch("baysys_call_audit.compliance.load_compliance_rules", return_value={"provider_rules": []})
    @patch("baysys_call_audit.compliance.load_fatal_level_rules", return_value={})
    def test_process_webhook_creates_all(self, _fl, _cr):
        r = _make_recording(status="submitted", provider_resource_id="RES-200")
        payload = {
            "resource_insight_id": "RES-200",
            "transcript": "Hello world",
            "detected_language": "en",
            "total_call_duration": 60,
            "audit_compliance_score": 2,
            "max_compliance_score": 4,
            "detected_restricted_keyword": False,
            "restricted_keywords": [],
            "insights": {
                "category_data": [],
                "subjective_data": [],
            },
        }
        result = process_provider_webhook(payload)
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "completed")
        self.assertTrue(CallTranscript.objects.filter(recording=r).exists())
        self.assertTrue(ProviderScore.objects.filter(recording=r).exists())

    def test_process_webhook_missing_resource_id(self):
        result = process_provider_webhook({})
        self.assertIsNone(result)

    def test_process_webhook_unknown_resource_id(self):
        result = process_provider_webhook({"resource_insight_id": "NOPE"})
        self.assertIsNone(result)

    def test_process_webhook_idempotent(self):
        _make_recording(status="completed", provider_resource_id="RES-300")
        result = process_provider_webhook({"resource_insight_id": "RES-300"})
        self.assertIsNotNone(result)
        self.assertEqual(CallTranscript.objects.count(), 0)


class OwnLLMScoringTests(TestCase):
    def test_run_scoring_no_recording(self):
        result = run_own_llm_scoring(999)
        self.assertIsNone(result)

    def test_run_scoring_no_transcript(self):
        r = _make_recording()
        result = run_own_llm_scoring(r.pk)
        self.assertIsNone(result)
