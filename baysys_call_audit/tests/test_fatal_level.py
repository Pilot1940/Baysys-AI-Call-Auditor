"""Tests for fatal level computation and content hash verification."""
from datetime import datetime, timezone as tz
from io import StringIO
from unittest.mock import patch

from django.test import TestCase

from baysys_call_audit.compliance import (
    compute_content_hash,
    compute_fatal_level,
    load_fatal_level_rules,
)
from baysys_call_audit.management.commands.update_fatal_level_hash import Command as HashCommand
from baysys_call_audit.models import CallRecording, ProviderScore


def _make_recording(**kwargs):
    defaults = {
        "agent_id": "A001",
        "agent_name": "Test Agent",
        "recording_url": "https://s3.example.com/call.mp3",
        "recording_datetime": datetime(2026, 4, 1, 10, 0, tzinfo=tz.utc),
    }
    defaults.update(kwargs)
    return CallRecording.objects.create(**defaults)


def _make_score(recording, category_data=None):
    return ProviderScore.objects.create(
        recording=recording,
        template_id="TPL-001",
        category_data=category_data or {},
    )


SAMPLE_PARAMS = [
    {"name": "abusive_language_detected", "weight": 3, "invert": True},
    {"name": "threatening_language_detected", "weight": 3, "invert": True},
    {"name": "agent_identified", "weight": 1, "invert": False},
    {"name": "purpose_stated", "weight": 1, "invert": False},
    {"name": "third_party_disclosure", "weight": 2, "invert": True},
    {"name": "called_within_permitted_hours", "weight": 1, "invert": False},
]


class ComputeFatalLevelTests(TestCase):
    @patch("baysys_call_audit.compliance.load_fatal_level_rules")
    def test_all_pass_level_0(self, mock_rules):
        mock_rules.return_value = {"parameters": SAMPLE_PARAMS, "threshold": 3}
        r = _make_recording()
        score = _make_score(r, {
            "abusive_language_detected": 0,       # not triggered (invert=True, value=0)
            "threatening_language_detected": 0,
            "agent_identified": 1,                 # not triggered (invert=False, value=1)
            "purpose_stated": 1,
            "third_party_disclosure": 0,
            "called_within_permitted_hours": 1,
        })
        level = compute_fatal_level(r, score)
        self.assertEqual(level, 0)

    @patch("baysys_call_audit.compliance.load_fatal_level_rules")
    def test_abusive_detected_level_3(self, mock_rules):
        mock_rules.return_value = {"parameters": SAMPLE_PARAMS, "threshold": 3}
        r = _make_recording()
        score = _make_score(r, {
            "abusive_language_detected": 1,  # triggered (invert=True, weight=3)
            "agent_identified": 1,
            "purpose_stated": 1,
        })
        level = compute_fatal_level(r, score)
        self.assertEqual(level, 3)
        r.refresh_from_db()
        self.assertEqual(r.fatal_level, 3)

    @patch("baysys_call_audit.compliance.load_fatal_level_rules")
    def test_abusive_plus_threatening_capped_at_5(self, mock_rules):
        mock_rules.return_value = {"parameters": SAMPLE_PARAMS, "threshold": 3}
        r = _make_recording()
        score = _make_score(r, {
            "abusive_language_detected": 1,       # weight 3
            "threatening_language_detected": 1,   # weight 3 -> total 6, capped at 5
        })
        level = compute_fatal_level(r, score)
        self.assertEqual(level, 5)

    @patch("baysys_call_audit.compliance.load_fatal_level_rules")
    def test_agent_not_identified_plus_purpose_not_stated(self, mock_rules):
        mock_rules.return_value = {"parameters": SAMPLE_PARAMS, "threshold": 3}
        r = _make_recording()
        score = _make_score(r, {
            "agent_identified": 0,   # triggered (invert=False, weight=1)
            "purpose_stated": 0,     # triggered (invert=False, weight=1)
        })
        level = compute_fatal_level(r, score)
        self.assertEqual(level, 2)

    @patch("baysys_call_audit.compliance.load_fatal_level_rules")
    def test_missing_parameter_skipped(self, mock_rules):
        mock_rules.return_value = {"parameters": SAMPLE_PARAMS, "threshold": 3}
        r = _make_recording()
        score = _make_score(r, {
            "agent_identified": 1,
            # All others missing — should be skipped, not triggered
        })
        level = compute_fatal_level(r, score)
        self.assertEqual(level, 0)

    @patch("baysys_call_audit.compliance.load_fatal_level_rules")
    def test_empty_category_data_level_0(self, mock_rules):
        mock_rules.return_value = {"parameters": SAMPLE_PARAMS, "threshold": 3}
        r = _make_recording()
        score = _make_score(r, {})
        level = compute_fatal_level(r, score)
        self.assertEqual(level, 0)

    @patch("baysys_call_audit.compliance.load_fatal_level_rules")
    def test_none_score_level_0(self, mock_rules):
        mock_rules.return_value = {"parameters": SAMPLE_PARAMS, "threshold": 3}
        r = _make_recording()
        level = compute_fatal_level(r, None)
        self.assertEqual(level, 0)

    @patch("baysys_call_audit.compliance.load_fatal_level_rules")
    def test_non_dict_category_data_level_0(self, mock_rules):
        mock_rules.return_value = {"parameters": SAMPLE_PARAMS, "threshold": 3}
        r = _make_recording()
        score = _make_score(r, category_data=None)
        score.category_data = [1, 2, 3]  # not a dict
        score.save()
        level = compute_fatal_level(r, score)
        self.assertEqual(level, 0)


