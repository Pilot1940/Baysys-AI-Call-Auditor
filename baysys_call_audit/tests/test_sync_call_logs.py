"""Tests for the sync_call_logs management command."""
from datetime import date, datetime, timedelta, timezone as dt_tz
from io import StringIO
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from baysys_call_audit.ingestion import SYNC_COLUMN_NAMES, map_sync_row
from baysys_call_audit.management.commands.sync_call_logs import Command
from baysys_call_audit.models import CallRecording


def _make_db_row(
    source_id=1, agent_id=101, agent_name="John Doe", agency_id=5,
    customer_id=200, customer_number="+919876543210",
    recording_s3_path="https://s3.example.com/rec1.mp3",
    call_start_time=None, call_duration=120,
    campaign_name="HDFC PL", loan_id="LN001",
):
    """Build a tuple matching SYNC_COLUMN_NAMES order."""
    if call_start_time is None:
        call_start_time = datetime(2026, 3, 30, 10, 0, 0, tzinfo=dt_tz.utc)
    return (
        source_id, agent_id, agent_name, agency_id, customer_id,
        customer_number, recording_s3_path, call_start_time, call_duration,
        campaign_name, loan_id,
    )


class MapSyncRowTests(TestCase):
    def test_basic_mapping(self):
        db_row = _make_db_row()
        row_dict = dict(zip(SYNC_COLUMN_NAMES, db_row))
        mapped = map_sync_row(row_dict)

        self.assertEqual(mapped["agent_id"], "101")
        self.assertEqual(mapped["agent_name"], "John Doe")
        self.assertEqual(mapped["agency_id"], "5")
        self.assertEqual(mapped["customer_id"], "200")
        self.assertEqual(mapped["customer_phone"], "+919876543210")
        self.assertEqual(mapped["recording_url"], "https://s3.example.com/rec1.mp3")
        self.assertEqual(mapped["bank_name"], "HDFC PL")
        self.assertEqual(mapped["portfolio_id"], "LN001")

    def test_none_values_handled(self):
        db_row = _make_db_row(customer_id=None, loan_id=None, agency_id=None)
        row_dict = dict(zip(SYNC_COLUMN_NAMES, db_row))
        mapped = map_sync_row(row_dict)

        self.assertIsNone(mapped["customer_id"])
        self.assertIsNone(mapped["portfolio_id"])
        self.assertIsNone(mapped["agency_id"])

    def test_unknown_agent_name(self):
        db_row = _make_db_row(agent_name="Unknown")
        row_dict = dict(zip(SYNC_COLUMN_NAMES, db_row))
        mapped = map_sync_row(row_dict)
        self.assertEqual(mapped["agent_name"], "Unknown")


