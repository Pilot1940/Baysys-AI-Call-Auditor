"""
Ingestion pipeline, scoring logic, and compliance integration.

Key services:
  - submit_pending_recordings()      -> batch-submit recordings to provider
  - process_provider_webhook()       -> handle provider callback, create transcript + scores + flags
  - run_poll_stuck_recordings()      -> poll provider for recordings stuck in status=submitted
  - run_own_llm_scoring()            -> placeholder for custom LLM scoring (future)

Compliance logic lives in compliance.py (config-driven engine).
"""
import logging

import newrelic.agent
from django.conf import settings
from django.utils import timezone

from . import speech_provider
from .compliance import check_provider_compliance, compute_fatal_level
from .crm_adapter import get_signed_url
from .models import (
    CallRecording,
    CallTranscript,
    OwnLLMScore,
    ProviderScore,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Ingestion: submit pending recordings to provider
# ─────────────────────────────────────────────────────────────────────────────

@newrelic.agent.background_task(name='submit_pending_recordings')
def submit_pending_recordings(
    batch_size: int = 100,
    tiers: list[str] | None = None,
) -> dict:
    """
    Query CallRecording where status=pending, submit to speech provider.

    Args:
        batch_size: Maximum recordings to process in this call.
        tiers: Optional list of submission_tier values to filter by
               (e.g. ["immediate"] or ["normal", "off_peak"]).
               If None, all tiers are included.

    Updates status to 'submitted' on success, 'failed' on error.
    Re-signs the S3 URL immediately before each submission (URLs expire in 10-15 min).

    Returns:
        {"submitted": int, "failed": int, "skipped": int}
    """
    qs = CallRecording.objects.filter(status="pending")
    if tiers:
        qs = qs.filter(submission_tier__in=tiers)
    pending = qs.order_by("created_at")[:batch_size]

    template_id = settings.SPEECH_PROVIDER_TEMPLATE_ID
    callback_url = settings.SPEECH_PROVIDER_CALLBACK_URL

    counts = {"submitted": 0, "failed": 0, "skipped": 0}

    for recording in pending:
        if not recording.recording_url:
            recording.status = "skipped"
            recording.error_message = "No recording URL"
            recording.save(update_fields=["status", "error_message"])
            counts["skipped"] += 1
            continue

        try:
            newrelic.agent.add_custom_attributes({
                'recording_id': recording.pk,
                'agent_id': recording.agent_id,
                'submission_tier': recording.submission_tier,
            })
            # Re-sign URL immediately before submission — stored URL may have expired
            try:
                signed_url = get_signed_url(recording.recording_url)
            except Exception as exc:
                logger.warning("Failed to re-sign URL for recording %s: %s", recording.pk, exc)
                signed_url = recording.recording_url

            resource_id = speech_provider.submit_recording(
                resource_url=signed_url,
                template_id=template_id,
                agent_id=recording.agent_id,
                agent_name=recording.agent_name,
                customer_id=str(recording.customer_id) if recording.customer_id else str(recording.id),
                recording_datetime=recording.recording_datetime.isoformat(),
                callback_url=callback_url,
            )
            recording.provider_resource_id = resource_id
            recording.status = "submitted"
            recording.submitted_at = timezone.now()
            recording.save(update_fields=[
                "provider_resource_id", "status", "submitted_at",
            ])
            counts["submitted"] += 1
            newrelic.agent.record_custom_metric('Custom/Pipeline/Recordings/Submitted', 1)

        except speech_provider.ProviderError as exc:
            recording.retry_count += 1
            recording.status = "failed"
            recording.error_message = str(exc)
            recording.save(update_fields=["retry_count", "status", "error_message"])
            counts["failed"] += 1
            newrelic.agent.record_custom_metric('Custom/Pipeline/Recordings/SubmitFailed', 1)
            logger.warning(
                "Failed to submit recording %s: %s | response_body=%s",
                recording.pk, exc, exc.response_body,
            )

    logger.info(
        "Batch submission complete: %d submitted, %d failed, %d skipped",
        counts["submitted"], counts["failed"], counts["skipped"],
    )
    return counts


# ─────────────────────────────────────────────────────────────────────────────
# Webhook processing: handle provider callback
# ─────────────────────────────────────────────────────────────────────────────

@newrelic.agent.background_task(name='process_provider_webhook')
def process_provider_webhook(payload: dict) -> CallRecording | None:
    """
    Process a provider webhook callback.

    Expects payload to contain 'resource_insight_id' (or similar) to look up
    the CallRecording, plus transcript data, scores, and insights.

    Returns:
        The updated CallRecording, or None if recording not found.
    """
    resource_id = (
        payload.get("resource_insight_id")
        or payload.get("resource_id")
        or payload.get("id")
    )
    if not resource_id:
        logger.warning("Webhook payload missing resource_id: %s", payload)
        return None

    try:
        recording = CallRecording.objects.get(provider_resource_id=str(resource_id))
    except CallRecording.DoesNotExist:
        logger.warning("No CallRecording for resource_id=%s", resource_id)
        return None

    newrelic.agent.add_custom_attributes({
        'recording_id': recording.pk,
        'agent_id': recording.agent_id,
        'provider_resource_id': resource_id,
    })

    # Idempotency: skip if already completed
    if recording.status == "completed":
        logger.info("Recording %s already completed, skipping", recording.pk)
        newrelic.agent.record_custom_metric('Custom/Pipeline/Webhooks/IdempotencySkip', 1)
        return recording

    # Create transcript
    _create_transcript(recording, payload)

    # Create provider scores
    score = _create_provider_score(recording, payload)

    # Compute fatal level from provider boolean scores
    compute_fatal_level(recording, score)

    # Run provider compliance rules (config-driven)
    check_provider_compliance(recording, payload)

    # Mark complete
    recording.status = "completed"
    recording.completed_at = timezone.now()
    recording.save(update_fields=["status", "completed_at"])
    newrelic.agent.record_custom_metric('Custom/Pipeline/Webhooks/Processed', 1)

    logger.info("Processed webhook for recording %s (resource_id=%s)", recording.pk, resource_id)
    return recording


def _create_transcript(recording: CallRecording, payload: dict) -> CallTranscript:
    """Extract transcript data from provider payload and create CallTranscript."""
    insights = payload.get("insights", {})
    subjective_data = insights.get("subjective_data", [])

    summary = _find_subjective(subjective_data, "Summary")
    next_actionable = _find_subjective(subjective_data, "Next Actionable")

    transcript, _ = CallTranscript.objects.update_or_create(
        recording=recording,
        defaults={
            "transcript_text": payload.get("transcript", ""),
            "detected_language": payload.get("detected_language"),
            "total_call_duration": payload.get("total_call_duration"),
            "total_non_speech_duration": payload.get("total_non_speech_duration"),
            "customer_talk_duration": payload.get("customer_talk_duration"),
            "agent_talk_duration": payload.get("agent_talk_duration"),
            "customer_sentiment": payload.get("customer_sentiment"),
            "agent_sentiment": payload.get("agent_sentiment"),
            "summary": summary,
            "next_actionable": next_actionable,
            "raw_provider_response": payload,
        },
    )
    return transcript


def _create_provider_score(recording: CallRecording, payload: dict) -> ProviderScore | None:
    """Extract scoring data from provider payload and create ProviderScore."""
    template_id = settings.SPEECH_PROVIDER_TEMPLATE_ID
    if not template_id:
        return None

    insights = payload.get("insights", {})

    score = ProviderScore(
        recording=recording,
        template_id=template_id,
        audit_compliance_score=payload.get("audit_compliance_score"),
        max_compliance_score=payload.get("max_compliance_score"),
        category_data=insights.get("category_data"),
        detected_restricted_keyword=payload.get("detected_restricted_keyword", False),
        restricted_keywords=payload.get("restricted_keywords", []),
        raw_score_payload=insights,
    )
    score.compute_percentage()
    score.save()
    return score


def _normalise_provider_payload(raw: dict, resource_id: str) -> dict:
    """
    Ensure the payload contains a resource identifier that process_provider_webhook()
    can use for lookup. Poll responses may omit the resource_id field that webhook
    deliveries include — add it if absent.
    """
    if raw.get("resource_insight_id") or raw.get("resource_id") or raw.get("id"):
        return raw
    return {**raw, "resource_insight_id": resource_id}


def _find_subjective(subjective_data: list, parameter_name: str) -> str | None:
    """Find a specific parameter in the subjective_data list."""
    for item in subjective_data:
        if item.get("audit_parameter_name") == parameter_name:
            return item.get("answer")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Polling: recover recordings stuck in status=submitted
# ─────────────────────────────────────────────────────────────────────────────

@newrelic.agent.background_task(name='run_poll_stuck_recordings')
def run_poll_stuck_recordings(
    batch_size: int = 50,
    dry_run: bool = False,
) -> dict:
    """
    Poll the provider for recordings stuck in status=submitted.

    Returns a summary dict:
        {
            "polled": int,
            "recovered": int,
            "still_processing": int,
            "errors": int,
            "dry_run": bool,
            "threshold_minutes": int,
        }
    """
    threshold_minutes = getattr(settings, "POLL_STUCK_AFTER_MINUTES", 30)
    cutoff = timezone.now() - timezone.timedelta(minutes=threshold_minutes)
    stuck_qs = (
        CallRecording.objects.filter(
            status="submitted",
            submitted_at__lt=cutoff,
            provider_resource_id__isnull=False,
        )
        .exclude(provider_resource_id="")
        .order_by("submitted_at")[:batch_size]
    )

    result = {
        "polled": 0,
        "recovered": 0,
        "still_processing": 0,
        "errors": 0,
        "dry_run": dry_run,
        "threshold_minutes": threshold_minutes,
    }

    if dry_run:
        result["polled"] = stuck_qs.count()
        return result

    for recording in stuck_qs:
        result["polled"] += 1
        try:
            poll_result = speech_provider.get_results(recording.provider_resource_id)

            # "Still processing" — absent transcript means results not ready yet
            if not poll_result.get("transcript"):
                result["still_processing"] += 1
                continue

            payload = _normalise_provider_payload(poll_result, recording.provider_resource_id)
            updated = process_provider_webhook(payload)
            if updated and updated.status == "completed":
                result["recovered"] += 1
            else:
                result["still_processing"] += 1

        except speech_provider.ProviderError as exc:
            result["errors"] += 1
            recording.retry_count += 1
            recording.save(update_fields=["retry_count"])
            logger.warning(
                "Poll error for recording %s (resource_id=%s): %s",
                recording.pk, recording.provider_resource_id, exc,
            )

    logger.info("run_poll_stuck_recordings: %s", result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Own LLM scoring (placeholder — implementation is a future prompt)
# ─────────────────────────────────────────────────────────────────────────────

@newrelic.agent.background_task(name='run_own_llm_scoring')
def run_own_llm_scoring(recording_id: int, template_name: str = "default") -> OwnLLMScore | None:
    """
    Placeholder for custom LLM scoring pipeline.
    Will run our own LLM against the transcript using a configurable scorecard.

    Returns:
        OwnLLMScore instance, or None if transcript not available.
    """
    try:
        recording = CallRecording.objects.get(pk=recording_id)
    except CallRecording.DoesNotExist:
        return None

    if not hasattr(recording, "transcript"):
        return None

    # TODO: Implement LLM scoring pipeline
    # 1. Get transcript text from recording.transcript.transcript_text
    # 2. Send to LLM with scoring template
    # 3. Parse response into score_breakdown
    # 4. Compute totals

    return None
