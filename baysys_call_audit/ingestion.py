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
import os
import re
import time

import newrelic.agent
from datetime import date, datetime, timedelta
from functools import lru_cache

from django.conf import settings
from django.db import connection
from django.db.models import Count
from django.utils import timezone

from .models import CallRecording

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Submission tier config
# ─────────────────────────────────────────────────────────────────────────────

_SUBMISSION_PRIORITY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "config",
    "submission_priority.yaml",
)


@lru_cache(maxsize=1)
def _load_submission_priority() -> dict:
    """
    Load config/submission_priority.yaml.
    Returns empty dict on missing file or parse error — never raises.
    Cached after first load (restart/reload to pick up changes).
    """
    try:
        import yaml  # noqa: PLC0415
        with open(_SUBMISSION_PRIORITY_PATH) as f:
            data = yaml.safe_load(f)
        return data or {}
    except FileNotFoundError:
        logger.warning("submission_priority.yaml not found — defaulting all recordings to 'normal'")
        return {}
    except Exception as exc:
        logger.warning("Failed to load submission_priority.yaml: %s — defaulting to 'normal'", exc)
        return {}


def _tier_matches(row: dict, tier_cfg: dict) -> bool:
    """Return True if any rule in tier_cfg matches the given row."""
    # agency_ids: exact match (compare as str)
    agency_ids = [str(a) for a in (tier_cfg.get("agency_ids") or [])]
    if agency_ids and str(row.get("agency_id") or "").strip() in agency_ids:
        return True

    # bank_names: substring match, case-insensitive
    bank_names = [str(b).lower() for b in (tier_cfg.get("bank_names") or [])]
    row_bank = str(row.get("bank_name") or "").lower()
    if bank_names and any(b in row_bank for b in bank_names if b):
        return True

    # product_types: exact match, case-insensitive
    product_types = [str(p).lower() for p in (tier_cfg.get("product_types") or [])]
    row_product = str(row.get("product_type") or "").lower()
    if product_types and row_product in product_types:
        return True

    return False


def _determine_submission_tier(row: dict) -> str:
    """
    Return 'immediate', 'normal', or 'off_peak' based on submission_priority.yaml config.
    Precedence: immediate > off_peak > normal.
    Defaults to 'normal' if config missing or no rules match.
    """
    config = _load_submission_priority()
    tiers_cfg = config.get("tiers") or {}

    if _tier_matches(row, tiers_cfg.get("immediate") or {}):
        return "immediate"
    if _tier_matches(row, tiers_cfg.get("off_peak") or {}):
        return "off_peak"
    return "normal"


SYNC_QUERY = """\
SELECT
    cl.id AS source_id,
    cl.agent_id,
    COALESCE(TRIM(u.first_name || ' ' || u.last_name), 'Unknown') AS agent_name,
    u.agency_id,
    cl.customer_id,
    cl.customer_number,
    cl.recording_s3_path,
    cl.call_start_time,
    cl.call_duration,
    cl.campaign_name,
    cl.loan_id
FROM uvarcl_live.call_logs cl
LEFT JOIN uvarcl_live.users u ON cl.agent_id = u.user_id
WHERE cl.call_start_time::date = %s
  AND cl.recording_s3_path IS NOT NULL
  AND cl.call_duration > %s
ORDER BY cl.call_start_time
"""

SYNC_COLUMN_NAMES = [
    "source_id", "agent_id", "agent_name", "agency_id", "customer_id",
    "customer_number", "recording_s3_path", "call_start_time", "call_duration",
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
        "recording_datetime": row_dict.get("call_start_time"),
        "bank_name": row_dict.get("campaign_name"),
        "portfolio_id": str(row_dict["loan_id"]) if row_dict.get("loan_id") is not None else None,
    }


