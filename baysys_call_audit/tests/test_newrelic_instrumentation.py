"""
Tests for New Relic instrumentation.

New Relic API calls are no-ops when no agent is initialised (which is always
the case in the test environment), so existing tests are unaffected.
These tests verify:
  - @background_task decorators are applied (via __wrapped__ attribute)
  - newrelic.agent is importable and its key functions are callable
"""
import newrelic.agent
from django.test import TestCase

from baysys_call_audit import ingestion, services


class TestBackgroundTaskDecorators(TestCase):
    """Verify @background_task has been applied to all service functions."""

    def test_submit_pending_recordings_is_wrapped(self):
        self.assertTrue(
            hasattr(services.submit_pending_recordings, '__wrapped__'),
            "submit_pending_recordings must be decorated with @background_task",
        )

    def test_process_provider_webhook_is_wrapped(self):
        self.assertTrue(
            hasattr(services.process_provider_webhook, '__wrapped__'),
            "process_provider_webhook must be decorated with @background_task",
        )

    def test_run_own_llm_scoring_is_wrapped(self):
        self.assertTrue(
            hasattr(services.run_own_llm_scoring, '__wrapped__'),
            "run_own_llm_scoring must be decorated with @background_task",
        )

    def test_run_sync_for_date_is_wrapped(self):
        self.assertTrue(
            hasattr(ingestion.run_sync_for_date, '__wrapped__'),
            "run_sync_for_date must be decorated with @background_task",
        )


class TestNewRelicNoOp(TestCase):
    """Verify New Relic API is importable and callable without an active agent."""

    def test_import_newrelic_agent(self):
        """newrelic.agent must import cleanly in test environment."""
        import newrelic.agent as nr  # noqa: PLC0415
        self.assertIsNotNone(nr)

    def test_record_custom_metric_is_callable(self):
        """record_custom_metric must be a no-op without an agent (no exception)."""
        newrelic.agent.record_custom_metric('Custom/Test/Metric', 1)

    def test_record_custom_event_is_callable(self):
        """record_custom_event must be a no-op without an agent (no exception)."""
        newrelic.agent.record_custom_event('TestEvent', {'key': 'value'})

    def test_add_custom_attributes_is_callable(self):
        """add_custom_attributes must be a no-op without an agent (no exception)."""
        newrelic.agent.add_custom_attributes({'recording_id': 1, 'agent_id': 'test'})
