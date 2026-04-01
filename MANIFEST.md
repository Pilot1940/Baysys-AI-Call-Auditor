# BaySys Call Audit AI — Code Repository Manifest

**Repo:** `Pilot1940/Baysys-AI-Call-Auditor`
**Last updated:** Session 1 (Prompt A)
**Test count:** 72 passing
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
| `requirements.txt` | Python deps: Django, DRF, psycopg2-binary, requests, python-decouple, ruff |
| `.env.example` | Template for environment variables |
| `.gitignore` | Standard Python/Node/Django ignores |
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
| `recording_url` | URLField(2000) | Signed S3 URL to MP3 |
| `recording_datetime` | DateTimeField | When call was recorded |
| `customer_phone` | CharField(20, null) | Customer phone |
| `product_type` | CharField(50, null) | PL / CC / other |
| `bank_name` | CharField(100, null) | Which bank's portfolio |
| `status` | CharField(20) | pending/submitted/processing/completed/failed/skipped |
| `provider_resource_id` | CharField(100, null, unique) | Provider's resource ID |
| `error_message` | TextField(null) | Last error if failed |
| `retry_count` | IntegerField(0) | Submission retries |
| `created_at` | DateTimeField(auto) | Row creation |
| `submitted_at` | DateTimeField(null) | When sent to provider |
| `completed_at` | DateTimeField(null) | When results received |

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
| `crm_adapter.py` | CRM mock/prod seam | `get_auth_backend_name()`, `get_user_portfolio()`, `get_team_users()`, `get_user_agency_id()`, `get_agency_list()`, `get_user_names()` |
| `speech_provider.py` | Provider adapter | `submit_recording()`, `get_results()`, `delete_resource()`, `ask_question()`, `submit_transcript()`, `update_metadata()`, `ProviderError` |
| `services.py` | Business logic | `submit_pending_recordings()`, `process_provider_webhook()`, `check_compliance()`, `run_own_llm_scoring()` (placeholder) |
| `serializers.py` | DRF serializers | `CallRecordingListSerializer`, `CallTranscriptSerializer`, `ProviderScoreSerializer`, `ComplianceFlagSerializer`, `OwnLLMScoreSerializer`, `CallDetailSerializer`, `DashboardSummarySerializer` |
| `views.py` | API views | `ProviderWebhookView`, `RecordingListView`, `RecordingDetailView`, `DashboardSummaryView`, `ComplianceFlagListView` |
| `urls.py` | URL patterns | 5 routes under `/audit/` |

### Tests (`tests/`)

| File | Tests | Coverage |
|------|-------|----------|
| `test_models.py` | 18 | All 5 models: CRUD, constraints, str, compute_percentage |
| `test_speech_provider.py` | 12 | All 6 provider functions: success + error paths |
| `test_webhook.py` | 8 | Webhook receiver: success, idempotency, compliance flags, edge cases |
| `test_services.py` | 13 | Ingestion, webhook processing, compliance checks, LLM scoring placeholder |
| `test_views.py` | 14 | All API views: list, detail, dashboard, compliance flags, pagination, filters |
| `test_crm_adapter.py` | 7 | All 6 adapter functions in mock mode |
| **Total** | **72** | — |

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

## `docs/`

| File | Purpose |
|------|---------|
| `OPERATIONS.md` | Ops guide: local setup, pipeline runs, troubleshooting |
| `speech-provider/api-reference.md` | Current provider (GreyLabs) API documentation |
| `testing/test-guide.md` | Test execution guide |

---

## GitHub Issue Map

| # | Title | Status |
|---|-------|--------|
| TBD | Prompt A: Project scaffold | To be created after push |
