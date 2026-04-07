# BaySys Call Audit AI — Deployment Next Steps

**Date:** 2026-04-07

## Project status

**Build complete**
- 317 automated tests, 0 linting issues. Prompts A–P done. Backend, CRM embed, and crm_apis sync all committed and pushed.

**Three PRs ready to merge — in order**
1. `crm_apis`: `call-auditor → master` — backend app, config YAML, all endpoints
2. `crm` (frontend): `call-audit-frontend-embed → master` — admin UI embed
3. After merge: set 4 env vars on the server, run migrations (0001–0004), restart

**Data is live — no import needed**
- Calls are already in `uvarcl_live` (Supabase production). Once deployed, a single sync command pulls today's calls by date — no CSV, no manual load.

**First live call push to GreyLabs**
- Sync 10 calls → submit → GreyLabs transcribes and scores → webhooks fire back within 15–30 mins → compliance flags visible immediately.

**What the product team gets in Phase 1 UI**
- Recordings list with status, agent, tier, fatal level, and compliance flags
- Call detail page with audio player — plays the actual recorded call
- Metadata compliance flags already visible: calling hours violations, Sunday calls, public holiday calls, max-calls-per-customer breaches
- Transcript and AI scores populate automatically once GreyLabs processes the call — no action needed from the team
- No curl commands or secret tokens required — standard login, role-based access

---

## Step 1 — Developer: Merge the PR into crm_apis master

Branch `call-auditor` is fully built and pushed. PR from `call-auditor → master` is open and unblocked. **Merge it.**

317 tests passing, 0 ruff findings. All 5 commits are on the branch: Prompt J (app merge into `arc/baysys_call_audit/`), env templates, Prompt P (final prompt sync), and the `.envs` doc commit.

After merging, confirm tests still pass on master:

```bash
# In the crm_apis repo, on master after merge
python -m pytest arc/baysys_call_audit/tests/ -q
ruff check arc/baysys_call_audit/
```

**Do NOT deploy to production until Step 2 (env vars) is complete.**

---

## Step 2 — DevOps/PC: Set environment variables in production

Add these to the production environment (`.envs/.production/.django` or your secret manager) **after** the existing `TRAINER_AUTH_BACKEND` block:

```ini
# BaySys Call Audit AI
AUDIT_AUTH_BACKEND=crm

# URL secret — all audit endpoints are unreachable without this segment in the path
# Generate with: python3 -c "import uuid; print(uuid.uuid4())"
AUDIT_URL_SECRET=<generate-a-uuid-and-keep-it-secret>

# Health check token — separate from the URL secret
# Generate with: python3 -c "import uuid; print(uuid.uuid4())"
AUDIT_STATUS_SECRET=<generate-a-second-uuid-and-keep-it-secret>

# GreyLabs credentials — from Kanishk Gunsola at GreyLabs
SPEECH_PROVIDER_API_KEY=<from GreyLabs>
SPEECH_PROVIDER_API_SECRET=<from GreyLabs>
SPEECH_PROVIDER_TEMPLATE_ID=1588

# Webhook URL — must include the AUDIT_URL_SECRET segment
# Replace <domain> with production domain and <AUDIT_URL_SECRET> with the value above
SPEECH_PROVIDER_CALLBACK_URL=https://<domain>/audit/<AUDIT_URL_SECRET>/webhook/provider/
```

**Note:** `AUDIT_URL_SECRET` appears in every API URL. Keep it secret. If it's ever compromised, rotate it (one env var change + server restart — no code change needed).

---

## Step 3 — Developer: Merge and deploy CRM frontend embed

Branch `call-audit-frontend-embed` is complete and pushed. PR from `call-audit-frontend-embed → master` is open. **Merge it after Step 2** — the frontend needs the `AUDIT_URL_SECRET` value you generated above.

After merging, set the frontend env var:

```bash
# In the crm (frontend) repo, in the production .env
VITE_AUDIT_URL_SECRET=<same value as AUDIT_URL_SECRET from Step 2>
```

Then trigger a frontend rebuild and deploy. The admin UI embed will be live once the build is deployed.

