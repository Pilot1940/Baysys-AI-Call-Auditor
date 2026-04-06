# GreyLabs UAT — Step-by-Step Instructions

**System:** Baysys Call Audit AI
**Provider:** GreyLabs Speech Analytics
**Goal:** End-to-end test with 10–20 real calls — submit, receive results, verify compliance scoring

---

## Prerequisites

- Prompt I complete (291 tests, `/submit/` and `/poll/` endpoints live)
- Prompt J complete (app merged into crm_apis, deployed to production)
- GreyLabs credentials in `.envs/.production/.django`

---

## Phase 1 — Configure GreyLabs credentials

Set these in `.envs/.production/.django` (or your production secret store):

```ini
SPEECH_PROVIDER_API_KEY=<GreyLabs API key from Kanishk>
SPEECH_PROVIDER_API_SECRET=<GreyLabs API secret from Kanishk>
SPEECH_PROVIDER_TEMPLATE_ID=1588
SPEECH_PROVIDER_CALLBACK_URL=https://<your-production-domain>/audit/webhook/provider/
```

Restart the server after setting env vars.

**Verify connection:**
```bash
curl -X GET https://<your-domain>/audit/recordings/ \
  -H "Authorization: Token <admin-token>"
```
Should return 200 with a (possibly empty) recordings list.

---

## Phase 2 — Load 10–20 calls into the system

### Option A — Sync from call_logs table (preferred)

Trigger via HTTP:
```bash
curl -X POST https://<your-domain>/audit/recordings/sync/ \
  -H "Authorization: Token <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"date": "2026-04-07"}'
```

Returns: `{"synced": N, "skipped": N, "errors": N}`

Use any date that has real calls in the `call_logs` table. Aim for a date with 10–20 records.

### Option B — CSV import

Download 10–20 rows from your call_logs table, save as `uat_calls.csv` with these columns:

```
call_id, agent_id, customer_id, call_date, call_duration_seconds, recording_url, loan_account_number
```

Upload via HTTP:
```bash
curl -X POST https://<your-domain>/audit/recordings/import/ \
  -H "Authorization: Token <admin-token>" \
  -F "file=@uat_calls.csv"
```

---

## Phase 3 — Verify calls are pending

```bash
curl -X GET "https://<your-domain>/audit/recordings/?status=pending" \
  -H "Authorization: Token <admin-token>"
```

Should show 10–20 recordings with `"status": "pending"`.

---

## Phase 4 — Submit to GreyLabs

```bash
curl -X POST https://<your-domain>/audit/recordings/submit/ \
  -H "Authorization: Token <admin-token>"
```

Returns: `{"submitted": N, "failed": 0}`

- `submitted` = recordings sent to GreyLabs (status changes to `submitted`)
- `failed` = recordings that errored (check server logs if > 0)

Check status:
```bash
curl -X GET "https://<your-domain>/audit/recordings/?status=submitted" \
  -H "Authorization: Token <admin-token>"
```

---

## Phase 5 — Wait for webhooks

GreyLabs will POST results to `https://<your-domain>/audit/webhook/provider/` as they complete.

Each webhook call will:
1. Update the recording status to `scored`
2. Store raw provider output
3. Trigger compliance scoring

Monitor progress:
```bash
curl -X GET "https://<your-domain>/audit/recordings/?status=scored" \
  -H "Authorization: Token <admin-token>"
```

GreyLabs typically responds within a few minutes per call. Wait 15–30 minutes for the batch.

---

## Phase 6 — Poll if any are stuck

If recordings remain in `submitted` status after 30+ minutes:

```bash
# Dry run first — see what would be polled
curl -X POST https://<your-domain>/audit/recordings/poll/ \
  -H "Authorization: Token <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'

# Actually poll
curl -X POST https://<your-domain>/audit/recordings/poll/ \
  -H "Authorization: Token <admin-token>"
```

Returns: `{"polled": N, "recovered": N, "still_processing": N, "errors": N, "dry_run": false, "threshold_minutes": 30}`

---

## Phase 7 — Inspect results

Check a single recording in detail:
```bash
curl -X GET https://<your-domain>/audit/recordings/<recording_id>/ \
  -H "Authorization: Token <admin-token>"
```

Look for:
- `"status": "scored"` — provider results received
- `"provider_score"` — GreyLabs raw score
- `"own_llm_score"` — our compliance score (if LLM scoring triggered)

---

## Phase 8 — Check compliance flags

```bash
curl -X GET "https://<your-domain>/audit/compliance-flags/?recording_id=<id>" \
  -H "Authorization: Token <admin-token>"
```

Each flag has:
- `parameter_name` — which of the 19 scorecard parameters
- `flag_type` — `fatal` / `warning` / `info`
- `value` — raw extracted value
- `score` — points awarded

Check the dashboard summary for aggregate stats:
```bash
curl -X GET https://<your-domain>/audit/dashboard/summary/ \
  -H "Authorization: Token <admin-token>"
```

---

## Full endpoint reference

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/audit/recordings/` | GET | Admin/Manager | List recordings (filter by `?status=`) |
| `/audit/recordings/<id>/` | GET | Admin/Manager | Single recording detail |
| `/audit/recordings/import/` | POST | Admin/Manager | CSV/Excel import |
| `/audit/recordings/sync/` | POST | Admin/Supervisor | Sync from call_logs for a date |
| `/audit/recordings/submit/` | POST | Admin/Manager | Submit pending to GreyLabs |
| `/audit/recordings/poll/` | POST | Admin/Manager | Poll stuck recordings |
| `/audit/webhook/provider/` | POST | None (provider) | Receive GreyLabs callbacks |
| `/audit/compliance-flags/` | GET | Admin/Manager | List compliance flags |
| `/audit/dashboard/summary/` | GET | Admin/Manager | Aggregate stats |

---

## Troubleshooting

**`submitted: 0` on submit call**
- Check recordings are actually in `pending` status
- Check `SPEECH_PROVIDER_API_KEY` / `SPEECH_PROVIDER_API_SECRET` are set correctly
- Check server logs for `speech_provider` errors

**Webhooks not arriving**
- Confirm `SPEECH_PROVIDER_CALLBACK_URL` points to the correct production domain with `/audit/webhook/provider/`
- Confirm the URL is publicly reachable (not localhost)
- Use the poll endpoint as fallback

**`failed > 0` on submit**
- Check the recording has a valid `recording_url` (accessible MP3)
- Check GreyLabs rate limit (200 requests/min max per their spec)

**Compliance flags missing after scoring**
- Check `fatal_level_rules.yaml` and `compliance_rules.yaml` are present in `config/`
- Check server logs for compliance scoring errors
