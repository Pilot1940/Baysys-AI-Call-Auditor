# BaySys Call Audit AI — Project Instructions

> Read this before doing anything in this folder. These instructions apply to all Claude Code sessions.

---

## What this project is

A standalone Django app (`baysys_call_audit`) that adds AI-powered call monitoring and scoring to UVARCL's debt-collection operation. It processes recorded MP3 calls (agent-customer), transcribes them via a Speech Analytics Provider (currently GreyLabs, swappable), scores them against configurable templates, and flags RBI Code of Conduct compliance violations. Architecturally modelled on the sister project **BaySys Voice Trainer** (`../baysys_trainer_dev/`).

**Owner:** PC (Parikshit Chitalkar) · **GitHub:** `Pilot1940/Baysys-AI-Call-Auditor`

---

## Folder layout

```
Baysys-AI-Call-Auditor/           <- git root
├── manage.py
├── settings.py                   <- flat, no config/ subfolder
├── settings_test.py              <- in-memory SQLite for tests
├── urls.py
├── requirements.txt
├── .env.example
├── CLAUDE.md                     <- this file
├── README.md                     <- architecture overview
├── MANIFEST.md                   <- file-level API reference
├── BUILD_LOG.md                  <- chronological build history
│
├── baysys_call_audit/            <- Django app
│   ├── models.py                 <- 5 models
│   ├── auth.py                   <- MockUser, MockCrmAuth, RBAC
│   ├── crm_adapter.py            <- mock/prod seam (ONLY file with CRM logic)
│   ├── speech_provider.py        <- provider adapter (ONLY file with provider-specific code)
│   ├── services.py               <- ingestion pipeline, scoring, compliance
│   ├── views.py                  <- webhook receiver + API views
│   ├── serializers.py            <- DRF serializers
│   ├── urls.py                   <- app URL patterns
│   └── tests/                    <- test suite
│
├── baysys_call_audit_ui/         <- React + Vite + TypeScript + Tailwind
│
└── docs/
    ├── OPERATIONS.md             <- ops guide
    ├── speech-provider/          <- provider API docs
    └── testing/                  <- test guide
```

---

## Non-negotiable rules

### 1. `speech_provider.py` is the ONLY file with provider-specific code
All interaction with the speech analytics provider goes through `speech_provider.py`. No other file should reference GreyLabs endpoints, headers, or payload structure. Model field names are provider-agnostic (`provider_resource_id`, not `greylabs_id`).

### 2. `crm_adapter.py` is the single mock/prod seam
Same pattern as Trainer. `AUDIT_AUTH_BACKEND=mock` in dev, `=crm` in prod. All CRM imports inside function bodies only with `# noqa: PLC0415`.

### 3. Test gate: 249 tests passing, 0 ruff findings
Before any commit or review:
```bash
python manage.py test --settings=settings_test -v 0   # must pass
ruff check baysys_call_audit/                          # must be 0 findings
```

### 4. No hardcoded thresholds
Compliance rules (8am-8pm window, score thresholds) come from settings or env vars. Never hardcode.

### 5. Provider API keys via env vars only
`SPEECH_PROVIDER_API_KEY`, `SPEECH_PROVIDER_API_SECRET`, `SPEECH_PROVIDER_TEMPLATE_ID`, `SPEECH_PROVIDER_HOST`. No provider name in env var keys.

### 6. Field names are fixed once migration 0001 lands
Webhook handler and all serializers depend on exact field names. No provider-specific names in models.

### 7. Separate tables, same DB
Audit tables and Trainer tables coexist in the same Supabase instance (different schemas) but share no foreign keys. Comparison happens at dashboard/reporting layer.

### 8. Code reviews use the `pc-code-review` skill
All reviews — however casually phrased.

### 9. Auth role IDs match the Trainer
1=Admin, 2=Manager/TL, 3=Agent, 4=Supervisor, 5=Agency Admin. Same RBAC scoping rules.

