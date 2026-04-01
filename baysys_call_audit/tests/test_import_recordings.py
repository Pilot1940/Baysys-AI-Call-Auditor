"""Tests for the import_recordings management command and the DRF import endpoint."""
import csv
import io
import os
import tempfile
from io import StringIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from baysys_call_audit.auth import MockUser
from baysys_call_audit.management.commands.import_recordings import (
    Command,
    read_csv_rows,
)
from baysys_call_audit.models import CallRecording
from baysys_call_audit.views import RecordingImportView


def _make_csv(rows, header=None):
    """Write rows to a temp CSV file and return the path."""
    if header is None:
        header = ["agent_id", "agent_name", "recording_url", "recording_datetime"]
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
    return path


def _make_csv_bytes(rows, header=None):
    """Return CSV content as bytes for upload."""
    if header is None:
        header = ["agent_id", "agent_name", "recording_url", "recording_datetime"]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# read_csv_rows unit tests
# ─────────────────────────────────────────────────────────────────────────────

class ReadCsvRowsTests(TestCase):
    def test_reads_valid_csv(self):
        path = _make_csv([
            ["101", "Agent A", "https://s3.example.com/r1.mp3", "2026-03-30T10:00:00"],
        ])
        try:
            rows = read_csv_rows(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["agent_id"], "101")
            self.assertEqual(rows[0]["recording_url"], "https://s3.example.com/r1.mp3")
        finally:
            os.unlink(path)

    def test_normalizes_column_names(self):
        path = _make_csv(
            [["101", "Agent A", "https://s3.example.com/r1.mp3", "2026-03-30"]],
            header=["Agent ID", "Agent Name", "Recording URL", "Recording DateTime"],
        )
        try:
            rows = read_csv_rows(path)
            self.assertIn("agent_id", rows[0])
            self.assertIn("recording_url", rows[0])
        finally:
            os.unlink(path)

    def test_empty_values_become_none(self):
        path = _make_csv([
            ["101", "", "https://s3.example.com/r1.mp3", "2026-03-30"],
        ])
        try:
            rows = read_csv_rows(path)
            self.assertIsNone(rows[0]["agent_name"])
        finally:
            os.unlink(path)


# ─────────────────────────────────────────────────────────────────────────────
# import_recordings management command tests
# ─────────────────────────────────────────────────────────────────────────────

