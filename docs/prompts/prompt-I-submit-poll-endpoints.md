# Prompt I — Submit & Poll HTTP Endpoints

**Project:** Baysys-AI-Call-Auditor
**Branch:** work in the current branch
**Depends on:** Prompt H complete (283 tests passing)
**Expected outcome:** ~291 tests passing, 0 ruff findings

---

## Context

Two operational actions currently exist only as management commands:
- `submit_pending_recordings()` in `services.py` — submits `pending` recordings to GreyLabs
- `poll_stuck_recordings` management command — polls provider for recordings stuck in `submitted`

For GreyLabs UAT and ongoing operations, both need HTTP endpoints so they can be triggered without a shell on the server. The endpoints must be Admin/Manager-only (same RBAC as `RecordingImportView`).

---

## Task 1 — Extract polling logic into services.py

In `baysys_call_audit/services.py`, add a new function `run_poll_stuck_recordings()` that contains the core logic currently in the management command's `handle()` method.

**Signature:**
```python
def run_poll_stuck_recordings(
    batch_size: int = 50,
    dry_run: bool = False,
) -> dict:
    """
    Poll the provider for recordings stuck in status=submitted.

    Returns a summary dict:
        {
            "polled": int,
            "recovered": int,
            "still_processing": int,
            "errors": int,
            "dry_run": bool,
            "threshold_minutes": int,
        }
    """
```

The management command's `handle()` should be refactored to call `run_poll_stuck_recordings()` and print the returned summary — no logic duplication.

Add `@newrelic.agent.background_task()` decorator to `run_poll_stuck_recordings`.

---

## Task 2 — Add two views in views.py

### SubmitRecordingsView

```
POST /audit/recordings/submit/
```

- Permission: `IsAuthenticated` + `IsAdminOrManager` (same as `RecordingImportView`)
- Calls `submit_pending_recordings()` from services
- Returns 200 with JSON: `{"submitted": <count>, "failed": <count>}`
- On exception: 500 with `{"error": "<message>"}`
- Add `newrelic.agent.add_custom_attributes([("endpoint", "submit_recordings")])` at entry

### PollStuckRecordingsView

```
POST /audit/recordings/poll/
```

- Permission: `IsAuthenticated` + `IsAdminOrManager`
- Accepts optional JSON body: `{"batch_size": int, "dry_run": bool}` (both default if omitted)
- Calls `run_poll_stuck_recordings(batch_size=..., dry_run=...)`
- Returns 200 with the summary dict from `run_poll_stuck_recordings`
- On exception: 500 with `{"error": "<message>"}`
- Add `newrelic.agent.add_custom_attributes([("endpoint", "poll_stuck_recordings")])` at entry

Update the views.py module docstring to list both new views.

---

## Task 3 — Register URLs in urls.py

```python
path("recordings/submit/", SubmitRecordingsView.as_view(), name="submit-recordings"),
path("recordings/poll/", PollStuckRecordingsView.as_view(), name="poll-stuck-recordings"),
```

Import both views in the `from .views import (...)` block.

---

## Task 4 — Tests: test_submit_api.py

Create `baysys_call_audit/tests/test_submit_api.py` with ~8 tests covering:

1. `POST /audit/recordings/submit/` as Admin → 200, returns `{"submitted": N, "failed": 0}`
2. `POST /audit/recordings/submit/` as unauthenticated → 401
3. `POST /audit/recordings/submit/` as Agent (non-admin) → 403
4. `POST /audit/recordings/submit/` when `submit_pending_recordings` raises → 500 with error key
5. `POST /audit/recordings/poll/` as Admin → 200, returns summary dict with expected keys
6. `POST /audit/recordings/poll/` with `{"dry_run": true}` → 200, `dry_run` in response
7. `POST /audit/recordings/poll/` as unauthenticated → 401
8. `POST /audit/recordings/poll/` when `run_poll_stuck_recordings` raises → 500 with error key

---

## Acceptance criteria

- `python -m pytest baysys_call_audit/tests/ -q` → `Ran 294 tests in ...`, 0 failures
- `ruff check .` → 0 findings
- `curl -X POST http://localhost:8000/audit/recordings/submit/ -H "Authorization: Token <admin-token>"` returns JSON
- `curl -X POST http://localhost:8000/audit/recordings/poll/ -H "Authorization: Token <admin-token>" -d '{"dry_run": true}'` returns summary JSON

---

## Files to touch

| File | Change |
|---|---|
| `baysys_call_audit/services.py` | Add `run_poll_stuck_recordings()` |
| `baysys_call_audit/management/commands/poll_stuck_recordings.py` | Refactor `handle()` to call `run_poll_stuck_recordings()` |
| `baysys_call_audit/views.py` | Add `SubmitRecordingsView`, `PollStuckRecordingsView` |
| `baysys_call_audit/urls.py` | Add 2 URL patterns |
| `baysys_call_audit/tests/test_submit_api.py` | New file, ~8 tests |
| `MANIFEST.md` | Add `test_submit_api.py` row, update total to 291 |
| `BUILD_LOG.md` | Add Prompt I entry |
| `CLAUDE.md` | Test gate 283 → 291 |

Do NOT touch `crm_adapter.py`, migrations, or settings.
