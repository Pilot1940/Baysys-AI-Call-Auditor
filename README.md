# BaySys Call Audit AI

AI-powered call monitoring and scoring system for UVARCL's debt-collection operation. Processes recorded MP3 calls, transcribes via a Speech Analytics Provider, scores against configurable templates, and flags RBI Code of Conduct compliance violations.

## Architecture

```
uvarcl_live.call_logs
  -> Redis (signed S3 URLs, refreshed every minute)
    -> CallRecording (staging table, ~18K/day)
      -> speech_provider.py (submit audio URL)
        -> Provider (async processing)
          -> Webhook callback
            -> CallTranscript + ProviderScore + ComplianceFlag
              -> Dashboard (React + Vite + TypeScript + Tailwind)
```

### Call flow

1. **Ingestion:** Recordings from `uvarcl_live.call_logs` populate `CallRecording` staging table (~18K new/day + 5K backfill). Filter: `recording_s3_path IS NOT NULL AND call_duration > 10`.
2. **Submission:** `submit_pending_recordings()` batch-submits pending recordings to provider at up to 200 requests/min via `speech_provider.py`.
3. **Processing:** Provider transcribes audio asynchronously. Results arrive via webhook at `/audit/webhook/provider/`.
4. **Scoring:** Two paths — provider template scoring (via `template_id`) and own LLM scoring (future).
5. **Compliance:** `check_compliance()` evaluates call timing (8am-8pm) and restricted keywords. Creates `ComplianceFlag` rows.
6. **Dashboard:** React app shows score distributions, agent comparisons, compliance heatmaps. Role-based views.

### Data model (5 tables)

| Table | Purpose | Key fields |
|-------|---------|------------|
| `CallRecording` | Staging/ingestion | agent_id, recording_url, status, provider_resource_id |
| `CallTranscript` | Transcript + metadata | transcript_text, durations, sentiments, raw_provider_response |
| `ProviderScore` | Template-based scores | template_id, audit_compliance_score, category_data |
| `ComplianceFlag` | Compliance violations | flag_type, severity, evidence, reviewed |
| `OwnLLMScore` | Custom LLM scoring (future) | score_template_name, score_breakdown |

### Provider abstraction

All speech analytics provider interaction goes through `speech_provider.py`. Currently implements GreyLabs. No other file knows provider-specific details. To swap providers, only `speech_provider.py` changes.

### RBAC

Same role IDs as Trainer: 1=Admin, 2=Manager/TL, 3=Agent, 4=Supervisor, 5=Agency Admin. Agents see own calls. TLs see agency. Admins see all.

## API endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/audit/webhook/provider/` | None | Provider callback receiver |
| GET | `/audit/recordings/` | Yes | Paginated recording list |
| GET | `/audit/recordings/<id>/` | Yes | Recording detail with transcript, scores, flags |
| GET | `/audit/dashboard/summary/` | Yes | Aggregate dashboard stats |
| GET | `/audit/compliance-flags/` | Yes | Compliance flag list |

## Local development

```bash
cp .env.example .env
# Fill in: DATABASE_URL, SPEECH_PROVIDER_API_KEY, etc.
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate --settings=settings
python manage.py runserver
```

## Tests

```bash
python manage.py test --settings=settings_test -v 0
ruff check baysys_call_audit/
```

## Tech stack

- **Backend:** Django 4.2+, Django REST Framework, PostgreSQL (Supabase)
- **Frontend:** React 18, Vite, TypeScript, Tailwind CSS
- **Provider:** GreyLabs API (swappable via `speech_provider.py`)
- **Linter:** ruff