class SyncCallLogsCommandTests(TestCase):
    """Tests for the sync_call_logs command using mocked DB cursor."""

    def _run_command(self, *args, **kwargs):
        out = StringIO()
        cmd = Command(stdout=out, stderr=StringIO())
        cmd.handle(*args, **kwargs)
        return out.getvalue()

    @patch("baysys_call_audit.ingestion.connection")
    def test_default_date_is_yesterday(self, mock_conn):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        self._run_command(date=None, batch_size=5000, dry_run=False)

        yesterday = str(date.today() - timedelta(days=1))
        cursor.execute.assert_called_once()
        actual_date = cursor.execute.call_args[0][1][0]
        self.assertEqual(actual_date, yesterday)

    @patch("baysys_call_audit.ingestion.connection")
    def test_custom_date(self, mock_conn):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        self._run_command(date="2026-03-30", batch_size=5000, dry_run=False)

        actual_date = cursor.execute.call_args[0][1][0]
        self.assertEqual(actual_date, "2026-03-30")

    @patch("baysys_call_audit.ingestion.connection")
    @patch("baysys_call_audit.compliance.load_compliance_rules", return_value={"metadata_rules": []})
    def test_creates_recordings(self, _cr, mock_conn):
        rows = [_make_db_row(source_id=i, recording_s3_path=f"https://s3.example.com/rec{i}.mp3")
                for i in range(3)]
        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        output = self._run_command(date="2026-03-30", batch_size=5000, dry_run=False)

        self.assertEqual(CallRecording.objects.count(), 3)
        self.assertIn("Created:            3", output)

    @patch("baysys_call_audit.ingestion.connection")
    @patch("baysys_call_audit.compliance.load_compliance_rules", return_value={"metadata_rules": []})
    def test_dedup_on_second_run(self, _cr, mock_conn):
        rows = [_make_db_row()]
        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        self._run_command(date="2026-03-30", batch_size=5000, dry_run=False)
        self.assertEqual(CallRecording.objects.count(), 1)

        # Second run with same data
        output = self._run_command(date="2026-03-30", batch_size=5000, dry_run=False)

        self.assertEqual(CallRecording.objects.count(), 1)
        self.assertIn("Skipped (dedup):    1", output)

    @patch("baysys_call_audit.ingestion.connection")
    def test_dry_run_no_db_writes(self, mock_conn):
        rows = [_make_db_row()]
        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        output = self._run_command(date="2026-03-30", batch_size=5000, dry_run=True)

        self.assertEqual(CallRecording.objects.count(), 0)
        self.assertIn("[DRY RUN]", output)
        self.assertIn("Created:            1", output)

    @patch("baysys_call_audit.ingestion.connection")
    @patch("baysys_call_audit.compliance.load_compliance_rules", return_value={"metadata_rules": []})
    def test_unknown_agent_counted(self, _cr, mock_conn):
        rows = [_make_db_row(agent_name="Unknown")]
        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        output = self._run_command(date="2026-03-30", batch_size=5000, dry_run=False)

        self.assertIn("Unknown agents:     1", output)

    @patch("baysys_call_audit.ingestion.connection")
    def test_empty_result_set(self, mock_conn):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        output = self._run_command(date="2026-03-30", batch_size=5000, dry_run=False)

        self.assertEqual(CallRecording.objects.count(), 0)
        self.assertIn("Fetched:            0", output)

    @patch("baysys_call_audit.ingestion.connection")
    def test_batch_size_accepted_fetchall_used(self, mock_conn):
        # batch_size no longer controls the raw cursor fetch — fetchall() drains all rows
        # before any ORM write. Verify fetchall is called and fetchmany is not.
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        self._run_command(date="2026-03-30", batch_size=100, dry_run=False)

        cursor.fetchall.assert_called_once()
        cursor.fetchmany.assert_not_called()

    @patch("baysys_call_audit.ingestion.connection")
    @override_settings(SYNC_MIN_CALL_DURATION=20)
    def test_min_duration_default_passed_to_query(self, mock_conn):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        self._run_command(date="2026-03-30", batch_size=5000, dry_run=False)

        params = cursor.execute.call_args[0][1]
        self.assertEqual(params[1], 20)

    @patch("baysys_call_audit.ingestion.connection")
    @override_settings(SYNC_MIN_CALL_DURATION=5)
    def test_min_duration_override_via_settings(self, mock_conn):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        self._run_command(date="2026-03-30", batch_size=5000, dry_run=False)

        params = cursor.execute.call_args[0][1]
        self.assertEqual(params[1], 5)


class BulkDedupPrefetchTests(TestCase):
    """Tests for the pre-fetch dedup optimisation (Prompt F)."""

    def _run_command(self, *args, **kwargs):
        out = StringIO()
        cmd = Command(stdout=out, stderr=StringIO())
        cmd.handle(*args, **kwargs)
        return out.getvalue()

    @patch("baysys_call_audit.ingestion.connection")
    @patch("baysys_call_audit.compliance.load_compliance_rules", return_value={"metadata_rules": []})
    def test_prefetch_dedup_pre_existing_recording(self, _cr, mock_conn):
        # A recording already in the DB for 2026-03-30 must be skipped via the pre-fetch set
        CallRecording.objects.create(
            agent_id="101",
            agent_name="Test Agent",
            recording_url="https://s3.example.com/rec1.mp3",
            recording_datetime=datetime(2026, 3, 30, 10, 0, 0, tzinfo=dt_tz.utc),
            status="pending",
        )
        rows = [_make_db_row(recording_s3_path="https://s3.example.com/rec1.mp3")]
        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        output = self._run_command(date="2026-03-30", batch_size=5000, dry_run=False)

        self.assertEqual(CallRecording.objects.count(), 1)  # no new row created
        self.assertIn("Skipped (dedup):    1", output)

    @patch("baysys_call_audit.ingestion.connection")
    @patch("baysys_call_audit.compliance.load_compliance_rules", return_value={"metadata_rules": []})
    def test_intrabatch_dedup_same_url(self, _cr, mock_conn):
        # Two rows with the same recording_url in one batch — second must be skipped
        url = "https://s3.example.com/same.mp3"
        rows = [
            _make_db_row(source_id=1, recording_s3_path=url),
            _make_db_row(source_id=2, recording_s3_path=url),
        ]
        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        output = self._run_command(date="2026-03-30", batch_size=5000, dry_run=False)

        self.assertEqual(CallRecording.objects.count(), 1)
        self.assertIn("Created:            1", output)
        self.assertIn("Skipped (dedup):    1", output)

    @patch("baysys_call_audit.ingestion.connection")
    @patch("baysys_call_audit.compliance.load_compliance_rules", return_value={"metadata_rules": []})
    def test_intrabatch_dedup_set_updated_after_create(self, _cr, mock_conn):
        # Three rows: A (new), B (same as A, should be dedup'd), C (different, new)
        rows = [
            _make_db_row(source_id=1, recording_s3_path="https://s3.example.com/a.mp3"),
            _make_db_row(source_id=2, recording_s3_path="https://s3.example.com/a.mp3"),
            _make_db_row(source_id=3, recording_s3_path="https://s3.example.com/c.mp3"),
        ]
        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        output = self._run_command(date="2026-03-30", batch_size=5000, dry_run=False)

        self.assertEqual(CallRecording.objects.count(), 2)
        self.assertIn("Created:            2", output)
        self.assertIn("Skipped (dedup):    1", output)


