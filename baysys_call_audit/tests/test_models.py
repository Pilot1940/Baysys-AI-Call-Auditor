"""Tests for all 5 models."""
from datetime import datetime, timezone as tz

from django.test import TestCase

from baysys_call_audit.models import (
    CallRecording,
    CallTranscript,
    ComplianceFlag,
    OwnLLMScore,
    ProviderScore,
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


class CallRecordingModelTests(TestCase):
    def test_create_recording(self):
        r = _make_recording()
        self.assertEqual(r.status, "pending")
        self.assertEqual(r.retry_count, 0)
        self.assertIsNotNone(r.created_at)

    def test_str_representation(self):
        r = _make_recording()
        self.assertIn("Test Agent", str(r))
        self.assertIn("pending", str(r))

    def test_status_choices(self):
        r = _make_recording(status="submitted")
        self.assertEqual(r.status, "submitted")

    def test_provider_resource_id_unique(self):
        _make_recording(provider_resource_id="RES-001")
        with self.assertRaises(Exception):
            _make_recording(provider_resource_id="RES-001")

    def test_raw_s3_key_saves_without_error(self):
        # recording_url is CharField — accepts raw S3 object keys (no URL scheme required)
        raw_key = "Konex/call_recordings/2026/03/31/call_abc.mp3"
        r = _make_recording(recording_url=raw_key)
        self.assertEqual(r.recording_url, raw_key)

    def test_raw_s3_key_round_trip(self):
        # Saves and retrieves unchanged — no URL normalisation applied
        raw_key = "Rezolution/call_recordings/2026/03/31/xxxxxx_agent_2026-03-31.mp3"
        r = _make_recording(recording_url=raw_key)
        r.refresh_from_db()
        self.assertEqual(r.recording_url, raw_key)

    def test_nullable_fields(self):
        r = _make_recording()
        self.assertIsNone(r.customer_id)
        self.assertIsNone(r.portfolio_id)
        self.assertIsNone(r.supervisor_id)
        self.assertIsNone(r.agency_id)
        self.assertIsNone(r.customer_phone)
        self.assertIsNone(r.product_type)
        self.assertIsNone(r.bank_name)
        self.assertIsNone(r.error_message)
        self.assertIsNone(r.submitted_at)
        self.assertIsNone(r.completed_at)


class CallTranscriptModelTests(TestCase):
    def test_create_transcript(self):
        r = _make_recording()
        t = CallTranscript.objects.create(
            recording=r,
            transcript_text="Hello, this is a test call.",
            detected_language="en",
            total_call_duration=120,
        )
        self.assertEqual(t.transcript_text, "Hello, this is a test call.")
        self.assertEqual(t.detected_language, "en")
        self.assertEqual(t.recording.pk, r.pk)

    def test_one_to_one_relationship(self):
        r = _make_recording()
        CallTranscript.objects.create(recording=r, transcript_text="test")
        with self.assertRaises(Exception):
            CallTranscript.objects.create(recording=r, transcript_text="duplicate")

    def test_str_representation(self):
        r = _make_recording()
        t = CallTranscript.objects.create(
            recording=r,
            transcript_text="test",
            detected_language="hi",
            total_call_duration=60,
        )
        self.assertIn("hi", str(t))
        self.assertIn("60", str(t))


class ProviderScoreModelTests(TestCase):
    def test_create_provider_score(self):
        r = _make_recording()
        s = ProviderScore.objects.create(
            recording=r,
            template_id="TPL-001",
            audit_compliance_score=3,
            max_compliance_score=4,
        )
        self.assertEqual(s.template_id, "TPL-001")
        self.assertFalse(s.detected_restricted_keyword)
        self.assertEqual(s.restricted_keywords, [])

    def test_compute_percentage(self):
        r = _make_recording()
        s = ProviderScore(
            recording=r,
            template_id="TPL-001",
            audit_compliance_score=3,
            max_compliance_score=4,
        )
        s.compute_percentage()
        self.assertEqual(s.score_percentage, 75.00)

    def test_compute_percentage_zero_max(self):
        r = _make_recording()
        s = ProviderScore(
            recording=r,
            template_id="TPL-001",
            audit_compliance_score=3,
            max_compliance_score=0,
        )
        s.compute_percentage()
        self.assertIsNone(s.score_percentage)

    def test_multiple_scores_per_recording(self):
        r = _make_recording()
        ProviderScore.objects.create(recording=r, template_id="TPL-001")
        ProviderScore.objects.create(recording=r, template_id="TPL-002")
        self.assertEqual(r.provider_scores.count(), 2)

    def test_str_representation(self):
        r = _make_recording()
        s = ProviderScore.objects.create(recording=r, template_id="TPL-001")
        self.assertIn("TPL-001", str(s))


class ComplianceFlagModelTests(TestCase):
    def test_create_flag(self):
        r = _make_recording()
        f = ComplianceFlag.objects.create(
            recording=r,
            flag_type="abusive_language",
            severity="critical",
            description="Agent used abusive language",
        )
        self.assertEqual(f.flag_type, "abusive_language")
        self.assertTrue(f.auto_detected)
        self.assertFalse(f.reviewed)

    def test_multiple_flags_per_recording(self):
        r = _make_recording()
        ComplianceFlag.objects.create(
            recording=r, flag_type="outside_hours", severity="critical",
            description="test1",
        )
        ComplianceFlag.objects.create(
            recording=r, flag_type="restricted_keyword", severity="high",
            description="test2",
        )
        self.assertEqual(r.compliance_flags.count(), 2)

    def test_str_representation(self):
        r = _make_recording()
        f = ComplianceFlag.objects.create(
            recording=r, flag_type="rbi_coc_violation", severity="high",
            description="test",
        )
        self.assertIn("rbi_coc_violation", str(f))
        self.assertIn("high", str(f))


class OwnLLMScoreModelTests(TestCase):
    def test_create_llm_score(self):
        r = _make_recording()
        s = OwnLLMScore.objects.create(
            recording=r,
            score_template_name="default",
            total_score=20,
            max_score=28,
            model_used="gpt-4.1-mini",
        )
        self.assertEqual(s.score_template_name, "default")
        self.assertEqual(s.model_used, "gpt-4.1-mini")

    def test_compute_percentage(self):
        r = _make_recording()
        s = OwnLLMScore(
            recording=r,
            score_template_name="default",
            total_score=21,
            max_score=28,
        )
        s.compute_percentage()
        self.assertEqual(s.score_percentage, 75.00)

    def test_str_representation(self):
        r = _make_recording()
        s = OwnLLMScore.objects.create(
            recording=r, score_template_name="default",
        )
        self.assertIn("default", str(s))
