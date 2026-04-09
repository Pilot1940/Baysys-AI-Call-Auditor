"""
Tests for submission tier system:
  - _determine_submission_tier() and _tier_matches() in ingestion.py
  - submission_tier set on CallRecording at creation
  - submit_pending_recordings() tier filter
  - S3 URL re-signing in submit_pending_recordings()
  - submit_recordings management command
"""
from datetime import datetime, timezone as tz
from io import StringIO
from unittest.mock import MagicMock, patch

from django.test import TestCase

from baysys_call_audit.ingestion import (
    _determine_submission_tier,
    _load_submission_priority,
    _tier_matches,
    create_recording_from_row,
)
from baysys_call_audit.management.commands.submit_recordings import Command as SubmitCommand
from baysys_call_audit.models import CallRecording
from baysys_call_audit.services import submit_pending_recordings


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_recording(**kwargs):
    defaults = {
        "agent_id": "A001",
        "agent_name": "Test Agent",
        "recording_url": "s3://bucket/call.mp3",
        "recording_datetime": datetime(2026, 4, 1, 10, 0, tzinfo=tz.utc),
        "status": "pending",
        "submission_tier": "normal",
        "download_recording_status": "success",
    }
    defaults.update(kwargs)
    return CallRecording.objects.create(**defaults)


