"""
Management command: submit pending recordings to speech provider.

Usage:
    python manage.py submit_recordings
    python manage.py submit_recordings --tier immediate
    python manage.py submit_recordings --tier normal --tier off_peak --batch-size 500
    python manage.py submit_recordings --dry-run
"""
from django.core.management.base import BaseCommand

from baysys_call_audit.models import CallRecording
from baysys_call_audit.services import submit_pending_recordings

VALID_TIERS = {"immediate", "normal", "off_peak"}


class Command(BaseCommand):
    help = "Submit pending CallRecording rows to the speech provider."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tier",
            action="append",
            dest="tiers",
            choices=list(VALID_TIERS),
            metavar="TIER",
            help=(
                "Limit submission to recordings of this tier. "
                "Can be specified multiple times. "
                "Omit to include all tiers."
            ),
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Maximum number of recordings to submit (default: 100).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count pending recordings without submitting.",
        )

    def handle(self, *args, **options):
        tiers = options["tiers"] or None  # None = all tiers
        batch_size = options["batch_size"]
        dry_run = options["dry_run"]

        if dry_run:
            qs = CallRecording.objects.filter(status="pending")
            if tiers:
                qs = qs.filter(submission_tier__in=tiers)
            count = qs.count()
            tier_label = ", ".join(sorted(tiers)) if tiers else "all"
            self.stdout.write(
                f"[dry-run] {count} pending recording(s) in tier(s): {tier_label}"
            )
            return

        result = submit_pending_recordings(batch_size=batch_size, tiers=tiers)

        tier_label = ", ".join(sorted(tiers)) if tiers else "all"
        self.stdout.write(
            f"Submitted {result['submitted']} | "
            f"Failed {result['failed']} | "
            f"Skipped {result['skipped']} "
            f"(tier: {tier_label}, batch_size: {batch_size})"
        )

        if result["failed"]:
            self.stderr.write(
                f"{result['failed']} recording(s) failed to submit. "
                "Check error_message on failed CallRecording rows."
            )
