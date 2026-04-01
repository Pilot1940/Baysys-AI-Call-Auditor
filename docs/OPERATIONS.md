# BaySys Call Audit AI — Operations Guide

## System Overview

BaySys Call Audit AI is a call monitoring system that processes recorded MP3 calls from UVARCL's debt-collection operation. It transcribes audio via a Speech Analytics Provider (currently GreyLabs), scores calls against configurable templates, and flags RBI Code of Conduct compliance violations. The system handles ~18K recordings/day plus ~5K/day backfill from a 200K historical archive.

---

## Dev Supabase Instance (Pre-populated)

A dev Supabase instance is pre-configured for development and testing — no cross-DB connections to source RDS required.

**Instance:** Same Supabase project as Voice Trainer (`DATABASE_URL` in `.env`)

**What's loaded:**

| Schema | Table | Rows | Notes |
|--------|-------|------|-------|
| `uvarcl_live` | `call_logs` | 500,000 | Most recent 500K rows ordered by `call_start_time DESC`. Raw S3 object keys in `recording_s3_path`. |
| `uvarcl_live` | `users` | 662 | All agents/supervisors. Credentials anonymised (`dev_{id}@dev.local`). Name + `agency_id` intact for JOIN. |
| `baysys_call_audit` | `call_recordings` | 99,998 | First 100K synced sample (2026-03-20 → 2026-03-31). All `status=pending`. |
| `baysys_call_audit` | `call_transcripts` | 0 | Empty — awaiting GreyLabs UAT key |
| `baysys_call_audit` | `provider_scores` | 0 | Empty — awaiting GreyLabs UAT key |
| `baysys_call_audit` | `compliance_flags` | 0 | Empty — populated by sync |
| `baysys_call_audit` | `own_llm_scores` | 0 | Empty — future prompt |

**Key facts about the loaded data:**
- `uvarcl_live.call_logs` date range: approx 2026-03-01 → 2026-03-31
- `users` table is the CRM agent table (plural) — not Django's `auth_user` (singular). The JOIN is `call_logs.agent_id = users.user_id`.
- 276 distinct agents, 43,043 distinct customers in `call_recordings`
- `recording_s3_path` format: raw S3 object key e.g. `Rezolution/call_recordings/2026/03/31/call.mp3` — no http:// prefix. This is expected.

**To test sync against dev Supabase:**
```bash
# Sync a date that exists in the loaded call_logs data
python manage.py sync_call_logs --date 2026-03-31 --dry-run

# Actual sync
python manage.py sync_call_logs --date 2026-03-31
```

Django connects to Supabase (`DATABASE_URL`). The sync query reads from `uvarcl_live.call_logs` and writes to `baysys_call_audit.call_recordings` — all within the same Supabase instance.

---

## Running the System Locally

### 1. Prerequisites
- Python 3.11+
- Node.js 18+ (for React UI)
- Access to Supabase DB (same instance as Trainer)

### 2. Setup

```bash
cd Baysys-AI-Call-Auditor/

# Copy env template and fill in values
cp .env.example .env
# Edit .env: DATABASE_URL, SPEECH_PROVIDER_API_KEY, SPEECH_PROVIDER_API_SECRET, etc.

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run migrations
python manage.py migrate --settings=settings

# Start Django server
python manage.py runserver
```

### 3. Verify Supabase connection
```bash
python manage.py dbshell --settings=settings
# Should connect to Supabase. Run: SELECT 1; to verify.
```

### 4. Start React dev server (separate terminal)
```bash
cd baysys_call_audit_ui/
npm install
npm run dev
# Opens at http://localhost:5173
```

---

## Populating CallRecording — Ingestion

CallRecording is the analytical source of truth. Two ingestion paths:

### Path 1: Daily sync from call_logs

Reads `uvarcl_live.call_logs`, JOINs to `uvarcl_live.users` for agent name + agency, creates `CallRecording` rows with `status=pending`.

```bash
# Sync yesterday's calls (default)
python manage.py sync_call_logs

# Sync a specific date
python manage.py sync_call_logs --date 2026-03-30

# Custom batch size (default: 5000)
python manage.py sync_call_logs --date 2026-03-30 --batch-size 10000

# Dry run — count and validate, no DB writes
python manage.py sync_call_logs --date 2026-03-30 --dry-run
```

**Output:** Summary showing fetched, created, skipped (dedup), skipped (invalid), unknown agents, errors.

**Filters applied:** `recording_s3_path IS NOT NULL AND call_duration > 10`.

**Dedup:** Safe to run twice for the same date — existing `recording_url` values are skipped.

**Scheduling:** Run daily via cron after midnight:
```cron
15 0 * * * cd /path/to/project && python manage.py sync_call_logs
```

### Path 2: CSV/Excel upload (backfill)

For the 200K historical backlog and ad-hoc imports.

