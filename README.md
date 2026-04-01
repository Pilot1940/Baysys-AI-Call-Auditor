# BaySys AI Call Auditor

AI-powered call monitoring and compliance system for Baysys.ai's debt collection process (on behalf of UVARCL). Processes recorded MP3 calls, transcribes via a Speech Analytics Provider (currently GreyLabs, swappable), scores against configurable templates, and flags RBI Code of Conduct compliance violations.

## Architecture

```
uvarcl_live.call_logs
  → CallRecording (staging, ~18K/day + 5K backfill)
    → speech_provider.py (submit signed S3 URL)
      → Provider (async transcription + scoring)
        → Webhook callback
          → CallTranscript + ProviderScore + ComplianceFlag
            → Dashboard (React + Vite + TypeScript + Tailwind)
```

### Call flow

1. **Ingestion:** `sync_call_logs` reads `uvarcl_live.call_logs` daily, JOINs `users` for agent metadata, creates `CallRecording` rows (`status=pending`). Filter: `recording_s3_path IS NOT NULL AND call_duration > 20`. Also supports CSV/Excel upload for backfill and an HTTP endpoint for on-demand sync.

2. **Tier assignment:** Each recording is tagged `immediate`, `normal`, or `off_peak` at ingestion based on `config/submission_priority.yaml` (agency, bank, product type). Separate cron schedules per tier.

3. **Submission:** `submit_pending_recordings()` batch-submits pending recordings to the provider at up to 200 requests/min. Raw S3 object keys are signed immediately before each API call via `crm_adapter.get_signed_url()` — never stored.

4. **Processing:** Provider transcribes audio asynchronously. Results arrive via webhook at `/audit/webhook/provider/`. Recovery polling (`poll_stuck_recordings`) catches any missed webhooks every 30 minutes.

5. **Scoring:** Provider template scoring (configurable via `SPEECH_PROVIDER_TEMPLATE_ID`). Own LLM scoring placeholder (`OwnLLMScore` table) for future use.

6. **Compliance:** `check_metadata_compliance()` runs at ingestion time using call metadata only. `check_provider_compliance()` runs at webhook time using transcript and scores. All time/date checks use IST (Asia/Kolkata). Rules are config-driven via `config/compliance_rules.yaml`.

7. **Fatal level:** Provider boolean parameters mapped to a weighted severity score (0–5) via `config/fatal_level_rules.yaml`. Versioned with SHA-256 hash for audit integrity.

8. **Dashboard:** React app with role-based views — agent sees own calls, TL sees agency, Admin sees all.

### Data model (5 tables)

| Table | Purpose | Key fields |
|-------|---------|------------|
| `CallRecording` | Staging + ingestion | agent_id, recording_url, status, submission_tier, fatal_level, provider_resource_id |
| `CallTranscript` | Transcript + metadata | transcript_text, durations, sentiments, raw_provider_response |
| `ProviderScore` | Template-based scores | template_id, audit_compliance_score, category_data |
| `ComplianceFlag` | Compliance violations | flag_type, severity, evidence, reviewed |
| `OwnLLMScore` | Custom LLM scoring (future) | score_template_name, score_breakdown |

### Provider abstraction

All speech analytics provider interaction goes through `speech_provider.py`. Currently implements GreyLabs. No other file contains provider-specific code. To swap providers, only `speech_provider.py` changes. System is named "BaySys AI Call Auditor", not after any provider.

### Config-driven compliance

| Rule | Trigger | Config |
|------|---------|--------|
| M1 call_window | Call outside 8am–8pm IST | `compliance_rules.yaml` |
| M2 blocked_weekday | Call on Sunday | `compliance_rules.yaml` |
| M3 gazette_holiday | Call on gazette holiday | `gazette_holidays_2026.txt` |
| M4 max_calls_per_customer | >15 calls to same customer per day | `compliance_rules.yaml` |
| P1 fatal_level_threshold | Fatal level ≥ threshold | `compliance_rules.yaml` |
| P2 provider_score_threshold | Compliance score below threshold | `compliance_rules.yaml` |
| P3 provider_transcript_field | Negative customer sentiment | `compliance_rules.yaml` |

Enable/disable any rule or change thresholds in YAML — no code changes needed.

### RBAC

Same role IDs as Voice Trainer: 1=Admin, 2=Manager/TL, 3=Agent, 4=Supervisor, 5=Agency Admin. Agents see own calls. TLs see their agency. Admins and Supervisors see all.

## API endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/audit/webhook/provider/` | None | Provider callback receiver |
| POST | `/audit/recordings/sync/` | Admin/Supervisor | On-demand sync (failsafe) |
| POST | `/audit/recordings/import/` | Admin/Manager | CSV/Excel upload |
| GET | `/audit/recordings/` | Yes | Paginated recording list |
| GET | `/audit/recordings/<id>/` | Yes | Recording detail with transcript, scores, flags |
| GET | `/audit/dashboard/summary/` | Yes | Aggregate dashboard stats |
| GET | `/audit/compliance-flags/` | Yes | Compliance flag list |

## Management commands

```bash
python manage.py sync_call_logs              # daily sync from call_logs (default: yesterday)
python manage.py sync_call_logs --date 2026-03-31 --dry-run
python manage.py import_recordings file.csv  # CSV/Excel backfill
python manage.py submit_recordings --tier immediate
python manage.py poll_stuck_recordings       # recover missed webhooks
python manage.py update_fatal_level_hash     # after editing fatal_level_rules.yaml
```

## Local development

```bash
cd Baysys-AI-Call-Auditor/
cp .env.example .env
# Fill in: DATABASE_URL, SPEECH_PROVIDER_API_KEY, SPEECH_PROVIDER_API_SECRET, etc.
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate --settings=settings
python manage.py runserver

# React UI (separate terminal)
cd baysys_call_audit_ui/
npm install
npm run dev  # http://localhost:5173
```

See `docs/OPERATIONS.md` for the full ops guide including cron setup, env var reference, and troubleshooting.

## Tests

```bash
python manage.py test --settings=settings_test -v 0   # 249 tests, all passing
ruff check baysys_call_audit/                          # 0 findings
```

## Tech stack

- **Backend:** Django 5.0, Django REST Framework, PostgreSQL (Supabase)
- **Frontend:** React 18, Vite, TypeScript, Tailwind CSS
- **Provider:** GreyLabs Speech Analytics API (swappable via `speech_provider.py`)
- **Linter:** ruff
