"""
Speech Analytics Provider Adapter.

This is the ONLY file that knows provider-specific API details.
Currently implements GreyLabs. When switching to an in-house pipeline,
only this file changes.

All other code references the provider generically via these functions:
  - submit_recording()    -> sends audio URL for processing
  - get_results()         -> polls for results by resource_id
  - delete_resource()     -> deletes a processed resource
  - ask_question()        -> asks a question against a transcript
  - submit_transcript()   -> submits raw transcript text for analysis
  - update_metadata()     -> adds metadata to a processed call
"""
import logging

import newrelic.agent
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Raised when the speech analytics provider returns an error."""

    def __init__(self, message: str, status_code: int | None = None, response_body: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


def _get_headers() -> dict:
    """Auth headers for the current provider."""
    return {
        "x-api-key": settings.SPEECH_PROVIDER_API_KEY,
        "x-api-secret": settings.SPEECH_PROVIDER_API_SECRET,
    }


def _get_base_url() -> str:
    return settings.SPEECH_PROVIDER_HOST.rstrip("/")


def submit_recording(
    resource_url: str,
    template_id: str,
    agent_id: str,
    agent_name: str,
    customer_id: str,
    recording_datetime: str,
    callback_url: str,
) -> str:
    """
    Submit an audio recording for processing.

    Args:
        resource_url: Signed S3 URL to the MP3 file.
        template_id: Provider template identifier for scoring.
        agent_id: CRM agent identifier.
        agent_name: Agent display name.
        customer_id: Unique customer identifier; uses 'unknown_<id>' if not available.
        recording_datetime: ISO 8601 datetime of the recording.
        callback_url: Webhook URL for provider to POST results to.

    Returns:
        provider_resource_id: The provider's identifier for this submission.

    Raises:
        ProviderError: If the provider returns a non-success response.
    """
    url = f"{_get_base_url()}/insights/resource/listen"
    payload = {
        "resource_url": resource_url,
        "template_id": template_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "customer_id": customer_id,
        "recording_datetime": recording_datetime,
        "callback_url": callback_url,
    }

    resp = requests.post(url, json=payload, headers=_get_headers(), timeout=30)

    if resp.status_code != 200:
        logger.error("GreyLabs 400 response body: %s", resp.text)
        exc = ProviderError(
            f"Submit failed: HTTP {resp.status_code}",
            status_code=resp.status_code,
            response_body=_safe_json(resp),
        )
        newrelic.agent.record_custom_event('ProviderError', {
            'endpoint': 'submit_recording',
            'status_code': resp.status_code,
            'message': str(exc)[:500],
        })
        raise exc

    data = resp.json()
    # GreyLabs may wrap the result in a "details" array — unwrap to get the actual record
    details = data.get("details", [])
    record = details[0] if details else data
    resource_id = record.get("resource_insight_id") or record.get("id")
    if not resource_id:
        raise ProviderError(
            "Submit succeeded but no resource_id in response",
            response_body=data,
        )

    logger.info("Submitted recording for agent %s, resource_id=%s", agent_id, resource_id)
    return str(resource_id)


def get_results(resource_id: str) -> dict:
    """
    Poll for processing results by resource_id.

    Returns:
        Full provider response dict containing transcript, scores, durations, etc.

    Raises:
        ProviderError: If the provider returns a non-success response.
    """
    url = f"{_get_base_url()}/insights/resource/insights"
    payload = {"resource_insight_id": resource_id}

    resp = requests.post(url, json=payload, headers=_get_headers(), timeout=30)

    if resp.status_code != 200:
        exc = ProviderError(
            f"Get results failed: HTTP {resp.status_code}",
            status_code=resp.status_code,
            response_body=_safe_json(resp),
        )
        newrelic.agent.record_custom_event('ProviderError', {
            'endpoint': 'get_results',
            'status_code': resp.status_code,
            'message': str(exc)[:500],
        })
        raise exc

    return resp.json()


def delete_resource(resource_id: str) -> bool:
    """
    Delete a processed resource from the provider.

    Returns:
        True if deletion succeeded.

    Raises:
        ProviderError: If the provider returns a non-success response.
    """
    url = f"{_get_base_url()}/insights/v1/resource/delete"
    payload = {"resource_insight_id": resource_id}

    resp = requests.post(url, json=payload, headers=_get_headers(), timeout=30)

    if resp.status_code != 200:
        raise ProviderError(
            f"Delete failed: HTTP {resp.status_code}",
            status_code=resp.status_code,
            response_body=_safe_json(resp),
        )

    return True


def ask_question(resource_id: str, question: str) -> dict:
    """
    Ask a natural-language question against a transcript.

    Returns:
        Provider response dict with the answer.
    """
    url = f"{_get_base_url()}/insights/v1/resource/ask"
    payload = {"resource_insight_id": resource_id, "question": question}

    resp = requests.post(url, json=payload, headers=_get_headers(), timeout=30)

    if resp.status_code != 200:
        raise ProviderError(
            f"Ask question failed: HTTP {resp.status_code}",
            status_code=resp.status_code,
            response_body=_safe_json(resp),
        )

    return resp.json()


def submit_transcript(transcript_text: str, template_id: str, callback_url: str) -> str:
    """
    Submit a raw transcript (not audio) for analysis.

    Returns:
        provider_resource_id for the submitted transcript.
    """
    url = f"{_get_base_url()}/insights/transcript/listen"
    payload = {
        "transcript": transcript_text,
        "template_id": template_id,
        "callback_url": callback_url,
    }

    resp = requests.post(url, json=payload, headers=_get_headers(), timeout=30)

    if resp.status_code != 200:
        raise ProviderError(
            f"Submit transcript failed: HTTP {resp.status_code}",
            status_code=resp.status_code,
            response_body=_safe_json(resp),
        )

    data = resp.json()
    resource_id = data.get("resource_insight_id") or data.get("id")
    if not resource_id:
        raise ProviderError(
            "Submit transcript succeeded but no resource_id in response",
            response_body=data,
        )

    return str(resource_id)


def update_metadata(resource_id: str, metadata: dict) -> bool:
    """
    Add metadata to a processed call.

    Returns:
        True if update succeeded.
    """
    url = f"{_get_base_url()}/insights/resource/insights/update/metadata"
    payload = {"resource_insight_id": resource_id, **metadata}

    resp = requests.post(url, json=payload, headers=_get_headers(), timeout=30)

    if resp.status_code != 200:
        raise ProviderError(
            f"Update metadata failed: HTTP {resp.status_code}",
            status_code=resp.status_code,
            response_body=_safe_json(resp),
        )

    return True


def _safe_json(resp: requests.Response) -> dict | None:
    """Attempt to parse JSON from response, return None on failure."""
    try:
        return resp.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        return None
