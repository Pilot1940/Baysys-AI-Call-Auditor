"""
Management command: poll_stuck_recordings

Finds recordings in status=submitted that have been waiting longer than
POLL_STUCK_AFTER_MINUTES and polls the provider for results.

Use as a fallback for missed webhooks. Schedule every 30 minutes via cron.

Usage:
    python manage.py poll_stuck_recordings
    python manage.py poll_stuck_recordings --batch-size 50
    python manage.py poll_stuck_recordings --dry-run
"""
import logging

from django.core.management.base import BaseCommand

from baysys_call_audit.services import run_poll_stuck_recordings

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Poll the provider for results on recordings stuck in status=submitted."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Maximum number of recordings to poll in one run (default: 50).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print which recordings would be polled, no API calls made.",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        dry_run = options["dry_run"]

        result = run_poll_stuck_recordings(batch_size=batch_size, dry_run=dry_run)
        threshold_minutes = result["threshold_minutes"]

        self.stdout.write(
            f"Polling stuck recordings "
            f"(threshold={threshold_minutes}min, batch_size={batch_size}, dry_run={dry_run})"
        )

        if dry_run:
            self.stdout.write(
                f"[dry-run] {result['polled']} recording(s) would be polled "
                f"(stuck > {threshold_minutes} min)"
            )
            return

        self.stdout.write(self.style.SUCCESS(
            f"\nPoll complete:\n"
            f"  Polled:           {result['polled']}\n"
            f"  Recovered:        {result['recovered']}\n"
            f"  Still processing: {result['still_processing']}\n"
            f"  Errors:           {result['errors']}"
        ))

        logger.info("poll_stuck_recordings: %s", result)
