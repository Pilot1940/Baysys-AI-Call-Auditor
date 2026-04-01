# BaySys Call Audit AI — Build Log

**Project:** BaySys Call Audit AI
**Repo:** `Pilot1940/Baysys-AI-Call-Auditor`
**Build start:** 2026-04-01
**Last updated:** 2026-04-01 (Session 1)
**Build method:** Claude Code (Opus 4.6)

---

## Prompt Build Order

| Prompt | Scope | Session date | Issues closed |
|--------|-------|-------------|---------------|
| A | Full scaffold: Django + React + models + tests | 2026-04-01 | — |
| B | React analytics dashboard — full build | TBD | — |
| C | End-to-end testing — integration + load | TBD | — |

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
