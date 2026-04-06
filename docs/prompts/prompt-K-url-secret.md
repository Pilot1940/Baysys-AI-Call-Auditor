# Prompt K — URL Secret Prefix

**Project:** Baysys-AI-Call-Auditor
**Branch:** work in the current branch
**Depends on:** Prompt I complete (294 tests passing)
**Expected outcome:** All endpoints hidden behind a secret URL segment; tests still pass

---

## Context

All audit endpoints — including the `AllowAny` webhook — should be unreachable without knowing a secret URL segment. The secret lives in an env var and is injected as a URL prefix at the root routing level. No changes are needed inside `baysys_call_audit/urls.py`.

Current root `urls.py`:
```python
path("audit/", include("baysys_call_audit.urls")),
```

Target:
```python
path(f"audit/{settings.AUDIT_URL_SECRET}/", include("baysys_call_audit.urls")),
```

With a random UUID secret, the webhook URL becomes e.g.:
`/audit/a3f9c2d1-7b4e-4f8a-9c1d-2e5f6a7b8c9d/webhook/provider/`

---

## Task 1 — Add setting

In `baysys_call_audit/settings.py` (or wherever Django settings live for this standalone repo), add:

```python
AUDIT_URL_SECRET = env("AUDIT_URL_SECRET", default="dev-secret")
```

---

## Task 2 — Update root urls.py

In the repo root `urls.py`:

```python
from django.conf import settings

urlpatterns = [
    path("admin/", admin.site.urls),
    path(f"audit/{settings.AUDIT_URL_SECRET}/", include("baysys_call_audit.urls")),
]
```

---

## Task 3 — Add to .env.example

```ini
# URL secret — all audit endpoints are prefixed with this segment
# Use a long random string (e.g. uuid4). Keep secret.
AUDIT_URL_SECRET=<generate-a-uuid>
```

---

## Task 4 — Update SPEECH_PROVIDER_CALLBACK_URL

In `.env.example` and `.envs/.production/.django`, update the callback URL comment to note the secret must be included:

```ini
# Must include the AUDIT_URL_SECRET segment:
# e.g. https://<domain>/audit/<AUDIT_URL_SECRET>/webhook/provider/
SPEECH_PROVIDER_CALLBACK_URL=https://<your-production-domain>/audit/<AUDIT_URL_SECRET>/webhook/provider/
```

---

## Task 5 — Verify tests still pass

Tests use `reverse("baysys_call_audit:<name>")` which is unaffected by the URL prefix. No test changes should be needed.

Run:
```bash
python -m pytest baysys_call_audit/tests/ -q
ruff check .
```

All 294 tests must pass, 0 ruff findings.

---

## Files to touch

| File | Change |
|---|---|
| `urls.py` (repo root) | Inject `AUDIT_URL_SECRET` into path prefix |
| `baysys_call_audit/settings.py` | Add `AUDIT_URL_SECRET = env(...)` |
| `.env.example` | Add `AUDIT_URL_SECRET` + update `SPEECH_PROVIDER_CALLBACK_URL` comment |
| `MANIFEST.md` | Note URL secret in env vars section |
| `BUILD_LOG.md` | Add Prompt K entry |
| `CLAUDE.md` | Note `AUDIT_URL_SECRET` in env vars section |

Do NOT touch `baysys_call_audit/urls.py` — the prefix is applied at the root level only.
Do NOT touch any test files unless a test is hardcoding `/audit/` paths (check first; use `reverse()` if so).
