# BaySys Call Audit AI — Build Log

**Project:** BaySys Call Audit AI
**Repo:** `Pilot1940/Baysys-AI-Call-Auditor`
**Build start:** 2026-04-01
**Last updated:** 2026-04-01 (Session 3)
**Build method:** Claude Code (Opus 4.6)

---

## Prompt Build Order

| Prompt | Scope | Session date | Issues closed |
|--------|-------|-------------|---------------|
| A | Full scaffold: Django + React + models + tests | 2026-04-01 | — |
| B | Ingestion pipeline: call_logs sync + CSV upload | 2026-04-01 | #4, #5 |
| C | Sync API + RBI COC compliance engine + fatal level | 2026-04-01 | #7 |

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
