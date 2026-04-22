# BaySys Call Audit AI — Code Repository Manifest

**Repo:** `Pilot1940/Baysys-AI-Call-Auditor`
**Last updated:** Session 30 (2026-04-22 — collapsible agency accordion, default collapsed; crm PR #77 open)
**Test count:** 320 passing (standalone) · backend unchanged in this session
**Ruff findings:** 0 (standalone) / 58 (crm_apis — auto-fixable)
**Open issues:** TBD (issues created after push)
**Production UI lives in:** `bsfg-finance/crm` repo, branch `call-audit-frontend-embed`. The `baysys_call_audit_ui/` scaffold in this repo is reference-only.

---

## Root files

| File | Purpose |
|------|---------|
| `manage.py` | Django CLI entry point |
| `settings.py` | Django settings — flat file, python-decouple for env vars, Supabase DB with `baysys_call_audit` schema. `TIME_ZONE = "Asia/Kolkata"`, `USE_TZ = True` (added 2026-04-08 — were absent, causing Django to default to America/Chicago for naive datetime handling). |
| `settings_test.py` | Test override — SQLite in-memory |
| `urls.py` | Root URL config: `admin/` + `audit/` (includes app urls) |
| `requirements.txt` | Python deps: Django, DRF, django-cors-headers, psycopg2-binary, dj-database-url, requests, python-decouple, openpyxl, pyyaml, newrelic, ruff |
| `.env.example` | Template for environment variables — includes `AUDIT_URL_SECRET`, `AUDIT_STATUS_SECRET`, batch size settings (`SYNC_BATCH_SIZE`, `SUBMIT_BATCH_SIZE`, `POLL_BATCH_SIZE`), OwnLLM settings (`OWN_LLM_ENABLED`, `OWN_LLM_API_KEY`, `OWN_LLM_MODEL`, `OWN_LLM_SCORING_TEMPLATE`), New Relic, GreyLabs webhook IP allowlist |
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
| `default_prompt_response` | TextField(null) | LLM-generated call narrative + audit report from GreyLabs (migration 0005) |
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
| `category_data` | JSONField(null) | category_data array from insights |
| `audit_template_parameters` | JSONField(null) | Per-parameter scores: answer, score, max_score, is_fatal_score, justification (migration 0005) |
| `function_calling_parameters` | JSONField(null) | Binary feature detection: greeting, closing, dead air, hold time, rate of speech (migration 0005) |
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

#### `OwnLLMScore` — Custom LLM scoring (schema ready; implementation in Prompt Q)
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
| `speech_provider.py` | Provider adapter | `submit_recording()`, `get_results()`, `delete_resource()`, `ask_question()`, `submit_transcript()`, `update_metadata()`, `ProviderError`. Session 25: `data=` → `json=` payload fix, `details[0]` unwrap from GreyLabs response, `customer_id` in submit payload. |
| `compliance.py` | Config-driven compliance engine | `check_metadata_compliance(recording, call_counts_cache=None)` — cache dict enables O(1) max_calls check (sync path); None falls back to DB query (webhook path). `check_provider_compliance()`, `compute_fatal_level()`, `load_compliance_rules()`, `load_fatal_level_rules()`, `load_gazette_holidays()`, `_sync_content_hash()` (standalone only — auto-updates YAML content hash with warning). All time/date checks use IST via `_IST = ZoneInfo("Asia/Kolkata")`. `lru_cache` on YAML loaders — requires restart to pick up config changes. |
| `ingestion.py` | Shared ingestion logic | `create_recording_from_row(row, existing_urls=None, call_counts_cache=None)` — `existing_urls` set: O(1) dedup; `call_counts_cache` dict: O(1) max_calls check. Both default to None (CSV/webhook paths use DB fallback). `run_sync_for_date()` — pre-fetches existing URLs (one query) and call counts dict (one annotated query) before loop; uses `fetchall()` to drain cursor before ORM writes (pgbouncer transaction-mode safe); `bulk_create()` for batch inserts (was N individual ORM creates). `validate_row()`, `parse_datetime_flexible()`, `normalize_column_name()`, `_determine_submission_tier()`, `_load_submission_priority()`. SYNC_QUERY filters on `call_start_time`; duration from `SYNC_MIN_CALL_DURATION` (default 20s). Session 25: IST timezone fix in `run_sync_for_date()`. Session 25 cont.: IST fix also applied to `create_recording_from_row()` — `make_aware()` now explicitly uses `ZoneInfo("Asia/Kolkata")` on both code paths. |
| `services.py` | Business logic | `submit_pending_recordings()`, `process_provider_webhook()`, `run_poll_stuck_recordings()`, `run_own_llm_scoring()` (placeholder — Prompt Q designed), `_normalise_provider_payload(raw, resource_id)` (private), `_create_provider_score()` (private), `_create_transcript()` (private). Session 25: fixed `add_custom_attributes` dict→tuple, batch_size from settings, defensive webhook JSON parse, `details[0]` unwrap, `customer_id` E009 fix. Session 25 cont.: webhook now treated as completion signal — calls `get_results()` after resource_id lookup to fetch full GET Insights response; `poll_stuck_recordings` fixed to unwrap `details[0]` before checking transcript/progress; `_create_provider_score` and `_create_transcript` read 3 new fields. |
| `serializers.py` | DRF serializers | `CallRecordingListSerializer`, `CallTranscriptSerializer`, `ProviderScoreSerializer`, `ComplianceFlagSerializer`, `OwnLLMScoreSerializer`, `CallDetailSerializer`, `DashboardSummarySerializer` |
| `views.py` | API views | `ProviderWebhookView`, `RecordingListView`, `RecordingDetailView`, `DashboardSummaryView`, `ComplianceFlagListView`, `RecordingImportView`, `SyncCallLogsView`, `SubmitRecordingsView`, `PollStuckRecordingsView`, `RecordingSignedUrlView`, `FlagReviewView`, `RecordingRetryView`, `SystemStatusView` — helpers: `_build_recording_activity`, `_fire_nr_audit_status_event`, `_AUDIT_ENV_VAR_KEYS`. Session 25: defensive JSON parse for non-JSON webhook Content-Type, batch_size from Django settings (`SYNC_BATCH_SIZE`, `SUBMIT_BATCH_SIZE`, `POLL_BATCH_SIZE`). |
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

## Production UI — `bsfg-finance/crm` repo · branch `call-audit-frontend-embed`

Ported in Session 14 (Prompt N), redesigned in Session 26 (Collexa wine theme), iterated in Session 27 (Trainer Action Board primitives + CallDrawer flyout), and Session 28 (agency grouping + Active Only toggle + inline ID pill).
Files live under `crm/src/pages/audit/` and `crm/src/types/audit.ts`.

| File (in crm repo) | Purpose |
|---|---|
| `src/pages/audit/AuditDashboardPage.tsx` | Top-level dashboard. Fetches `DashboardSummary`, derives KPIs + agency options, applies `Privilege.callAudit.edit()` gate, renders `AuditShell` with tab content. |
| `src/pages/audit/AuditCallDetailPage.tsx` | Legacy full-page 2-column detail view (kept for deep linking). Session 27 added `CallDrawer` flyout that is now the default open-path from RecordingsTab. |
| `src/pages/audit/components/AuditShell.tsx` | Page chrome: wine header, agency+period filter bar, tab strip. Props: `activeTab`, `agency`, `agencies`, `period`, `showOpsTab`. |
| `src/pages/audit/components/primitives.tsx` | Session 26 set: `KpiCard` (wine/amber/red/slate accents), `StatusPill`, `FatalBadge`, `ScoreCell`, `FilterChip`. **Session 27 added** Trainer Action Board vocabulary: `BandStatusPill`, `LevelBadge`, `ScoreBar`, `TrendArrow`. |
| `src/pages/audit/components/RecordingsTab.tsx` | Exception triage. Session 27: compact filter row lives inside column headers — status, agent_id, customer_id, date range, FATAL ≥3, critical, unreviewed, score <50%. View column removed; whole row clickable. **Session 28:** rows grouped by `agency_id` with subtle `bg-slate-50` header row; inline agent-ID pill (single-line Agent cell with small slate ID pill). **Session 30:** agency header is now a collapsible accordion row (chevron, `role=button`, keyboard toggle) — all collapsed by default; "Expand all / Collapse all" text button next to Score <50%. |
| `src/pages/audit/components/AgentsTab.tsx` | Sortable table (agent / calls / avg_score / fatals). Session 27 adopts Trainer primitives (BandStatusPill, LevelBadge, ScoreBar, TrendArrow) and denser layout. Opens `AgentDrawer` on row click. **Session 28:** # column dropped; "Active Only" wine pill in the header (default ON, `calls > 0` heuristic — no `is_active` field exists); "N active · M total" counter; rows grouped by `agency_id` (alphabetical, "Unassigned" last) with in-group sort preserved; inline agent-ID pill. **Session 30:** agency header is now a collapsible accordion row (chevron, `role=button`, keyboard toggle) — all collapsed by default; "Expand all / Collapse all" text button next to Active Only. |
| `src/pages/audit/components/AgentDrawer.tsx` | Slide-in panel with Overview + Call History tabs. Session 27 adopts the same Trainer primitive set. `role="dialog"`, ESC-to-close, `aria-modal`. |
| `src/pages/audit/components/CallDrawer.tsx` | **Session 27** — right-side call-detail flyout that replaces the full-page route as the default open-path from RecordingsTab. Mounted from `App.tsx`. Consumes the shared fragments in `callDetailParts.tsx`. `role="dialog"`, ESC-to-close, `aria-modal`. |
| `src/pages/audit/components/callDetailParts.tsx` | **Session 27** — shared detail sub-components (score hero, transcript with flag-evidence highlighting, flag review, metadata) consumed by both `CallDrawer` and the legacy `AuditCallDetailPage`. |
| `src/pages/audit/components/OpsTab.tsx` | Pipeline status + dry-run toggle + sync/submit/poll action cards. Session 27 uses a 2×2 tile grid. `canWrite` prop disables buttons. |
| `src/pages/audit/components/ScoreTrendChart.tsx` | Recharts LineChart with 85/70/55 band reference lines. Currently referenced for future per-call-score backend endpoint (not rendered in Session 26 — see H-1). |
| `src/types/audit.ts` | TypeScript interfaces + helpers (`scoreBand`, `scoreBandLabel`, `formatDuration`, `formatDateTime`). |
| `src/utils/auditAxios.ts` | Axios instance (baseURL = `${apiBase}/audit/${AUDIT_URL_SECRET}`, cookie + Bearer auth, 60s timeout). |
| `src/utils/auditApi.ts` | `AUDIT_API` endpoint constants. |
| `src/utils/PrivilegeList.tsx` | `Privilege.callAudit.edit()` returns true for level ≥ 3 (Manager/TL, Admin). Driver of Ops tab visibility. |

**Brand palette** (from `tailwind.config.js` in crm): `brand.wine = #7d0552`, `brand.wine-dark = #5c0339`, `brand.wine-light = #f8f0f5`. Tailwind `preflight` is disabled to coexist with Bootstrap reset.

---

## `baysys_call_audit_ui/` — React scaffold (reference only; not deployed)

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
| `prompts/prompt-Q-own-llm-scoring.md` | Claude Code prompt spec for OwnLLM scoring backend (pending execution) |
| `prompts/prompt-R-own-llm-score-ui.md` | Claude Code prompt spec for OwnLLM score UI swap (pending, depends on Q) |
| `speech-provider/api-reference.md` | Current provider (GreyLabs) API documentation |
| `testing/test-guide.md` | Test execution guide |

---

## GitHub Issue Map

| # | Title | Status |
|---|-------|--------|
| TBD | Prompt A: Project scaffold | To be created after push |

---

## Code Reviews (NOT in git — in parent `BaySys-Voice/Documentation/Code-Reviews/` or `BaySysAI/DOCUMENTATION/Code-Reviews/`)

| File | Purpose |
|------|---------|
| `code-review-crm-call-audit-ui-redesign-2026-04-19.md` | Session 26 — UI redesign in crm repo: 0 CRITICAL, 2 HIGH, 5 MEDIUM, 4 MINOR (all HIGH + MEDIUM fixes applied in commit `1309a75`) |
| `code-review-call-auditor-session25-2026-04-07.md` | Session 25 deep review: 0 CRITICAL, 8 HIGH, 9 MEDIUM, 4 MINOR |
| `code-review-call-auditor-deep-scan-2026-04-07.md` | Session 25 early scan |
| `code-review-call-auditor-2026-04-07.md` | Session 14 review |

---

## Session 25 — Known Issues (pending fixes)

| ID | Severity | Summary | Fix location |
|----|----------|---------|-------------|
| H-1 | HIGH | Duplicate `ProviderScore` on webhook retry — needs `update_or_create` | `services.py:_create_provider_score()` |
| H-2 | HIGH | Duplicate `ComplianceFlag` on retry — needs unique constraint + `get_or_create` | `compliance.py` + migration |
| H-3 | HIGH | `process_provider_webhook()` not wrapped in `transaction.atomic()` | `services.py` |
| H-4 | HIGH | `_create_provider_score()` reads `category_data` from `insights` (empty) — should read root | `services.py` (fix in Prompt Q) |
| H-5 | HIGH | crm_apis `compliance.py` missing `_sync_content_hash()` | crm_apis mirror after Prompt Q |
| H-6 | HIGH | crm_apis has 58 ruff errors from file mirror | `ruff check --fix` on crm_apis |
| H-7 | HIGH | Timezone inconsistency: sync path explicit IST vs import path defaulting to UTC | `ingestion.py` |
| H-8 | HIGH | `RecordingListView` does not honour `customer_id`, `fatal_level_gte`, `score_lt`, `has_critical_flags`, `has_unreviewed_flags` query params sent by the Session 27 UI filters (chips render but filter nothing server-side). Fix needed in both standalone `baysys_call_audit/views.py` and crm_apis `arc/baysys_call_audit/views.py`; separate task spawned 2026-04-21. | `views.py` + serializer + tests |
| M-1 | MEDIUM | Batch size user input not validated in views | `views.py` |
| M-2 | MEDIUM | `fetchall()` defeats batch_size memory protection | `ingestion.py` |