**Verify:** Log into the CRM admin UI — the Call Audit section should be visible in the nav. Recordings list may be empty at this point; that's expected until calls are synced in Step 7.

---

## Step 4 — Run database migrations

After deploying the backend code:

```bash
python manage.py migrate baysys_call_audit
```

This applies migrations 0001–0004. Idempotent — safe to re-run.

Confirm all 4 are applied:
```bash
python manage.py showmigrations baysys_call_audit
```

Expected output:
```
baysys_call_audit
 [X] 0001_initial
 [X] 0002_...
 [X] 0003_...
 [X] 0004_...
```

---

## Step 5 — Restart and smoke test

Restart the production server, then run these checks (replace `<S>` with the value of `AUDIT_URL_SECRET`, `<TOKEN>` with an admin auth token):

```bash
# Health check — should return JSON with migrations, backend git info, recording activity
curl "https://<domain>/audit/<S>/admin/status/?token=<AUDIT_STATUS_SECRET>"

# API connectivity — should return 200 with empty recordings list
curl "https://<domain>/audit/<S>/recordings/" \
  -H "Authorization: Token <TOKEN>"

# Confirm webhook URL is reachable (GreyLabs will POST here)
curl -X POST "https://<domain>/audit/<S>/webhook/provider/" \
  -H "Content-Type: application/json" \
  -d '{}'
# Expected: 400 (bad payload) — confirms the URL is live and routing correctly
```

If health check returns 200 with `"pending_migrations": []` — ready for UAT.

---

## Step 6 — GreyLabs UAT (10–20 calls)

Full instructions: `docs/uat-greylabs-instructions.md`

Quick sequence:
1. Sync calls from `call_logs` — `POST /audit/<S>/recordings/sync/` with `{"date": "YYYY-MM-DD"}` (calls are already in `uvarcl_live` — no CSV needed)
2. Confirm synced calls are pending — `GET /audit/<S>/recordings/?status=pending`
3. Submit to GreyLabs — `POST /audit/<S>/recordings/submit/`
4. Wait 15–30 minutes for webhook callbacks — monitor with `GET /audit/<S>/recordings/?status=completed`
5. If any stuck after 30 min: `POST /audit/<S>/recordings/poll/`
6. Check scores and compliance flags: `GET /audit/<S>/recordings/<id>/`

---

## Full endpoint reference

All paths require `AUDIT_URL_SECRET` as `<S>`.

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /audit/<S>/webhook/provider/` | None (GreyLabs posts here) | Receive provider results |
| `GET /audit/<S>/recordings/` | Token | List recordings |
| `GET /audit/<S>/recordings/<id>/` | Token | Recording detail |
| `POST /audit/<S>/recordings/import/` | Admin/Manager | CSV/Excel upload |
| `POST /audit/<S>/recordings/sync/` | Admin/Supervisor | Trigger daily sync |
| `POST /audit/<S>/recordings/submit/` | Admin/Manager | Submit pending to GreyLabs |
| `POST /audit/<S>/recordings/poll/` | Admin/Manager | Poll stuck recordings |
| `GET /audit/<S>/dashboard/summary/` | Token | Aggregate stats |
| `GET /audit/<S>/compliance-flags/` | Token | Compliance flag list |
| `GET /audit/<S>/admin/status/?token=<AUDIT_STATUS_SECRET>` | URL token | Health check |

---

## What's in the code

- **10 API endpoints** covering ingestion, submission, webhook, dashboard, and ops
- **317 automated tests**, 0 linting issues
- **Config-driven compliance engine** — rules in `config/compliance_rules.yaml`, no code changes needed to adjust thresholds
- **Fatal level scoring** (0–5) — weighted boolean parameters from `config/fatal_level_rules.yaml`
- **New Relic APM** instrumented — all pipeline operations tracked as named transactions
- **Submission tiers** (immediate/normal/off_peak) — assigned at ingestion, separate cron schedules per tier
- **GreyLabs adapter** in `speech_provider.py` — swappable if provider changes

---

## Step 7 — Push 10 calls to GreyLabs today

Do this after Steps 1–5 are complete and GreyLabs credentials are in production. Calls are already live in the `uvarcl_live` Supabase schema — sync directly from `call_logs`, no CSV needed.

> **All of this can be done via the Admin UI — no curl required.** Log in to the CRM as an Admin, navigate to "Call Audit" in the nav, and use the Operations panel (Sync date → Submit pending calls → Recover stuck calls) and the recordings table/call detail pages. Full UI walkthrough: `docs/uat-greylabs-instructions.md` → "Doing the UAT via the Admin UI".

The curl commands below are for reference or if you need to script/debug any step.

Replace `<S>` with your `AUDIT_URL_SECRET` and `<TOKEN>` with an admin auth token throughout.

### 1. Sync 10 calls from call_logs

**Via UI:** Operations panel → "Sync date" → pick date → click Sync. Stats bar shows how many were created.

**Via curl:**
```bash
curl -X POST https://<domain>/audit/<S>/recordings/sync/ \
  -H "Authorization: Token <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"date": "2026-04-07"}'