class ImportRecordingsCommandTests(TestCase):
    def _run_command(self, file_path, **kwargs):
        out = StringIO()
        cmd = Command(stdout=out, stderr=StringIO())
        cmd.handle(file_path=file_path, sheet=None, dry_run=False, **kwargs)
        return out.getvalue()

    def test_imports_csv(self):
        path = _make_csv([
            ["101", "Agent A", "https://s3.example.com/r1.mp3", "2026-03-30T10:00:00"],
            ["102", "Agent B", "https://s3.example.com/r2.mp3", "2026-03-30T11:00:00"],
        ])
        try:
            output = self._run_command(path)
            self.assertEqual(CallRecording.objects.count(), 2)
            self.assertIn("Created:            2", output)
        finally:
            os.unlink(path)

    def test_dedup_across_runs(self):
        path = _make_csv([
            ["101", "Agent A", "https://s3.example.com/r1.mp3", "2026-03-30T10:00:00"],
        ])
        try:
            self._run_command(path)
            output = self._run_command(path)
            self.assertEqual(CallRecording.objects.count(), 1)
            self.assertIn("Skipped (dedup):    1", output)
        finally:
            os.unlink(path)

    def test_dry_run(self):
        path = _make_csv([
            ["101", "Agent A", "https://s3.example.com/r1.mp3", "2026-03-30T10:00:00"],
        ])
        try:
            out = StringIO()
            cmd = Command(stdout=out, stderr=StringIO())
            cmd.handle(file_path=path, sheet=None, dry_run=True)
            self.assertEqual(CallRecording.objects.count(), 0)
            self.assertIn("[DRY RUN]", out.getvalue())
        finally:
            os.unlink(path)

    def test_validation_errors_reported(self):
        path = _make_csv([
            ["", "Agent A", "not-a-url", "2026-03-30T10:00:00"],
        ])
        try:
            out = StringIO()
            cmd = Command(stdout=out, stderr=StringIO())
            cmd.handle(file_path=path, sheet=None, dry_run=False)
            output = out.getvalue()
            self.assertIn("Skipped (invalid)", output)
        finally:
            os.unlink(path)

    def test_missing_required_columns_raises(self):
        path = _make_csv(
            [["Agent A", "https://s3.example.com/r1.mp3"]],
            header=["agent_name", "recording_url"],
        )
        try:
            from django.core.management.base import CommandError
            out = StringIO()
            cmd = Command(stdout=out, stderr=StringIO())
            with self.assertRaises(CommandError) as ctx:
                cmd.handle(file_path=path, sheet=None, dry_run=False)
            self.assertIn("Missing required columns", str(ctx.exception))
        finally:
            os.unlink(path)

    def test_unsupported_file_format(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            from django.core.management.base import CommandError
            out = StringIO()
            cmd = Command(stdout=out, stderr=StringIO())
            with self.assertRaises(CommandError):
                cmd.handle(file_path=path, sheet=None, dry_run=False)
        finally:
            os.unlink(path)

    def test_high_failure_rate_warning(self):
        # All rows invalid (empty agent_id + bad url)
        path = _make_csv([
            ["", "Agent", "not-url", "2026-03-30"],
            ["", "Agent", "bad", "2026-03-30"],
            ["", "Agent", "nope", "2026-03-30"],
        ])
        try:
            out = StringIO()
            cmd = Command(stdout=out, stderr=StringIO())
            cmd.handle(file_path=path, sheet=None, dry_run=False)
            self.assertIn("High failure rate", out.getvalue())
        finally:
            os.unlink(path)


# ─────────────────────────────────────────────────────────────────────────────
# DRF RecordingImportView tests
# ─────────────────────────────────────────────────────────────────────────────

class RecordingImportViewTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = RecordingImportView.as_view()

    def _post(self, file_data=None, filename="test.csv", role_id=1, dry_run=False):
        if file_data is None:
            file_data = _make_csv_bytes([
                ["101", "Agent A", "https://s3.example.com/r1.mp3", "2026-03-30T10:00:00"],
            ])
        uploaded = SimpleUploadedFile(filename, file_data, content_type="text/csv")
        url = "/audit/recordings/import/"
        if dry_run:
            url += "?dry_run=true"
        request = self.factory.post(url, {"file": uploaded}, format="multipart")
        request.user = MockUser(role_id=role_id)
        return self.view(request)

    def test_admin_can_upload(self):
        response = self._post(role_id=1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["created"], 1)
        self.assertEqual(CallRecording.objects.count(), 1)

    def test_manager_can_upload(self):
        response = self._post(role_id=2)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["created"], 1)

    def test_agent_forbidden(self):
        response = self._post(role_id=3)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(CallRecording.objects.count(), 0)

    def test_no_file_returns_400(self):
        request = self.factory.post("/audit/recordings/import/", {}, format="multipart")
        request.user = MockUser(role_id=1)
        response = self.view(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("No file", response.data["error"])

    def test_unsupported_format_returns_400(self):
        uploaded = SimpleUploadedFile("data.json", b"{}", content_type="application/json")
        request = self.factory.post(
            "/audit/recordings/import/", {"file": uploaded}, format="multipart"
        )
        request.user = MockUser(role_id=1)
        response = self.view(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported", response.data["error"])

    def test_dry_run(self):
        response = self._post(dry_run=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["created"], 1)
        self.assertEqual(CallRecording.objects.count(), 0)

    def test_missing_columns_returns_400(self):
        data = _make_csv_bytes(
            [["Agent A"]], header=["agent_name"],
        )
        response = self._post(file_data=data)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Missing required columns", response.data["error"])

    def test_dedup(self):
        self._post()
        response = self._post()
        self.assertEqual(response.data["skipped_dedup"], 1)
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(CallRecording.objects.count(), 1)
