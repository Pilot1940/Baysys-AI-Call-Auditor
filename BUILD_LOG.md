# BaySys Call Audit AI — Build Log

**Project:** BaySys Call Audit AI
**Repo:** `Pilot1940/Baysys-AI-Call-Auditor`
**Build start:** 2026-04-01
**Last updated:** 2026-04-01 (Session 5)
**Build method:** Claude Code (Opus 4.6)

---

## Prompt Build Order

| Prompt | Scope | Session date | Issues closed |
|--------|-------|-------------|---------------|
| A | Full scaffold: Django + React + models + tests | 2026-04-01 | — |
| B | Ingestion pipeline: call_logs sync + CSV upload | 2026-04-01 | #4, #5 |
| C | Sync API + RBI COC compliance engine + fatal level | 2026-04-01 | #7 |
| D | S3 URL re-signing + submission tier system | 2026-04-01 | #6 |
| E | S3 raw key storage + IST timezone compliance | 2026-04-01 | #8, #9 |
| F | Bulk dedup pre-fetch: O(1) per row sync performance | 2026-04-01 | #10 |

---

## Session 1 — Prompt A: Project Scaffold

**Date:** 2026-04-01
**Scope:** Complete project scaffold — Django app, React UI scaffold, full test suite, documentation.

### Files created

**Root:**
- `manage.py` — Django CLI entry point
- `settings.py` — flat Django settings with python-decouple, Supabase DB, CORS, provider env vars
- `settings_test.py` — SQLite in-memory override for tests
- `urls.py` — root URL config (admin + audit app)
- `requirements.txt` — Django, DRF, psycopg2-binary, requests, python-decouple, ruff
- `.env.example` — template for all env vars
- `.gitignore` — Python, Node, Django, OS ignores

**Django app (`baysys_call_audit/`):**
- `__init__.py`, `apps.py` — app config
- `models.py` — 5 models: CallRecording, CallTranscript, ProviderScore, ComplianceFlag, OwnLLMScore
- `admin.py` — all 5 models registered
- `auth.py` — MockUser, MockCrmAuth, get_auth_backend(), AuditPermissionMixin
- `crm_adapter.py` — 6 functions with mock/prod branching
- `speech_provider.py` — 6 public functions + ProviderError, implements GreyLabs
- `services.py` — submit_pending_recordings(), process_provider_webhook(), check_compliance(), run_own_llm_scoring() (placeholder)
- `serializers.py` — 7 serializers
- `views.py` — 5 views (webhook, recording list/detail, dashboard summary, compliance flags)
- `urls.py` — 5 URL patterns
- `migrations/0001_initial.py` — auto-generated

**Tests (`baysys_call_audit/tests/`):**
- `test_models.py` — 18 tests
- `test_speech_provider.py` — 12 tests
- `test_webhook.py` — 8 tests
- `test_services.py` — 13 tests
- `test_views.py` — 14 tests
- `test_crm_adapter.py` — 7 tests

**React scaffold (`baysys_call_audit_ui/`):**
- Full Vite + TypeScript + Tailwind config
- 2 pages (Dashboard, CallDetail), 4 components (ScoreCard, ComplianceFlags, AgentTable, TrendChart)
- Types, API client, mock auth context

**Documentation:**
- `CLAUDE.md`, `README.md`, `MANIFEST.md`, `BUILD_LOG.md`
- `docs/OPERATIONS.md`, `docs/speech-provider/api-reference.md`, `docs/testing/test-guide.md`

### Key decisions

1. **Provider abstraction via `speech_provider.py`** — all GreyLabs-specific code isolated in one file. Model fields use generic names (`provider_resource_id` not `greylabs_id`). Swapping providers requires changing only this file.

2. **Webhook idempotency on `provider_resource_id`** — if a recording is already `completed`, the webhook returns 200 without reprocessing. Prevents duplicate transcripts/scores from provider retries.

3. **Compliance as separate model** — `ComplianceFlag` is a standalone table (not embedded in scores) to support multiple flag types per recording, independent review workflow, and severity-based alerting.

