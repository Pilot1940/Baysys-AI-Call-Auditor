# BaySys Call Audit AI — Code Repository Manifest

**Repo:** `Pilot1940/Baysys-AI-Call-Auditor`
**Last updated:** Session 14 (Prompt P — crm_apis fully synced; PR call-auditor → master unblocked)
**Test count:** 317 passing
**Ruff findings:** 0
**Open issues:** TBD (issues created after push)

---

## Root files

| File | Purpose |
|------|---------|
| `manage.py` | Django CLI entry point |
| `settings.py` | Django settings — flat file, python-decouple for env vars, Supabase DB with `baysys_call_audit` schema |
| `settings_test.py` | Test override — SQLite in-memory |
| `urls.py` | Root URL config: `admin/` + `audit/` (includes app urls) |
| `requirements.txt` | Python deps: Django, DRF, django-cors-headers, psycopg2-binary, dj-database-url, requests, python-decouple, openpyxl, pyyaml, newrelic, ruff |
| `.env.example` | Template for environment variables — includes `AUDIT_URL_SECRET` (secret URL prefix for all audit endpoints) |
| `.gitignore` | Standard Python/Node/Django ignores |
| `newrelic.ini.example` | New Relic APM config template (no secrets; committed to git) |
| `CLAUDE.md` | Build rules for Claude Code sessions |
| `README.md` | Architecture overview, API reference, local dev guide |
| `MANIFEST.md` | This file — code repository manifest |
| `BUILD_LOG.md` | Chronological build history |

---

## `baysys_call_audit/` — Django app

### Models (`models.py`)

#### `CallRecording` — Staging/ingestion table
| Field | Type | Purpose |
|-------|------|---------|
| `id` | AutoField PK | — |
| `agent_id` | CharField(50) | CRM agent identifier |
| `agent_name` | CharField(200) | Agent display name |
| `customer_id` | CharField(50, null) | CRM customer identifier |
| `portfolio_id` | CharField(50, null) | Portfolio identifier |
| `supervisor_id` | CharField(50, null) | Supervisor reference |
| `agency_id` | CharField(50, null) | Agency identifier for RBAC |
| `recording_url` | CharField(2000) | Raw S3 object key (no URL scheme); signed at submission time via `crm_adapter.get_signed_url()` |
| `recording_datetime` | DateTimeField | When call was recorded |
| `customer_phone` | CharField(20, null) | Customer phone |
| `product_type` | CharField(50, null) | PL / CC / other |
| `bank_name` | CharField(100, null) | Which bank's portfolio |
| `status` | CharField(20) | pending/submitted/processing/completed/failed/skipped |
| `submission_tier` | CharField(20) | immediate/normal/off_peak — assigned at ingestion |
| `provider_resource_id` | CharField(100, null, unique) | Provider's resource ID |
| `error_message` | TextField(null) | Last error if failed |
| `retry_count` | IntegerField(0) | Submission retries |
| `created_at` | DateTimeField(auto) | Row creation |
| `submitted_at` | DateTimeField(null) | When sent to provider |
| `completed_at` | DateTimeField(null) | When results received |
| `fatal_level` | IntegerField(0) | Computed severity 0-5 from provider boolean scores |

#### `CallTranscript` — Processed transcript + metadata
| Field | Type | Purpose |
|-------|------|---------|
| `id` | AutoField PK | — |
| `recording` | OneToOneField(CallRecording) | Source recording |
| `transcript_text` | TextField | Full transcript |
| `detected_language` | CharField(10, null) | e.g. "en", "hi" |
| `total_call_duration` | IntegerField(null) | Seconds |
| `total_non_speech_duration` | IntegerField(null) | Seconds |
| `customer_talk_duration` | IntegerField(null) | Seconds |
| `agent_talk_duration` | IntegerField(null) | Seconds |
| `customer_sentiment` | CharField(20, null) | From provider |
| `agent_sentiment` | CharField(20, null) | From provider |
| `summary` | TextField(null) | From provider subjective data |
| `next_actionable` | TextField(null) | From provider subjective data |
| `raw_provider_response` | JSONField(null) | Full provider JSON |
| `created_at` | DateTimeField(auto) | — |

