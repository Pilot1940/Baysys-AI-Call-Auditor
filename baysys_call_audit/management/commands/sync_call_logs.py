"""
Daily sync from uvarcl_live.call_logs + users -> CallRecording.

Thin wrapper around ingestion.run_sync_for_date().

Usage:
    python manage.py sync_call_logs                          # yesterday
    python manage.py sync_call_logs --date 2026-03-30        # specific date
    python manage.py sync_call_logs --batch-size 5000        # custom batch
    python manage.py sync_call_logs --dry-run                # count only
"""
import logging
from datetime import date, timedelta

from django.core.management.base import BaseCommand

from baysys_call_audit.ingestion import run_sync_for_date

logger = logging.getLogger(__name__)


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

        counts = run_sync_for_date(
            target_date=target_date,
            batch_size=batch_size,
            dry_run=dry_run,
        )

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"\n{prefix}Sync complete for {target_date} in {counts['duration_seconds']}s:\n"
            f"  Fetched:            {counts['fetched']}\n"
            f"  Created:            {counts['created']}\n"
            f"  Skipped (dedup):    {counts['skipped_dedup']}\n"
            f"  Skipped (invalid):  {counts['skipped_validation']}\n"
            f"  Unknown agents:     {counts['unknown_agents']}\n"
            f"  Errors:             {counts['errors']}"
        ))

        logger.info("sync_call_logs %s: %s", target_date, counts)
        return str(counts)
