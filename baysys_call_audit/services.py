"""
Ingestion pipeline, scoring logic, and compliance integration.

Key services:
  - submit_pending_recordings()   -> batch-submit recordings to provider
  - process_provider_webhook()    -> handle provider callback, create transcript + scores + flags
  - run_own_llm_scoring()         -> placeholder for custom LLM scoring (future)

Compliance logic lives in compliance.py (config-driven engine).
"""
import logging

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

        except speech_provider.ProviderError as exc:
            recording.retry_count += 1
            recording.status = "failed"
            recording.error_message = str(exc)
            recording.save(update_fields=["retry_count", "status", "error_message"])
            counts["failed"] += 1
            logger.warning("Failed to submit recording %s: %s", recording.pk, exc)

    logger.info(
        "Batch submission complete: %d submitted, %d failed, %d skipped",
        counts["submitted"], counts["failed"], counts["skipped"],
    )
    return counts


# ─────────────────────────────────────────────────────────────────────────────
# Webhook processing: handle provider callback
# ─────────────────────────────────────────────────────────────────────────────

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

    # Idempotency: skip if already completed
    if recording.status == "completed":
        logger.info("Recording %s already completed, skipping", recording.pk)
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
# Own LLM scoring (placeholder — implementation is a future prompt)
# ─────────────────────────────────────────────────────────────────────────────

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
