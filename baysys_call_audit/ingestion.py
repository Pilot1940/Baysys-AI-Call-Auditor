"""
Shared ingestion logic for populating CallRecording from external sources.

Used by:
  - sync_call_logs management command (daily sync from uvarcl_live.call_logs)
  - import_recordings management command (CSV/Excel upload)
  - SyncCallLogsView API endpoint (failsafe trigger)

Key functions:
  - create_recording_from_row()   -> dedup + create CallRecording
  - run_sync_for_date()           -> core sync logic (raw SQL + ingestion)
  - validate_row()                -> validate a row dict
  - parse_datetime_flexible()     -> parse various datetime formats
  - normalize_column_name()       -> normalize CSV/Excel headers
"""
import logging
import re
import time
from datetime import date, datetime, timedelta

from django.db import connection
from django.utils import timezone

from .models import CallRecording

logger = logging.getLogger(__name__)

SYNC_QUERY = """\
SELECT
    cl.id AS source_id,
    cl.agent_id,
    COALESCE(TRIM(u.first_name || ' ' || u.last_name), 'Unknown') AS agent_name,
    u.agency_id,
    cl.customer_id,
    cl.customer_number,
    cl.recording_s3_path,
    cl.created_at,
    cl.call_duration,
    cl.campaign_name,
    cl.loan_id
FROM uvarcl_live.call_logs cl
LEFT JOIN uvarcl_live.users u ON cl.agent_id = u.user_id
WHERE cl.created_at::date = %s
  AND cl.recording_s3_path IS NOT NULL
  AND cl.call_duration > 10
ORDER BY cl.created_at
"""

SYNC_COLUMN_NAMES = [
    "source_id", "agent_id", "agent_name", "agency_id", "customer_id",
    "customer_number", "recording_s3_path", "created_at", "call_duration",
    "campaign_name", "loan_id",
]


def map_sync_row(row_dict: dict) -> dict:
    """Map raw query result columns to CallRecording field names."""
    return {
        "agent_id": str(row_dict["agent_id"]) if row_dict.get("agent_id") is not None else None,
        "agent_name": row_dict.get("agent_name") or "Unknown",
        "agency_id": str(row_dict["agency_id"]) if row_dict.get("agency_id") is not None else None,
        "customer_id": str(row_dict["customer_id"]) if row_dict.get("customer_id") is not None else None,
        "customer_phone": row_dict.get("customer_number"),
        "recording_url": row_dict.get("recording_s3_path"),
        "recording_datetime": row_dict.get("created_at"),
        "bank_name": row_dict.get("campaign_name"),
        "portfolio_id": str(row_dict["loan_id"]) if row_dict.get("loan_id") is not None else None,
    }


def run_sync_for_date(
    target_date: date | None = None,
    batch_size: int = 5000,
    dry_run: bool = False,
) -> dict:
    """
    Core sync logic: read from uvarcl_live.call_logs + users, create CallRecording rows.

    Called by both the management command and the API endpoint.

    Returns dict with keys: fetched, created, skipped_dedup, skipped_validation,
    unknown_agents, errors, duration_seconds.
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    start_time = time.monotonic()
    counts = {
        "fetched": 0,
        "created": 0,
        "skipped_dedup": 0,
        "skipped_validation": 0,
        "unknown_agents": 0,
        "errors": 0,
    }

    with connection.cursor() as cursor:
        cursor.execute(SYNC_QUERY, [str(target_date)])
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break

            for db_row in rows:
                counts["fetched"] += 1
                row_dict = dict(zip(SYNC_COLUMN_NAMES, db_row))
                mapped = map_sync_row(row_dict)

                if mapped.get("agent_name") == "Unknown":
                    counts["unknown_agents"] += 1

                if dry_run:
                    errors = validate_row(mapped)
                    if errors:
                        counts["skipped_validation"] += 1
                    else:
                        counts["created"] += 1
                    continue

                try:
                    recording, created = create_recording_from_row(mapped)
                    if created:
                        counts["created"] += 1
                    elif recording is None:
                        counts["skipped_validation"] += 1
                    else:
                        counts["skipped_dedup"] += 1
                except Exception:
                    counts["errors"] += 1
                    logger.exception("Error creating recording from row")

    counts["duration_seconds"] = round(time.monotonic() - start_time, 1)
    return counts


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

    # Run metadata compliance checks at ingestion time
    from .compliance import check_metadata_compliance  # noqa: PLC0415

    check_metadata_compliance(recording)

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