4. **OwnLLMScore as placeholder** — schema created with minimal fields. `run_own_llm_scoring()` returns None. Implementation deferred to a future prompt.

5. **Same RBAC as Trainer** — role IDs 1-5, `AuditPermissionMixin` with `get_user_filter()` that scopes queries by role. Agents see own calls, TLs see agency, admins see all.

6. **Recording URL max_length=2000** — S3 signed URLs with presigned params can be very long.

7. **Separate schema, same Supabase instance** — `DB_SCHEMA=baysys_call_audit` in settings. No FK relationships to Trainer tables. Comparison happens at dashboard layer.

### Test count at end of session: 72 passing, 0 ruff findings

---

## Session 2 — Prompt B: Ingestion Pipeline

**Date:** 2026-04-01
**Scope:** Two ingestion paths to populate CallRecording: daily sync from uvarcl_live.call_logs + CSV/Excel upload.
**Issues closed:** #4, #5

### Files created

- `baysys_call_audit/ingestion.py` — shared ingestion logic: `create_recording_from_row()`, `validate_row()`, `parse_datetime_flexible()`, `normalize_column_name()`
- `baysys_call_audit/management/__init__.py`
- `baysys_call_audit/management/commands/__init__.py`
- `baysys_call_audit/management/commands/sync_call_logs.py` — daily sync from `uvarcl_live.call_logs` LEFT JOIN `uvarcl_live.users`, raw SQL via `django.db.connection`, args: `--date`, `--batch-size`, `--dry-run`
- `baysys_call_audit/management/commands/import_recordings.py` — CSV/Excel upload via `csv` + `openpyxl`, normalized column headers, args: `file_path`, `--sheet`, `--dry-run`
- `baysys_call_audit/tests/test_ingestion.py` — 28 tests
- `baysys_call_audit/tests/test_sync_call_logs.py` — 11 tests
- `baysys_call_audit/tests/test_import_recordings.py` — 24 tests

### Files modified

- `baysys_call_audit/views.py` — added `RecordingImportView` (POST /audit/recordings/import/, Admin/Manager only)
- `baysys_call_audit/urls.py` — added `recordings/import/` route
- `requirements.txt` — added `openpyxl>=3.1`
- `MANIFEST.md` — updated with new files, test counts
- `BUILD_LOG.md` — this entry
- `docs/OPERATIONS.md` — added sync + import usage sections

### Key decisions

1. **Raw SQL for call_logs/users** — these are CRM-owned tables in `uvarcl_live` schema. No Django models created. Raw SQL with `django.db.connection.cursor()` keeps us read-only.

2. **Single JOIN, not two-pass** — agent name resolved in the same query via LEFT JOIN to `users`. No second enrichment step. `agent_name` defaults to `'Unknown'` if user lookup fails.

3. **Dedup on `recording_url`** — `create_recording_from_row()` checks for existing rows before creating. Running sync twice for the same date is safe.

4. **Shared ingestion layer** — `ingestion.py` contains all validation, dedup, datetime parsing, and column normalization. Both the sync command and import command use the same core function.

5. **DRF import endpoint** — convenience API at `/audit/recordings/import/`. Restricted to role_id 1 (Admin) and 2 (Manager/TL). Management command is the primary mechanism.

6. **Column name normalization** — `normalize_column_name()` handles spaces, camelCase, hyphens, so CSV headers like "Agent ID" or "agentId" both map to `agent_id`.

7. **openpyxl for Excel** — added to requirements.txt. Only imported inside function bodies to avoid import errors if not installed.

### Test count at end of session: 135 passing, 0 ruff findings

---

## Session 3 — Prompt C: Sync API + Compliance Engine + Fatal Level

**Date:** 2026-04-01
**Scope:** Failsafe sync API endpoint, config-driven RBI COC compliance engine (YAML), fatal level weighted boolean scoring.
**Issues closed:** #7

### Files created

