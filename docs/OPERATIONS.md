# BaySys Call Audit AI — Operations Guide

## System Overview

BaySys Call Audit AI is a call monitoring system that processes recorded MP3 calls from Baysys.ai's debt collection process (on behalf of UVARCL). It transcribes audio via a Speech Analytics Provider (currently GreyLabs, swappable), scores calls against the **UVARCL Scorecard v2** (19 parameters, 7 FATALs — see `docs/SCORECARD.md`), and flags RBI Code of Conduct compliance violations. The system handles ~18K recordings/day plus ~5K/day backfill from a 200K historical archive.

---

## PC-Supabase (Pre-populated Dev Instance)

PC-Supabase is the shared dev instance for all BaySys projects — pre-configured for development and testing with no cross-DB connections to source RDS required.

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

**To test sync against PC-Supabase:**
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

**Dedup:** Safe to run twice for the same date — existing `recording_url` values are skipped. The sync pre-fetches all existing URLs for the target date in one query before the loop (O(1) per-row check); a full date's sync against Supabase runs in under 30 seconds.

**Scheduling:** See the full cron schedule in the **Cron Setup** section below.

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

See the full cron schedule in the **Cron Setup** section below.

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
- The `poll_stuck_recordings` cron job (job 5) runs every 30 minutes and automatically recovers these. Check `/var/log/baysys_audit/poll.log` for recovery counts.
- To trigger recovery immediately: `python manage.py poll_stuck_recordings`
- To check how many are stuck: `python manage.py poll_stuck_recordings --dry-run`

### Webhook Recovery

If the provider cannot deliver webhooks (server unreachable, retry exhausted), recordings stay in `status=submitted` indefinitely. The `poll_stuck_recordings` command is the recovery mechanism:

```bash
# See how many are stuck (no API calls made)
python manage.py poll_stuck_recordings --dry-run

# Recover up to 50 at a time (default)
python manage.py poll_stuck_recordings

# Recover a large backlog
python manage.py poll_stuck_recordings --batch-size 500
```

**How it works:**
1. Finds recordings with `status=submitted`, `submitted_at < now - POLL_STUCK_AFTER_MINUTES`, `provider_resource_id IS NOT NULL`
2. Calls `get_results()` for each → if transcript is present, calls `process_provider_webhook()` (same logic as live webhook delivery)
3. If transcript is absent → "still processing", leave as `submitted`
4. On `ProviderError` → increments `retry_count`, leaves as `submitted`

**Threshold:** `POLL_STUCK_AFTER_MINUTES` (default 30). Set lower (e.g. 15) for faster recovery in high-volume environments.

### Failed recordings
```sql
SELECT id, agent_name, error_message, retry_count
FROM call_recordings
WHERE status = 'failed'
ORDER BY created_at DESC;
```
- Reset to pending for retry: `UPDATE call_recordings SET status='pending', retry_count=0 WHERE id=<ID>;`

### GreyLabs webhook payload format (Session 25 — learned from live UAT)

GreyLabs wraps all webhook data in a `details` array:
```json
{"status": "success", "details": [{"resource_insight_id": "...", "transcript": "...", "category_data": [...]}]}
```

**Key facts discovered during live testing:**
- Data is always in `details[0]` — the code unwraps this in `process_provider_webhook()`
- `category_data` is a **list at root level** (not nested inside `insights`). Code that reads `payload.get("insights", {}).get("category_data")` gets None.
- Submission requires `json=payload` (not `data=payload`) — otherwise GreyLabs receives an empty body
- `customer_id` must be included in the submission payload (GreyLabs error E009 otherwise)
- Webhook Content-Type may not be `application/json` — defensive JSON parse handles this

### NewRelic `add_custom_attributes` format

The NR API requires a **list of tuples**, NOT a dict:
```python
# WRONG — causes ValueError: too many values to unpack
newrelic.agent.add_custom_attributes({'key': 'value'})

# CORRECT
newrelic.agent.add_custom_attributes([('key', 'value')])
```

### Config YAML changes require restart

`compliance_rules.yaml` and `fatal_level_rules.yaml` are loaded with `@lru_cache`. Changes to these files are not picked up without restarting Django. This is a known trade-off (documented in code review H-6 / M-6).

---

## Cron Setup

All cron jobs run from the project root with the virtualenv activated. Replace `/path/to/project` with the actual deployment path inside the CRM API server.

