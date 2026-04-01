"""Tests for compliance.py — config-driven compliance engine."""
from datetime import date, datetime, timezone as tz
from unittest.mock import patch

import yaml
from django.test import TestCase, override_settings

from baysys_call_audit.compliance import (
    check_metadata_compliance,
    check_provider_compliance,
    load_compliance_rules,
    load_gazette_holidays,
)
from baysys_call_audit.models import (
    CallRecording,
    CallTranscript,
    ProviderScore,
)


def _make_recording(**kwargs):
    defaults = {
        "agent_id": "A001",
        "agent_name": "Test Agent",
        "recording_url": "https://s3.example.com/call.mp3",
        "recording_datetime": datetime(2026, 4, 1, 10, 0, tzinfo=tz.utc),  # Wednesday
    }
    defaults.update(kwargs)
    return CallRecording.objects.create(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# Config loading
# ─────────────────────────────────────────────────────────────────────────────

class LoadComplianceRulesTests(TestCase):
    def test_loads_valid_yaml(self):
        rules = load_compliance_rules()
        self.assertIn("metadata_rules", rules)
        self.assertIn("provider_rules", rules)

    @patch("baysys_call_audit.compliance._BASE_DIR")
    def test_missing_file_returns_empty(self, mock_dir):
        from pathlib import Path
        mock_dir.__truediv__ = lambda self, x: Path("/nonexistent") / x
        rules = load_compliance_rules()
        self.assertEqual(rules, {})

    @patch("baysys_call_audit.compliance.yaml.safe_load", side_effect=yaml.YAMLError("parse error"))
    def test_malformed_yaml_returns_empty(self, _):
        rules = load_compliance_rules()
        self.assertEqual(rules, {})


class LoadGazetteHolidaysTests(TestCase):
    def test_loads_valid_file(self):
        load_gazette_holidays.cache_clear()
        holidays = load_gazette_holidays("config/gazette_holidays_2026.txt")
        self.assertIn(date(2026, 1, 26), holidays)  # Republic Day
        self.assertIn(date(2026, 8, 15), holidays)  # Independence Day

    def test_comments_and_blanks_skipped(self):
        load_gazette_holidays.cache_clear()
        holidays = load_gazette_holidays("config/gazette_holidays_2026.txt")
        # Should have exactly 22 holidays per the file
        self.assertEqual(len(holidays), 22)

    def test_missing_file_returns_empty(self):
        load_gazette_holidays.cache_clear()
        holidays = load_gazette_holidays("config/nonexistent.txt")
        self.assertEqual(len(holidays), 0)


# ─────────────────────────────────────────────────────────────────────────────
# Metadata rules: call_window
# ─────────────────────────────────────────────────────────────────────────────

class CallWindowTests(TestCase):
    RULES = {"metadata_rules": [{
        "id": "M1", "name": "test", "enabled": True,
        "check_type": "call_window", "severity": "critical",
        "flag_type": "outside_hours", "description": "Outside {start_hour}-{end_hour}",
        "params": {"start_hour": 8, "end_hour": 20},
    }], "provider_rules": []}

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_CALL_WINDOW_START_HOUR=8, COMPLIANCE_CALL_WINDOW_END_HOUR=20)
    def test_call_at_1am_utc_creates_flag(self, mock_rules):
        # 1:00am UTC = 6:30am IST — before 8am IST window start → flagged
        mock_rules.return_value = self.RULES
        r = _make_recording(recording_datetime=datetime(2026, 4, 1, 1, 0, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0].severity, "critical")
        self.assertEqual(flags[0].flag_type, "outside_hours")

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_CALL_WINDOW_START_HOUR=8, COMPLIANCE_CALL_WINDOW_END_HOUR=20)
    def test_call_at_10am_no_flag(self, mock_rules):
        # 10:00am UTC = 3:30pm IST — within 8am-8pm window → no flag
        mock_rules.return_value = self.RULES
        r = _make_recording(recording_datetime=datetime(2026, 4, 1, 10, 0, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        window_flags = [f for f in flags if f.flag_type == "outside_hours"]
        self.assertEqual(len(window_flags), 0)

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_CALL_WINDOW_START_HOUR=8, COMPLIANCE_CALL_WINDOW_END_HOUR=20)
    def test_call_at_16_utc_creates_flag(self, mock_rules):
        # 16:00 UTC = 9:30pm IST — after 8pm IST window end → flagged
        mock_rules.return_value = self.RULES
        r = _make_recording(recording_datetime=datetime(2026, 4, 1, 16, 0, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        self.assertTrue(any(f.flag_type == "outside_hours" for f in flags))

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_CALL_WINDOW_START_HOUR=9, COMPLIANCE_CALL_WINDOW_END_HOUR=19)
    def test_custom_window_via_settings(self, mock_rules):
        # 2:30am UTC = 8:00am IST — outside custom 9am-7pm window → flagged
        mock_rules.return_value = self.RULES
        r = _make_recording(recording_datetime=datetime(2026, 4, 1, 2, 30, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        self.assertTrue(any(f.flag_type == "outside_hours" for f in flags))

    # ── IST-aware call window tests ──────────────────────────────────────────

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_CALL_WINDOW_START_HOUR=8, COMPLIANCE_CALL_WINDOW_END_HOUR=20)
    def test_8am_ist_boundary_no_flag(self, mock_rules):
        # 2:30am UTC = 8:00am IST — exactly at window start → compliant
        mock_rules.return_value = self.RULES
        r = _make_recording(recording_datetime=datetime(2026, 4, 1, 2, 30, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        window_flags = [f for f in flags if f.flag_type == "outside_hours"]
        self.assertEqual(len(window_flags), 0)

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_CALL_WINDOW_START_HOUR=8, COMPLIANCE_CALL_WINDOW_END_HOUR=20)
    def test_8_30am_ist_no_flag(self, mock_rules):
        # 3:00am UTC = 8:30am IST — within window → no flag (previously incorrectly flagged)
        mock_rules.return_value = self.RULES
        r = _make_recording(recording_datetime=datetime(2026, 4, 1, 3, 0, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        window_flags = [f for f in flags if f.flag_type == "outside_hours"]
        self.assertEqual(len(window_flags), 0)

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_CALL_WINDOW_START_HOUR=8, COMPLIANCE_CALL_WINDOW_END_HOUR=20)
    def test_7_59pm_ist_no_flag(self, mock_rules):
        # 14:29 UTC = 7:59pm IST — still within window → no flag
        mock_rules.return_value = self.RULES
        r = _make_recording(recording_datetime=datetime(2026, 4, 1, 14, 29, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        window_flags = [f for f in flags if f.flag_type == "outside_hours"]
        self.assertEqual(len(window_flags), 0)

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_CALL_WINDOW_START_HOUR=8, COMPLIANCE_CALL_WINDOW_END_HOUR=20)
    def test_8pm_ist_creates_flag(self, mock_rules):
        # 14:30 UTC = 8:00pm IST — end of window (exclusive) → flagged
        mock_rules.return_value = self.RULES
        r = _make_recording(recording_datetime=datetime(2026, 4, 1, 14, 30, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        self.assertTrue(any(f.flag_type == "outside_hours" for f in flags))

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_CALL_WINDOW_START_HOUR=8, COMPLIANCE_CALL_WINDOW_END_HOUR=20)
    def test_9_30pm_ist_creates_flag(self, mock_rules):
        # 16:00 UTC = 9:30pm IST — after window end → flagged (previously missed by UTC engine)
        mock_rules.return_value = self.RULES
        r = _make_recording(recording_datetime=datetime(2026, 4, 1, 16, 0, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        self.assertTrue(any(f.flag_type == "outside_hours" for f in flags))


# ─────────────────────────────────────────────────────────────────────────────
# Metadata rules: blocked_weekday
# ─────────────────────────────────────────────────────────────────────────────

class BlockedWeekdayTests(TestCase):
    RULES = {"metadata_rules": [{
        "id": "M2", "name": "test", "enabled": True,
        "check_type": "blocked_weekday", "severity": "high",
        "flag_type": "rbi_coc_violation", "description": "Sunday call",
        "params": {"weekday": 6},
    }], "provider_rules": []}

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    def test_sunday_creates_flag(self, mock_rules):
        mock_rules.return_value = self.RULES
        # 2026-04-05 is a Sunday
        r = _make_recording(recording_datetime=datetime(2026, 4, 5, 10, 0, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0].severity, "high")

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    def test_monday_no_flag(self, mock_rules):
        mock_rules.return_value = self.RULES
        # 2026-04-06 is a Monday
        r = _make_recording(recording_datetime=datetime(2026, 4, 6, 10, 0, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        self.assertEqual(len(flags), 0)

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    def test_disabled_rule_skipped(self, mock_rules):
        rules = {"metadata_rules": [{
            "id": "M2", "name": "test", "enabled": False,
            "check_type": "blocked_weekday", "severity": "high",
            "flag_type": "rbi_coc_violation", "description": "Sunday call",
            "params": {"weekday": 6},
        }], "provider_rules": []}
        mock_rules.return_value = rules
        r = _make_recording(recording_datetime=datetime(2026, 4, 5, 10, 0, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        self.assertEqual(len(flags), 0)

    # ── IST-aware weekday tests ──────────────────────────────────────────────

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    def test_saturday_11pm_utc_is_sunday_ist(self, mock_rules):
        # 2026-04-04 23:00 UTC = 2026-04-05 04:30 IST → Sunday IST → flagged
        # Old UTC code: weekday() = 5 (Saturday) → missed
        mock_rules.return_value = self.RULES
        r = _make_recording(recording_datetime=datetime(2026, 4, 4, 23, 0, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0].flag_type, "rbi_coc_violation")

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    def test_sunday_10am_utc_is_sunday_ist(self, mock_rules):
        # 2026-04-05 10:00 UTC = 2026-04-05 15:30 IST → Sunday both → flagged
        mock_rules.return_value = self.RULES
        r = _make_recording(recording_datetime=datetime(2026, 4, 5, 10, 0, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        self.assertEqual(len(flags), 1)


# ─────────────────────────────────────────────────────────────────────────────
# Metadata rules: gazette_holiday
# ─────────────────────────────────────────────────────────────────────────────

class GazetteHolidayTests(TestCase):
    RULES = {"metadata_rules": [{
        "id": "M3", "name": "test", "enabled": True,
        "check_type": "gazette_holiday", "severity": "high",
        "flag_type": "rbi_coc_violation",
        "description": "Holiday: {holiday_date}",
        "params": {"holidays_file": "config/gazette_holidays_2026.txt"},
    }], "provider_rules": []}

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    def test_holiday_creates_flag(self, mock_rules):
        mock_rules.return_value = self.RULES
        load_gazette_holidays.cache_clear()
        # 2026-01-26 is Republic Day
        r = _make_recording(recording_datetime=datetime(2026, 1, 26, 10, 0, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        self.assertEqual(len(flags), 1)
        self.assertIn("2026-01-26", flags[0].description)

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    def test_non_holiday_no_flag(self, mock_rules):
        mock_rules.return_value = self.RULES
        load_gazette_holidays.cache_clear()
        # 2026-04-01 is not a holiday
        r = _make_recording(recording_datetime=datetime(2026, 4, 1, 10, 0, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        self.assertEqual(len(flags), 0)

    # ── IST-aware holiday tests ──────────────────────────────────────────────

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    def test_night_before_holiday_utc_is_holiday_ist(self, mock_rules):
        # 2026-01-25 23:00 UTC = 2026-01-26 04:30 IST → Republic Day IST → flagged
        # Old UTC code: date() = 2026-01-25 → not a holiday → missed
        mock_rules.return_value = self.RULES
        load_gazette_holidays.cache_clear()
        r = _make_recording(recording_datetime=datetime(2026, 1, 25, 23, 0, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        self.assertEqual(len(flags), 1)
        self.assertIn("2026-01-26", flags[0].description)

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    def test_holiday_morning_utc_is_holiday_ist(self, mock_rules):
        # 2026-01-26 10:00 UTC = 2026-01-26 15:30 IST → Republic Day → flagged (still correct)
        mock_rules.return_value = self.RULES
        load_gazette_holidays.cache_clear()
        r = _make_recording(recording_datetime=datetime(2026, 1, 26, 10, 0, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        self.assertEqual(len(flags), 1)

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    def test_missing_holidays_file_no_flag(self, mock_rules):
        rules = {"metadata_rules": [{
            "id": "M3", "name": "test", "enabled": True,
            "check_type": "gazette_holiday", "severity": "high",
            "flag_type": "rbi_coc_violation",
            "description": "Holiday: {holiday_date}",
            "params": {"holidays_file": "config/nonexistent.txt"},
        }], "provider_rules": []}
        mock_rules.return_value = rules
        load_gazette_holidays.cache_clear()
        r = _make_recording(recording_datetime=datetime(2026, 1, 26, 10, 0, tzinfo=tz.utc))
        flags = check_metadata_compliance(r)
        self.assertEqual(len(flags), 0)


# ─────────────────────────────────────────────────────────────────────────────
# Metadata rules: max_calls_per_customer
# ─────────────────────────────────────────────────────────────────────────────

class MaxCallsPerCustomerTests(TestCase):
    RULES = {"metadata_rules": [{
        "id": "M4", "name": "test", "enabled": True,
        "check_type": "max_calls_per_customer", "severity": "medium",
        "flag_type": "rbi_coc_violation",
        "description": "{customer_id} got {call_count} calls on {date} (limit: {max_calls})",
        "params": {"max_calls": 3},
    }], "provider_rules": []}

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_MAX_CALLS_PER_CUSTOMER_PER_DAY=3)
    def test_1_call_no_flag(self, mock_rules):
        mock_rules.return_value = self.RULES
        r = _make_recording(customer_id="C001")
        flags = check_metadata_compliance(r)
        max_flags = [f for f in flags if f.flag_type == "rbi_coc_violation"]
        self.assertEqual(len(max_flags), 0)

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_MAX_CALLS_PER_CUSTOMER_PER_DAY=3)
    def test_3_calls_no_flag(self, mock_rules):
        mock_rules.return_value = self.RULES
        dt = datetime(2026, 4, 1, 10, 0, tzinfo=tz.utc)
        for i in range(3):
            _make_recording(
                customer_id="C002",
                recording_url=f"https://s3.example.com/c002_{i}.mp3",
                recording_datetime=dt,
            )
        r = CallRecording.objects.filter(customer_id="C002").last()
        flags = check_metadata_compliance(r)
        max_flags = [f for f in flags if f.description and "limit" in f.description]
        self.assertEqual(len(max_flags), 0)

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_MAX_CALLS_PER_CUSTOMER_PER_DAY=3)
    def test_4th_call_creates_flag(self, mock_rules):
        mock_rules.return_value = self.RULES
        dt = datetime(2026, 4, 1, 10, 0, tzinfo=tz.utc)
        for i in range(4):
            _make_recording(
                customer_id="C003",
                recording_url=f"https://s3.example.com/c003_{i}.mp3",
                recording_datetime=dt,
            )
        r = CallRecording.objects.filter(customer_id="C003").last()
        flags = check_metadata_compliance(r)
        max_flags = [f for f in flags if f.flag_type == "rbi_coc_violation" and "limit" in f.description]
        self.assertEqual(len(max_flags), 1)
        self.assertEqual(max_flags[0].severity, "medium")

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_MAX_CALLS_PER_CUSTOMER_PER_DAY=3)
    def test_null_customer_id_skipped(self, mock_rules):
        mock_rules.return_value = self.RULES
        r = _make_recording(customer_id=None)
        flags = check_metadata_compliance(r)
        max_flags = [f for f in flags if f.flag_type == "rbi_coc_violation"]
        self.assertEqual(len(max_flags), 0)

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_MAX_CALLS_PER_CUSTOMER_PER_DAY=3)
    def test_different_customers_independent(self, mock_rules):
        mock_rules.return_value = self.RULES
        dt = datetime(2026, 4, 1, 10, 0, tzinfo=tz.utc)
        for i in range(4):
            _make_recording(customer_id="C004", recording_url=f"https://s3.example.com/c004_{i}.mp3", recording_datetime=dt)
        for i in range(2):
            _make_recording(customer_id="C005", recording_url=f"https://s3.example.com/c005_{i}.mp3", recording_datetime=dt)
        r = CallRecording.objects.filter(customer_id="C005").last()
        flags = check_metadata_compliance(r)
        max_flags = [f for f in flags if f.flag_type == "rbi_coc_violation" and "limit" in f.description]
        self.assertEqual(len(max_flags), 0)


# ─────────────────────────────────────────────────────────────────────────────
# Provider rules
# ─────────────────────────────────────────────────────────────────────────────

class FatalLevelThresholdTests(TestCase):
    RULES = {"metadata_rules": [], "provider_rules": [{
        "id": "P1", "name": "test", "enabled": True,
        "check_type": "fatal_level_threshold", "severity": "critical",
        "flag_type": "rbi_coc_violation",
        "description": "Fatal {fatal_level} >= {threshold}",
        "params": {"threshold": 3},
    }]}

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_FATAL_THRESHOLD=3)
    def test_fatal_4_creates_flag(self, mock_rules):
        mock_rules.return_value = self.RULES
        r = _make_recording(fatal_level=4)
        flags = check_provider_compliance(r, {"restricted_keywords": [], "detected_restricted_keyword": False})
        fatal_flags = [f for f in flags if f.flag_type == "rbi_coc_violation"]
        self.assertEqual(len(fatal_flags), 1)

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_FATAL_THRESHOLD=3)
    def test_fatal_2_no_flag(self, mock_rules):
        mock_rules.return_value = self.RULES
        r = _make_recording(fatal_level=2)
        flags = check_provider_compliance(r, {"restricted_keywords": [], "detected_restricted_keyword": False})
        fatal_flags = [f for f in flags if f.flag_type == "rbi_coc_violation"]
        self.assertEqual(len(fatal_flags), 0)

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_FATAL_THRESHOLD=3)
    def test_fatal_0_no_flag(self, mock_rules):
        mock_rules.return_value = self.RULES
        r = _make_recording(fatal_level=0)
        flags = check_provider_compliance(r, {"restricted_keywords": [], "detected_restricted_keyword": False})
        fatal_flags = [f for f in flags if f.flag_type == "rbi_coc_violation"]
        self.assertEqual(len(fatal_flags), 0)


class ProviderScoreThresholdTests(TestCase):
    RULES = {"metadata_rules": [], "provider_rules": [{
        "id": "P2", "name": "test", "enabled": True,
        "check_type": "provider_score_threshold", "severity": "high",
        "flag_type": "rbi_coc_violation",
        "description": "Score {score}% < {threshold}%",
        "params": {"score_field": "score_percentage", "threshold": 50},
    }]}

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    def test_low_score_creates_flag(self, mock_rules):
        mock_rules.return_value = self.RULES
        r = _make_recording()
        ProviderScore.objects.create(
            recording=r, template_id="T1", score_percentage=45,
        )
        flags = check_provider_compliance(r, {"restricted_keywords": [], "detected_restricted_keyword": False})
        score_flags = [f for f in flags if f.flag_type == "rbi_coc_violation"]
        self.assertEqual(len(score_flags), 1)

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    def test_passing_score_no_flag(self, mock_rules):
        mock_rules.return_value = self.RULES
        r = _make_recording()
        ProviderScore.objects.create(
            recording=r, template_id="T1", score_percentage=60,
        )
        flags = check_provider_compliance(r, {"restricted_keywords": [], "detected_restricted_keyword": False})
        score_flags = [f for f in flags if f.flag_type == "rbi_coc_violation"]
        self.assertEqual(len(score_flags), 0)

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    def test_no_score_no_flag(self, mock_rules):
        mock_rules.return_value = self.RULES
        r = _make_recording()
        flags = check_provider_compliance(r, {"restricted_keywords": [], "detected_restricted_keyword": False})
        score_flags = [f for f in flags if f.flag_type == "rbi_coc_violation"]
        self.assertEqual(len(score_flags), 0)


class ProviderTranscriptFieldTests(TestCase):
    RULES = {"metadata_rules": [], "provider_rules": [{
        "id": "P3", "name": "test", "enabled": True,
        "check_type": "provider_transcript_field", "severity": "medium",
        "flag_type": "other",
        "description": "Sentiment: {value}",
        "params": {"field": "customer_sentiment", "flagged_values": ["negative", "very_negative", "angry"]},
    }]}

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    def test_negative_sentiment_creates_flag(self, mock_rules):
        mock_rules.return_value = self.RULES
        r = _make_recording()
        CallTranscript.objects.create(
            recording=r, transcript_text="test", customer_sentiment="negative",
        )
        flags = check_provider_compliance(r, {"restricted_keywords": [], "detected_restricted_keyword": False})
        sent_flags = [f for f in flags if f.flag_type == "other"]
        self.assertEqual(len(sent_flags), 1)

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    def test_neutral_sentiment_no_flag(self, mock_rules):
        mock_rules.return_value = self.RULES
        r = _make_recording()
        CallTranscript.objects.create(
            recording=r, transcript_text="test", customer_sentiment="neutral",
        )
        flags = check_provider_compliance(r, {"restricted_keywords": [], "detected_restricted_keyword": False})
        sent_flags = [f for f in flags if f.flag_type == "other"]
        self.assertEqual(len(sent_flags), 0)

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    def test_no_transcript_no_flag(self, mock_rules):
        mock_rules.return_value = self.RULES
        r = _make_recording()
        flags = check_provider_compliance(r, {"restricted_keywords": [], "detected_restricted_keyword": False})
        sent_flags = [f for f in flags if f.flag_type == "other"]
        self.assertEqual(len(sent_flags), 0)


# ─────────────────────────────────────────────────────────────────────────────
# Unknown check_type
# ─────────────────────────────────────────────────────────────────────────────

class UnknownCheckTypeTests(TestCase):
    @patch("baysys_call_audit.compliance.load_compliance_rules")
    def test_unknown_metadata_check_type_skipped(self, mock_rules):
        mock_rules.return_value = {"metadata_rules": [{
            "id": "MX", "name": "test", "enabled": True,
            "check_type": "nonexistent_type", "severity": "low",
            "flag_type": "other", "description": "test", "params": {},
        }], "provider_rules": []}
        r = _make_recording()
        flags = check_metadata_compliance(r)
        self.assertEqual(len(flags), 0)

    @patch("baysys_call_audit.compliance.load_compliance_rules")
    def test_unknown_provider_check_type_skipped(self, mock_rules):
        mock_rules.return_value = {"metadata_rules": [], "provider_rules": [{
            "id": "PX", "name": "test", "enabled": True,
            "check_type": "nonexistent_type", "severity": "low",
            "flag_type": "other", "description": "test", "params": {},
        }]}
        r = _make_recording()
        flags = check_provider_compliance(r, {"restricted_keywords": [], "detected_restricted_keyword": False})
        self.assertEqual(len(flags), 0)
