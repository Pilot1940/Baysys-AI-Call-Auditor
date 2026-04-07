# BaySys Call Auditor — Pre-Production Code Review

**Review Date:** 2026-04-07
**Scope:** Production readiness assessment of baysys_call_audit codebase
**Reviewer:** Claude Code Agent

---

## Executive Summary

The Call Auditor codebase is **ready for production deployment with the following critical fixes required before go-live**. There are **5 CRITICAL issues**, **8 HIGH issues**, and **4 MEDIUM issues** that must be addressed. Most are in auth/validation edge cases, timezone handling, and error recovery paths.

---

## CRITICAL Issues

### 1. `views.py` (line 114) — Integer parsing vulnerability in pagination
**File:** `baysys_call_audit/views.py:114–115`
**Severity:** CRITICAL
**Issue:**
```python
page = int(request.query_params.get("page", 1))
page_size = min(int(request.query_params.get("page_size", 25)), 100)
```
No error handling for non-integer values. If a user sends `?page=abc` or `?page_size=xyz`, the view will crash with a 500 error instead of returning a 400 Bad Request.

**Impact:** Allows attackers to trigger crashes. Production will show internal error traces. DoS vector.

**Fix:**
```python
try:
    page = int(request.query_params.get("page", 1))
    page_size = int(request.query_params.get("page_size", 25))
except (ValueError, TypeError):
    return Response(
        {"error": "page and page_size must be integers"},
        status=status.HTTP_400_BAD_REQUEST,
    )
page_size = min(page_size, 100)
if page < 1:
    return Response(
        {"error": "page must be >= 1"},
        status=status.HTTP_400_BAD_REQUEST,
    )
```

**Also applies to:** Lines 248–249 (ComplianceFlagListView).

---

### 2. `views.py` (line 289) — Date format error not handled
**File:** `baysys_call_audit/views.py:286–294`
**Severity:** CRITICAL
**Issue:**
```python
date_str = data.get("date")
if date_str:
    try:
        target_date = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return Response(...)
else:
    target_date = None  # run_sync_for_date defaults to yesterday
```

The error handler correctly returns 400, but **there is a logic gap**: if `date_str` is provided but is empty string `""`, it will pass the `if date_str:` check (falsy strings), fail to parse, and crash. Similarly, `date_str=None` is correctly handled but the control flow is fragile.

**Impact:** Empty `date` parameter silently treated as `None` (yesterday), which may not be the user's intent.

**Fix:**
```python
date_str = (data.get("date") or "").strip()
if date_str:
    try:
        target_date = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return Response(
            {"error": "Invalid date format. Use YYYY-MM-DD."},
            status=status.HTTP_400_BAD_REQUEST,
        )
else:
    target_date = None
```

---

### 3. `views.py` (line 567) — FlagReviewView missing agency/recording ownership check
**File:** `baysys_call_audit/views.py:548–587`
**Severity:** CRITICAL
**Issue:**
The `FlagReviewView` retrieves a flag by `flag_id` without checking if the user has permission to view/edit that recording. The code checks only that:
1. User role is Admin/Manager/Supervisor
2. Flag belongs to a recording (line 571)

**Missing:** RBAC check against the recording's agency/agent. An agency-scoped manager (role_id=2) in Agency A could mark flags as reviewed on recordings from Agency B.

**Impact:** Authorization bypass. Managers can modify compliance flags outside their jurisdiction.

**Fix:**
```python
def patch(self, request, recording_id, flag_id):
    role = self.get_user_role(request)
    if role not in self.ALLOWED_ROLES:
        return Response(
            {"error": "Insufficient permissions. Admin, Manager, or Supervisor required."},
            status=status.HTTP_403_FORBIDDEN,
        )

    filters = self.get_user_filter(request)  # Gets agency filter for scoped users
    try:
        recording = CallRecording.objects.get(pk=recording_id, **filters)
    except CallRecording.DoesNotExist:
        return Response({"error": "Recording not found"}, status=status.HTTP_404_NOT_FOUND)

    try:
        flag = ComplianceFlag.objects.get(pk=flag_id, recording=recording)
    except ComplianceFlag.DoesNotExist:
        return Response({"error": "Flag not found"}, status=status.HTTP_404_NOT_FOUND)

    # ... rest of patch logic
```

