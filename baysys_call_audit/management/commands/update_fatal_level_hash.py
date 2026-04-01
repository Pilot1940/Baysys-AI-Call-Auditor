"""
Compute and update the content_hash in config/fatal_level_rules.yaml.

Usage:
    python manage.py update_fatal_level_hash

Workflow:
    1. Ops edits config/fatal_level_rules.yaml (weights, parameters, threshold)
    2. Ops bumps version, last_updated, updated_by
    3. Runs this command
    4. Commits to git -> audit trail complete
"""
import re

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from baysys_call_audit.compliance import compute_content_hash


class Command(BaseCommand):
    help = "Compute and update the content_hash in config/fatal_level_rules.yaml."

    def handle(self, *args, **options):
        path = settings.BASE_DIR / "config" / "fatal_level_rules.yaml"
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)

        # Validate required metadata fields
        for field in ("version", "last_updated", "updated_by"):
            if not data.get(field):
                raise CommandError(
                    f"Missing or empty '{field}' in {path}. "
                    f"Update this field before running."
                )

        # Compute hash (excluding content_hash line)
        new_hash = compute_content_hash(raw)

        # Write hash back into file
        updated = re.sub(
            r'^(content_hash:\s*)(".*?"|\'.*?\'|\S*)',
            f'\\1"{new_hash}"',
            raw,
            count=1,
            flags=re.MULTILINE,
        )
        path.write_text(updated, encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(
            f"Updated config/fatal_level_rules.yaml:\n"
            f"  version:      {data['version']}\n"
            f"  last_updated: {data['last_updated']}\n"
            f"  updated_by:   {data['updated_by']}\n"
            f"  content_hash: {new_hash}"
        ))
