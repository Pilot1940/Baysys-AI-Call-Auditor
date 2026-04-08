"""Tests for baysys_call_audit.ingestion — shared ingestion logic."""
from datetime import datetime, timezone as dt_tz
from zoneinfo import ZoneInfo

from django.test import TestCase

from baysys_call_audit.ingestion import (
    SYNC_COLUMN_NAMES,
    SYNC_QUERY,
    create_recording_from_row,
    map_sync_row,
    normalize_column_name,
    parse_datetime_flexible,
    validate_row,
)
from baysys_call_audit.models import CallRecording


def _valid_row(**overrides):
    """Return a minimal valid row dict, with optional overrides."""
    base = {
        "agent_id": "101",
        "agent_name": "Test Agent",
        "recording_url": "https://s3.example.com/recording.mp3",
        "recording_datetime": "2026-03-30T10:00:00",
    }
    base.update(overrides)
    return base


class ValidateRowTests(TestCase):
    def test_valid_row(self):
        self.assertEqual(validate_row(_valid_row()), [])

    def test_missing_agent_id(self):
        errors = validate_row(_valid_row(agent_id=None))
        self.assertTrue(any("agent_id" in e for e in errors))

    def test_empty_agent_id(self):
        errors = validate_row(_valid_row(agent_id=""))
        self.assertTrue(any("agent_id" in e for e in errors))

    def test_missing_recording_url(self):
        errors = validate_row(_valid_row(recording_url=None))
        self.assertTrue(any("recording_url" in e for e in errors))

    def test_raw_s3_key_accepted(self):
        # Raw S3 object key (no scheme) — now accepted; signing happens at submission time
        errors = validate_row(_valid_row(recording_url="Konex/call_recordings/2026/03/31/call.mp3"))
        self.assertEqual(errors, [])

    def test_ftp_url_accepted(self):
        # No URL format validation — any non-empty path accepted
        errors = validate_row(_valid_row(recording_url="ftp://bad.com/file.mp3"))
        self.assertEqual(errors, [])

    def test_s3_scheme_url_accepted(self):
        errors = validate_row(_valid_row(recording_url="s3://bucket/key.mp3"))
        self.assertEqual(errors, [])

    def test_missing_recording_datetime(self):
        errors = validate_row(_valid_row(recording_datetime=None))
        self.assertTrue(any("recording_datetime" in e for e in errors))

    def test_unparseable_datetime(self):
        errors = validate_row(_valid_row(recording_datetime="not-a-date"))
        self.assertTrue(any("not parseable" in e for e in errors))

    def test_multiple_errors(self):
        errors = validate_row({"agent_id": None, "recording_url": None, "recording_datetime": None})
        self.assertEqual(len(errors), 3)


class ParseDatetimeFlexibleTests(TestCase):
    def test_none(self):
        self.assertIsNone(parse_datetime_flexible(None))

    def test_empty_string(self):
        self.assertIsNone(parse_datetime_flexible(""))

    def test_datetime_passthrough(self):
        dt = datetime(2026, 3, 30, 10, 0, 0)
        self.assertEqual(parse_datetime_flexible(dt), dt)

    def test_iso_8601(self):
        result = parse_datetime_flexible("2026-03-30T10:00:00")
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.hour, 10)

    def test_iso_8601_with_tz(self):
        result = parse_datetime_flexible("2026-03-30T10:00:00+05:30")
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.tzinfo)

    def test_date_only(self):
        result = parse_datetime_flexible("2026-03-30")
        self.assertEqual(result, datetime(2026, 3, 30))

    def test_postgres_timestamp(self):
        result = parse_datetime_flexible("2026-03-30 10:15:30")
        self.assertEqual(result.minute, 15)

    def test_postgres_timestamp_with_microseconds(self):
        result = parse_datetime_flexible("2026-03-30 10:15:30.123456")
        self.assertIsNotNone(result)

    def test_unparseable(self):
        self.assertIsNone(parse_datetime_flexible("banana"))


class NormalizeColumnNameTests(TestCase):
    def test_spaces_to_underscores(self):
        self.assertEqual(normalize_column_name("Agent ID"), "agent_id")

    def test_camel_case(self):
        self.assertEqual(normalize_column_name("agentId"), "agent_id")

    def test_already_snake(self):
        self.assertEqual(normalize_column_name("recording_url"), "recording_url")

    def test_leading_trailing_spaces(self):
        self.assertEqual(normalize_column_name("  Agent Name  "), "agent_name")

    def test_hyphens(self):
        self.assertEqual(normalize_column_name("bank-name"), "bank_name")

    def test_mixed_case_with_spaces(self):
        self.assertEqual(normalize_column_name("Recording DateTime"), "recording_date_time")

    def test_multiple_underscores_collapsed(self):
        self.assertEqual(normalize_column_name("agent__id"), "agent_id")