#### `ProviderScore` — Provider template-based scores
| Field | Type | Purpose |
|-------|------|---------|
| `id` | AutoField PK | — |
| `recording` | ForeignKey(CallRecording) | Source recording |
| `template_id` | CharField(50) | Provider template ID |
| `template_name` | CharField(200, null) | Human-readable name |
| `audit_compliance_score` | IntegerField(null) | Score achieved |
| `max_compliance_score` | IntegerField(null) | Maximum possible |
| `score_percentage` | DecimalField(5,2, null) | Computed percentage |
| `category_data` | JSONField(null) | category_data array |
| `detected_restricted_keyword` | BooleanField(False) | — |
| `restricted_keywords` | JSONField(default=list) | Detected keywords |
| `raw_score_payload` | JSONField(null) | Full scoring JSON |
| `created_at` | DateTimeField(auto) | — |

#### `ComplianceFlag` — Individual compliance violations
| Field | Type | Purpose |
|-------|------|---------|
| `id` | AutoField PK | — |
| `recording` | ForeignKey(CallRecording) | Source recording |
| `flag_type` | CharField(50) | abusive_language/outside_hours/restricted_keyword/rbi_coc_violation/other |
| `severity` | CharField(20) | critical/high/medium/low |
| `description` | TextField | Human-readable description |
| `evidence` | TextField(null) | Supporting transcript excerpt |
| `auto_detected` | BooleanField(True) | System vs manual |
| `reviewed` | BooleanField(False) | Supervisor reviewed? |
| `reviewed_by` | CharField(50, null) | Reviewer user ID |
| `reviewed_at` | DateTimeField(null) | — |
| `created_at` | DateTimeField(auto) | — |

#### `OwnLLMScore` — Custom LLM scoring (placeholder)
| Field | Type | Purpose |
|-------|------|---------|
| `id` | AutoField PK | — |
| `recording` | ForeignKey(CallRecording) | Source recording |
| `score_template_name` | CharField(100) | Scoring template name |
| `total_score` | IntegerField(null) | Computed total |
| `max_score` | IntegerField(null) | Maximum possible |
| `score_percentage` | DecimalField(5,2, null) | Computed percentage |
| `score_breakdown` | JSONField(null) | Per-item scores |
| `model_used` | CharField(100, null) | Which LLM |
| `created_at` | DateTimeField(auto) | — |

### Other app files

