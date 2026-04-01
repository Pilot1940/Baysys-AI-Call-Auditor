"""
CSV/Excel upload for manual backfill of CallRecording rows.

Reads a file, normalizes column headers, and creates CallRecording rows
via the shared ingestion logic.

Usage:
    python manage.py import_recordings recordings.csv
    python manage.py import_recordings recordings.xlsx --sheet "Sheet1"
    python manage.py import_recordings recordings.csv --dry-run
"""
import csv
import logging
import time

from django.core.management.base import BaseCommand, CommandError

from baysys_call_audit.ingestion import (
    create_recording_from_row,
    normalize_column_name,
    validate_row,
)

logger = logging.getLogger(__name__)

# Expected columns after normalization
EXPECTED_COLUMNS = {
    "agent_id", "agent_name", "recording_url", "recording_datetime",
    "customer_id", "portfolio_id", "agency_id", "customer_phone",
    "product_type", "bank_name",
}
REQUIRED_COLUMNS = {"agent_id", "recording_url", "recording_datetime"}


def read_csv_rows(file_path: str) -> list[dict]:
    """Read CSV file and return list of dicts with normalized column names."""
    rows = []
    with open(file_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return rows
        col_map = {name: normalize_column_name(name) for name in reader.fieldnames}
        for raw_row in reader:
            normalized = {}
            for orig_name, value in raw_row.items():
                norm_name = col_map.get(orig_name, normalize_column_name(orig_name))
                normalized[norm_name] = value if value != "" else None
            rows.append(normalized)
    return rows


def read_excel_rows(file_path: str, sheet_name: str | None = None) -> list[dict]:
    """Read Excel file and return list of dicts with normalized column names."""
    import openpyxl  # noqa: PLC0415

    wb = openpyxl.load_workbook(file_path, read_only=True)
    ws = wb[sheet_name] if sheet_name else wb.active

    rows_iter = ws.iter_rows(values_only=True)
    header_row = next(rows_iter, None)
    if header_row is None:
        wb.close()
        return []

    col_names = [normalize_column_name(str(h)) if h else f"col_{i}" for i, h in enumerate(header_row)]

    rows = []
    for data_row in rows_iter:
        row_dict = {}
        for col_name, value in zip(col_names, data_row):
            row_dict[col_name] = value if value is not None and str(value).strip() != "" else None
        rows.append(row_dict)

    wb.close()
    return rows


class Command(BaseCommand):
    help = "Import call recordings from a CSV or Excel file."

    def add_arguments(self, parser):
        parser.add_argument(
            "file_path",
            type=str,
            help="Path to CSV or XLSX file.",
        )
        parser.add_argument(
            "--sheet",
            type=str,
            default=None,
            help="Excel sheet name. Default: first sheet.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Validate and count but do not create records.",
        )

    def handle(self, *args, **options):
        file_path = options["file_path"]
        sheet = options["sheet"]
        dry_run = options["dry_run"]

        # Determine file type
        lower_path = file_path.lower()
        if lower_path.endswith(".csv"):
            rows = read_csv_rows(file_path)
        elif lower_path.endswith((".xlsx", ".xls")):
            rows = read_excel_rows(file_path, sheet)
        else:
            raise CommandError(f"Unsupported file format: {file_path}. Use .csv or .xlsx.")

        if not rows:
            self.stdout.write(self.style.WARNING("No data rows found in file."))
            return

        # Check required columns exist
        first_row_keys = set(rows[0].keys())
        missing = REQUIRED_COLUMNS - first_row_keys
        if missing:
            raise CommandError(
                f"Missing required columns: {', '.join(sorted(missing))}. "
                f"Found columns: {', '.join(sorted(first_row_keys))}"
            )

        self.stdout.write(
            f"Importing {len(rows)} rows from {file_path} (dry_run={dry_run})"
        )

        start_time = time.monotonic()
        counts = {
            "total": len(rows),
            "created": 0,
            "skipped_dedup": 0,
            "skipped_validation": 0,
            "errors": 0,
        }
        row_errors = []

        for i, row in enumerate(rows, start=2):  # Row 2 = first data row (after header)
            if dry_run:
                errors = validate_row(row)
                if errors:
                    counts["skipped_validation"] += 1
                    row_errors.append({"row": i, "errors": errors})
                else:
                    counts["created"] += 1
                continue

            try:
                recording, created = create_recording_from_row(row)
                if created:
                    counts["created"] += 1
                elif recording is None:
                    counts["skipped_validation"] += 1
                    errors = validate_row(row)
                    row_errors.append({"row": i, "errors": errors})
                else:
                    counts["skipped_dedup"] += 1
            except Exception as exc:
                counts["errors"] += 1
                row_errors.append({"row": i, "errors": [str(exc)]})
                logger.exception("Error importing row %d", i)

        elapsed = time.monotonic() - start_time

        # Warn if >10% validation failures
        fail_count = counts["skipped_validation"] + counts["errors"]
        if counts["total"] > 0 and fail_count / counts["total"] > 0.10:
            self.stdout.write(self.style.WARNING(
                f"\n⚠ High failure rate: {fail_count}/{counts['total']} rows "
                f"({fail_count / counts['total'] * 100:.0f}%) failed validation or errored."
            ))

        # Show first 10 row errors
        if row_errors:
            self.stdout.write(self.style.WARNING(
                f"\nRow-level errors (showing first {min(10, len(row_errors))}):"
            ))
            for err in row_errors[:10]:
                self.stdout.write(f"  Row {err['row']}: {'; '.join(err['errors'])}")

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"\n{prefix}Import complete in {elapsed:.1f}s:\n"
            f"  Total rows:         {counts['total']}\n"
            f"  Created:            {counts['created']}\n"
            f"  Skipped (dedup):    {counts['skipped_dedup']}\n"
            f"  Skipped (invalid):  {counts['skipped_validation']}\n"
            f"  Errors:             {counts['errors']}"
        ))

        logger.info("import_recordings %s: %s", file_path, counts)
        return str(counts)
