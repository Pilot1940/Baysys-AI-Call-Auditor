"""
Shared ingestion logic for populating CallRecording from external sources.

Used by:
  - sync_call_logs management command (daily sync from uvarcl_live.call_logs)
  - import_recordings management command (CSV/Excel upload)

Key functions:
  - create_recording_from_row()   -> dedup + create CallRecording
  - validate_row()                -> validate a row dict
  - parse_datetime_flexible()     -> parse various datetime formats
  - normalize_column_name()       -> normalize CSV/Excel headers
"""
import logging
import re
from datetime import datetime

from django.utils import timezone

from .models import CallRecording

logger = logging.getLogger(__name__)


def create_recording_from_row(row: dict) -> tuple[CallRecording | None, bool]:
    """
    Create or skip a CallRecording from a dict of field values.

    Dedup: skip if a CallRecording already exists with the same recording_url.
    Validation: skip if recording_url is empty/None, or recording_datetime is missing.

    Args:
        row: dict with keys matching CallRecording fields.
             Required: agent_id, recording_url, recording_datetime
             Expected: agent_name (populated by sync JOIN; CSV may provide directly)
             Optional: customer_id, portfolio_id, supervisor_id, agency_id,
                       customer_phone, product_type, bank_name

    Returns:
        (recording, created) — the CallRecording instance and whether it was newly created.
        If skipped due to dedup or validation failure, returns (None, False).
    """
    errors = validate_row(row)
    if errors:
        logger.debug("Row validation failed: %s", errors)
        return (None, False)

    recording_url = str(row["recording_url"]).strip()

    # Dedup on recording_url
    existing = CallRecording.objects.filter(recording_url=recording_url).first()
    if existing:
        return (existing, False)

    # Parse datetime
    recording_dt = parse_datetime_flexible(row["recording_datetime"])
    if recording_dt is None:
        return (None, False)

    # Make timezone-aware if naive
    if timezone.is_naive(recording_dt):
        recording_dt = timezone.make_aware(recording_dt)

    recording = CallRecording.objects.create(
        agent_id=str(row["agent_id"]).strip(),
        agent_name=str(row.get("agent_name") or "Unknown").strip(),
        customer_id=str(row["customer_id"]).strip() if row.get("customer_id") else None,
        portfolio_id=str(row["portfolio_id"]).strip() if row.get("portfolio_id") else None,
        supervisor_id=str(row["supervisor_id"]).strip() if row.get("supervisor_id") else None,
        agency_id=str(row["agency_id"]).strip() if row.get("agency_id") else None,
        recording_url=recording_url,
        recording_datetime=recording_dt,
        customer_phone=str(row["customer_phone"]).strip() if row.get("customer_phone") else None,
        product_type=str(row["product_type"]).strip() if row.get("product_type") else None,
        bank_name=str(row["bank_name"]).strip() if row.get("bank_name") else None,
        status="pending",
    )
    return (recording, True)


def validate_row(row: dict) -> list[str]:
    """
    Validate a row dict. Returns a list of error messages (empty = valid).

    Checks:
    - agent_id is present and non-empty
    - recording_url is present, non-empty, and looks like a URL (starts with http or s3)
    - recording_datetime is present and parseable
    Note: agent_name is NOT required — warn if missing but don't fail.
    """
    errors = []

    # agent_id
    agent_id = row.get("agent_id")
    if not agent_id or str(agent_id).strip() == "":
        errors.append("agent_id is required")

    # recording_url
    url = row.get("recording_url")
    if not url or str(url).strip() == "":
        errors.append("recording_url is required")
    elif not str(url).strip().startswith(("http", "s3")):
        errors.append(f"recording_url does not look like a URL: {url}")

    # recording_datetime
    dt_val = row.get("recording_datetime")
    if not dt_val:
        errors.append("recording_datetime is required")
    elif parse_datetime_flexible(dt_val) is None:
        errors.append(f"recording_datetime is not parseable: {dt_val}")

    # Warn (not error) if agent_name missing
    if not row.get("agent_name"):
        logger.warning("Row missing agent_name for agent_id=%s", row.get("agent_id"))

    return errors


def parse_datetime_flexible(value) -> datetime | None:
    """
    Parse a datetime from various formats:
    - datetime object (pass through)
    - ISO 8601 string
    - date string (YYYY-MM-DD) -> midnight
    - Postgres timestamp string (YYYY-MM-DD HH:MM:SS[.f][+TZ])
    Returns None if unparseable.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    s = str(value).strip()
    if not s:
        return None

    # Try ISO 8601 (handles most cases including timezone offsets)
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        pass

    # Try date-only: YYYY-MM-DD -> midnight
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except (ValueError, TypeError):
        pass

    # Try common Postgres timestamp format
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            pass

    return None


def normalize_column_name(name: str) -> str:
    """
    Normalize a column header for flexible matching.
    'Agent ID' -> 'agent_id', 'agentId' -> 'agent_id',
    'Recording URL' -> 'recording_url', etc.
    Lowercase, strip whitespace, replace spaces with underscores,
    insert underscore before camelCase capitals.
    """
    s = str(name).strip()
    # Insert underscore before uppercase letters (camelCase -> camel_case)
    s = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", s)
    s = s.lower()
    # Replace spaces and hyphens with underscores
    s = re.sub(r"[\s\-]+", "_", s)
    # Collapse multiple underscores
    s = re.sub(r"_+", "_", s)
    return s.strip("_")