---

### 4. `auth.py` (line 53) — Invalid role IDs in MANAGER_ROLES
**File:** `baysys_call_audit/auth.py:52–56`
**Severity:** CRITICAL
**Issue:**
```python
MANAGER_ROLES = {1, 2, 4, 5}
```

Role ID 5 (Agency Admin) is included in MANAGER_ROLES, but there is **no role 5 definition in the docstring** and no corresponding models in crm_adapter. The docstring (lines 5–10) lists only roles 1–4. Role 5 is undefined and may not exist in the CRM schema.

**Impact:** Role 5 users will be treated as managers if they somehow exist, creating security assumptions about non-existent users. Code maintainers will be confused by the mismatch.

**Fix:**
Clarify in docstring whether role 5 exists:
```python
"""
Role IDs (same as Trainer):
  1 = Admin (cross-agency)
  2 = Manager/TL (agency-scoped)
  3 = Agent (own only)
  4 = Supervisor (cross-agency)
  5 = Agency Admin (agency-scoped)  [CONFIRM this exists in CRM]
"""
MANAGER_ROLES = {1, 2, 4, 5}
```

If role 5 does not exist in crm_apis, remove it:
```python
MANAGER_ROLES = {1, 2, 4}
```

**Check with:** Verify against CRM schema `arc.crm.models.user_model`.

---

### 5. `ingestion.py` (line 206) — SYNC_QUERY returns no error on SQL failure
**File:** `baysys_call_audit/ingestion.py:199–207`
**Severity:** CRITICAL
**Issue:**
```python
with connection.cursor() as cursor:
    min_duration = getattr(settings, "SYNC_MIN_CALL_DURATION", 20)
    cursor.execute(SYNC_QUERY, [str(target_date), min_duration])
    raw_rows = cursor.fetchall()
```

