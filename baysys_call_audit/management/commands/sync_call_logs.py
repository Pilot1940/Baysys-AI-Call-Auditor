"""
Daily sync from uvarcl_live.call_logs + users → CallRecording.

Reads recording metadata from the CRM's call_logs table, JOINs to users
for agent name + agency, and creates enriched CallRecording rows with
status=pending.

Usage:
    python manage.py sync_call_logs                          # yesterday
    python manage.py sync_call_logs --date 2026-03-30        # specific date
    python manage.py sync_call_logs --batch-size 5000        # custom batch
    python manage.py sync_call_logs --dry-run                # count only
"""
import logging
import time
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import connection

from baysys_call_audit.ingestion import create_recording_from_row

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

COLUMN_NAMES = [
    "source_id", "agent_id", "agent_name", "agency_id", "customer_id",
    "customer_number", "recording_s3_path", "created_at", "call_duration",
    "campaign_name", "loan_id",
]


def map_row_to_recording(row_dict: dict) -> dict:
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


class Command(BaseCommand):
    help = "Sync call recordings from uvarcl_live.call_logs for a target date."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Target date in YYYY-MM-DD format. Defaults to yesterday.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=5000,
            help="Number of rows to fetch per query. Default: 5000.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Count and validate but do not create records.",
        )

    def handle(self, *args, **options):
        target_date = options["date"]
        if target_date:
            target_date = date.fromisoformat(target_date)
        else:
            target_date = date.today() - timedelta(days=1)

        batch_size = options["batch_size"]
        dry_run = options["dry_run"]

        self.stdout.write(
            f"Syncing call_logs for {target_date}"
            f" (batch_size={batch_size}, dry_run={dry_run})"
        )

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
                    row_dict = dict(zip(COLUMN_NAMES, db_row))
                    mapped = map_row_to_recording(row_dict)

                    if mapped.get("agent_name") == "Unknown":
                        counts["unknown_agents"] += 1

                    if dry_run:
                        # Still validate
                        from baysys_call_audit.ingestion import validate_row  # noqa: PLC0415

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

        elapsed = time.monotonic() - start_time

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"\n{prefix}Sync complete for {target_date} in {elapsed:.1f}s:\n"
            f"  Fetched:            {counts['fetched']}\n"
            f"  Created:            {counts['created']}\n"
            f"  Skipped (dedup):    {counts['skipped_dedup']}\n"
            f"  Skipped (invalid):  {counts['skipped_validation']}\n"
            f"  Unknown agents:     {counts['unknown_agents']}\n"
            f"  Errors:             {counts['errors']}"
        ))

        logger.info("sync_call_logs %s: %s", target_date, counts)
        return str(counts)
