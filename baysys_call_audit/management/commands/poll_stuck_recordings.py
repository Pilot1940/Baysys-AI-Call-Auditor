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
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from baysys_call_audit import speech_provider
from baysys_call_audit.models import CallRecording
from baysys_call_audit.services import _normalise_provider_payload, process_provider_webhook

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
        threshold_minutes = getattr(settings, "POLL_STUCK_AFTER_MINUTES", 30)

        self.stdout.write(
            f"Polling stuck recordings "
            f"(threshold={threshold_minutes}min, batch_size={batch_size}, dry_run={dry_run})"
        )

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

        if dry_run:
            count = stuck_qs.count()
            self.stdout.write(
                f"[dry-run] {count} recording(s) would be polled "
                f"(stuck > {threshold_minutes} min)"
            )
            return

        start_time = time.monotonic()
        counts = {"polled": 0, "recovered": 0, "still_processing": 0, "errors": 0}

        for recording in stuck_qs:
            counts["polled"] += 1
            try:
                result = speech_provider.get_results(recording.provider_resource_id)

                # "Still processing" — transcript absent means results not ready yet
                if not result.get("transcript"):
                    counts["still_processing"] += 1
                    continue

                payload = _normalise_provider_payload(result, recording.provider_resource_id)
                updated = process_provider_webhook(payload)
                if updated and updated.status == "completed":
                    counts["recovered"] += 1
                else:
                    counts["still_processing"] += 1

            except speech_provider.ProviderError as exc:
                counts["errors"] += 1
                recording.retry_count += 1
                recording.save(update_fields=["retry_count"])
                logger.warning(
                    "Poll error for recording %s (resource_id=%s): %s",
                    recording.pk, recording.provider_resource_id, exc,
                )

        duration = round(time.monotonic() - start_time, 1)
        self.stdout.write(self.style.SUCCESS(
            f"\nPoll complete in {duration}s:\n"
            f"  Polled:           {counts['polled']}\n"
            f"  Recovered:        {counts['recovered']}\n"
            f"  Still processing: {counts['still_processing']}\n"
            f"  Errors:           {counts['errors']}"
        ))

        logger.info("poll_stuck_recordings: %s", counts)