SAMPLE_PRIORITY_CONFIG = {
    "tiers": {
        "immediate": {
            "agency_ids": [1, 2],
            "bank_names": ["Axis Bank"],
            "product_types": ["credit card"],
        },
        "off_peak": {
            "agency_ids": [99],
            "bank_names": ["Rural Bank"],
            "product_types": [],
        },
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# _tier_matches
# ─────────────────────────────────────────────────────────────────────────────

class TierMatchesTests(TestCase):
    def test_agency_id_match(self):
        tier_cfg = {"agency_ids": [1, 2], "bank_names": [], "product_types": []}
        self.assertTrue(_tier_matches({"agency_id": "1"}, tier_cfg))
        self.assertFalse(_tier_matches({"agency_id": "3"}, tier_cfg))

    def test_bank_name_substring_match(self):
        tier_cfg = {"agency_ids": [], "bank_names": ["Axis Bank"], "product_types": []}
        self.assertTrue(_tier_matches({"bank_name": "Axis Bank - PL"}, tier_cfg))
        self.assertTrue(_tier_matches({"bank_name": "axis bank"}, tier_cfg))
        self.assertFalse(_tier_matches({"bank_name": "HDFC Bank"}, tier_cfg))

    def test_product_type_exact_match(self):
        tier_cfg = {"agency_ids": [], "bank_names": [], "product_types": ["credit card"]}
        self.assertTrue(_tier_matches({"product_type": "Credit Card"}, tier_cfg))
        self.assertFalse(_tier_matches({"product_type": "Personal Loan"}, tier_cfg))

    def test_empty_config_no_match(self):
        tier_cfg = {"agency_ids": [], "bank_names": [], "product_types": []}
        self.assertFalse(_tier_matches({"agency_id": "1", "bank_name": "Axis"}, tier_cfg))

    def test_none_config_no_match(self):
        self.assertFalse(_tier_matches({"agency_id": "1"}, {}))

    def test_missing_row_fields_no_match(self):
        tier_cfg = {"agency_ids": [1], "bank_names": ["Axis"], "product_types": ["PL"]}
        self.assertFalse(_tier_matches({}, tier_cfg))

    def test_none_row_values_no_match(self):
        tier_cfg = {"agency_ids": [1], "bank_names": ["Axis"], "product_types": ["PL"]}
        self.assertFalse(_tier_matches({"agency_id": None, "bank_name": None, "product_type": None}, tier_cfg))


# ─────────────────────────────────────────────────────────────────────────────
# _determine_submission_tier
# ─────────────────────────────────────────────────────────────────────────────

class DetermineSubmissionTierTests(TestCase):
    @patch("baysys_call_audit.ingestion._load_submission_priority")
    def test_immediate_by_agency(self, mock_config):
        mock_config.return_value = SAMPLE_PRIORITY_CONFIG
        row = {"agency_id": "2", "bank_name": "Some Bank", "product_type": "Personal Loan"}
        self.assertEqual(_determine_submission_tier(row), "immediate")

    @patch("baysys_call_audit.ingestion._load_submission_priority")
    def test_immediate_by_bank(self, mock_config):
        mock_config.return_value = SAMPLE_PRIORITY_CONFIG
        row = {"agency_id": "50", "bank_name": "Axis Bank PL", "product_type": "Personal Loan"}
        self.assertEqual(_determine_submission_tier(row), "immediate")

    @patch("baysys_call_audit.ingestion._load_submission_priority")
    def test_immediate_by_product_type(self, mock_config):
        mock_config.return_value = SAMPLE_PRIORITY_CONFIG
        row = {"agency_id": "50", "bank_name": "HDFC Bank", "product_type": "Credit Card"}
        self.assertEqual(_determine_submission_tier(row), "immediate")

    @patch("baysys_call_audit.ingestion._load_submission_priority")
    def test_off_peak_by_agency(self, mock_config):
        mock_config.return_value = SAMPLE_PRIORITY_CONFIG
        row = {"agency_id": "99", "bank_name": "HDFC Bank", "product_type": "Personal Loan"}
        self.assertEqual(_determine_submission_tier(row), "off_peak")

    @patch("baysys_call_audit.ingestion._load_submission_priority")
    def test_off_peak_by_bank(self, mock_config):
        mock_config.return_value = SAMPLE_PRIORITY_CONFIG
        row = {"agency_id": "50", "bank_name": "Rural Bank Loans", "product_type": "Personal Loan"}
        self.assertEqual(_determine_submission_tier(row), "off_peak")

    @patch("baysys_call_audit.ingestion._load_submission_priority")
    def test_immediate_beats_off_peak(self, mock_config):
        """Agency matches both immediate and off_peak — immediate wins."""
        config = {
            "tiers": {
                "immediate": {"agency_ids": [1], "bank_names": [], "product_types": []},
                "off_peak": {"agency_ids": [1], "bank_names": [], "product_types": []},
            }
        }
        mock_config.return_value = config
        self.assertEqual(_determine_submission_tier({"agency_id": "1"}), "immediate")

    @patch("baysys_call_audit.ingestion._load_submission_priority")
    def test_default_normal(self, mock_config):
        mock_config.return_value = SAMPLE_PRIORITY_CONFIG
        row = {"agency_id": "50", "bank_name": "HDFC Bank", "product_type": "Personal Loan"}
        self.assertEqual(_determine_submission_tier(row), "normal")

    @patch("baysys_call_audit.ingestion._load_submission_priority")
    def test_empty_config_returns_normal(self, mock_config):
        mock_config.return_value = {}
        self.assertEqual(_determine_submission_tier({"agency_id": "1"}), "normal")

    @patch("baysys_call_audit.ingestion._load_submission_priority")
    def test_missing_tiers_key_returns_normal(self, mock_config):
        mock_config.return_value = {"version": "1.0"}
        self.assertEqual(_determine_submission_tier({"agency_id": "1"}), "normal")


# ─────────────────────────────────────────────────────────────────────────────
# Config loading
# ─────────────────────────────────────────────────────────────────────────────

class LoadSubmissionPriorityTests(TestCase):
    def test_real_file_loads(self):
        """The real submission_priority.yaml loads without error."""
        # Clear cache before test
        _load_submission_priority.cache_clear()
        config = _load_submission_priority()
        self.assertIn("tiers", config)
        _load_submission_priority.cache_clear()

    @patch("baysys_call_audit.ingestion.open", side_effect=FileNotFoundError)
    def test_missing_file_returns_empty(self, _mock):
        _load_submission_priority.cache_clear()
        config = _load_submission_priority()
        self.assertEqual(config, {})
        _load_submission_priority.cache_clear()

    @patch("baysys_call_audit.ingestion.open")
    def test_malformed_yaml_returns_empty(self, mock_open):
        import yaml  # noqa: PLC0415
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        mock_open.return_value.read = MagicMock(return_value="")
        _load_submission_priority.cache_clear()
        with patch("yaml.safe_load", side_effect=yaml.YAMLError("bad yaml")):
            config = _load_submission_priority()
        self.assertEqual(config, {})
        _load_submission_priority.cache_clear()


# ─────────────────────────────────────────────────────────────────────────────
# Tier assigned at creation
# ─────────────────────────────────────────────────────────────────────────────

class TierAssignedAtCreationTests(TestCase):
    # check_metadata_compliance is a lazy import inside create_recording_from_row:
    # "from .compliance import check_metadata_compliance"
    # Patch via the compliance module to prevent actual compliance logic running.

    @patch("baysys_call_audit.ingestion._load_submission_priority")
    @patch("baysys_call_audit.compliance.check_metadata_compliance")
    def test_default_tier_is_normal(self, mock_compliance, mock_config):
        mock_config.return_value = {}
        row = {
            "agent_id": "A001",
            "agent_name": "Agent One",
            "recording_url": "s3://bucket/call001.mp3",
            "recording_datetime": "2026-04-01T10:00:00",
        }
        recording, created = create_recording_from_row(row)
        self.assertTrue(created)
        self.assertEqual(recording.submission_tier, "normal")

    @patch("baysys_call_audit.ingestion._load_submission_priority")
    @patch("baysys_call_audit.compliance.check_metadata_compliance")
    def test_immediate_tier_assigned(self, mock_compliance, mock_config):
        mock_config.return_value = {
            "tiers": {
                "immediate": {"agency_ids": [5], "bank_names": [], "product_types": []},
                "off_peak": {"agency_ids": [], "bank_names": [], "product_types": []},
            }
        }
        row = {
            "agent_id": "A002",
            "agent_name": "Agent Two",
            "recording_url": "s3://bucket/call002.mp3",
            "recording_datetime": "2026-04-01T10:00:00",
            "agency_id": "5",
        }
        recording, created = create_recording_from_row(row)
        self.assertTrue(created)
        self.assertEqual(recording.submission_tier, "immediate")

    @patch("baysys_call_audit.ingestion._load_submission_priority")
    @patch("baysys_call_audit.compliance.check_metadata_compliance")
    def test_off_peak_tier_assigned(self, mock_compliance, mock_config):
        mock_config.return_value = {
            "tiers": {
                "immediate": {"agency_ids": [], "bank_names": [], "product_types": []},
                "off_peak": {"agency_ids": [7], "bank_names": [], "product_types": []},
            }
        }
        row = {
            "agent_id": "A003",
            "agent_name": "Agent Three",
            "recording_url": "s3://bucket/call003.mp3",
            "recording_datetime": "2026-04-01T10:00:00",
            "agency_id": "7",
        }
        recording, created = create_recording_from_row(row)
        self.assertTrue(created)
        self.assertEqual(recording.submission_tier, "off_peak")


# ─────────────────────────────────────────────────────────────────────────────
# submit_pending_recordings — tier filter
# ─────────────────────────────────────────────────────────────────────────────

def _unique_resource_id():
    """Generator yielding unique provider resource IDs."""
    counter = [0]
    def _gen(url):
        counter[0] += 1
        return f"RES-{counter[0]:04d}"
    return _gen


class SubmitPendingRecordingsTierTests(TestCase):
    def setUp(self):
        self.r_immediate = _make_recording(
            recording_url="s3://bucket/imm.mp3", submission_tier="immediate"
        )
        self.r_normal = _make_recording(
            recording_url="s3://bucket/norm.mp3", submission_tier="normal"
        )
        self.r_off_peak = _make_recording(
            recording_url="s3://bucket/off.mp3", submission_tier="off_peak"
        )

    @patch("baysys_call_audit.services.get_signed_url", side_effect=lambda x: x)
    @patch("baysys_call_audit.services.speech_provider.submit_recording")
    def test_no_tier_filter_submits_all(self, mock_submit, mock_sign):
        mock_submit.side_effect = ["RES-T1-A", "RES-T1-B", "RES-T1-C"]
        result = submit_pending_recordings(batch_size=10)
        self.assertEqual(result["submitted"], 3)
        self.assertEqual(mock_submit.call_count, 3)

    @patch("baysys_call_audit.services.get_signed_url", side_effect=lambda x: x)
    @patch("baysys_call_audit.services.speech_provider.submit_recording")
    def test_immediate_tier_only(self, mock_submit, mock_sign):
        mock_submit.side_effect = ["RES-T2-A"]
        result = submit_pending_recordings(batch_size=10, tiers=["immediate"])
        self.assertEqual(result["submitted"], 1)
        submitted_id = CallRecording.objects.get(submission_tier="immediate").provider_resource_id
        self.assertEqual(submitted_id, "RES-T2-A")
        # normal and off_peak still pending
        self.assertEqual(CallRecording.objects.filter(status="pending").count(), 2)

    @patch("baysys_call_audit.services.get_signed_url", side_effect=lambda x: x)
    @patch("baysys_call_audit.services.speech_provider.submit_recording")
    def test_normal_and_off_peak_tiers(self, mock_submit, mock_sign):
        mock_submit.side_effect = ["RES-T3-A", "RES-T3-B"]
        result = submit_pending_recordings(batch_size=10, tiers=["normal", "off_peak"])
        self.assertEqual(result["submitted"], 2)
        self.assertEqual(CallRecording.objects.filter(status="pending").count(), 1)
        # immediate still pending
        self.r_immediate.refresh_from_db()
        self.assertEqual(self.r_immediate.status, "pending")

    @patch("baysys_call_audit.services.get_signed_url", side_effect=lambda x: x)
    @patch("baysys_call_audit.services.speech_provider.submit_recording")
    def test_empty_tier_list_treated_as_no_filter(self, mock_submit, mock_sign):
        """Passing tiers=[] is falsy — treated same as None (no filter)."""
        mock_submit.side_effect = ["RES-T4-A", "RES-T4-B", "RES-T4-C"]
        result = submit_pending_recordings(batch_size=10, tiers=[])
        self.assertEqual(result["submitted"], 3)


# ─────────────────────────────────────────────────────────────────────────────
# S3 URL re-signing in submit_pending_recordings
# ─────────────────────────────────────────────────────────────────────────────

class S3ReSigningTests(TestCase):
    def setUp(self):
        self.recording = _make_recording(recording_url="s3://bucket/call.mp3")

    @patch("baysys_call_audit.services.speech_provider.submit_recording", return_value="RES-SIGN")
    @patch("baysys_call_audit.services.get_signed_url", return_value="https://signed.s3.example.com/call.mp3?X-Amz-Expires=900")
    def test_signed_url_passed_to_provider(self, mock_sign, mock_submit):
        submit_pending_recordings(batch_size=1)
        mock_sign.assert_called_once_with("s3://bucket/call.mp3")
        call_kwargs = mock_submit.call_args
        self.assertIn(
            "https://signed.s3.example.com/call.mp3?X-Amz-Expires=900",
            call_kwargs[1].values() if call_kwargs[1] else call_kwargs[0],
        )

    @patch("baysys_call_audit.services.speech_provider.submit_recording", return_value="RES-FALLBACK")
    @patch("baysys_call_audit.services.get_signed_url", side_effect=Exception("S3 error"))
    def test_resign_failure_falls_back_to_stored_url(self, mock_sign, mock_submit):
        """If re-signing fails, falls back to stored URL and still attempts submission."""
        result = submit_pending_recordings(batch_size=1)
        self.assertEqual(result["submitted"], 1)
        call_kwargs = mock_submit.call_args
        submitted_url = (
            call_kwargs[1].get("resource_url")
            if call_kwargs[1]
            else call_kwargs[0][0]
        )
        self.assertEqual(submitted_url, "s3://bucket/call.mp3")

    @patch("baysys_call_audit.services.speech_provider.submit_recording", return_value="RES-ORIG")
    @patch("baysys_call_audit.services.get_signed_url", side_effect=lambda x: x)
    def test_stored_url_not_overwritten(self, mock_sign, mock_submit):
        """The recording_url in DB must not be modified after submission."""
        submit_pending_recordings(batch_size=1)
        self.recording.refresh_from_db()
        self.assertEqual(self.recording.recording_url, "s3://bucket/call.mp3")


# ─────────────────────────────────────────────────────────────────────────────
# submit_recordings management command
# ─────────────────────────────────────────────────────────────────────────────

class SubmitRecordingsCommandTests(TestCase):
    def setUp(self):
        self.r1 = _make_recording(recording_url="s3://b/c1.mp3", submission_tier="immediate")
        self.r2 = _make_recording(recording_url="s3://b/c2.mp3", submission_tier="normal")

    @patch("baysys_call_audit.management.commands.submit_recordings.submit_pending_recordings")
    def test_command_no_args_submits_all_tiers(self, mock_submit):
        mock_submit.return_value = {"submitted": 2, "failed": 0, "skipped": 0}
        out = StringIO()
        cmd = SubmitCommand(stdout=out, stderr=StringIO())
        cmd.handle(tiers=None, batch_size=100, dry_run=False)
        mock_submit.assert_called_once_with(batch_size=100, tiers=None)

    @patch("baysys_call_audit.management.commands.submit_recordings.submit_pending_recordings")
    def test_command_with_tier(self, mock_submit):
        mock_submit.return_value = {"submitted": 1, "failed": 0, "skipped": 0}
        out = StringIO()
        cmd = SubmitCommand(stdout=out, stderr=StringIO())
        cmd.handle(tiers=["immediate"], batch_size=50, dry_run=False)
        mock_submit.assert_called_once_with(batch_size=50, tiers=["immediate"])

    def test_dry_run_counts_without_submitting(self):
        out = StringIO()
        cmd = SubmitCommand(stdout=out, stderr=StringIO())
        cmd.handle(tiers=None, batch_size=100, dry_run=True)
        output = out.getvalue()
        self.assertIn("[dry-run]", output)
        self.assertIn("2", output)
        # No recordings submitted
        self.assertEqual(CallRecording.objects.filter(status="pending").count(), 2)

    def test_dry_run_with_tier_filter(self):
        out = StringIO()
        cmd = SubmitCommand(stdout=out, stderr=StringIO())
        cmd.handle(tiers=["immediate"], batch_size=100, dry_run=True)
        output = out.getvalue()
        self.assertIn("[dry-run]", output)
        self.assertIn("1", output)
        self.assertIn("immediate", output)

    @patch("baysys_call_audit.management.commands.submit_recordings.submit_pending_recordings")
    def test_command_outputs_failure_warning(self, mock_submit):
        mock_submit.return_value = {"submitted": 1, "failed": 1, "skipped": 0}
        err = StringIO()
        cmd = SubmitCommand(stdout=StringIO(), stderr=err)
        cmd.handle(tiers=None, batch_size=100, dry_run=False)
        self.assertIn("failed", err.getvalue())

    @patch("baysys_call_audit.management.commands.submit_recordings.submit_pending_recordings")
    def test_command_batch_size_passed(self, mock_submit):
        mock_submit.return_value = {"submitted": 0, "failed": 0, "skipped": 0}
        cmd = SubmitCommand(stdout=StringIO(), stderr=StringIO())
        cmd.handle(tiers=None, batch_size=500, dry_run=False)
        mock_submit.assert_called_once_with(batch_size=500, tiers=None)
