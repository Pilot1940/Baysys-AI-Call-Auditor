"""Tests for the poll_stuck_recordings management command."""
from datetime import datetime, timezone as dt_tz
from io import StringIO
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from baysys_call_audit.management.commands.poll_stuck_recordings import Command
from baysys_call_audit.models import CallRecording


def _make_submitted_recording(
    recording_url="https://s3.example.com/rec.mp3",
    provider_resource_id="RES001",
    submitted_minutes_ago=60,
    **kwargs,
):
    """Create a CallRecording in status=submitted."""
    submitted_at = timezone.now() - timezone.timedelta(minutes=submitted_minutes_ago)
    return CallRecording.objects.create(
        agent_id="A001",
        agent_name="Test Agent",
        recording_url=recording_url,
        recording_datetime=datetime(2026, 3, 30, 10, 0, 0, tzinfo=dt_tz.utc),
        status="submitted",
        provider_resource_id=provider_resource_id,
        submitted_at=submitted_at,
        **kwargs,
    )


def _run_command(*args, **options):
    out = StringIO()
    cmd = Command(stdout=out, stderr=StringIO())
    defaults = {"batch_size": 50, "dry_run": False}
    defaults.update(options)
    cmd.handle(*args, **defaults)
    return out.getvalue()


class PollStuckRecordingsQueryTests(TestCase):
    """Tests for which recordings are selected for polling."""

    @override_settings(POLL_STUCK_AFTER_MINUTES=30)
    def test_no_submitted_recordings_runs_cleanly(self):
        output = _run_command()
        self.assertIn("Polled:           0", output)

    @override_settings(POLL_STUCK_AFTER_MINUTES=30)
    @patch("baysys_call_audit.management.commands.poll_stuck_recordings.speech_provider")
    def test_recent_submission_not_polled(self, mock_provider):
        # Submitted only 5 minutes ago — within the 30-minute threshold
        _make_submitted_recording(submitted_minutes_ago=5)
        _run_command()
        mock_provider.get_results.assert_not_called()

    @override_settings(POLL_STUCK_AFTER_MINUTES=30)
    @patch("baysys_call_audit.management.commands.poll_stuck_recordings.speech_provider")
    def test_old_submission_is_polled(self, mock_provider):
        # Submitted 60 minutes ago — past the threshold
        _make_submitted_recording(submitted_minutes_ago=60)
        mock_provider.get_results.return_value = {"transcript": ""}  # still processing
        mock_provider.ProviderError = Exception
        _run_command()
        mock_provider.get_results.assert_called_once_with("RES001")

    @override_settings(POLL_STUCK_AFTER_MINUTES=30)
    def test_no_provider_resource_id_excluded(self):
        # No provider_resource_id — not eligible for polling
        CallRecording.objects.create(
            agent_id="A001",
            agent_name="Test Agent",
            recording_url="https://s3.example.com/no_res.mp3",
            recording_datetime=datetime(2026, 3, 30, 10, 0, 0, tzinfo=dt_tz.utc),
            status="submitted",
            provider_resource_id=None,
            submitted_at=timezone.now() - timezone.timedelta(minutes=60),
        )
        with patch(
            "baysys_call_audit.management.commands.poll_stuck_recordings.speech_provider"
        ) as mock_provider:
            mock_provider.ProviderError = Exception
            _run_command()
            mock_provider.get_results.assert_not_called()


class PollStuckRecordingsRecoveryTests(TestCase):
    """Tests for successful recovery and error handling."""

    VALID_PAYLOAD = {
        "resource_insight_id": "RES001",
        "transcript": "Hello, this is a call transcript.",
        "total_call_duration": 120,
        "insights": {},
    }

    @override_settings(POLL_STUCK_AFTER_MINUTES=30)
    @patch("baysys_call_audit.management.commands.poll_stuck_recordings.process_provider_webhook")
    @patch("baysys_call_audit.management.commands.poll_stuck_recordings.speech_provider")
    def test_successful_recovery(self, mock_provider, mock_webhook):
        recording = _make_submitted_recording()
        mock_provider.get_results.return_value = self.VALID_PAYLOAD
        mock_provider.ProviderError = Exception

        # process_provider_webhook returns the recording with completed status
        recording.status = "completed"
        mock_webhook.return_value = recording

        output = _run_command()
        mock_webhook.assert_called_once()
        self.assertIn("Recovered:        1", output)

    @override_settings(POLL_STUCK_AFTER_MINUTES=30)
    @patch("baysys_call_audit.management.commands.poll_stuck_recordings.speech_provider")
    def test_provider_error_increments_retry_count(self, mock_provider):
        recording = _make_submitted_recording()
        initial_retry = recording.retry_count

        mock_provider.ProviderError = Exception
        mock_provider.get_results.side_effect = Exception("API unavailable")

        _run_command()

        recording.refresh_from_db()
        self.assertEqual(recording.retry_count, initial_retry + 1)
        self.assertEqual(recording.status, "submitted")  # stays submitted

    @override_settings(POLL_STUCK_AFTER_MINUTES=30)
    @patch("baysys_call_audit.management.commands.poll_stuck_recordings.speech_provider")
    def test_still_processing_not_counted_as_error(self, mock_provider):
        _make_submitted_recording()
        mock_provider.ProviderError = Exception
        mock_provider.get_results.return_value = {"transcript": ""}  # no transcript = not ready

        output = _run_command()
        self.assertIn("Still processing: 1", output)
        self.assertIn("Errors:           0", output)

    @override_settings(POLL_STUCK_AFTER_MINUTES=30)
    @patch("baysys_call_audit.management.commands.poll_stuck_recordings.speech_provider")
    def test_dry_run_no_api_calls(self, mock_provider):
        _make_submitted_recording(submitted_minutes_ago=60)
        mock_provider.ProviderError = Exception

        output = _run_command(dry_run=True)

        mock_provider.get_results.assert_not_called()
        self.assertIn("[dry-run]", output)
        self.assertIn("1 recording(s)", output)

    @override_settings(POLL_STUCK_AFTER_MINUTES=30)
    @patch("baysys_call_audit.management.commands.poll_stuck_recordings.speech_provider")
    def test_batch_size_limits_polling(self, mock_provider):
        # Create 5 stuck recordings
        for i in range(5):
            _make_submitted_recording(
                recording_url=f"https://s3.example.com/rec{i}.mp3",
                provider_resource_id=f"RES{i:03d}",
                submitted_minutes_ago=60,
            )
        mock_provider.ProviderError = Exception
        mock_provider.get_results.return_value = {"transcript": ""}  # still processing

        _run_command(batch_size=2)

        self.assertEqual(mock_provider.get_results.call_count, 2)