```cron
# ── BaySys AI Call Auditor — Cron Schedule ────────────────────────────────────

# 1. Daily sync: pull previous day's calls from call_logs → call_recordings
#    Runs at 00:15 every night (after midnight, gives CRM time to finish writing)
15 0 * * * cd /path/to/project && .venv/bin/python manage.py sync_call_logs >> /var/log/baysys_audit/sync.log 2>&1

# 2. Immediate tier: submit highest-priority recordings to provider
#    Runs every 15 minutes throughout the day
*/15 * * * * cd /path/to/project && .venv/bin/python manage.py submit_recordings --tier immediate --batch-size 200 >> /var/log/baysys_audit/submit.log 2>&1

# 3. Normal tier: submit standard recordings
#    Runs every hour
0 * * * * cd /path/to/project && .venv/bin/python manage.py submit_recordings --tier normal --batch-size 1000 >> /var/log/baysys_audit/submit.log 2>&1

# 4. Off-peak tier: submit backfill / archival recordings overnight
#    Runs once at 2am
0 2 * * * cd /path/to/project && .venv/bin/python manage.py submit_recordings --tier off_peak --batch-size 5000 >> /var/log/baysys_audit/submit.log 2>&1

# 5. Poll for stuck recordings — webhook fallback recovery
#    Runs every 30 minutes
*/30 * * * * cd /path/to/project && .venv/bin/python manage.py poll_stuck_recordings >> /var/log/baysys_audit/poll.log 2>&1
```

**Notes:**
- The sync command (job 1) and submission commands (jobs 2–4) are independent. Sync populates `call_recordings` with `status=pending`; submission picks up pending rows and sends them to the provider.
- Job 5 (`poll_stuck_recordings`) is a safety net — it recovers recordings whose webhook delivery was missed. Under normal conditions most recordings are processed via webhook; polling handles the remainder.
- If cron misses, use the failsafe API endpoint: `POST /audit/recordings/sync/` (Admin/Supervisor only).
- Rate limit: 200 requests/min to provider. At that rate, 18K daily recordings clear in ~90 minutes.
- Log rotation for `/var/log/baysys_audit/` recommended — same as Voice Trainer setup.

---

## Environment Variables Reference

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `SECRET_KEY` | Prod | dev-insecure-key | Django secret key |
| `DEBUG` | No | True | Django debug mode |
| `DATABASE_URL` | Yes | — | Supabase connection string |
| `DB_SCHEMA` | No | baysys_call_audit | PostgreSQL search_path |
| `AUDIT_AUTH_BACKEND` | No | mock | `mock` for dev, `crm` for production |
| `SPEECH_PROVIDER_HOST` | Yes | — | Provider API base URL (no default — must be set explicitly) |
| `SPEECH_PROVIDER_API_KEY` | Yes | — | Provider API key |
| `SPEECH_PROVIDER_API_SECRET` | Yes | — | Provider API secret |
| `SPEECH_PROVIDER_TEMPLATE_ID` | Yes | — | Provider scoring template ID |
| `SPEECH_PROVIDER_CALLBACK_URL` | Yes | — | Webhook URL for provider callbacks |
| `SPEECH_PROVIDER_RATE_LIMIT` | No | 200 | Max requests/min to provider |
| `COMPLIANCE_CALL_WINDOW_START_HOUR` | No | 8 | Earliest permitted call hour |
| `COMPLIANCE_CALL_WINDOW_END_HOUR` | No | 20 | Latest permitted call hour |
| `COMPLIANCE_MAX_CALLS_PER_CUSTOMER_PER_DAY` | No | 15 | Max calls to same customer per day before compliance flag |
| `COMPLIANCE_FATAL_THRESHOLD` | No | 3 | Fatal level threshold for compliance flag |
| `SYNC_MIN_CALL_DURATION` | No | 20 | Minimum call duration (seconds) to sync; shorter calls excluded |
| `POLL_STUCK_AFTER_MINUTES` | No | 30 | Minutes after submission before polling for missed webhooks |
| `SYNC_BATCH_SIZE` | No | 5000 | Max rows to sync from `call_logs` per run |
| `SUBMIT_BATCH_SIZE` | No | 100 | Max recordings to submit to provider per run |
| `POLL_BATCH_SIZE` | No | 50 | Max stuck recordings to poll per run |
| `SPEECH_PROVIDER_WEBHOOK_ALLOWED_IPS` | No | — | Comma-separated IP allowlist for webhook endpoint (X-Forwarded-For extraction) |
| `OWN_LLM_ENABLED` | No | false | Enable own LLM scoring (Anthropic API) |
| `OWN_LLM_API_KEY` | Cond. | — | Anthropic API key (required if `OWN_LLM_ENABLED=true`) |
| `OWN_LLM_MODEL` | No | claude-haiku-4-5-20251001 | LLM model for scoring |
| `OWN_LLM_SCORING_TEMPLATE` | No | scoring_template_uvarcl_v2 | Scoring template name (matches `config/*.yaml`) |

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