```bash
# Import from CSV
python manage.py import_recordings /path/to/recordings.csv

# Import from Excel (specific sheet)
python manage.py import_recordings /path/to/recordings.xlsx --sheet "Sheet1"

# Dry run
python manage.py import_recordings /path/to/recordings.csv --dry-run
```

**Required columns:** `agent_id`, `recording_url`, `recording_datetime`
**Expected columns:** `agent_name` (defaults to "Unknown" if missing)
**Optional columns:** `customer_id`, `portfolio_id`, `agency_id`, `customer_phone`, `product_type`, `bank_name`

Column headers are case-insensitive and accept spaces, hyphens, or camelCase (e.g., "Agent ID", "agent_id", "agentId" all work).

**API endpoint** (alternative to CLI):
```
POST /audit/recordings/import/
Content-Type: multipart/form-data
Body: file=<csv or xlsx>
Query: ?dry_run=true (optional)

Requires: Admin (role_id=1) or Manager/TL (role_id=2)
```

### Path 3: Sync API endpoint (failsafe)

Same logic as the management command, triggered via HTTP. Use when cron missed or for ad-hoc sync.

```
POST /audit/recordings/sync/
Content-Type: application/json
Auth: Admin (role_id=1) or Supervisor (role_id=4)

Body (all optional):
{
    "date": "2026-04-01",
    "batch_size": 5000,
    "dry_run": false
}

Response: {"status": "ok", "date": "...", "created": N, ...}
```

### Submitting to speech provider

After ingestion, `CallRecording` rows are in `status=pending`. Submit them using the management command:

```bash
# Submit up to 100 pending recordings (all tiers)
python manage.py submit_recordings

# Submit only immediate-tier recordings
python manage.py submit_recordings --tier immediate

# Submit normal + off_peak (not immediate)
python manage.py submit_recordings --tier normal --tier off_peak

# Custom batch size
python manage.py submit_recordings --batch-size 500

# Dry run — count pending without submitting
python manage.py submit_recordings --dry-run
python manage.py submit_recordings --tier immediate --dry-run
```

Or call directly from Python:

```python
from baysys_call_audit.services import submit_pending_recordings

# Submit up to 100 pending recordings (all tiers)
result = submit_pending_recordings(batch_size=100)

# Submit only immediate-tier recordings
result = submit_pending_recordings(batch_size=100, tiers=["immediate"])

# Returns: {"submitted": N, "failed": N, "skipped": N}
```

**S3 URL re-signing:** Pre-signed S3 URLs expire in 10–15 minutes, but the submission batch takes ~90 minutes at 200/min. The service calls `crm_adapter.get_signed_url()` immediately before each provider API call to get a fresh URL. The stored `recording_url` is never overwritten.

### Submission tiers

Recordings are assigned a `submission_tier` at ingestion time:
- `immediate` — highest priority (VIP clients, regulatory accounts)
- `normal` — standard priority (default)
- `off_peak` — lowest priority (backfill, archival)

Tier assignment is config-driven via `config/submission_priority.yaml`. Matching uses OR logic within each tier:
- `agency_ids`: exact match on `agency_id`
- `bank_names`: substring match on `bank_name` (case-insensitive)
- `product_types`: exact match on `product_type` (case-insensitive)

Precedence: `immediate` > `off_peak` > `normal`. If no rule matches, tier defaults to `normal`.

**Recommended cron schedule (tier-based):**
```cron
# Immediate tier — run every 15 minutes
*/15 * * * * cd /path/to/project && python manage.py submit_recordings --tier immediate --batch-size 200

# Normal tier — run hourly
0 * * * * cd /path/to/project && python manage.py submit_recordings --tier normal --batch-size 1000

# Off-peak tier — run once at night
0 2 * * * cd /path/to/project && python manage.py submit_recordings --tier off_peak --batch-size 5000
```

### Rate limiting
- Provider rate limit: 200 requests/min
- At 200/min, 23K recordings (18K daily + 5K backfill) clears in ~2 hours

---

## Checking Pipeline Health

### Recording status distribution
```sql
SELECT status, COUNT(*) FROM call_recordings GROUP BY status;
```

Expected healthy state:
- `pending`: low (new arrivals waiting for submission)
- `submitted`: moderate (in provider queue)
- `completed`: growing (processed successfully)
- `failed`: low (check error_message for details)

### Recent webhook activity
```sql
SELECT id, status, completed_at
FROM call_recordings
WHERE completed_at IS NOT NULL
ORDER BY completed_at DESC
LIMIT 10;
```

### Compliance flag summary
```sql
SELECT flag_type, severity, COUNT(*)
FROM compliance_flags
GROUP BY flag_type, severity
ORDER BY severity, flag_type;
```

---

## Common Troubleshooting

### Provider submission errors
- **HTTP 401/403:** Check `SPEECH_PROVIDER_API_KEY` and `SPEECH_PROVIDER_API_SECRET` in `.env`
- **HTTP 429:** Rate limit exceeded. Reduce batch size or add delay between batches.
- **Timeout:** Provider may be slow. Check `SPEECH_PROVIDER_HOST` is reachable.