| File | Purpose | Key details |
|------|---------|-------------|
| `apps.py` | AppConfig | name=`baysys_call_audit`, verbose_name=`BaySys Call Audit AI` |
| `admin.py` | Django admin registrations | All 5 models registered with list_display, filters, search |
| `auth.py` | Authentication + RBAC | `MockUser`, `MockCrmAuth`, `get_auth_backend()`, `AuditPermissionMixin` |
| `crm_adapter.py` | CRM mock/prod seam | `get_auth_backend_name()`, `get_user_portfolio()`, `get_team_users()`, `get_user_agency_id()`, `get_agency_list()`, `get_user_names()`, `get_signed_url()` |
| `speech_provider.py` | Provider adapter | `submit_recording()`, `get_results()`, `delete_resource()`, `ask_question()`, `submit_transcript()`, `update_metadata()`, `ProviderError` |
| `compliance.py` | Config-driven compliance engine | `check_metadata_compliance(recording, call_counts_cache=None)` — cache dict enables O(1) max_calls check (sync path); None falls back to DB query (webhook path). `check_provider_compliance()`, `compute_fatal_level()`, `load_compliance_rules()`, `load_fatal_level_rules()`, `load_gazette_holidays()`. All time/date checks use IST via `_IST = ZoneInfo("Asia/Kolkata")`. |
| `ingestion.py` | Shared ingestion logic | `create_recording_from_row(row, existing_urls=None, call_counts_cache=None)` — `existing_urls` set: O(1) dedup; `call_counts_cache` dict: O(1) max_calls check. Both default to None (CSV/webhook paths use DB fallback). `run_sync_for_date()` — pre-fetches existing URLs (one query) and call counts dict (one annotated query) before loop; uses `fetchall()` to drain cursor before ORM writes (pgbouncer transaction-mode safe). `validate_row()`, `parse_datetime_flexible()`, `normalize_column_name()`, `_determine_submission_tier()`, `_load_submission_priority()`. SYNC_QUERY filters on `call_start_time`; duration from `SYNC_MIN_CALL_DURATION` (default 20s). |
| `services.py` | Business logic | `submit_pending_recordings()`, `process_provider_webhook()`, `run_poll_stuck_recordings()`, `run_own_llm_scoring()` (placeholder), `_normalise_provider_payload(raw, resource_id)` (private — ensures resource_insight_id present in poll responses) |
| `serializers.py` | DRF serializers | `CallRecordingListSerializer`, `CallTranscriptSerializer`, `ProviderScoreSerializer`, `ComplianceFlagSerializer`, `OwnLLMScoreSerializer`, `CallDetailSerializer`, `DashboardSummarySerializer` |
| `views.py` | API views | `ProviderWebhookView`, `RecordingListView`, `RecordingDetailView`, `DashboardSummaryView`, `ComplianceFlagListView`, `RecordingImportView`, `SyncCallLogsView`, `SubmitRecordingsView`, `PollStuckRecordingsView`, `RecordingSignedUrlView`, `FlagReviewView`, `RecordingRetryView`, `SystemStatusView` — helpers: `_build_recording_activity`, `_fire_nr_audit_status_event`, `_AUDIT_ENV_VAR_KEYS` |
| `urls.py` | URL patterns | 13 routes under `/audit/<URL_SECRET>/` |

### Management commands (`management/commands/`)

| File | Purpose |
|------|---------|
| `sync_call_logs.py` | Daily sync from `uvarcl_live.call_logs` + `users` JOIN -> `CallRecording`. Args: `--date`, `--batch-size`, `--dry-run` |
| `import_recordings.py` | CSV/Excel upload -> `CallRecording`. Args: `file_path`, `--sheet`, `--dry-run` |
| `update_fatal_level_hash.py` | Compute and update `content_hash` in `config/fatal_level_rules.yaml` |
| `submit_recordings.py` | Submit pending recordings to provider. Args: `--tier`, `--batch-size`, `--dry-run` |
| `poll_stuck_recordings.py` | Poll provider for results on recordings stuck in `status=submitted` past `POLL_STUCK_AFTER_MINUTES` (default 30). Args: `--batch-size`, `--dry-run` |

### Tests (`tests/`)

| File | Tests | Coverage |
|------|-------|----------|
| `test_models.py` | 21 | All 5 models: CRUD, constraints, str, compute_percentage |
| `test_speech_provider.py` | 10 | All 6 provider functions: success + error paths |
| `test_webhook.py` | 12 | Webhook receiver: success, idempotency, compliance flags, edge cases |
| `test_services.py` | 11 | Submission pipeline, webhook processing, LLM scoring placeholder |
| `test_views.py` | 28 | All API views: list, detail, dashboard, compliance flags, pagination, filters, signed-url, flag review, retry |
| `test_crm_adapter.py` | 10 | All 7 adapter functions in mock mode |
| `test_ingestion.py` | 47 | Shared ingestion: validate_row, parse_datetime, normalize_column, create_recording_from_row, existing_urls fast-path dedup, call_counts_cache, SYNC_QUERY param count |
| `test_sync_call_logs.py` | 18 | sync_call_logs command: mapping, date args, dedup, dry-run, batch-size, pre-fetch dedup, intra-batch dedup, min_duration param |
| `test_import_recordings.py` | 18 | import_recordings command + DRF import endpoint: CSV parsing, dedup, RBAC, dry-run, errors |
| `test_compliance.py` | 48 | Compliance engine: all metadata + provider rules, config loading, holidays, unknown types, max_calls default 15, call_counts_cache paths |
| `test_fatal_level.py` | 14 | Fatal level computation, content hash, update_fatal_level_hash command |
| `test_sync_api.py` | 9 | Sync API endpoint: RBAC, date parsing, dry-run, response format |
| `test_submission_tiers.py` | 35 | Tier matching, tier assignment at creation, submit tier filter, S3 re-signing, submit_recordings command |
| `test_poll_stuck_recordings.py` | 9 | poll_stuck_recordings command: query selection, threshold, recovery, errors, dry-run, batch-size |
| `test_newrelic_instrumentation.py` | 8 | `@background_task` decorators verified; NR API callable as no-op without agent |
| `test_submit_api.py` | 11 | SubmitRecordingsView + PollStuckRecordingsView: RBAC, 403 for unauthenticated, 500 on exception, dry_run passthrough, batch_size passthrough |
| `test_system_status.py` | 8 | SystemStatusView: token auth (correct/missing/wrong/unset), top-level keys, recording_activity DB query, env_vars dict of booleans, migrations block |
| **Total** | **317** | — |