@newrelic.agent.background_task(name='run_sync_for_date')
def run_sync_for_date(
    target_date: date | None = None,
    batch_size: int = 5000,
    dry_run: bool = False,
) -> dict:
    """
    Core sync logic: read from uvarcl_live.call_logs + users, create CallRecording rows.

    Called by both the management command and the API endpoint.

    batch_size is accepted for API compatibility but no longer controls the raw SQL
    fetch — all rows are drained into a Python list before ORM writes begin, so the
    raw cursor is closed before any transaction-generating ORM call is made.  This
    is required for pgbouncer transaction-mode pooling, where an ORM commit can
    invalidate an open server-side cursor.

    Returns dict with keys: fetched, created, skipped_dedup, skipped_validation,
    unknown_agents, errors, duration_seconds.
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    # Pre-fetch existing recording_urls for this date in one query.
    # This avoids N individual SELECT queries during the dedup check below.
    existing_urls: set[str] = set(
        CallRecording.objects.filter(
            recording_datetime__date=target_date,
        ).values_list("recording_url", flat=True)
    )

    # Pre-fetch per-customer call counts for this date in one query.
    # Avoids an N+1 DB query inside _check_max_calls_per_customer.
    # The dict is mutated in-place inside create_recording_from_row as new
    # rows are created, keeping counts accurate across loop iterations.
    call_counts_cache: dict[str, int] = {
        row["customer_id"]: row["cnt"]
        for row in CallRecording.objects.filter(
            recording_datetime__date=target_date,
            customer_id__isnull=False,
        ).values("customer_id").annotate(cnt=Count("id"))
    }

    start_time = time.monotonic()
    counts = {
        "fetched": 0,
        "created": 0,
        "skipped_dedup": 0,
        "skipped_validation": 0,
        "unknown_agents": 0,
        "errors": 0,
    }

    # Drain the raw cursor entirely before starting ORM writes.
    # Under pgbouncer transaction-mode pooling each ORM commit returns the
    # connection to the pool, which invalidates any open server-side cursor.
    # fetchall() pulls every row into a Python list so the cursor (and its
    # DB connection) can be released before any ORM call is made.
    with connection.cursor() as cursor:
        min_duration = getattr(settings, "SYNC_MIN_CALL_DURATION", 20)
        cursor.execute(SYNC_QUERY, [str(target_date), min_duration])
        raw_rows = cursor.fetchall()
    if batch_size:
        raw_rows = raw_rows[:batch_size]

    records_to_create: list[CallRecording] = []

    for db_row in raw_rows:
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

        recording_url = str(mapped.get("recording_url") or "").strip()
        if recording_url and recording_url in existing_urls:
            counts["skipped_dedup"] += 1
            continue

        errors = validate_row(mapped)
        if errors:
            counts["skipped_validation"] += 1
            logger.debug("Row validation failed: %s", errors)
            continue

        recording_dt = parse_datetime_flexible(mapped["recording_datetime"])
        if recording_dt is None:
            counts["skipped_validation"] += 1
            continue
        if timezone.is_naive(recording_dt):
            recording_dt = timezone.make_aware(recording_dt)

        tier = _determine_submission_tier(mapped)

        records_to_create.append(CallRecording(
            agent_id=str(mapped["agent_id"]).strip(),
            agent_name=str(mapped.get("agent_name") or "Unknown").strip(),
            customer_id=str(mapped["customer_id"]).strip() if mapped.get("customer_id") else None,
            portfolio_id=str(mapped["portfolio_id"]).strip() if mapped.get("portfolio_id") else None,
            supervisor_id=str(mapped["supervisor_id"]).strip() if mapped.get("supervisor_id") else None,
            agency_id=str(mapped["agency_id"]).strip() if mapped.get("agency_id") else None,
            recording_url=recording_url,
            recording_datetime=recording_dt,
            customer_phone=str(mapped["customer_phone"]).strip() if mapped.get("customer_phone") else None,
            product_type=str(mapped["product_type"]).strip() if mapped.get("product_type") else None,
            bank_name=str(mapped["bank_name"]).strip() if mapped.get("bank_name") else None,
            status="pending",
            submission_tier=tier,
        ))
        # Mark seen so within-batch duplicates are skipped
        existing_urls.add(recording_url)
        # Update per-customer count so compliance sees accurate totals
        if mapped.get("customer_id"):
            cid = str(mapped["customer_id"]).strip()
            call_counts_cache[cid] = call_counts_cache.get(cid, 0) + 1

    if records_to_create:
        try:
            CallRecording.objects.bulk_create(records_to_create, ignore_conflicts=True)
        except Exception:
            counts["errors"] += len(records_to_create)
            logger.exception("bulk_create failed")
            records_to_create = []

        counts["created"] = len(records_to_create)

        if records_to_create:
            from .compliance import check_metadata_compliance  # noqa: PLC0415
            # Re-fetch inserted rows by URL — bulk_create does not reliably set PKs
            # on SQLite (used in tests); a WHERE IN fetch is still a single query.
            inserted_urls = [r.recording_url for r in records_to_create]
            for recording in CallRecording.objects.filter(recording_url__in=inserted_urls):
                try:
                    check_metadata_compliance(recording, call_counts_cache=call_counts_cache)
                except Exception:
                    logger.exception("Compliance check failed for recording_url=%s", recording.recording_url)

    counts["duration_seconds"] = round(time.monotonic() - start_time, 1)
    newrelic.agent.record_custom_event('SyncCompleted', {
        'target_date': str(target_date),
        'fetched': counts['fetched'],
        'created': counts['created'],
        'skipped_dedup': counts['skipped_dedup'],
        'skipped_validation': counts['skipped_validation'],
        'duration_seconds': counts.get('duration_seconds', 0),
    })
    return counts


def create_recording_from_row(
    row: dict,
    existing_urls: set[str] | None = None,
    call_counts_cache: dict | None = None,
) -> tuple[CallRecording | None, bool]:
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
        existing_urls: pre-fetched set of recording_url values already in the DB for
                       the target date. When provided, dedup uses O(1) set lookup
                       instead of a DB query. Pass None to fall back to DB query
                       (used by CSV/Excel import path).
        call_counts_cache: optional dict[customer_id, int] pre-fetched by
                           run_sync_for_date.  Passed through to
                           check_metadata_compliance so that
                           _check_max_calls_per_customer avoids a per-row DB query.
                           Mutated in-place: incremented for this recording's
                           customer_id after a successful create.  Pass None to
                           fall back to DB query (CSV/Excel import and webhook paths).

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
    if existing_urls is not None:
        # Fast path: O(1) set lookup (pre-fetched by run_sync_for_date)
        if recording_url in existing_urls:
            return (None, False)
    else:
        # Fallback: DB query (used by CSV/Excel import path)
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

    tier = _determine_submission_tier(row)

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
        submission_tier=tier,
    )

    # Increment the per-customer count before compliance so the check sees the
    # correct total (pre-fetched count + this newly created recording).
    if call_counts_cache is not None and recording.customer_id:
        call_counts_cache[recording.customer_id] = (
            call_counts_cache.get(recording.customer_id, 0) + 1
        )

    # Run metadata compliance checks at ingestion time
    from .compliance import check_metadata_compliance  # noqa: PLC0415

    check_metadata_compliance(recording, call_counts_cache=call_counts_cache)

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
    # Note: recording_url is a raw S3 object key — no URL format check.
    # Signing happens at submission time via crm_adapter.get_signed_url().

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
