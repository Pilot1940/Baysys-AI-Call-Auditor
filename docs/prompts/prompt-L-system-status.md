# Prompt L — System Status / Health Check Endpoint

**Project:** Baysys-AI-Call-Auditor
**Branch:** work in the current branch
**Depends on:** Prompt K complete (294 tests, AUDIT_URL_SECRET in place)
**Actual outcome:** 302 tests passing, 0 ruff findings. Note: `_build_recording_activity()` uses `status="completed"` / `completed_at` (not `scored`/`scored_at` — those fields don't exist). Auth via `getattr(settings, 'AUDIT_STATUS_SECRET', '')` so `override_settings` works in tests.

---

## Context

The Voice Trainer has a `SystemStatusView` at `GET /trainer/admin/status/?token=<SYNC_PROMPTS_SECRET>` that returns a JSON health snapshot: migrations, backend git info, frontend build hash, call activity metrics, and env var presence flags. It also fires a `BaySysSystemStatus` New Relic custom event.

Add an equivalent for the Call Auditor. Because all audit URLs are behind `AUDIT_URL_SECRET`, the status endpoint is already hidden. The `?token=` query param provides a second auth layer so monitoring tools can hit it with a stable secret independent of the URL secret.

**URL:** `GET audit/<AUDIT_URL_SECRET>/admin/status/?token=<AUDIT_STATUS_SECRET>`

---

## Task 1 — Add AUDIT_STATUS_SECRET setting

In `baysys_call_audit/settings.py` (or wherever Django settings live for this standalone repo), add:

```python
AUDIT_STATUS_SECRET = env("AUDIT_STATUS_SECRET", default="dev-status-secret")
```

Add to `.env.example`:
```ini
# Health check token — used for GET /audit/<URL_SECRET>/admin/status/?token=<this>
AUDIT_STATUS_SECRET=<generate a separate long random string>
```

---

## Task 2 — Helper functions in views.py

Add before `SystemStatusView` at the bottom of `views.py`:

### _build_recording_activity()

```python
def _build_recording_activity() -> dict:
    """Return recording activity metrics. Returns null values on DB error."""
    from django.db.models.functions import TruncHour  # noqa: PLC0415

    now = timezone.now()
    today = now.date()
    week_start = today - _date.resolution * today.weekday()  # Monday
    try:
        scored = CallRecording.objects.filter(status="scored")
        recordings_today = scored.filter(scored_at__date=today).count()
        recordings_this_week = scored.filter(scored_at__date__gte=week_start).count()
        recordings_this_month = scored.filter(
            scored_at__year=today.year, scored_at__month=today.month
        ).count()
        last_ts = (
            scored.order_by("-scored_at")
            .values_list("scored_at", flat=True)
            .first()
        )
        last_scored = last_ts.isoformat() if last_ts else None
        pending_count = CallRecording.objects.filter(status="pending").count()
        submitted_count = CallRecording.objects.filter(status="submitted").count()
        # Hourly breakdown for today
        hourly_qs = (
            scored.filter(scored_at__date=today)
            .annotate(hour=TruncHour("scored_at"))
            .values("hour")
            .annotate(cnt=Count("call_id"))
        )
        hourly: dict[str, int] = {f"{h:02d}": 0 for h in range(24)}
        for row in hourly_qs:
            if row["hour"] is not None:
                h_key = f"{row['hour'].hour:02d}"
                hourly[h_key] = row["cnt"]
    except Exception:  # noqa: BLE001
        logger.warning("SystemStatusView: recording_activity DB query failed", exc_info=True)
        recordings_today = None
        recordings_this_week = None
        recordings_this_month = None
        last_scored = None
        pending_count = None
        submitted_count = None
        hourly = None
    return {
        "recordings_today": recordings_today,
        "recordings_this_week": recordings_this_week,
        "recordings_this_month": recordings_this_month,
        "last_scored": last_scored,
        "pending": pending_count,
        "submitted": submitted_count,
        "hourly_today": hourly,
    }
```

`scored_at` may not exist on the model — if the field is named differently (e.g. `updated_at`), use that. Check `models.py` before writing this function and use the correct field name for when a recording was last updated to `scored` status.

### _AUDIT_ENV_VAR_KEYS

```python
_AUDIT_ENV_VAR_KEYS = [
    "AUDIT_AUTH_BACKEND",
    "AUDIT_URL_SECRET",
    "AUDIT_STATUS_SECRET",
    "SPEECH_PROVIDER_API_KEY",
    "SPEECH_PROVIDER_API_SECRET",
    "SPEECH_PROVIDER_TEMPLATE_ID",
    "SPEECH_PROVIDER_CALLBACK_URL",
    "NEW_RELIC_INSERT_KEY",
    "NEW_RELIC_LICENSE_KEY",
    "NEW_RELIC_ACCOUNT_ID",
    "GIT_COMMIT_HASH",
    "GIT_BRANCH",
    "DATABASE_URL",
    "SECRET_KEY",
]
```

### _fire_nr_audit_status_event()

```python
def _fire_nr_audit_status_event(data: dict) -> None:
    """POST a BaySysAuditSystemStatus event to New Relic Insights API. Silent no-op on failure."""
    import requests as _requests  # noqa: PLC0415

    nr_key = os.environ.get("NEW_RELIC_INSERT_KEY") or os.environ.get("NEW_RELIC_LICENSE_KEY", "")
    nr_account = os.environ.get("NEW_RELIC_ACCOUNT_ID", "")
    if not nr_key or not nr_account:
        return
    ra = data["recording_activity"]
    event = {
        "eventType": "BaySysAuditSystemStatus",
        "git_commit": data["backend"]["git_commit"],
        "git_branch": data["backend"]["git_branch"],
        "frontend_build_hash": data["frontend"]["build_hash"],
        "latest_migration": data["migrations"]["latest_applied"],
        "pending_migrations": len(data["migrations"]["pending"]),
        "recordings_today": ra["recordings_today"],
        "recordings_this_week": ra["recordings_this_week"],
        "last_scored": ra["last_scored"],
        "pending": ra["pending"],
        "submitted": ra["submitted"],
    }
    url = f"https://insights-collector.newrelic.com/v1/accounts/{nr_account}/events"
    headers = {"Content-Type": "application/json", "X-Insert-Key": nr_key}
    try:
        _requests.post(url, json=[event], headers=headers, timeout=5)
    except Exception:  # noqa: BLE001
        logger.debug("NR audit status event failed", exc_info=True)
```

---

## Task 3 — SystemStatusView in views.py

Add at the bottom of `views.py` (after the helpers above):

```python
class SystemStatusView(View):
    """
    GET /audit/<URL_SECRET>/admin/status/?token=<AUDIT_STATUS_SECRET>

    Read-only system health snapshot. Token auth via query param so the
    endpoint is navigable directly in a browser or monitoring tool.
    Returns 403 if token is missing or wrong.
    """

    def get(self, request, *args, **kwargs):
        # ── Auth ──────────────────────────────────────────────────────────────
        expected = os.environ.get("AUDIT_STATUS_SECRET", "")
        provided = request.GET.get("token", "")
        if not expected or not hmac.compare_digest(expected, provided):
            return JsonResponse({"error": "Forbidden"}, status=403)

        # ── Migrations ────────────────────────────────────────────────────────
        from django.db import connection  # noqa: PLC0415
        from django.db.migrations.executor import MigrationExecutor  # noqa: PLC0415

        executor = MigrationExecutor(connection)
        applied = executor.loader.applied_migrations
        audit_applied = sorted(name for app, name in applied if app == "baysys_call_audit")
        latest_applied = audit_applied[-1] if audit_applied else "unknown"
        total_applied = len(audit_applied)
        pending_plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        pending = [migration.name for migration, _ in pending_plan]

        # ── Backend ───────────────────────────────────────────────────────────
        git_commit = os.environ.get("GIT_COMMIT_HASH", "unknown")
        git_branch = os.environ.get("GIT_BRANCH", "unknown")

        # ── Frontend ──────────────────────────────────────────────────────────
        version_path = os.path.join(
            settings.STATIC_ROOT or settings.BASE_DIR, "version.json"
        )
        try:
            with open(version_path) as fh:
                ver = json.load(fh)
            build_hash = ver.get("build_hash", "unknown")
            build_time = ver.get("build_time", "unknown")
        except Exception:  # noqa: BLE001
            build_hash = "unknown"
            build_time = "unknown"

        data = {
            "generated_at": timezone.now().isoformat(),
            "migrations": {
                "latest_applied": latest_applied,
                "total_applied": total_applied,
                "pending": pending,
            },
            "backend": {
                "git_commit": git_commit,
                "git_branch": git_branch,
            },
            "frontend": {
                "build_hash": build_hash,
                "build_time": build_time,
            },
            "recording_activity": _build_recording_activity(),
            "env_vars": {k: bool(os.environ.get(k, "")) for k in _AUDIT_ENV_VAR_KEYS},
        }

        _fire_nr_audit_status_event(data)

        return JsonResponse(data)
```

Add `import hmac` and `import json` to the top of `views.py` if not already present.
Add `from datetime import date as _date` if not already present.

---

## Task 4 — Register URL in urls.py

In `baysys_call_audit/urls.py`:

```python
from .views import (
    ...
    SystemStatusView,
)

urlpatterns = [
    ...
    path("admin/status/", SystemStatusView.as_view(), name="system-status"),
]
```

---

## Task 5 — Tests: test_system_status.py

Create `baysys_call_audit/tests/test_system_status.py` with ~6 tests:

1. `GET /audit/.../admin/status/?token=<correct>` → 200, response contains `migrations`, `backend`, `recording_activity`, `env_vars` keys
2. `GET .../admin/status/` with no token → 403
3. `GET .../admin/status/?token=wrong` → 403
4. `GET .../admin/status/?token=<correct>` with `AUDIT_STATUS_SECRET` unset → 403
5. `GET .../admin/status/?token=<correct>` — `recording_activity.pending` is an integer (DB query runs without error)
6. `GET .../admin/status/?token=<correct>` — `env_vars` is a dict of booleans

Use `override_settings(AUDIT_STATUS_SECRET="test-secret")` to set the token in tests.

---

## Acceptance criteria

- `python -m pytest baysys_call_audit/tests/ -q` → ~300 tests, 0 failures
- `ruff check .` → 0 findings
- `curl "http://localhost:8000/audit/<URL_SECRET>/admin/status/?token=<AUDIT_STATUS_SECRET>"` returns JSON with all expected keys
- `curl "http://localhost:8000/audit/<URL_SECRET>/admin/status/"` returns 403

---

## Files to touch

| File | Change |
|---|---|
| `baysys_call_audit/views.py` | Add `_build_recording_activity`, `_AUDIT_ENV_VAR_KEYS`, `_fire_nr_audit_status_event`, `SystemStatusView` |
| `baysys_call_audit/urls.py` | Add `admin/status/` URL pattern |
| `baysys_call_audit/settings.py` | Add `AUDIT_STATUS_SECRET` |
| `.env.example` | Add `AUDIT_STATUS_SECRET` |
| `baysys_call_audit/tests/test_system_status.py` | New file, ~6 tests |
| `MANIFEST.md` | Add `test_system_status.py` row, update total |
| `BUILD_LOG.md` | Add Prompt L entry |
| `CLAUDE.md` | Update test gate count |

Do NOT copy the Trainer's `_ENV_VAR_KEYS` list — use `_AUDIT_ENV_VAR_KEYS` with Call Auditor env vars only.
