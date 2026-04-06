# Prompt J — crm_apis Merge

**Project:** crm_apis repo (`Pilot1940/crm_apis` or local equivalent)
**Branch:** `call-auditor` — create this branch fresh from `main`; never work on `main` or any currently-checked-out branch
**Depends on:** Prompt I complete (291 tests passing in standalone repo)
**Expected outcome:** `call-auditor` branch ready for PR; full test suite passes

---

## Context

The Voice Trainer app lives in `crm_apis` as `arc/baysys_trainer/`, registered as `"arc.baysys_trainer"` in `INSTALLED_APPS`, routed at `"trainer/"`. The Call Auditor follows the same pattern.

---

## Step 0 — Create the branch

```bash
cd <crm_apis-root>
git checkout main
git pull
git checkout -b call-auditor
```

Never commit to `main`, `master`, or whatever branch was previously checked out. All work goes on `call-auditor`.

---

## Step 1 — Copy the app

```bash
cp -r <path-to-Baysys-AI-Call-Auditor>/baysys_call_audit/ arc/baysys_call_audit/
```

---

## Step 2 — Fix apps.py

In `arc/baysys_call_audit/apps.py`, change:

```python
# Before
name = "baysys_call_audit"

# After
name = "arc.baysys_call_audit"
```

---

## Step 3 — Copy config YAMLs

```bash
cp <path-to-Baysys-AI-Call-Auditor>/config/compliance_rules.yaml  config/
cp <path-to-Baysys-AI-Call-Auditor>/config/fatal_level_rules.yaml  config/
cp <path-to-Baysys-AI-Call-Auditor>/config/submission_priority.yaml  config/
cp <path-to-Baysys-AI-Call-Auditor>/config/holidays_in.yaml  config/
```

(Copy all YAML files from the standalone repo's `config/` directory.)

---

## Step 4 — Fix config path bug in ingestion.py

`arc/baysys_call_audit/ingestion.py` currently uses:

```python
_SUBMISSION_PRIORITY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "config",
    "submission_priority.yaml",
)
```

In the crm_apis layout `__file__` is `arc/baysys_call_audit/ingestion.py`, so `dirname(dirname(__file__))` resolves to `arc/` — not the repo root where `config/` lives.

Replace with the same pattern used in `compliance.py`:

```python
from django.conf import settings as django_settings
from pathlib import Path

_SUBMISSION_PRIORITY_PATH = Path(django_settings.BASE_DIR) / "config" / "submission_priority.yaml"
```

Remove the `os.path` import line if it is no longer used elsewhere in the file.

---

## Step 5 — Register in INSTALLED_APPS

In `config/settings/base.py` (or wherever `INSTALLED_APPS` lives), add after the Trainer entry:

```python
"arc.baysys_call_audit",
```

---

## Step 6 — Add environment variables

In `.envs/.production/.django` (and `.envs/.local/.django`), add after the `TRAINER_AUTH_BACKEND` block:

```ini
# Call Auditor
AUDIT_AUTH_BACKEND=crm
AUDIT_URL_SECRET=<generate a UUID — keep secret, this is part of every endpoint URL>
SPEECH_PROVIDER_API_KEY=<from GreyLabs>
SPEECH_PROVIDER_API_SECRET=<from GreyLabs>
SPEECH_PROVIDER_TEMPLATE_ID=1588
SPEECH_PROVIDER_CALLBACK_URL=https://<production-domain>/audit/<AUDIT_URL_SECRET>/webhook/provider/
```

For local `.envs/.local/.django`, set `AUDIT_AUTH_BACKEND=mock` and any `AUDIT_URL_SECRET` value.

---

## Step 7 — Wire up URLs

In `config/urls.py`, add alongside the Trainer route:

```python
from django.conf import settings
path(f"audit/{settings.AUDIT_URL_SECRET}/", include("arc.baysys_call_audit.urls")),
```

Also add to `config/settings/base.py`:
```python
AUDIT_URL_SECRET = env("AUDIT_URL_SECRET", default="dev-secret")
```

---

## Step 8 — Verify crm_adapter import paths

Open `arc/baysys_call_audit/crm_adapter.py`. Confirm that any CRM model imports are inside function bodies with `# noqa: PLC0415`. No top-level CRM imports.

---

## Step 9 — Run migrations

```bash
python manage.py migrate baysys_call_audit
```

Verify all 4 migrations apply cleanly (0001–0004).

---

## Step 10 — Run the test suite

```bash
python -m pytest arc/baysys_call_audit/tests/ -q
ruff check arc/baysys_call_audit/
```

All 291 tests must pass, 0 ruff findings.

---

## Step 11 — Commit

```bash
git add arc/baysys_call_audit/ config/*.yaml config/settings/base.py config/urls.py
git commit -m "feat: merge baysys_call_audit into crm_apis (Prompt J)"
```

Do NOT push to `main`. Open a PR from `call-auditor` → `main` for review.

---

## Files touched in crm_apis

| File | Change |
|---|---|
| `arc/baysys_call_audit/` | New directory — full app copy |
| `arc/baysys_call_audit/apps.py` | `name` → `"arc.baysys_call_audit"` |
| `arc/baysys_call_audit/ingestion.py` | Fix `_SUBMISSION_PRIORITY_PATH` to use `settings.BASE_DIR` |
| `config/*.yaml` | Copy 4 YAML files from standalone repo |
| `config/settings/base.py` | Add `"arc.baysys_call_audit"` to `INSTALLED_APPS` + `AUDIT_URL_SECRET` setting |
| `config/urls.py` | Add `path(f"audit/{settings.AUDIT_URL_SECRET}/", include(...))` |
| `.envs/.production/.django` | Add 6 Call Auditor env vars (includes `AUDIT_URL_SECRET`) |
| `.envs/.local/.django` | Add `AUDIT_AUTH_BACKEND=mock` + `AUDIT_URL_SECRET` + placeholder vars |

Do NOT modify `arc/baysys_trainer/` or any Trainer files.
Do NOT commit to `main` or `master`.
