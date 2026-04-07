# GreyLabs UAT — Step-by-Step Instructions

**System:** Baysys Call Audit AI
**Provider:** GreyLabs Speech Analytics
**Goal:** End-to-end test with 10–20 real calls — submit, receive results, verify compliance scoring

---

## Prerequisites

- crm_apis `call-auditor` branch merged to master and deployed to production (317 tests, 0 ruff)
- Steps 1–4 of `docs/deployment-next-steps.md` complete — env vars set, migrations applied, smoke tests passing
- GreyLabs UAT credentials received from Kanishk Gunsola and added to `.envs/.production/.django`

**Note on `<SECRET>`:** Replace `<SECRET>` throughout with your `AUDIT_URL_SECRET` env var value (a UUID). Without it every endpoint returns 404.

---

## Doing the UAT via the Admin UI (no curl needed)

The full UAT workflow can be done through the CRM admin UI without any curl commands. Access is Admin-only (`role_id = 1`) — the "Call Audit" section appears in the nav after login.

### Step 1 — Sync calls

In the dashboard, find the **Operations panel** (always visible on the right). Use the **"Sync date"** date picker — select a recent date with real agent calls, then click Sync. The stats bar updates immediately showing how many calls were created.

Pick a date where `total_fetched` ≥ 10. If the count is low, try the previous day.

### Step 2 — Confirm calls are pending

The **pipeline stats bar** at the top of the dashboard shows live counts:

| Card | What it means |
|---|---|
| Synced today | Recordings created today |
| Pending | Awaiting submission to GreyLabs |
| In queue | Submitted, waiting for GreyLabs response |
| Scored | Completed and scored (shown as "Scored" in UI, `completed` in DB) |
| Failed | Errored — check logs |

After sync, the **Pending** count should show ≥ 10. Below the cards: "Last sync: X minutes ago".

### Step 3 — Submit to GreyLabs

Click **"Submit pending calls"** in the Operations panel. The button is disabled if Pending = 0. A toast confirms how many were submitted. The Pending count drops to 0 and **In queue** rises.

### Step 4 — Monitor scoring

Watch the stats bar. As GreyLabs processes calls (15–30 min), **In queue** drops and **Scored** rises. The recordings table updates in real time — completed calls show a score badge (Excellent / Good / Needs Improvement / Critical) and a fatal level chip.

If any calls stay "In queue" after 30 minutes, click **"Recover stuck calls"** (tick the dry-run checkbox first to preview, then run it for real). A toast shows how many were recovered.

### Step 5 — Review results in the recordings table

The recordings table shows all calls with columns: Call date, Agent, Product, Bank, Tier, Status, Score %, Fatal level. Filterable by status, date range, and agent name. Click any row to open the call detail page.

### Step 6 — Call detail page

Each call detail page has four sections:

**Audio player** — plays the actual recorded call directly in the browser. No download or separate tool needed.

**Metadata Compliance** — flags detected at ingestion time (calling hours violations, Sunday calls, public holiday calls, max calls per customer). Visible even for calls still in queue. Each flag shows severity, type, and evidence. Admins can click "Mark reviewed" to log that a flag has been assessed.

**Call Quality Score** — appears once GreyLabs scores the call. Shows overall score percentage with a colour band, a FATAL banner if any fatal parameter triggered, and four collapsible group sections (Introduction Quality / Call Quality / Compliance & RBI / Scam & Trust) with the 19 individual parameter scores.

**Call Transcript** — scrollable full transcript once available. Above the transcript: total call duration, agent talk %, customer talk % as a bar.

If a call shows **Failed**: a "Retry this call" button re-queues it for submission.

### Step 7 — Agent leaderboard

Switch to the **Agent leaderboard** tab on the dashboard. Shows per-agent: calls scored, average score, score band, fatal flag count. Clicking a row filters the recordings table to that agent's calls.

---

## Phase 1 — Configure GreyLabs credentials

Set these in `.envs/.production/.django` (or your production secret store):

```ini
SPEECH_PROVIDER_API_KEY=<GreyLabs API key from Kanishk>
SPEECH_PROVIDER_API_SECRET=<GreyLabs API secret from Kanishk>
SPEECH_PROVIDER_TEMPLATE_ID=1588
SPEECH_PROVIDER_CALLBACK_URL=https://<your-production-domain>/audit/<SECRET>/webhook/provider/
```

Restart the server after setting env vars.

