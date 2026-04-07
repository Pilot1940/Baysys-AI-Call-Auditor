# Prompt P — Sync Prompt M to crm_apis

**Branch:** `call-auditor` (already checked out in crm_apis repo)
**Repo:** `crm_apis/arc/baysys_call_audit/`
**Goal:** Bring `arc/baysys_call_audit` up to parity with the standalone `Baysys-AI-Call-Auditor` repo at Prompt M (317 tests). crm_apis was merged at Prompt J (302 tests) and is missing these additions.

---

## What is missing (added by Prompt M, not in crm_apis yet)

### 1. Three new view classes

- `RecordingSignedUrlView` — GET `/recordings/<id>/signed-url/`
- `FlagReviewView` — PATCH `/recordings/<id>/flags/<flag_id>/review/`
- `RecordingRetryView` — POST `/recordings/<id>/retry/`

### 2. Extended `DashboardSummaryView.get()`

Missing fields: `submitted`, `last_sync_at`, `last_completed_at`, `agent_summary`.

### 3. Three new URL routes

In `arc/baysys_call_audit/urls.py`.

### 4. New test classes in `arc/baysys_call_audit/tests/test_views.py`

`RecordingSignedUrlViewTests`, `FlagReviewViewTests`, `RecordingRetryViewTests`.

---

## Task 1 — Copy the 3 new view classes into `arc/baysys_call_audit/views.py`

**Source:** `Baysys-AI-Call-Auditor/baysys_call_audit/views.py`

Copy these 3 classes verbatim, inserted after `PollStuckRecordingsView` and before `SystemStatusView`:

- `RecordingSignedUrlView` (lines ~519–545)
- `FlagReviewView` (lines ~548–586)
- `RecordingRetryView` (lines ~589–623)

**Important:** The classes reference `crm_adapter`, `ComplianceFlag`, `CallRecording`, `timezone`, `logger`, `status`, `Response`, `IsAuthenticated`, `AuditPermissionMixin`, `get_auth_backend`. All of these are already imported in `arc/baysys_call_audit/views.py` — do NOT add duplicate imports.

Check that `newrelic` is imported — if not, add: `import newrelic.agent`

The inline import in `FlagReviewView`:
```python
from .serializers import ComplianceFlagSerializer  # noqa: PLC0415
```
Keep exactly as-is (noqa comment included).

---

## Task 2 — Update `DashboardSummaryView.get()` in `arc/baysys_call_audit/views.py`

Replace the existing `DashboardSummaryView.get()` method body with the extended version from the standalone.

The extended version adds after `avg_score`:
```python
flags_qs = ComplianceFlag.objects.filter(recording__in=qs)

last_sync_at = qs.order_by("-created_at").values_list("created_at", flat=True).first()
last_completed_at = (
    qs.filter(status="completed")
    .order_by("-completed_at")
    .values_list("completed_at", flat=True)
    .first()
)

agent_summary = list(
    qs.filter(status="completed")
    .values("agent_id", "agent_name")
    .annotate(
        calls=Count("pk"),
        avg_score=Avg("provider_scores__score_percentage"),
        fatals=Count("pk", filter=Q(fatal_level__gte=3)),
    )
    .order_by("-avg_score")[:20]
)
```

And the `data` dict is extended to include:
```python
"submitted": qs.filter(status="submitted").count(),
"last_sync_at": last_sync_at.isoformat() if last_sync_at else None,
"last_completed_at": last_completed_at.isoformat() if last_completed_at else None,
"agent_summary": agent_summary,
```

**Critical:** Use `provider_scores__score_percentage` (the `related_name` on the FK), NOT `providerscore__score_percentage`. The standalone hit this bug and fixed it — do not reintroduce it.

Check that `Q` is imported from `django.db.models`. If not, add it to the existing import.

---

## Task 3 — Update `arc/baysys_call_audit/urls.py`

Add 3 new routes to `urlpatterns`. Insert them after the `recording-detail` route, before `recording-import`:

```python
path("recordings/<int:recording_id>/signed-url/", RecordingSignedUrlView.as_view(), name="recording-signed-url"),
path("recordings/<int:recording_id>/retry/", RecordingRetryView.as_view(), name="recording-retry"),
path("recordings/<int:recording_id>/flags/<int:flag_id>/review/", FlagReviewView.as_view(), name="flag-review"),
```

Add the 3 new views to the import block at the top of `urls.py`:
```python
RecordingSignedUrlView,
FlagReviewView,
RecordingRetryView,
```

---

## Task 4 — Add new test classes to `arc/baysys_call_audit/tests/test_views.py`

Copy these 3 test classes from the standalone test file and adapt them for the crm_apis context.

**Source:** `Baysys-AI-Call-Auditor/baysys_call_audit/tests/test_views.py`
Classes: `RecordingSignedUrlViewTests`, `FlagReviewViewTests`, `RecordingRetryViewTests`

**Required adaptations:**

1. `@patch()` paths: change `baysys_call_audit.` → `arc.baysys_call_audit.`
   - Example: `@patch("baysys_call_audit.views.crm_adapter.get_signed_url", ...)` → `@patch("arc.baysys_call_audit.views.crm_adapter.get_signed_url", ...)`

2. `reverse()` names: keep as `"baysys_call_audit:recording-signed-url"` etc. — the `app_name` in `urls.py` is already `"baysys_call_audit"`, so the namespace is the same.

3. The `test_signed_url_service_error` test uses `APIRequestFactory` directly (not test client) to avoid a Python 3.14 + `AdminEmailHandler` crash in except blocks. Copy it exactly as written in the standalone — do NOT simplify it to use `self.client`.

4. If `APIRequestFactory` is not yet imported in the crm_apis test file, add it to the imports:
   ```python
   from rest_framework.test import APIRequestFactory
   ```

---

## Task 5 — Run verification

```bash
cd crm_apis
python3 -m ruff check arc/baysys_call_audit/ 2>&1
python manage.py test arc.baysys_call_audit --settings=settings_test 2>&1
```

**Expected:** 0 ruff findings. All tests pass. Count should be roughly standalone count (317) minus the New Relic and system status tests that are in the standalone but may behave differently in the crm_apis context — expect 310+ tests passing.

If any test fails because of import path differences (`baysys_call_audit.` vs `arc.baysys_call_audit.`), fix the `@patch()` path.

---

## Task 6 — Commit

```bash
git add arc/baysys_call_audit/views.py arc/baysys_call_audit/urls.py arc/baysys_call_audit/tests/test_views.py
git commit -m "feat(call-audit): sync Prompt M to crm_apis — signed-url, retry, flag-review + extended dashboard"
```

---

## Task 7 — Update `DashboardSummarySerializer` in `arc/baysys_call_audit/serializers.py`

The crm_apis serializer is missing the 4 new fields added in Prompt M. The current serializer ends at `critical_flags`. Add these 4 fields after `critical_flags`:

```python
submitted = serializers.IntegerField()
last_sync_at = serializers.DateTimeField(allow_null=True)
last_completed_at = serializers.DateTimeField(allow_null=True)
agent_summary = serializers.ListField(child=serializers.DictField())
```

Add `serializers.py` to the commit in Task 6.

---

## Notes

- Do NOT touch `crm_adapter.py`, `speech_provider.py`, `models.py`, or migrations — these are already in sync from Prompt J.
- Do NOT change any Trainer files.
- The `DashboardSummarySerializer` in crm_apis already has all the fields needed for the extended response — check `arc/baysys_call_audit/serializers.py` first. If `submitted`, `last_sync_at`, `last_completed_at`, `agent_summary` are missing from the serializer, add them to match the standalone.