---

## `baysys_call_audit_ui/` — React scaffold

| File | Purpose |
|------|---------|
| `package.json` | React 18 + Vite + TypeScript + Tailwind |
| `vite.config.ts` | Dev server on :5173, proxy `/audit` to Django |
| `tsconfig.json` | Strict TypeScript config |
| `tailwind.config.js` | Tailwind with src content paths |
| `index.html` | SPA entry point |
| `src/main.tsx` | React root mount |
| `src/App.tsx` | Router: `/audit` -> Dashboard, `/audit/call/:id` -> CallDetail |
| `src/types/audit.ts` | TypeScript interfaces for all API types |
| `src/utils/Request.tsx` | HTTP helper with auth headers |
| `src/utils/Api.tsx` | Typed API client (recordings, dashboard, flags) |
| `src/mock/AuthContext.ts` | Auth context definition |
| `src/mock/MockAuthContext.tsx` | Mock auth provider (user_id=1, role_id=2) |
| `src/mock/useAuth.ts` | Auth hook |
| `src/pages/audit/DashboardPage.tsx` | Dashboard scaffold (full build in Prompt B) |
| `src/pages/audit/CallDetailPage.tsx` | Call detail scaffold (full build in Prompt B) |
| `src/pages/audit/components/ScoreCard.tsx` | Score card component scaffold |
| `src/pages/audit/components/ComplianceFlags.tsx` | Compliance flags display scaffold |
| `src/pages/audit/components/AgentTable.tsx` | Agent comparison table scaffold |
| `src/pages/audit/components/TrendChart.tsx` | Trend chart scaffold (charting lib TBD) |

---

## `config/`

| File | Purpose |
|------|---------|
| `compliance_rules.yaml` | Metadata + provider compliance rules (YAML config) |
| `fatal_level_rules.yaml` | Fatal level parameter weights + content hash |
| `gazette_holidays_2026.txt` | India gazette holidays for 2026 |
| `submission_priority.yaml` | Tier assignment rules: agency_ids, bank_names, product_types per tier |

## `docs/`

| File | Purpose |
|------|---------|
| `OPERATIONS.md` | Ops guide: local setup, pipeline runs, troubleshooting, New Relic APM |
| `SCORECARD.md` | Canonical scoring rubric (19 params, 7 FATALs) |
| `new-relic-telemetry-plan.md` | New Relic phased implementation plan (4 phases) |
| `prompts/prompt-H-new-relic.md` | Claude Code prompt spec for New Relic instrumentation (Prompt H executed — complete) |
| `speech-provider/api-reference.md` | Current provider (GreyLabs) API documentation |
| `testing/test-guide.md` | Test execution guide |

---

## GitHub Issue Map

| # | Title | Status |
|---|-------|--------|
| TBD | Prompt A: Project scaffold | To be created after push |