If `cursor.execute()` fails (e.g., uvarcl_live schema doesn't exist, permission denied, call_logs table missing), the exception **will propagate uncaught** and crash the sync. The endpoint (SyncCallLogsView line 308–325) does not wrap this in try-catch and will return 500 to the user.

**Impact:** Sync endpoint crashes on production database issues instead of returning a graceful error.

**Fix:**
```python
try:
    with connection.cursor() as cursor:
        min_duration = getattr(settings, "SYNC_MIN_CALL_DURATION", 20)
        cursor.execute(SYNC_QUERY, [str(target_date), min_duration])
        raw_rows = cursor.fetchall()
except Exception as exc:
    logger.error("SYNC_QUERY failed for date %s: %s", target_date, exc)
    return {
        "fetched": 0,
        "created": 0,
        "skipped_dedup": 0,
        "skipped_validation": 0,
        "unknown_agents": 0,
        "errors": 0,
        "duration_seconds": 0,
        "query_error": str(exc),  # Expose error reason to API caller
    }
```

Also wrap the view call:
```python
# views.py, lines 308–325
try:
    counts = run_sync_for_date(
        target_date=target_date,
        batch_size=batch_size,
        dry_run=dry_run,
    )
except Exception as exc:
    logger.exception("Sync endpoint error")
    return Response(
        {"error": f"Sync failed: {exc}"},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
```

---

## HIGH Issues

### 6. `views.py` (line 243) — Unsafe boolean parsing in query params
**File:** `baysys_call_audit/views.py:242–243`
**Severity:** HIGH
**Issue:**
```python
if request.query_params.get("reviewed") is not None:
    qs = qs.filter(reviewed=request.query_params["reviewed"].lower() == "true")
```

If `reviewed` is not a string (unlikely but possible if someone sends malformed multipart data), `.lower()` will crash with AttributeError. Also, any truthy value besides the string `"true"` is treated as False (e.g., `?reviewed=1` → False, `?reviewed=yes` → False).

**Impact:** Inconsistent API behavior. Query `?reviewed=1` returns all reviewed=False when user likely meant reviewed=True.

**Fix:**
```python
reviewed_str = request.query_params.get("reviewed", "").strip().lower()
if reviewed_str in ("true", "1", "yes"):
    qs = qs.filter(reviewed=True)
elif reviewed_str in ("false", "0", "no"):
    qs = qs.filter(reviewed=False)
# If neither, no filter applied (allow both)
```

---

### 7. `compliance.py` (line 161) — Timezone handling at midnight edge case
**File:** `baysys_call_audit/compliance.py:156–174`
**Severity:** HIGH
**Issue:**
```python
ist_dt = recording.recording_datetime.astimezone(_IST)
call_hour = ist_dt.hour
if call_hour < start_hour or call_hour >= end_hour:
    # Flag violation
```

IST is UTC+5:30. A call at `2026-01-01 23:30:00 UTC` converts to `2026-01-02 05:00:00 IST` (next calendar day). The rule **correctly checks IST hour**, but if a customer checks the recorded call date in UTC vs IST, there will be a date mismatch in reports/evidence.

**Specific edge case:** A call at 23:30 UTC on Day 1 is flagged as outside hours (5:00 IST Day 2, assuming 8–20 IST window). The `evidence` field stores UTC timestamp, but the flag description implicitly refers to IST date. Users will be confused why a "Day 1" call is flagged on "Day 2".

**Impact:** Confusing audit trail. Users see evidence timestamp in UTC, but rule was evaluated in IST.

**Fix:**
```python
ist_dt = recording.recording_datetime.astimezone(_IST)
call_hour = ist_dt.hour
if call_hour < start_hour or call_hour >= end_hour:
    desc = rule.get("description", "Call outside permitted hours").format(
        start_hour=start_hour, end_hour=end_hour,
    )
    return ComplianceFlag.objects.create(
        recording=recording,
        flag_type=rule.get("flag_type", "outside_hours"),
        severity=rule.get("severity", "critical"),
        description=desc,
        evidence=f"IST: {ist_dt.isoformat()} (UTC: {recording.recording_datetime.isoformat()})",
    )
```

---

### 8. `compliance.py` (line 198) — Gazette holiday check assumes file exists
**File:** `baysys_call_audit/compliance.py:192–210`
**Severity:** HIGH
**Issue:**
```python
holidays = load_gazette_holidays(holidays_file)
call_date = recording.recording_datetime.astimezone(_IST).date()
if call_date in holidays:
    # Flag violation
```

If the holidays file is missing and `load_gazette_holidays()` returns empty frozenset (line 115), the check will silently pass (no flags), even though the compliance rule was supposed to run. Users will see "no violations" when in fact the file couldn't be loaded.

**Impact:** Silent compliance check failure. Calls made on actual bank holidays won't be flagged if the holidays file is missing.

**Fix:**
```python
def load_gazette_holidays(holidays_file: str) -> frozenset[date]:
    path = _BASE_DIR / holidays_file
    holidays = set()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                try:
                    holidays.add(date.fromisoformat(stripped))
                except ValueError:
                    logger.warning("Skipping malformed holiday date: %s", stripped)
    except FileNotFoundError:
        logger.error("CRITICAL: Gazette holidays file not found: %s", path)
        # Re-raise to fail loudly
        raise FileNotFoundError(f"Gazette holidays file required but not found: {path}")
    return frozenset(holidays)
```

Then handle in compliance check:
```python
def _check_gazette_holiday(recording: CallRecording, rule: dict, **_kwargs) -> ComplianceFlag | None:
    params = rule.get("params", {})
    holidays_file = params.get("holidays_file", "")
    if not holidays_file:
        return None

    try:
        holidays = load_gazette_holidays(holidays_file)
    except FileNotFoundError as exc:
        logger.error("Gazette holiday check failed: %s", exc)
        # Create a flag to alert admins
        return ComplianceFlag.objects.create(
            recording=recording,
            flag_type="rbi_coc_violation",
            severity="critical",
            description=f"Compliance check error: {exc}",
            evidence="holidays_file_missing",
            auto_detected=False,
        )

    call_date = recording.recording_datetime.astimezone(_IST).date()
    if call_date in holidays:
        ...
```

---

### 9. `speech_provider.py` (line 81) — Timeout too long for production SLAs
**File:** `baysys_call_audit/speech_provider.py:81, 121, 152, 172, 200, 230`
**Severity:** HIGH
**Issue:**
All provider API calls use `timeout=30` seconds. For a high-volume system (18K calls/day), a 30-second timeout per request will cause thread/worker exhaustion if the provider experiences any latency spikes.

**From project memory (call_audit_greylabs_call.md):** GreyLabs has a 200/min rate limit (3.3 calls/sec). A 30-second timeout on a submit request blocks the worker for 30 seconds, effectively limiting throughput to ~0.03 submissions/sec (vs target 3+ req/sec).

**Impact:** Batch submission (submit_pending_recordings) will take hours to complete if any API call times out. System will back up.

**Fix:**
```python
SPEECH_PROVIDER_SUBMIT_TIMEOUT = 10  # seconds
SPEECH_PROVIDER_POLL_TIMEOUT = 5     # seconds

def submit_recording(...) -> str:
    ...
    timeout = getattr(settings, "SPEECH_PROVIDER_SUBMIT_TIMEOUT", 10)
    resp = requests.post(url, data=payload, headers=_get_headers(), timeout=timeout)
    ...

def get_results(resource_id: str) -> dict:
    ...
    timeout = getattr(settings, "SPEECH_PROVIDER_POLL_TIMEOUT", 5)
    resp = requests.post(url, json=payload, headers=_get_headers(), timeout=timeout)
    ...
```

Add exponential backoff + retry logic:
```python
import time
from requests.exceptions import Timeout, ConnectionError

def submit_recording(...) -> str:
    max_retries = 3
    base_delay = 1  # seconds

    for attempt in range(max_retries):
        try:
            timeout = getattr(settings, "SPEECH_PROVIDER_SUBMIT_TIMEOUT", 10)
            resp = requests.post(url, data=payload, headers=_get_headers(), timeout=timeout)

            if resp.status_code != 200:
                exc = ProviderError(...)
                raise exc

            data = resp.json()
            resource_id = data.get("resource_insight_id") or data.get("id")
            if not resource_id:
                raise ProviderError(...)

            return str(resource_id)

        except (Timeout, ConnectionError) as exc:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning("Provider timeout, retry %d/%d in %ds: %s", attempt + 1, max_retries, delay, exc)
                time.sleep(delay)
            else:
                raise ProviderError(f"Submit failed after {max_retries} retries: {exc}")
```

---

### 10. `services.py` (line 103–110) — Retry count increments on any ProviderError
**File:** `baysys_call_audit/services.py:103–110`
**Severity:** HIGH
**Issue:**
```python
except speech_provider.ProviderError as exc:
    recording.retry_count += 1
    recording.status = "failed"
    recording.error_message = str(exc)
    recording.save(...)
```

If a ProviderError is raised (e.g., provider rate-limited with 429, network timeout, or permanent failure like invalid S3 URL), the retry_count is incremented regardless. There's no distinction between:
- Transient errors (network timeout) — should retry
- Rate limit (429) — should retry with backoff
- Permanent errors (invalid URL) — should not retry

**Impact:** A recording with an invalid S3 URL will accumulate retry_count forever on each sync, wasting API quota.

**Fix:**
```python
except speech_provider.ProviderError as exc:
    # Determine if error is retryable
    retryable = _is_retryable_error(exc)

    if retryable:
        recording.retry_count += 1
        max_retries = getattr(settings, "MAX_SUBMISSION_RETRIES", 5)
        if recording.retry_count >= max_retries:
            recording.status = "failed"
            recording.error_message = f"Max retries reached: {str(exc)}"
        else:
            recording.status = "pending"  # Re-queue for next batch
            recording.error_message = str(exc)
    else:
        # Permanent failure — don't retry
        recording.status = "failed"
        recording.error_message = f"Permanent error (no retry): {str(exc)}"

    recording.save(update_fields=["retry_count", "status", "error_message"])
    counts["failed"] += 1

def _is_retryable_error(exc: speech_provider.ProviderError) -> bool:
    # Retry on network errors, timeouts, 5xx, 429
    # Don't retry on 4xx (except 429)
    if exc.status_code in (429, 500, 502, 503, 504):
        return True
    if exc.status_code and exc.status_code < 400:
        return True
    return False
```

---

## MEDIUM Issues

### 11. `models.py` (line 48) — provider_resource_id unique constraint blocks duplicates
**File:** `baysys_call_audit/models.py:48`
**Severity:** MEDIUM
**Issue:**
```python
provider_resource_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
```

The `unique=True` constraint means if a webhook arrives twice with the same `provider_resource_id` (network retry), the second insertion will fail with IntegrityError. The code in `process_provider_webhook()` line 156–159 correctly handles idempotency by checking `status == "completed"`, but if the status is still "submitted", a duplicate webhook will crash.

**Scenario:**
1. Webhook 1 arrives, recording status = "submitted" → "processing"
2. Provider sends duplicate webhook (network retry)
3. Webhook 2 tries to update the same provider_resource_id
4. IntegrityError (unless we're in the completed check)

**Impact:** Webhook handler may crash on provider retries, leaving recording stuck in "processing".

**Fix:**
Change unique constraint to allow null duplicates:
```python
provider_resource_id = models.CharField(
    max_length=100,
    null=True,
    blank=True,
    unique=True,
    db_index=True,
)
```

Then in `process_provider_webhook()`, make the lookup more explicit:
```python
try:
    recording = CallRecording.objects.get(provider_resource_id=str(resource_id))
except CallRecording.MultipleObjectsReturned:
    logger.error("Multiple recordings with same provider_resource_id=%s", resource_id)
    # Return the most recently updated one
    recording = CallRecording.objects.filter(
        provider_resource_id=str(resource_id)
    ).order_by("-completed_at").first()
except CallRecording.DoesNotExist:
    ...
```

Or add a migration to make it a non-unique index:
```python
# In a migration:
class Migration(migrations.Migration):
    dependencies = [...]

    operations = [
        migrations.AlterField(
            model_name='callrecording',
            name='provider_resource_id',
            field=models.CharField(max_length=100, null=True, blank=True, db_index=True),
        ),
    ]
```

---

### 12. `views.py` (line 240) — QueryDict.get() on strings with isinstance check missing
**File:** `baysys_call_audit/views.py:238–243`
**Severity:** MEDIUM
**Issue:**
```python
if request.query_params.get("reviewed") is not None:
    qs = qs.filter(reviewed=request.query_params["reviewed"].lower() == "true")
```

Django's QueryDict can contain lists if a query param is repeated (e.g., `?reviewed=true&reviewed=false`). Calling `.lower()` on a list will fail.

**Impact:** Malformed query params crash the endpoint.

**Fix:**
```python
reviewed_param = request.query_params.get("reviewed")
if reviewed_param is not None:
    # Ensure it's a string, not a list
    reviewed_str = reviewed_param[0] if isinstance(reviewed_param, list) else reviewed_param
    qs = qs.filter(reviewed=reviewed_str.lower() == "true")
```

Or use QueryDict's getlist():
```python
reviewed_list = request.query_params.getlist("reviewed")
if reviewed_list:
    reviewed_str = reviewed_list[0].lower()
    qs = qs.filter(reviewed=reviewed_str == "true")
```

---

### 13. `ingestion.py` (line 311) — naive datetime not checked before make_aware()
**File:** `baysys_call_audit/ingestion.py:310–317`
**Severity:** MEDIUM
**Issue:**
```python
recording_dt = parse_datetime_flexible(row["recording_datetime"])
if recording_dt is None:
    return (None, False)

# Make timezone-aware if naive
if timezone.is_naive(recording_dt):
    recording_dt = timezone.make_aware(recording_dt)
```

If `parse_datetime_flexible()` returns a datetime with an explicit UTC offset (e.g., `2026-01-01T12:00:00+00:00`), then `timezone.is_naive()` will return False, and the datetime is used as-is. But if the same datetime is created as a naive UTC datetime (e.g., from Postgres raw query), it's assumed to be in Django's default timezone (which may not be UTC).

**Scenario:**
- Sync query returns `2026-01-01 12:00:00` (naive, Postgres default)
- `parse_datetime_flexible()` parses it as naive
- `timezone.make_aware()` uses Django's `get_current_timezone()` → maybe IST
- Recording is stored as `2026-01-01 12:00:00 IST` instead of UTC

**Impact:** Recordings in IST timezone create wrong dates in compliance checks.

**Fix:**
Explicitly convert naive datetimes to UTC:
```python
recording_dt = parse_datetime_flexible(row["recording_datetime"])
if recording_dt is None:
    return (None, False)

if timezone.is_naive(recording_dt):
    # Assume naive datetimes from uvarcl_live are in UTC (Postgres default)
    from zoneinfo import ZoneInfo
    utc_tz = ZoneInfo("UTC")
    recording_dt = recording_dt.replace(tzinfo=utc_tz)
else:
    # Already aware; ensure it's in UTC for storage consistency
    recording_dt = recording_dt.astimezone(ZoneInfo("UTC"))
```

---

### 14. `compliance.py` (line 226) — Date comparison ignores timezone in max_calls check
**File:** `baysys_call_audit/compliance.py:213–251`
**Severity:** MEDIUM
**Issue:**
```python
call_date = recording.recording_datetime.astimezone(_IST).date()
...
call_count = CallRecording.objects.filter(
    customer_id=recording.customer_id,
    recording_datetime__date=call_date,
).count()
```

The rule converts UTC `recording_datetime` to IST and extracts the date. But the ORM filter `recording_datetime__date` uses the database's date extraction on the UTC value. If a call is at 23:30 UTC (= 05:00 IST next day), the rule checks counts for IST Day 2, but the filter queries for UTC Day 1.

**Impact:** Max calls per day check is inconsistent. IST Day 2 calls are counted against UTC Day 1's limit.

**Fix:**
Perform the date extraction consistently in UTC or IST:
```python
call_date_utc = recording.recording_datetime.date()
call_count = CallRecording.objects.filter(
    customer_id=recording.customer_id,
    recording_datetime__date=call_date_utc,
).count()
```

Or do the conversion for both:
```python
ist_dt = recording.recording_datetime.astimezone(_IST)
call_date_ist = ist_dt.date()
# Convert back to UTC date range for query
call_date_start_ist = ist_dt.replace(hour=0, minute=0, second=0, microsecond=0)
call_date_end_ist = ist_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
call_date_start_utc = call_date_start_ist.astimezone(ZoneInfo("UTC"))
call_date_end_utc = call_date_end_ist.astimezone(ZoneInfo("UTC"))

call_count = CallRecording.objects.filter(
    customer_id=recording.customer_id,
    recording_datetime__gte=call_date_start_utc,
    recording_datetime__lte=call_date_end_utc,
).count()
```

---

## MINOR Issues

### 15. `views.py` (line 472) — add_custom_attributes() misuse
**File:** `baysys_call_audit/views.py:472`
**Severity:** MINOR
**Issue:**
```python
newrelic.agent.add_custom_attributes([("endpoint", "submit_recordings")])
```

The function expects a dict, not a list of tuples. This is a New Relic API misuse. It should be:
```python
newrelic.agent.add_custom_attributes({"endpoint": "submit_recordings"})
```

**Impact:** New Relic won't capture this attribute; monitoring will be incomplete.

**Also appears in:** Lines 74–77, 301–303, 472, 501, 529.

---

### 16. `ingestion.py` (line 345) — Circular import of compliance module
**File:** `baysys_call_audit/ingestion.py:344–347`
**Severity:** MINOR
**Issue:**
```python
# Run metadata compliance checks at ingestion time
from .compliance import check_metadata_compliance  # noqa: PLC0415

check_metadata_compliance(recording, call_counts_cache=call_counts_cache)
```

The import is deferred to avoid circular imports, but it's imported inside a function that's called in a loop (once per recording). This causes the module to be imported repeatedly, though Python caches the import.

**Impact:** Minor performance impact. Not incorrect, but could be cleaner.

**Fix:**
Import at module level if there's no circular dependency:
```python
# At top of ingestion.py
from .compliance import check_metadata_compliance

# In create_recording_from_row():
check_metadata_compliance(recording, call_counts_cache=call_counts_cache)
```

Verify no circular import by checking: does `compliance.py` import anything from `ingestion.py`? (It doesn't.)

---

### 17. `services.py` (line 81–84) — Silent fallback to unsigned URL
**File:** `baysys_call_audit/services.py:80–84`
**Severity:** MINOR
**Issue:**
```python
try:
    signed_url = get_signed_url(recording.recording_url)
except Exception as exc:
    logger.warning("Failed to re-sign URL for recording %s: %s", recording.pk, exc)
    signed_url = recording.recording_url  # Silent fallback
```

If URL signing fails (e.g., S3 service down, invalid credentials), the code falls back to sending the unsigned URL to the provider. In production, unsigned S3 URLs expire quickly and may not be accessible, causing a provider error.

**Impact:** Submission fails silently at provider side instead of failing fast here.

**Fix:**
```python
try:
    signed_url = get_signed_url(recording.recording_url)
except Exception as exc:
    logger.error("Failed to re-sign URL for recording %s: %s", recording.pk, exc)
    recording.retry_count += 1
    recording.status = "failed"
    recording.error_message = f"URL signing failed: {exc}"
    recording.save(update_fields=["retry_count", "status", "error_message"])
    counts["failed"] += 1
    continue  # Skip to next recording
```

---

### 18. `auth.py` (line 39–41) — MockUser lacks username attribute
**File:** `baysys_call_audit/auth.py:16–28`
**Severity:** MINOR
**Issue:**
```python
class MockUser:
    is_authenticated = True
    def __init__(self, user_id=1, role_id=2, agency_id=1, ...):
        self.user_id = user_id
        ...
```

Django's `User` models typically have a `username` attribute. MockUser doesn't. If any code calls `request.user.username`, it will raise AttributeError. This is primarily a testing issue but affects development.

**Impact:** Dev/test scenarios might fail if code assumes `username` exists.

**Fix:**
```python
class MockUser:
    is_authenticated = True

    def __init__(self, user_id=1, role_id=2, agency_id=1,
                 phone_number="+9190000000", first_name="BaySys.AI",
                 last_name="Test User", email="connect@baysys.ai",
                 username=None):
        self.user_id = user_id
        self.role_id = role_id
        self.agency_id = agency_id
        self.phone_number = phone_number
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.username = username or f"user_{user_id}"
```

---

## Invariant Verification

### ✓ speech_provider.py is the only provider-specific code
**Status:** PASS
All GreyLabs-specific API endpoints, headers, and payload structures are isolated to `speech_provider.py`. No provider references elsewhere.

### ✓ crm_adapter.py is the only mock/prod branching
**Status:** PASS
All mock/prod logic uses `AUDIT_AUTH_BACKEND` setting checked in `crm_adapter.py`. No other files contain `if mock else prod` patterns.

### ✓ No SQL injection vectors
**Status:** PASS with note
- `SYNC_QUERY` uses parameterized query with `%s` placeholders.
- All ORM queries use `.filter()` with named kwargs, never f-strings.
- Note: `SYNC_QUERY` hard-codes table names (uvarcl_live.call_logs) which is acceptable for this schema.

### ✓ No hardcoded thresholds
**Status:** PASS
All compliance thresholds come from:
- `settings.COMPLIANCE_CALL_WINDOW_START_HOUR` (default from rule config)
- `settings.COMPLIANCE_MAX_CALLS_PER_CUSTOMER_PER_DAY` (default from rule config)
- `settings.POLL_STUCK_AFTER_MINUTES` (default 30)
- Config YAML files (submission_priority.yaml, compliance_rules.yaml, fatal_level_rules.yaml)

### ✓ Provider field names are agnostic
**Status:** PASS
Model uses generic field names: `provider_resource_id`, `raw_provider_response`, `raw_score_payload`. No "greylabs" or provider-specific naming in models/views/serializers.

### ✓ Status transitions are valid
**Status:** PASS with note
Defined transitions:
- pending → submitted (on submit)
- submitted → completed (on webhook)
- submitted → processing (no, not explicitly — code goes directly to completed)
- pending/submitted → failed (on provider error)
- failed → pending (on retry)
- pending → skipped (if no recording_url)

Note: There's no "processing" state used, though it's defined. Code jumps from "submitted" directly to "completed".

### ✓ Error handling doesn't silently swallow exceptions
**Status:** FAIL (see CRITICAL issue #5)
- ✗ `SYNC_QUERY` execution has no error handling
- ✗ Most views lack try-catch for critical operations
- ✓ Webhook processing logs errors before returning None
- ✓ Compliance checks log warnings when files are missing

### ✓ Timezone handling correct for IST
**Status:** PARTIAL (see HIGH issues #7, MEDIUM issue #14)
- ✓ Compliance checks convert recording_datetime from UTC to IST
- ✗ Timezone handling at day boundaries is inconsistent
- ✗ Date comparisons mix UTC and IST dates

---

## Summary Table

| Severity | Count | Must Fix Before Prod | Files |
|----------|-------|----------------------|-------|
| CRITICAL | 5 | YES | views.py (3), auth.py (1), ingestion.py (1) |
| HIGH | 5 | YES | views.py (2), compliance.py (2), speech_provider.py (1) |
| MEDIUM | 4 | RECOMMENDED | models.py (1), views.py (1), ingestion.py (1), compliance.py (1) |
| MINOR | 4 | OPTIONAL | views.py (1), ingestion.py (1), services.py (1), auth.py (1) |

---

## Recommended Pre-Prod Deployment Checklist

- [ ] Fix all 5 CRITICAL issues (pagination, date parsing, RBAC in FlagReviewView, role 5 validation, SYNC_QUERY error handling)
- [ ] Fix all 5 HIGH issues (query param parsing, timezone edge cases, gazette holiday file handling, provider timeouts, retry logic)
- [ ] Fix or acknowledge 4 MEDIUM issues (unique constraint, QueryDict handling, timezone conversions, max_calls date mismatch)
- [ ] Fix or acknowledge 4 MINOR issues (New Relic attributes, circular imports, silent fallbacks, MockUser username)
- [ ] Run full test suite (302 tests must pass, 0 ruff findings)
- [ ] Test with GreyLabs UAT environment (webhook idempotency, rate limiting, error scenarios)
- [ ] Load test with 18K+ recordings/day throughput
- [ ] Verify crm_apis PR is merged and prod env vars are set
- [ ] Confirm compliance rules YAML files exist and are valid
- [ ] Set up alerting for "query_error" responses from sync endpoint

---

## Conclusion

The Call Auditor codebase is well-structured and feature-complete, but has **5 blocking production-readiness issues** that must be fixed before deployment. The CRITICAL issues in auth, pagination, and error handling pose security and reliability risks. Most fixes are straightforward parameter validation and error handling additions.

**Estimated fix time:** 4–6 hours for all issues (including testing).

**Risk level:** HIGH if deployed as-is. MEDIUM after fixes.