- `baysys_call_audit/compliance.py` — config-driven compliance engine: metadata rules (call_window, blocked_weekday, gazette_holiday, max_calls_per_customer), provider rules (fatal_level_threshold, provider_score_threshold, provider_transcript_field), fatal level computation from provider boolean scores, content hash verification
- `config/compliance_rules.yaml` — 4 metadata rules + 3 provider rules
- `config/fatal_level_rules.yaml` — 6 boolean parameters with weights, content hash
- `config/gazette_holidays_2026.txt` — 22 India gazette holidays
- `baysys_call_audit/migrations/0002_callrecording_fatal_level.py` — adds `fatal_level` IntegerField
- `baysys_call_audit/management/commands/update_fatal_level_hash.py` — computes SHA-256 content hash for fatal_level_rules.yaml
- `baysys_call_audit/tests/test_compliance.py` — 38 tests
- `baysys_call_audit/tests/test_fatal_level.py` — 14 tests
- `baysys_call_audit/tests/test_sync_api.py` — 9 tests

### Files modified

- `baysys_call_audit/models.py` — added `fatal_level` field to CallRecording
- `baysys_call_audit/services.py` — removed old `check_compliance()` + `_check_call_timing()`, integrated `compliance.py` (compute_fatal_level + check_provider_compliance) into webhook processing
- `baysys_call_audit/ingestion.py` — factored `run_sync_for_date()` as shared sync core, added `check_metadata_compliance()` call after recording creation
- `baysys_call_audit/views.py` — added `SyncCallLogsView` (POST /audit/recordings/sync/, Admin/Supervisor only)
- `baysys_call_audit/urls.py` — added `recordings/sync/` route
- `baysys_call_audit/management/commands/sync_call_logs.py` — thin wrapper calling `run_sync_for_date()`
- `settings.py` — added `COMPLIANCE_MAX_CALLS_PER_CUSTOMER_PER_DAY`, `COMPLIANCE_FATAL_THRESHOLD`, `SYNC_ALLOWED_ROLES`
- `requirements.txt` — added `pyyaml>=6.0`
- `baysys_call_audit/tests/test_services.py` — updated: removed `check_compliance` import, mocked compliance in webhook tests
- `baysys_call_audit/tests/test_webhook.py` — updated: mocked compliance engine, adjusted outside_hours test
- `baysys_call_audit/tests/test_sync_call_logs.py` — updated: imports from `ingestion.py` instead of command module

### Key decisions

1. **Config-driven compliance** — rules in `config/compliance_rules.yaml`. Adding a rule of an existing check_type = YAML-only change, no code.

2. **Metadata rules at ingestion, provider rules at webhook** — clear separation. Metadata compliance runs when CallRecording is created; provider compliance runs when webhook delivers results.

3. **Fatal level from boolean scores** — `config/fatal_level_rules.yaml` maps provider boolean parameters to weighted scores. `fatal_level = min(sum_triggered_weights, 5)`. Ops edits weights, runs `update_fatal_level_hash`, commits to git.

4. **Content hash for audit integrity** — SHA-256 of YAML content (excluding hash line) stored in `content_hash` field. Mismatch logs WARNING but does not block scoring.

5. **Settings override YAML params** — Django settings (`COMPLIANCE_CALL_WINDOW_START_HOUR`, etc.) take precedence over YAML defaults.

6. **Sync logic factored into `ingestion.py`** — `run_sync_for_date()` is the single implementation. Management command and API view are both thin wrappers.

7. **Restricted keywords preserved in provider compliance** — carried over from the old engine as a hardcoded check alongside config-driven rules.

### Test count at end of session: 186 passing, 0 ruff findings

---

## Session 4 — Prompt D: S3 URL Re-signing + Submission Tier System

**Date:** 2026-04-01
**Scope:** Fix S3 URL expiry problem; add config-driven submission tier system (immediate/normal/off_peak).
**Issues closed:** #6

### Files created

- `config/submission_priority.yaml` — tier assignment config: agency_ids, bank_names, product_types per tier
- `baysys_call_audit/migrations/0003_callrecording_submission_tier.py` — adds `submission_tier` CharField
- `baysys_call_audit/management/commands/submit_recordings.py` — submit pending recordings. Args: `--tier`, `--batch-size`, `--dry-run`
- `baysys_call_audit/tests/test_submission_tiers.py` — 35 tests