## New Relic APM

New Relic provides request-level tracing, database query visibility, external call monitoring, and custom business metrics.

### Environment variables

| Variable | Default | Notes |
|----------|---------|-------|
| `NEW_RELIC_LICENSE_KEY` | (required) | Account licence key |
| `NEW_RELIC_APP_NAME` | `BaySys-CallAudit-dev` | Use `-dev`, `-staging`, `-prod` suffix |
| `NEW_RELIC_ENVIRONMENT` | `development` | `development` / `staging` / `production` |

### Running with New Relic

**Web server (gunicorn):**
```bash
NEW_RELIC_CONFIG_FILE=newrelic.ini newrelic-admin run-program gunicorn settings:wsgi --bind 0.0.0.0:8000
```

**Management commands (cron):**
```bash
# All cron commands must be wrapped with newrelic-admin
NEW_RELIC_CONFIG_FILE=newrelic.ini newrelic-admin run-program python manage.py sync_call_logs
NEW_RELIC_CONFIG_FILE=newrelic.ini newrelic-admin run-program python manage.py submit_recordings --tier immediate --batch-size 500
NEW_RELIC_CONFIG_FILE=newrelic.ini newrelic-admin run-program python manage.py poll_stuck_recordings
```

### Auto-instrumented (no code needed)

- All DRF API endpoints (request timing, throughput, error rate)
- All database queries (ORM and raw SQL including `SYNC_QUERY`)
- All outbound HTTP calls via `requests` library (GreyLabs/STT provider API calls)
- Django middleware chain

### Custom business metrics

| Metric | Source file | What it tracks |
|--------|-----------|----------------|
| `Custom/Pipeline/Recordings/Submitted` | services.py | Recordings sent to provider |
| `Custom/Pipeline/Recordings/SubmitFailed` | services.py | Provider submission failures |
| `Custom/Pipeline/Webhooks/Processed` | services.py | Webhook callbacks processed |
| `Custom/Compliance/MetadataFlags/{type}` | compliance.py | Compliance flags by type |
| `Custom/Compliance/FatalLevel` | compliance.py | Fatal level distribution |
| `SyncCompleted` (event) | ingestion.py | Daily sync health (row counts, duration) |
| `ProviderError` (event) | speech_provider.py | Provider incident detection |

### Kubernetes migration

When moving to K8s: drop `newrelic.ini`, use env vars exclusively via ConfigMap (non-secret) + Secret (licence key). The agent respects env vars natively.

Full plan: `docs/new-relic-telemetry-plan.md`

---

## OwnLLM Scoring (Pending — Prompt Q)

Own LLM scoring uses the Anthropic API to score call transcripts against the UVARCL 19-parameter scorecard. This replaces GreyLabs' internal score as the primary compliance metric.

**Status:** Architecture designed, prompts written (`docs/prompts/prompt-Q-own-llm-scoring.md`, `docs/prompts/prompt-R-own-llm-score-ui.md`). Not yet implemented.

**How it will work:**
1. After `process_provider_webhook()` stores the transcript, `run_own_llm_scoring()` is called
2. Transcript + scoring YAML template sent to Anthropic API (Claude Haiku)
3. Response parsed into `OwnLLMScore` record with per-parameter breakdown
4. `OwnLLMScore` displayed as primary "Compliance Score" in UI
5. `ProviderScore` (GreyLabs) demoted to collapsible "GreyLabs Analytics" section

**Env vars required on production:**
```bash
OWN_LLM_ENABLED=true
OWN_LLM_API_KEY=<anthropic-api-key>
OWN_LLM_MODEL=claude-haiku-4-5-20251001
OWN_LLM_SCORING_TEMPLATE=scoring_template_uvarcl_v2
```

**Scoring template:** `config/scoring_template_uvarcl_v2.yaml` (created by Prompt Q)

**Not-scoreable calls:** WPC (Wrong Party Connect), voicemail, no-answer calls are classified as `call_type: not_scoreable` with a disposition label. They receive no numeric score.

---

## Dashboard Access

- **Local:** http://localhost:5173/audit
- **Role-based views:**
  - Agent (role_id=3): sees own calls only
  - Manager/TL (role_id=2): sees all calls in their agency
  - Admin (role_id=1) / Supervisor (role_id=4): sees all calls across agencies
