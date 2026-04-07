# BaySys Call Audit AI — Deployment Next Steps

**Date:** 2026-04-07
**Status:** Backend complete (302 tests, 0 linting issues). Phase 1 UI in progress (Prompt M). Ready for crm_apis merge and GreyLabs UAT in parallel.

**What product team gets in Phase 1 UI:**
- Recordings list with status, agent, tier, fatal level, compliance flags
- Call detail page with audio player (plays the actual call)
- Metadata compliance flags already visible (calling hours, Sunday, holiday, max calls violations)
- Placeholder sections for transcript and scores — fill in automatically once GreyLabs processes the call
- No curl or secret tokens needed once logged in

---

## Step 1 — Developer: Merge into crm_apis ✅ COMPLETE

**Branch `call-auditor` is ready. PR from `call-auditor → master` is open. Merge when ready.**

302 tests passing, 0 ruff findings. For reference, the spec is in `Baysys-AI-Call-Auditor/docs/prompts/prompt-J-crm-apis-merge.md`.

```bash
# In the crm_apis repo
git checkout main && git pull
git checkout -b call-auditor

# Copy the app
cp -r <path-to-Baysys-AI-Call-Auditor>/baysys_call_audit/  arc/baysys_call_audit/

# Copy config files
cp <path-to-Baysys-AI-Call-Auditor>/config/*.yaml  config/

# Edit arc/baysys_call_audit/apps.py — change:
#   name = "baysys_call_audit"
# to:
#   name = "arc.baysys_call_audit"

# Edit arc/baysys_call_audit/ingestion.py — replace the _SUBMISSION_PRIORITY_PATH block:
#   from pathlib import Path
#   _SUBMISSION_PRIORITY_PATH = Path(django_settings.BASE_DIR) / "config" / "submission_priority.yaml"

# In config/settings/base.py — add to INSTALLED_APPS:
#   "arc.baysys_call_audit",
# Add setting:
#   AUDIT_URL_SECRET = env("AUDIT_URL_SECRET", default="dev-secret")
#   AUDIT_STATUS_SECRET = env("AUDIT_STATUS_SECRET", default="dev-status-secret")

# In config/urls.py — add alongside trainer route:
#   from django.conf import settings
#   path(f"audit/{settings.AUDIT_URL_SECRET}/", include("arc.baysys_call_audit.urls")),

# Verify tests pass
python -m pytest arc/baysys_call_audit/tests/ -q
ruff check arc/baysys_call_audit/

# Commit and raise PR
git add arc/baysys_call_audit/ config/*.yaml config/settings/base.py config/urls.py
git commit -m "feat: merge baysys_call_audit into crm_apis (Prompt J)"
# Raise PR: call-auditor → main
# Do NOT merge to main until env vars are confirmed in production
```

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

## Step 3 — Run database migrations

After deploying the code:

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

## Step 4 — Restart and smoke test

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

## Step 5 — GreyLabs UAT (10–20 calls)

Full instructions: `docs/uat-greylabs-instructions.md`

Quick sequence:
1. Load 10–20 calls via sync or CSV import
2. `POST /audit/<S>/recordings/submit/` — sends them to GreyLabs
3. Wait 15–30 minutes for webhook callbacks
4. If any stuck after 30 min: `POST /audit/<S>/recordings/poll/`
5. Check scores and compliance flags: `GET /audit/<S>/recordings/<id>/`

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
- **302 automated tests**, 0 linting issues
- **Config-driven compliance engine** — rules in `config/compliance_rules.yaml`, no code changes needed to adjust thresholds
- **Fatal level scoring** (0–5) — weighted boolean parameters from `config/fatal_level_rules.yaml`
- **New Relic APM** instrumented — all pipeline operations tracked as named transactions
- **Submission tiers** (immediate/normal/off_peak) — assigned at ingestion, separate cron schedules per tier
- **GreyLabs adapter** in `speech_provider.py` — swappable if provider changes