**Verify connection:**
```bash
curl -X GET https://<your-domain>/audit/<SECRET>/recordings/ \
  -H "Authorization: Token <admin-token>"
```
Should return 200 with a (possibly empty) recordings list.

---

## Phase 2 — Sync calls from production into the system

Calls are already live in `uvarcl_live` (Supabase production). The sync reads directly from `call_logs` — no CSV, no manual data prep.

### What the sync does

The sync runs a SQL query against `uvarcl_live.call_logs` joined with `uvarcl_live.users`. It automatically filters to:
- Calls on the target date (`call_start_time::date = <date>`)
- Calls with a recording file (`recording_s3_path IS NOT NULL`)
- Calls longer than 20 seconds (`call_duration > 20`) — configurable via `SYNC_MIN_CALL_DURATION` setting

Fields pulled per call: agent_id, agent name (from users table), agency_id, customer_id, customer phone, recording S3 path, call start time, call duration, campaign name (maps to bank_name), loan_id (maps to portfolio_id).

Dedup is automatic — if a recording URL is already in the system, it's skipped. Safe to re-run for the same date.

Each synced recording is auto-assigned a **submission tier** (`immediate` / `normal` / `off_peak`) based on `config/submission_priority.yaml` rules (agency_id, bank_name, product_type). This controls processing priority — for UAT it doesn't matter, all pending recordings are submitted together.

### Run the sync

Pick a recent date with real agent calls in `call_logs`:

```bash
curl -X POST https://<your-domain>/audit/<SECRET>/recordings/sync/ \
  -H "Authorization: Token <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"date": "2026-04-07"}'
```

**Optional parameters:**
- `"dry_run": true` — shows what would be created without writing anything, useful to check a date before committing
- `"batch_size": 5000` — default is 5000, lower this if you want to limit the sync

**Response fields explained:**
```json
{
  "status": "ok",
  "date": "2026-04-07",
  "dry_run": false,
  "total_fetched": 45,
  "created": 38,
  "skipped_dedup": 6,
  "skipped_validation": 1,
  "unknown_agents": 2,
  "errors": 0
}
```
- `total_fetched` — rows returned by the SQL query (has recording + duration > 20s)
- `created` — new CallRecording rows created, status set to `pending`
- `skipped_dedup` — already in the system from a previous sync of this date
- `skipped_validation` — missing agent_id, recording URL, or call datetime — check server logs
- `unknown_agents` — agent_id not found in `users` table; recording is still created, agent_name = "Unknown"
- `errors` — unexpected exceptions — check server logs if > 0

### Pick a good date

If you're not sure which date has calls, run a dry_run first:

```bash
curl -X POST https://<your-domain>/audit/<SECRET>/recordings/sync/ \
  -H "Authorization: Token <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"date": "2026-04-06", "dry_run": true}'
```

A date is good for UAT if `total_fetched` ≥ 10 and `errors` = 0.

### Alternative: CSV import (not needed in production)

In production, calls are already in `uvarcl_live` — use the sync above. CSV import exists as a fallback for testing environments or one-off loads only.

Export rows from `call_logs` with these columns:
```
call_id, agent_id, customer_id, call_date, call_duration_seconds, recording_url, loan_account_number
```

```bash
curl -X POST https://<your-domain>/audit/<SECRET>/recordings/import/ \
  -H "Authorization: Token <admin-token>" \
  -F "file=@uat_calls.csv"
```

Supports `?dry_run=true` as a query param. Same dedup rules apply.

---

### Filter after sync (optional)

Once synced, you can inspect what's pending and narrow by agent before submitting:

```bash
# All pending recordings for the date
curl "https://<your-domain>/audit/<SECRET>/recordings/?status=pending&date_from=2026-04-07&date_to=2026-04-07" \
  -H "Authorization: Token <admin-token>"

# Pending for a specific agent
curl "https://<your-domain>/audit/<SECRET>/recordings/?status=pending&agent_id=<agent_id>" \
  -H "Authorization: Token <admin-token>"
```

Supported list filters: `?status=`, `?agent_id=`, `?date_from=`, `?date_to=`, `?page=`, `?page_size=` (max 100 per page).

---

## Phase 3 — Verify calls are pending

```bash
curl -X GET "https://<your-domain>/audit/<SECRET>/recordings/?status=pending" \
  -H "Authorization: Token <admin-token>"
```

Should show 10–20 recordings with `"status": "pending"`.

---

## Phase 4 — Submit to GreyLabs

```bash
curl -X POST https://<your-domain>/audit/<SECRET>/recordings/submit/ \
  -H "Authorization: Token <admin-token>"
```