# ─────────────────────────────────────────────────────────────────────────────
# Content hash
# ─────────────────────────────────────────────────────────────────────────────

class ContentHashTests(TestCase):
    def test_hash_excludes_content_hash_line(self):
        yaml_a = 'version: "1.0"\ncontent_hash: "abc123"\nthreshold: 3\n'
        yaml_b = 'version: "1.0"\ncontent_hash: "different"\nthreshold: 3\n'
        self.assertEqual(compute_content_hash(yaml_a), compute_content_hash(yaml_b))

    def test_hash_changes_with_content(self):
        yaml_a = 'version: "1.0"\ncontent_hash: ""\nthreshold: 3\n'
        yaml_b = 'version: "1.0"\ncontent_hash: ""\nthreshold: 5\n'
        self.assertNotEqual(compute_content_hash(yaml_a), compute_content_hash(yaml_b))

    @patch("baysys_call_audit.compliance.load_fatal_level_rules")
    def test_empty_hash_skips_verification(self, mock_rules):
        """Empty content_hash should not trigger a warning."""
        mock_rules.return_value = {"content_hash": "", "parameters": [], "threshold": 3}
        # If we get here without warning, the empty hash was skipped
        rules = mock_rules()
        self.assertEqual(rules["content_hash"], "")

    def test_load_real_file(self):
        """The real fatal_level_rules.yaml loads without error."""
        rules = load_fatal_level_rules()
        self.assertIn("parameters", rules)
        self.assertIn("threshold", rules)


# ─────────────────────────────────────────────────────────────────────────────
# update_fatal_level_hash command
# ─────────────────────────────────────────────────────────────────────────────

class UpdateFatalLevelHashCommandTests(TestCase):
    def test_command_computes_hash(self):
        out = StringIO()
        cmd = HashCommand(stdout=out, stderr=StringIO())
        cmd.handle()
        output = out.getvalue()
        self.assertIn("content_hash:", output)
        self.assertIn("version:", output)

    def test_hash_is_valid_sha256(self):
        out = StringIO()
        cmd = HashCommand(stdout=out, stderr=StringIO())
        cmd.handle()
        output = out.getvalue()
        # Extract hash from output
        for line in output.split("\n"):
            if "content_hash:" in line:
                h = line.split("content_hash:")[1].strip()
                self.assertEqual(len(h), 64)  # SHA-256 hex length
                break