### Files modified

- `baysys_call_audit/crm_adapter.py` — added `get_signed_url(s3_path)` (mock: returns path unchanged; prod: calls `arc.s3.service.s3_download()`)
- `baysys_call_audit/models.py` — added `submission_tier` CharField(20, default=normal, db_index=True) with TIER_CHOICES
- `baysys_call_audit/ingestion.py` — added `_load_submission_priority()` (lru_cache), `_tier_matches()`, `_determine_submission_tier()`; set `submission_tier` in `create_recording_from_row()`
- `baysys_call_audit/services.py` — added `tiers` parameter to `submit_pending_recordings()`; added `get_signed_url()` call immediately before each provider submission with fallback to stored URL
- `baysys_call_audit/tests/test_crm_adapter.py` — added 3 tests for `get_signed_url` in mock mode
- `MANIFEST.md`, `BUILD_LOG.md`, `docs/OPERATIONS.md` — updated

### Key decisions

1. **Re-sign immediately before submission, never store** — `get_signed_url()` is called per-recording inside the submission loop. The `recording_url` in DB always holds the raw S3 path, never a signed URL.

2. **Fallback on re-sign failure** — if `get_signed_url()` raises, log a warning and fall back to the stored URL. Submission is still attempted (may fail at provider, but doesn't block the batch).

3. **Config-driven tier assignment at ingestion** — `_determine_submission_tier()` reads `config/submission_priority.yaml` via `_load_submission_priority()` (lru_cache). Config errors (missing file, malformed YAML) default to `normal` and log a warning — never fail ingestion.

4. **OR logic within tier, immediate > off_peak > normal precedence** — a recording matches a tier if ANY rule matches. Tiers are checked in order: immediate first, then off_peak, else normal.

5. **Integer vs string agency_id** — config stores `agency_ids` as integers; `CallRecording.agency_id` is CharField. `_tier_matches()` converts both sides to str before comparing.

6. **submit_recordings command as thin wrapper** — delegates to `submit_pending_recordings()`. Supports `--tier` (repeatable), `--batch-size`, `--dry-run`.

### Test count at end of session: 224 passing, 0 ruff findings

---

## Session 5 — Prompt E: S3 Raw Key Storage + IST Timezone Compliance

**Date:** 2026-04-01
**Scope:** Three bugs found during live DB validation against `uvarcl_live.call_logs`.
**Issues closed:** #8 (recording_url field type), #9 (IST timezone in compliance)

### Files created

- `baysys_call_audit/migrations/0004_recording_url_charfield.py` — AlterField recording_url URLField → CharField

### Files modified

- `baysys_call_audit/models.py` — `recording_url`: `URLField` → `CharField`. S3 object keys have no URL scheme.
- `baysys_call_audit/ingestion.py` — `validate_row()`: removed URL format check, non-empty only. `SYNC_QUERY` + `SYNC_COLUMN_NAMES` + `map_sync_row()`: `created_at` → `call_start_time`.
- `baysys_call_audit/compliance.py` — added `_IST = ZoneInfo("Asia/Kolkata")`; all four metadata handlers now convert `recording_datetime` (UTC) to IST before extracting hour/weekday/date.
- `baysys_call_audit/tests/test_models.py` — 2 new tests: raw S3 key saves without error, round-trip unchanged
- `baysys_call_audit/tests/test_ingestion.py` — updated `test_bad_url_prefix` → accepts any non-empty path; added 5 new tests (raw S3 key, SYNC_QUERY strings, map_sync_row)
- `baysys_call_audit/tests/test_compliance.py` — updated 2 call_window tests (now use UTC times matching IST window boundary); added 9 IST-aware tests (call window, blocked weekday, gazette holiday)
- `baysys_call_audit/tests/test_sync_call_logs.py` — renamed `created_at` → `call_start_time` in `_make_db_row()`
- `MANIFEST.md`, `BUILD_LOG.md`, `CLAUDE.md`, `docs/OPERATIONS.md` — updated

### Bug source

Live DB validation against `uvarcl_live.call_logs` revealed:
1. `recording_s3_path` stores raw S3 object keys (no `http://` prefix) — URLField rejected them
2. All compliance time checks were UTC-based; RBI rules are IST (+5:30) → 23% of calls misclassified
3. `created_at` is DB insert timestamp (erratic); `call_start_time` is actual call start (reliable)

### Key decisions

1. **CharField not URLField** — S3 object keys like `Konex/recordings/call.mp3` have no URL scheme. Validation is non-empty only. Signing happens at submission time.

2. **`_IST` module-level constant** — `ZoneInfo("Asia/Kolkata")` computed once, reused in all four compliance handlers. Python 3.9+ stdlib, no new dependency.

3. **UTC stored, IST for compliance** — `recording_datetime` stays as UTC in the DB. All four metadata handlers call `.astimezone(_IST)` at check time. No DB schema change.

4. **`call_start_time` not `created_at`** — filter, sort, and `recording_datetime` mapping all use `call_start_time`. No `created_at` in SYNC_QUERY.

5. **Existing tests updated** — `CallWindowTests` tests adjusted to use UTC times that correctly map to the intended IST hours. `test_sync_call_logs.py` helper renamed to reflect the column change.

### Test count at end of session: 241 passing, 0 ruff findings

---

## Session 6 — Prompt F: Sync Performance — Bulk Dedup Pre-fetch

**Date:** 2026-04-01
**Scope:** Fix N-query dedup performance bug discovered during first real sync run against Supabase.
**Issues closed:** #10

### Bug source

First live sync of a single date (11,429 rows) issued one `SELECT` per row to check for duplicates over a Supabase pooler connection. At 50–100ms per round trip, a single date took 10–20 minutes — unacceptable for a nightly cron job.

### Fix

`run_sync_for_date()` now pre-fetches all existing `recording_url` values for the target date in **one** ORM query before the loop:

```python
existing_urls: set[str] = set(
    CallRecording.objects.filter(recording_datetime__date=target_date)
    .values_list("recording_url", flat=True)
)
```

Dedup inside the loop is then an O(1) `in` check. `existing_urls` is updated after each successful create for correct intra-batch dedup.

`create_recording_from_row()` accepts an optional `existing_urls: set[str] | None = None` parameter — fast path when provided, DB-query fallback when None (CSV/Excel import path unchanged).

### Performance impact

| | Before | After |
|---|---|---|
| DB queries for 11K row sync | ~11,429 | 1 pre-fetch + N creates |
| Duration for one date | 10–20 min | < 30 seconds |
| CSV import path | unchanged | unchanged |

### Files modified

- `baysys_call_audit/ingestion.py` — `run_sync_for_date()` pre-fetch + intra-batch dedup; `create_recording_from_row()` `existing_urls` parameter
- `baysys_call_audit/tests/test_ingestion.py` — 5 new tests for `existing_urls` parameter
- `baysys_call_audit/tests/test_sync_call_logs.py` — 3 new tests for pre-fetch + intra-batch dedup
- `CLAUDE.md`, `MANIFEST.md`, `BUILD_LOG.md`, `docs/OPERATIONS.md` — updated

### Key decisions

1. **Pre-fetch scoped to target date** — filters on `recording_datetime__date=target_date`. Avoids loading the entire table into memory for large historical datasets.

2. **Loop check before calling `create_recording_from_row()`** — dedup counter (`skipped_dedup`) is incremented cleanly in the loop via `continue`, not inside the function. Function's fast path is belt-and-suspenders.

3. **`existing_urls` is optional, defaults to None** — CSV/Excel import callers pass no argument. DB fallback path is untouched.

4. **Intra-batch dedup via set update** — after a successful create, the URL is added to `existing_urls` so a duplicate in the same batch is caught without a DB round trip.

### Test count at end of session: 249 passing, 0 ruff findings