# ─────────────────────────────────────────────────────────────────────────────
# call_counts_cache: pre-fetch and in-loop increment
# ─────────────────────────────────────────────────────────────────────────────

class CallCountsCacheTests(TestCase):
    """Tests for the per-customer call-count cache that eliminates the N+1
    DB query in _check_max_calls_per_customer during sync."""

    RULES_MAX3 = {"metadata_rules": [{
        "id": "M4", "name": "max_calls", "enabled": True,
        "check_type": "max_calls_per_customer", "severity": "medium",
        "flag_type": "rbi_coc_violation",
        "description": "{customer_id} got {call_count} calls on {date} (limit: {max_calls})",
        "params": {"max_calls": 3},
    }], "provider_rules": []}

    def _run_command(self, *args, **kwargs):
        out = StringIO()
        cmd = Command(stdout=out, stderr=StringIO())
        cmd.handle(*args, **kwargs)
        return out.getvalue()

    @patch("baysys_call_audit.ingestion.connection")
    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_MAX_CALLS_PER_CUSTOMER_PER_DAY=3)
    def test_cache_pre_fetched_from_existing_rows(self, mock_rules, mock_conn):
        """Pre-existing recordings for the date seed the cache; new rows increment it."""
        mock_rules.return_value = self.RULES_MAX3
        # Pre-seed: 3 recordings for customer C001 already in DB
        dt = datetime(2026, 3, 30, 10, 0, 0, tzinfo=dt_tz.utc)
        for i in range(3):
            CallRecording.objects.create(
                agent_id="101", agent_name="Agent",
                customer_id="C001",
                recording_url=f"https://s3.example.com/pre_{i}.mp3",
                recording_datetime=dt, status="pending",
            )
        # Sync brings one more call for the same customer
        rows = [_make_db_row(
            source_id=99,
            customer_id="C001",
            recording_s3_path="https://s3.example.com/new_c001.mp3",
            call_start_time=dt,
        )]
        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        self._run_command(date="2026-03-30", batch_size=5000, dry_run=False)

        # 4th call (> limit 3) must have a compliance flag
        new_rec = CallRecording.objects.get(recording_url="https://s3.example.com/new_c001.mp3")
        from baysys_call_audit.models import ComplianceFlag
        flags = ComplianceFlag.objects.filter(recording=new_rec, flag_type="rbi_coc_violation")
        self.assertEqual(flags.count(), 1)

    @patch("baysys_call_audit.ingestion.connection")
    @patch("baysys_call_audit.compliance.load_compliance_rules")
    @override_settings(COMPLIANCE_MAX_CALLS_PER_CUSTOMER_PER_DAY=3)
    def test_cache_incremented_within_batch(self, mock_rules, mock_conn):
        """Cache increments correctly across rows in the same batch."""
        mock_rules.return_value = self.RULES_MAX3
        dt = datetime(2026, 3, 30, 10, 0, 0, tzinfo=dt_tz.utc)
        # 4 rows for the same customer in one batch — 4th must be flagged
        rows = [
            _make_db_row(
                source_id=i, customer_id="C002",
                recording_s3_path=f"https://s3.example.com/c002_{i}.mp3",
                call_start_time=dt,
            )
            for i in range(4)
        ]
        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        self._run_command(date="2026-03-30", batch_size=5000, dry_run=False)

        self.assertEqual(CallRecording.objects.filter(customer_id="C002").count(), 4)
        from baysys_call_audit.models import ComplianceFlag
        flagged_recs = ComplianceFlag.objects.filter(flag_type="rbi_coc_violation")
        self.assertGreaterEqual(flagged_recs.count(), 1)