### 10. Documentation freshness is mandatory
Every session that modifies code MUST update MANIFEST.md, BUILD_LOG.md, and docs/OPERATIONS.md. A code change without a doc update is incomplete.

---

## Current state (as of 2026-04-01)

- **249 tests passing, 0 ruff findings**
- 5 Django models: CallRecording, CallTranscript, ProviderScore, ComplianceFlag, OwnLLMScore
- Migrations 0001–0004 applied
- **Dev Supabase fully configured:** `uvarcl_live.call_logs` (500K rows), `uvarcl_live.users` (662 rows, anonymised), `baysys_call_audit.*` all 5 tables created. Sync can be run end-to-end against Supabase with no RDS connection needed.
- speech_provider.py implements GreyLabs (6 public functions)
- Webhook receiver live at `/audit/webhook/provider/`
- Ingestion service: `submit_pending_recordings()`, `process_provider_webhook()`, `run_own_llm_scoring()` (placeholder)
- **Ingestion pipeline live:** `sync_call_logs` command (daily sync from `uvarcl_live.call_logs` + `users` JOIN), `import_recordings` command (CSV/Excel upload), DRF import endpoint at `/audit/recordings/import/`
- Shared ingestion logic in `ingestion.py`: dedup on `recording_url`, flexible datetime parsing, column name normalization
- **Config-driven compliance engine** in `compliance.py`: 4 metadata rules + 3 provider rules from `config/compliance_rules.yaml`
- **Fatal level system**: weighted boolean scoring from `config/fatal_level_rules.yaml`, stored on `CallRecording.fatal_level` (0-5)
- **Sync API endpoint** at `/audit/recordings/sync/` (Admin/Supervisor only) — failsafe trigger for daily sync
- **S3 URL re-signing**: `crm_adapter.get_signed_url()` called immediately before each provider submission (never stored)
- **Submission tier system**: `submission_tier` field (immediate/normal/off_peak) assigned at ingestion via `config/submission_priority.yaml`; `submit_recordings` command with `--tier`, `--batch-size`, `--dry-run`
- **`recording_url` is CharField**: raw S3 object key, no URL scheme. Signed at submission time via `crm_adapter.get_signed_url()`
- **IST compliance**: all metadata rule time/date checks convert UTC → IST (`_IST = ZoneInfo("Asia/Kolkata")`) before comparison
- **SYNC_QUERY uses `call_start_time`**: actual call start (not `created_at` insert timestamp)
- React scaffold (Vite + TS + Tailwind) with pages, types, API client, mock auth
- AUDIT_AUTH_BACKEND=mock for dev, =crm for production

---

## Key architecture reference

| Topic | Where to look |
|-------|---------------|
| Full architecture | `README.md` |
| Every file's API | `MANIFEST.md` |
| Build history | `BUILD_LOG.md` |
| Ops guide | `docs/OPERATIONS.md` |
| Provider API docs | `docs/speech-provider/api-reference.md` |
| Test guide | `docs/testing/test-guide.md` |

---

## Build history summary

| Prompt | What was built |
|--------|---------------|
| A | Full scaffold: 5 models, auth, crm_adapter, speech_provider, webhook, ingestion, serializers, views, React scaffold, 72 tests, docs |
| B | Ingestion pipeline: sync_call_logs command, import_recordings command, DRF import endpoint, 63 new tests |
| C | Sync API endpoint, config-driven compliance engine (YAML), fatal level weighted scoring, 51 new tests |
| D | S3 URL re-signing (get_signed_url in crm_adapter), submission_tier field + migration, config/submission_priority.yaml, submit_recordings command, 38 new tests |
| E | recording_url URLField→CharField, validate_row URL check removed, SYNC_QUERY→call_start_time, IST compliance conversion, migration 0004, 17 new tests |
| B | Ingestion pipeline: sync_call_logs + import_recordings + DRF endpoint, 63 new tests (72→135) |
| C | Sync API + RBI COC compliance engine + fatal level, 51 new tests (135→186) |

Full details in `BUILD_LOG.md`.