### Webhook not receiving results
1. Verify `SPEECH_PROVIDER_CALLBACK_URL` in `.env` points to your public `/audit/webhook/provider/` endpoint
2. Check Django server logs for incoming POST requests
3. Verify provider has the correct callback URL configured

### Recordings stuck in "submitted" status
- Provider may still be processing (async). Check provider dashboard.
- If stuck for >1 hour, try polling with `speech_provider.get_results(resource_id)`.

### Failed recordings
```sql
SELECT id, agent_name, error_message, retry_count
FROM call_recordings
WHERE status = 'failed'
ORDER BY created_at DESC;
```
- Reset to pending for retry: `UPDATE call_recordings SET status='pending', retry_count=0 WHERE id=<ID>;`

---

## Environment Variables Reference

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `SECRET_KEY` | Prod | dev-insecure-key | Django secret key |
| `DEBUG` | No | True | Django debug mode |
| `DATABASE_URL` | Yes | — | Supabase connection string |
| `DB_SCHEMA` | No | baysys_call_audit | PostgreSQL search_path |
| `AUDIT_AUTH_BACKEND` | No | mock | `mock` for dev, `crm` for production |
| `SPEECH_PROVIDER_HOST` | No | https://api.greylabs.ai | Provider API base URL |
| `SPEECH_PROVIDER_API_KEY` | Yes | — | Provider API key |
| `SPEECH_PROVIDER_API_SECRET` | Yes | — | Provider API secret |
| `SPEECH_PROVIDER_TEMPLATE_ID` | Yes | — | Provider scoring template ID |
| `SPEECH_PROVIDER_CALLBACK_URL` | Yes | — | Webhook URL for provider callbacks |
| `SPEECH_PROVIDER_RATE_LIMIT` | No | 200 | Max requests/min to provider |
| `COMPLIANCE_CALL_WINDOW_START_HOUR` | No | 8 | Earliest permitted call hour |
| `COMPLIANCE_CALL_WINDOW_END_HOUR` | No | 20 | Latest permitted call hour |
| `COMPLIANCE_MAX_CALLS_PER_CUSTOMER_PER_DAY` | No | 3 | Max calls to same customer per day |
| `COMPLIANCE_FATAL_THRESHOLD` | No | 3 | Fatal level threshold for compliance flag |

---

## Compliance Rules (config/compliance_rules.yaml)

Rules are config-driven. Two categories:

- **Metadata rules** — run at ingestion time using CallRecording fields only
  - `M1 call_window`: Call outside permitted hours (8am-8pm default, settings override)
  - `M2 blocked_weekday`: Call on Sunday
  - `M3 gazette_holiday`: Call on gazette holiday (dates in `config/gazette_holidays_2026.txt`)
  - `M4 max_calls_per_customer`: >3 calls to same customer on same day

- **Provider rules** — run after webhook delivers results
  - `P1 fatal_level_threshold`: Fatal level >= threshold
  - `P2 provider_score_threshold`: Compliance score below threshold
  - `P3 provider_transcript_field`: Negative customer sentiment

**Timezone:** All compliance time/date checks (call window, blocked weekday, gazette holiday, max calls per customer) use **IST (Asia/Kolkata, UTC+5:30)**. `recording_datetime` is stored in UTC; conversion to IST happens in `compliance.py` at check time. No ops action needed — this is automatic.

**To add/modify rules:** Edit `config/compliance_rules.yaml`. Adding a rule of an existing `check_type` requires no code changes.

**To disable a rule:** Set `enabled: false` in the YAML.

**To add gazette holidays for a new year:** Create `config/gazette_holidays_2027.txt` (one date per line, YYYY-MM-DD), then update `M3.params.holidays_file` in `compliance_rules.yaml`.

---

## Fatal Level System (config/fatal_level_rules.yaml)

Maps provider boolean scoring parameters to a severity score (0-5).

**Formula:** `fatal_level = min(sum_of_triggered_weights, 5)`

A parameter is "triggered" when:
- Normal (`invert: false`): provider returns 0 (failed)
- Inverted (`invert: true`): provider returns 1 (e.g. abusive language detected)

### Version update workflow

1. Edit `config/fatal_level_rules.yaml` (weights, parameters, threshold)
2. Bump `version` (semver), update `last_updated` (ISO date), `updated_by` (name)
3. Run: `python manage.py update_fatal_level_hash`
4. Commit to git — audit trail complete

The `content_hash` field provides audit integrity. If the hash doesn't match, the engine logs a WARNING but continues scoring.

---

## Dashboard Access

- **Local:** http://localhost:5173/audit
- **Role-based views:**
  - Agent (role_id=3): sees own calls only
  - Manager/TL (role_id=2): sees all calls in their agency
  - Admin (role_id=1) / Supervisor (role_id=4): sees all calls across agencies