```

Returns: `{"total_fetched": N, "created": N, "skipped_dedup": N, "skipped_validation": N, "errors": N}` — aim for `created` ≥ 10.

### 2. Confirm they're pending

**Via UI:** Check the **Pending** card in the pipeline stats bar — should show ≥ 10.

**Via curl:**
```bash
curl "https://<domain>/audit/<S>/recordings/?status=pending" \
  -H "Authorization: Token <TOKEN>"
```

### 3. Submit to GreyLabs

**Via UI:** Click **"Submit pending calls"** in the Operations panel (disabled if Pending = 0). Toast confirms how many were submitted.

**Via curl:**
```bash
curl -X POST https://<domain>/audit/<S>/recordings/submit/ \
  -H "Authorization: Token <TOKEN>"
```

Returns: `{"submitted": 10, "failed": 0}` — if `failed > 0`, check server logs for `speech_provider` errors. Status changes to `submitted`.

### 4. Wait 15–30 minutes

**Via UI:** Watch the stats bar — **In queue** drops and **Scored** rises as GreyLabs processes calls. The recordings table updates in real time with score badges.

**Via curl:**
```bash
curl "https://<domain>/audit/<S>/recordings/?status=completed" \
  -H "Authorization: Token <TOKEN>"
```

### 5. Poll if any are stuck

**Via UI:** Click **"Recover stuck calls"** in the Operations panel. Tick dry-run first to preview, then run it.

**Via curl:**
```bash
curl -X POST https://<domain>/audit/<S>/recordings/poll/ \
  -H "Authorization: Token <TOKEN>"
```

Returns: `{"polled": N, "recovered": N, "still_processing": N, "errors": N}`

### 6. Check a result

**Via UI:** Click any row in the recordings table to open the call detail page — audio player, metadata compliance flags, scorecard (19 parameters), and full transcript.

**Via curl:**
```bash
curl "https://<domain>/audit/<S>/recordings/<recording_id>/" \
  -H "Authorization: Token <TOKEN>"
```

Look for `"status": "completed"` and a populated `provider_score`. Compliance flags:

```bash
curl "https://<domain>/audit/<S>/compliance-flags/?recording_id=<id>" \
  -H "Authorization: Token <TOKEN>"
```

### 7. Dashboard summary

**Via UI:** Stats bar and agent leaderboard tab on the dashboard.

**Via curl:**
```bash
curl "https://<domain>/audit/<S>/dashboard/summary/" \
  -H "Authorization: Token <TOKEN>"
```

**Troubleshooting**
- `submitted: 0` → check recordings are actually `pending`; check `SPEECH_PROVIDER_API_KEY` / `SPEECH_PROVIDER_API_SECRET` are set
- Webhooks not arriving → confirm `SPEECH_PROVIDER_CALLBACK_URL` points to the correct production domain and is publicly reachable; use poll as fallback
- `failed > 0` → check `recording_url` is a valid accessible MP3; check GreyLabs rate limit (200 req/min max)
