"""Tests for speech_provider.py — mocks HTTP calls."""
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from baysys_call_audit.speech_provider import (
    ProviderError,
    ask_question,
    delete_resource,
    get_results,
    submit_recording,
    submit_transcript,
    update_metadata,
)


@override_settings(
    SPEECH_PROVIDER_HOST="https://api.test.provider",
    SPEECH_PROVIDER_API_KEY="test-key",
    SPEECH_PROVIDER_API_SECRET="test-secret",
)
class SubmitRecordingTests(TestCase):
    @patch("baysys_call_audit.speech_provider.requests.post")
    def test_submit_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"resource_insight_id": "RES-123"}
        mock_post.return_value = mock_resp

        result = submit_recording(
            resource_url="https://s3.example.com/call.mp3",
            template_id="TPL-001",
            agent_id="A001",
            agent_name="Test Agent",
            recording_datetime="2026-04-01T10:00:00Z",
            callback_url="https://example.com/webhook/",
        )
        self.assertEqual(result, "RES-123")
        mock_post.assert_called_once()

    @patch("baysys_call_audit.speech_provider.requests.post")
    def test_submit_http_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {"error": "Internal Server Error"}
        mock_post.return_value = mock_resp

        with self.assertRaises(ProviderError) as ctx:
            submit_recording(
                resource_url="https://s3.example.com/call.mp3",
                template_id="TPL-001",
                agent_id="A001",
                agent_name="Test Agent",
                recording_datetime="2026-04-01T10:00:00Z",
                callback_url="https://example.com/webhook/",
            )
        self.assertEqual(ctx.exception.status_code, 500)

    @patch("baysys_call_audit.speech_provider.requests.post")
    def test_submit_missing_resource_id(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        mock_post.return_value = mock_resp

        with self.assertRaises(ProviderError):
            submit_recording(
                resource_url="https://s3.example.com/call.mp3",
                template_id="TPL-001",
                agent_id="A001",
                agent_name="Test Agent",
                recording_datetime="2026-04-01T10:00:00Z",
                callback_url="https://example.com/webhook/",
            )


@override_settings(
    SPEECH_PROVIDER_HOST="https://api.test.provider",
    SPEECH_PROVIDER_API_KEY="test-key",
    SPEECH_PROVIDER_API_SECRET="test-secret",
)
class GetResultsTests(TestCase):
    @patch("baysys_call_audit.speech_provider.requests.post")
    def test_get_results_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"transcript": "hello", "audit_compliance_score": 3}
        mock_post.return_value = mock_resp

        result = get_results("RES-123")
        self.assertEqual(result["transcript"], "hello")

    @patch("baysys_call_audit.speech_provider.requests.post")
    def test_get_results_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"error": "Not found"}
        mock_post.return_value = mock_resp

        with self.assertRaises(ProviderError) as ctx:
            get_results("RES-INVALID")
        self.assertEqual(ctx.exception.status_code, 404)


@override_settings(
    SPEECH_PROVIDER_HOST="https://api.test.provider",
    SPEECH_PROVIDER_API_KEY="test-key",
    SPEECH_PROVIDER_API_SECRET="test-secret",
)
class DeleteResourceTests(TestCase):
    @patch("baysys_call_audit.speech_provider.requests.post")
    def test_delete_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        self.assertTrue(delete_resource("RES-123"))

    @patch("baysys_call_audit.speech_provider.requests.post")
    def test_delete_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {}
        mock_post.return_value = mock_resp

        with self.assertRaises(ProviderError):
            delete_resource("RES-123")


@override_settings(
    SPEECH_PROVIDER_HOST="https://api.test.provider",
    SPEECH_PROVIDER_API_KEY="test-key",
    SPEECH_PROVIDER_API_SECRET="test-secret",
)
class AskQuestionTests(TestCase):
    @patch("baysys_call_audit.speech_provider.requests.post")
    def test_ask_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"answer": "The agent greeted the customer."}
        mock_post.return_value = mock_resp

        result = ask_question("RES-123", "Did the agent greet?")
        self.assertEqual(result["answer"], "The agent greeted the customer.")


@override_settings(
    SPEECH_PROVIDER_HOST="https://api.test.provider",
    SPEECH_PROVIDER_API_KEY="test-key",
    SPEECH_PROVIDER_API_SECRET="test-secret",
)
class SubmitTranscriptTests(TestCase):
    @patch("baysys_call_audit.speech_provider.requests.post")
    def test_submit_transcript_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"resource_insight_id": "RES-456"}
        mock_post.return_value = mock_resp

        result = submit_transcript("Hello...", "TPL-001", "https://example.com/webhook/")
        self.assertEqual(result, "RES-456")


@override_settings(
    SPEECH_PROVIDER_HOST="https://api.test.provider",
    SPEECH_PROVIDER_API_KEY="test-key",
    SPEECH_PROVIDER_API_SECRET="test-secret",
)
class UpdateMetadataTests(TestCase):
    @patch("baysys_call_audit.speech_provider.requests.post")
    def test_update_metadata_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        self.assertTrue(update_metadata("RES-123", {"key": "value"}))