Returns: `{"submitted": N, "failed": 0}`

- `submitted` = recordings sent to GreyLabs (status changes to `submitted`)
- `failed` = recordings that errored (check server logs if > 0)

Check status:
```bash
curl -X GET "https://<your-domain>/audit/<SECRET>/recordings/?status=submitted" \
  -H "Authorization: Token <admin-token>"
```

---

## Phase 5 — Wait for webhooks

GreyLabs will POST results to `https://<your-domain>/audit/<SECRET>/webhook/provider/` as they complete.

Each webhook call will:
1. Update the recording status to `completed`
2. Store raw provider output
3. Trigger compliance scoring

Monitor progress:
```bash
curl -X GET "https://<your-domain>/audit/<SECRET>/recordings/?status=completed" \
  -H "Authorization: Token <admin-token>"
```

GreyLabs typically responds within a few minutes per call. Wait 15–30 minutes for the batch.

---

## Phase 6 — Poll if any are stuck

If recordings remain in `submitted` status after 30+ minutes:

```bash
# Dry run first — see what would be polled
curl -X POST https://<your-domain>/audit/<SECRET>/recordings/poll/ \
  -H "Authorization: Token <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'

# Actually poll
curl -X POST https://<your-domain>/audit/<SECRET>/recordings/poll/ \
  -H "Authorization: Token <admin-token>"
```

Returns: `{"polled": N, "recovered": N, "still_processing": N, "errors": N, "dry_run": false, "threshold_minutes": 30}`

---

## Phase 7 — Inspect results

Check a single recording in detail:
```bash
curl -X GET https://<your-domain>/audit/<SECRET>/recordings/<recording_id>/ \
  -H "Authorization: Token <admin-token>"
```

Look for:
- `"status": "completed"` — provider results received
- `"provider_score"` — GreyLabs raw score
- `"own_llm_score"` — our compliance score (if LLM scoring triggered)

---

## Phase 8 — Check compliance flags

```bash
curl -X GET "https://<your-domain>/audit/<SECRET>/compliance-flags/?recording_id=<id>" \
  -H "Authorization: Token <admin-token>"
```

Each flag has:
- `parameter_name` — which of the 19 scorecard parameters
- `flag_type` — `fatal` / `warning` / `info`
- `value` — raw extracted value
- `score` — points awarded

Check the dashboard summary for aggregate stats:
```bash
curl -X GET https://<your-domain>/audit/<SECRET>/dashboard/summary/ \
  -H "Authorization: Token <admin-token>"
```

---

## Full endpoint reference

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/audit/<SECRET>/recordings/` | GET | Admin/Manager | List recordings (filter by `?status=`) |
| `/audit/<SECRET>/recordings/<id>/` | GET | Admin/Manager | Single recording detail |
| `/audit/<SECRET>/recordings/import/` | POST | Admin/Manager | CSV/Excel import |
| `/audit/<SECRET>/recordings/sync/` | POST | Admin/Supervisor | Sync from call_logs for a date |
| `/audit/<SECRET>/recordings/submit/` | POST | Admin/Manager | Submit pending to GreyLabs |
| `/audit/<SECRET>/recordings/poll/` | POST | Admin/Manager | Poll stuck recordings |
| `/audit/<SECRET>/webhook/provider/` | POST | None (provider) | Receive GreyLabs callbacks |
| `/audit/<SECRET>/compliance-flags/` | GET | Admin/Manager | List compliance flags |
| `/audit/<SECRET>/dashboard/summary/` | GET | Admin/Manager | Aggregate stats |

---

## Troubleshooting

**`submitted: 0` on submit call**
- Check recordings are actually in `pending` status
- Check `SPEECH_PROVIDER_API_KEY` / `SPEECH_PROVIDER_API_SECRET` are set correctly
- Check server logs for `speech_provider` errors

**Webhooks not arriving**
- Confirm `SPEECH_PROVIDER_CALLBACK_URL` points to the correct production domain with `/audit/<SECRET>/webhook/provider/`
- Confirm the URL is publicly reachable (not localhost)
- Use the poll endpoint as fallback

**`failed > 0` on submit**
- Check the recording has a valid `recording_url` (accessible MP3)
- Check GreyLabs rate limit (200 requests/min max per their spec)

**Compliance flags missing after scoring**
- Check `fatal_level_rules.yaml` and `compliance_rules.yaml` are present in `config/`
- Check server logs for compliance scoring errors