class CreateRecordingFromRowTests(TestCase):
    def test_creates_recording(self):
        recording, created = create_recording_from_row(_valid_row())
        self.assertTrue(created)
        self.assertIsNotNone(recording)
        self.assertEqual(recording.agent_id, "101")
        self.assertEqual(recording.agent_name, "Test Agent")
        self.assertEqual(recording.status, "pending")

    def test_dedup_on_recording_url(self):
        create_recording_from_row(_valid_row())
        recording, created = create_recording_from_row(_valid_row())
        self.assertFalse(created)
        self.assertIsNotNone(recording)
        self.assertEqual(CallRecording.objects.count(), 1)

    def test_skips_invalid_row(self):
        recording, created = create_recording_from_row({"agent_id": None})
        self.assertIsNone(recording)
        self.assertFalse(created)

    def test_optional_fields_set(self):
        row = _valid_row(
            customer_id="C001", portfolio_id="P001", agency_id="5",
            customer_phone="+919876543210", product_type="PL", bank_name="HDFC",
        )
        recording, created = create_recording_from_row(row)
        self.assertTrue(created)
        self.assertEqual(recording.customer_id, "C001")
        self.assertEqual(recording.portfolio_id, "P001")
        self.assertEqual(recording.agency_id, "5")
        self.assertEqual(recording.bank_name, "HDFC")

    def test_missing_agent_name_defaults_to_unknown(self):
        row = _valid_row()
        del row["agent_name"]
        recording, created = create_recording_from_row(row)
        self.assertTrue(created)
        self.assertEqual(recording.agent_name, "Unknown")

    def test_integer_ids_cast_to_string(self):
        row = _valid_row(agent_id=101, customer_id=200, portfolio_id=300)
        recording, created = create_recording_from_row(row)
        self.assertTrue(created)
        self.assertEqual(recording.agent_id, "101")
        self.assertEqual(recording.customer_id, "200")

    def test_timezone_aware_datetime(self):
        row = _valid_row(recording_datetime="2026-03-30T10:00:00+05:30")
        recording, created = create_recording_from_row(row)
        self.assertTrue(created)
        self.assertIsNotNone(recording.recording_datetime.tzinfo)

    def test_naive_datetime_made_aware_as_ist(self):
        # Naive datetime must be treated as IST, not Django's default TIME_ZONE.
        row = _valid_row(recording_datetime="2026-03-30T10:00:00")
        recording, created = create_recording_from_row(row)
        self.assertTrue(created)
        ist = ZoneInfo("Asia/Kolkata")
        aware_in_ist = datetime(2026, 3, 30, 10, 0, 0, tzinfo=ist)
        self.assertEqual(recording.recording_datetime, aware_in_ist)

    def test_datetime_object_passthrough(self):
        dt = datetime(2026, 3, 30, 10, 0, 0, tzinfo=dt_tz.utc)
        row = _valid_row(recording_datetime=dt)
        recording, created = create_recording_from_row(row)
        self.assertTrue(created)
        self.assertEqual(recording.recording_datetime, dt)


class CreateRecordingExistingUrlsTests(TestCase):
    """Tests for the existing_urls parameter (fast-path dedup)."""

    def test_existing_urls_none_fallback_to_db(self):
        # Default (None): dedup falls back to DB query
        create_recording_from_row(_valid_row())  # create once
        recording, created = create_recording_from_row(_valid_row(), existing_urls=None)
        self.assertFalse(created)
        self.assertIsNotNone(recording)  # DB fallback returns the existing instance
        self.assertEqual(CallRecording.objects.count(), 1)

    def test_existing_urls_empty_set_creates(self):
        # Empty set — no dedup hit, recording is created
        recording, created = create_recording_from_row(_valid_row(), existing_urls=set())
        self.assertTrue(created)
        self.assertIsNotNone(recording)
        self.assertEqual(CallRecording.objects.count(), 1)

    def test_existing_urls_hit_returns_none_false(self):
        # URL already in set — returns (None, False), no DB write
        url = "https://s3.example.com/recording.mp3"
        recording, created = create_recording_from_row(
            _valid_row(recording_url=url),
            existing_urls={url},
        )
        self.assertIsNone(recording)
        self.assertFalse(created)
        self.assertEqual(CallRecording.objects.count(), 0)

    def test_existing_urls_hit_no_db_query(self):
        # URL in set — no DB query issued (dedup returns immediately after validation)
        url = "https://s3.example.com/recording.mp3"
        with self.assertNumQueries(0):
            result = create_recording_from_row(
                _valid_row(recording_url=url),
                existing_urls={url},
            )
        self.assertEqual(result, (None, False))

    def test_existing_urls_miss_creates_normally(self):
        # Different URL in set — row's URL is not a hit, recording is created
        recording, created = create_recording_from_row(
            _valid_row(recording_url="https://s3.example.com/new.mp3"),
            existing_urls={"https://s3.example.com/other.mp3"},
        )
        self.assertTrue(created)
        self.assertIsNotNone(recording)
        self.assertEqual(CallRecording.objects.count(), 1)


# ─────────────────────────────────────────────────────────────────────────────
# SYNC_QUERY and map_sync_row: call_start_time
# ─────────────────────────────────────────────────────────────────────────────

class SyncQueryCallStartTimeTests(TestCase):
    def test_sync_query_uses_call_start_time(self):
        self.assertIn("call_start_time", SYNC_QUERY)

    def test_sync_query_not_created_at(self):
        self.assertNotIn("created_at", SYNC_QUERY)

    def test_sync_column_names_has_call_start_time(self):
        self.assertIn("call_start_time", SYNC_COLUMN_NAMES)

    def test_sync_column_names_not_created_at(self):
        self.assertNotIn("created_at", SYNC_COLUMN_NAMES)

    def test_map_sync_row_maps_call_start_time_to_recording_datetime(self):
        dt = datetime(2026, 3, 30, 10, 0, 0, tzinfo=dt_tz.utc)
        row_dict = dict.fromkeys(SYNC_COLUMN_NAMES, None)
        row_dict["call_start_time"] = dt
        row_dict["agent_id"] = 101
        row_dict["agent_name"] = "Test Agent"
        mapped = map_sync_row(row_dict)
        self.assertEqual(mapped["recording_datetime"], dt)


class SyncQueryMinDurationTests(TestCase):
    def test_sync_query_has_two_params(self):
        # SYNC_QUERY must use %s for both target_date and min_duration — no hardcoded values
        self.assertEqual(SYNC_QUERY.count("%s"), 2)

    def test_sync_query_no_hardcoded_duration(self):
        self.assertNotIn("> 10", SYNC_QUERY)
        self.assertNotIn("> 20", SYNC_QUERY)
