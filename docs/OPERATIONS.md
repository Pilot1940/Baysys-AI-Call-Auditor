# BaySys Call Audit AI — Operations Guide

## System Overview

BaySys Call Audit AI is a call monitoring system that processes recorded MP3 calls from UVARCL's debt-collection operation. It transcribes audio via a Speech Analytics Provider (currently GreyLabs), scores calls against configurable templates, and flags RBI Code of Conduct compliance violations. The system handles ~18K recordings/day plus ~5K/day backfill from a 200K historical archive.

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

### Submitting to speech provider

After ingestion, `CallRecording` rows are in `status=pending`. Submit them to the provider:

```python
# In Django shell or management command:
from baysys_call_audit.services import submit_pending_recordings

# Submit up to 100 pending recordings
result = submit_pending_recordings(batch_size=100)
# Returns: {"submitted": N, "failed": N, "skipped": N}
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

---

## Dashboard Access

- **Local:** http://localhost:5173/audit
- **Role-based views:**
  - Agent (role_id=3): sees own calls only
  - Manager/TL (role_id=2): sees all calls in their agency
  - Admin (role_id=1) / Supervisor (role_id=4): sees all calls across agencies
