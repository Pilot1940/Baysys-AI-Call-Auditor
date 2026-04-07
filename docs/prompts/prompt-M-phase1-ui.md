# Prompt M — Backend additions for Phase 1 UI

**Project:** Baysys-AI-Call-Auditor (standalone repo)
**Branch:** work in the current branch
**Depends on:** Prompt L complete (302 tests)
**Expected outcome:** ~315 tests, 0 ruff findings

---

## Context

Three new backend endpoints are needed to support the Phase 1 UI (Prompt N). The UI lives in the `crm` React repo — this prompt is backend only.

---

## Task 1 — Extend DashboardSummaryView

Add to the `data` dict in `DashboardSummaryView.get()`:

```python
"submitted": qs.filter(status="submitted").count(),
"last_sync_at": (
    qs.order_by("-created_at").values_list("created_at", flat=True)
    .first()
),
"last_completed_at": (
    qs.filter(status="completed").order_by("-completed_at")
    .values_list("completed_at", flat=True).first()
),
```

Convert both datetimes to `.isoformat()` if not None.

Add an `agent_summary` block for the leaderboard:

```python
from django.db.models import Avg, Count, Q  # noqa: PLC0415 (if not already at top)

agent_summary = list(
    qs.filter(status="completed")
    .values("agent_id", "agent_name")
    .annotate(
        calls=Count("id"),
        avg_score=Avg("providerscore__score_percentage"),
        fatals=Count("id", filter=Q(fatal_level__gte=3)),
    )
    .order_by("-avg_score")[:20]
)
data["agent_summary"] = agent_summary
```

Update `DashboardSummarySerializer` to add:
```python
submitted = serializers.IntegerField()
last_sync_at = serializers.DateTimeField(allow_null=True)
last_completed_at = serializers.DateTimeField(allow_null=True)
agent_summary = serializers.ListField(child=serializers.DictField())
```

No new tests required — update existing DashboardSummaryView tests if they assert exact field counts.

---

## Task 2 — Signed URL endpoint

Add `RecordingSignedUrlView` to `views.py`:

```
GET /audit/<S>/recordings/<recording_id>/signed-url/
Auth: IsAuthenticated + AuditPermissionMixin (all roles)
Returns: {"signed_url": "<s3-url>", "expires_in_seconds": 300}
503 if get_signed_url raises
```

Call `crm_adapter.get_signed_url(recording.recording_url)`.
Add NR attribute `("endpoint", "signed_url")`.

Register in `urls.py`:
```python
path("recordings/<int:recording_id>/signed-url/", RecordingSignedUrlView.as_view(), name="recording-signed-url"),
```

~4 tests in `test_views.py`:
1. Admin → 200 with `signed_url` + `expires_in_seconds`
2. Unauthenticated → 403
3. Recording not found → 404
4. `get_signed_url` raises → 503

---

## Task 3 — Compliance flag review endpoint

Add `FlagReviewView` to `views.py`:

```
PATCH /audit/<S>/recordings/<recording_id>/flags/<flag_id>/review/
Auth: IsAuthenticated + role_id in {1, 2, 4} (Admin, Manager, Supervisor)
Body: {"reviewed": true}
Returns: 200 with full flag serializer data
```

Logic:
- If `reviewed=true`: set `flag.reviewed=True`, `flag.reviewed_by=str(request.user.user_id)`, `flag.reviewed_at=timezone.now()`
- If `reviewed=false`: clear all three fields
- Validate `flag.recording_id == recording_id` → 404 if mismatch

Register in `urls.py`:
```python
path("recordings/<int:recording_id>/flags/<int:flag_id>/review/", FlagReviewView.as_view(), name="flag-review"),
```

~4 tests:
1. Admin marks reviewed → 200, `reviewed=true`, `reviewed_by` set
2. Admin marks unreviewed → 200, fields cleared
3. Agent (role_id=3) → 403
4. Wrong recording_id → 404

---

## Task 4 — Failed call retry endpoint

Add `RecordingRetryView` to `views.py`:

```
POST /audit/<S>/recordings/<recording_id>/retry/
Auth: IsAuthenticated + role_id in {1, 2} (Admin, Manager only)
Returns: 200 {"status": "pending", "retry_count": N}
400 if recording is not status=failed
404 if not found
```

Logic: set `recording.status="pending"`, `recording.error_message=None`. Do NOT reset `retry_count` — leave it incrementing for observability.

Register in `urls.py`:
```python
path("recordings/<int:recording_id>/retry/", RecordingRetryView.as_view(), name="recording-retry"),
```

~4 tests:
1. Failed recording → 200, `status=pending`
2. Non-failed recording → 400
3. Agent (role_id=3) → 403
4. Not found → 404

---

## Task 5 — Expose compliance flags on RecordingDetailView

Check if `compliance_flags` is already nested in `CallDetailSerializer`. If not, add:
```python
compliance_flags = ComplianceFlagSerializer(many=True, read_only=True)
```
Ensure `RecordingDetailView` uses `prefetch_related("compliance_flags")`. No new tests if already wired.

---

## Acceptance criteria

- `python -m pytest baysys_call_audit/tests/ -q` → ~315 tests, 0 failures
- `ruff check baysys_call_audit/` → 0 findings
- `GET .../recordings/1/signed-url/` → `{"signed_url": "...", "expires_in_seconds": 300}`
- `PATCH .../recordings/1/flags/1/review/` with body `{"reviewed": true}` → 200
- `POST .../recordings/1/retry/` (status=failed) → 200 `{"status": "pending"}`

---

## Files to touch

| File | Change |
|------|--------|
| `baysys_call_audit/views.py` | Add `RecordingSignedUrlView`, `FlagReviewView`, `RecordingRetryView` |
| `baysys_call_audit/urls.py` | Add 3 URL patterns |
| `baysys_call_audit/serializers.py` | Update `DashboardSummarySerializer`; verify `compliance_flags` nested |
| `baysys_call_audit/tests/test_views.py` | Add ~12 tests |
| `MANIFEST.md` | Update views list, URL count, test count |
| `BUILD_LOG.md` | Add Prompt M entry |
| `CLAUDE.md` | Update test gate |

Do NOT touch the React scaffold or settings.py — frontend is Prompt N.
