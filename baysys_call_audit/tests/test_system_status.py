"""Tests for SystemStatusView — GET /audit/<URL_SECRET>/admin/status/"""
from django.test import TestCase, override_settings
from django.urls import reverse

from baysys_call_audit.models import CallRecording


def _url():
    return reverse("baysys_call_audit:system-status")


@override_settings(AUDIT_STATUS_SECRET="test-secret")
class SystemStatusViewTests(TestCase):
    """Correct token → 200 with expected payload structure."""

    def test_returns_200_with_correct_token(self):
        resp = self.client.get(_url() + "?token=test-secret")
        self.assertEqual(resp.status_code, 200)

    def test_response_contains_top_level_keys(self):
        resp = self.client.get(_url() + "?token=test-secret")
        data = resp.json()
        for key in ("generated_at", "migrations", "backend", "recording_activity", "env_vars", "frontend"):
            self.assertIn(key, data, f"Missing top-level key: {key}")

    def test_recording_activity_pending_is_integer(self):
        # DB query should execute without error; pending count is 0 with no data
        CallRecording.objects.create(
            agent_id="A001",
            agent_name="Test Agent",
            recording_url="s3-key/rec.mp3",
            recording_datetime="2026-04-07T10:00:00Z",
            status="pending",
        )
        resp = self.client.get(_url() + "?token=test-secret")
        data = resp.json()
        self.assertIsInstance(data["recording_activity"]["pending"], int)
        self.assertEqual(data["recording_activity"]["pending"], 1)

    def test_env_vars_is_dict_of_booleans(self):
        resp = self.client.get(_url() + "?token=test-secret")
        env_vars = resp.json()["env_vars"]
        self.assertIsInstance(env_vars, dict)
        for key, val in env_vars.items():
            self.assertIsInstance(val, bool, f"env_vars[{key!r}] is not bool")

    def test_migrations_block_present(self):
        resp = self.client.get(_url() + "?token=test-secret")
        migrations = resp.json()["migrations"]
        self.assertIn("latest_applied", migrations)
        self.assertIn("total_applied", migrations)
        self.assertIn("pending", migrations)


class SystemStatusAuthTests(TestCase):
    """Token auth edge cases."""

    def test_no_token_returns_403(self):
        resp = self.client.get(_url())
        self.assertEqual(resp.status_code, 403)

    def test_wrong_token_returns_403(self):
        with override_settings(AUDIT_STATUS_SECRET="real-secret"):
            resp = self.client.get(_url() + "?token=wrong-token")
        self.assertEqual(resp.status_code, 403)

    def test_unset_secret_returns_403(self):
        # Empty string → always deny (prevents accidental open access)
        with override_settings(AUDIT_STATUS_SECRET=""):
            resp = self.client.get(_url() + "?token=")
        self.assertEqual(resp.status_code, 403)
