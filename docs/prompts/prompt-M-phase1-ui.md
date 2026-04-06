# Prompt M — Phase 1 UI: Call List + Call Detail with Audio Player

**Project:** Baysys-AI-Call-Auditor
**Branch:** work in the current branch
**Depends on:** Prompt L complete (302 tests)
**Expected outcome:** ~310 tests, 0 ruff findings. Working React UI: recordings list + call detail with audio player, compliance flags, and placeholders for GreyLabs data.

---

## Context

Phase 1 UI shows everything available without GreyLabs results. The product team needs to be able to:
- See all recordings with their status (pending/submitted/completed/failed)
- Open a call and play the audio
- See metadata compliance flags already computed at ingestion (M1–M4)
- See placeholders where transcript and scores will appear post-GreyLabs

The React scaffold already exists at `baysys_call_audit_ui/` with `DashboardPage.tsx` and `CallDetailPage.tsx` stubs.

---

## Backend: Task 1 — Extend DashboardSummaryView

The existing summary endpoint is missing `submitted`, `last_sync_at`, and `last_completed_at`. Add to the `data` dict in `DashboardSummaryView.get()`:

```python
"submitted": qs.filter(status="submitted").count(),
"last_sync_at": (
    qs.order_by("-created_at").values_list("created_at", flat=True).first()
),
"last_completed_at": (
    qs.filter(status="completed").order_by("-completed_at")
    .values_list("completed_at", flat=True).first()
),
```

Convert datetimes to `.isoformat()` if not None.

Update `DashboardSummarySerializer` to add the three new fields:
```python
submitted = serializers.IntegerField()
last_sync_at = serializers.DateTimeField(allow_null=True)
last_completed_at = serializers.DateTimeField(allow_null=True)
```

No new tests needed for the field additions — existing serializer tests will need updating if they assert exact field counts.

---

## Backend: Task 2 — Signed URL endpoint

The `recording_url` field stores a raw S3 object key (no scheme, no signature). The frontend needs a time-limited playable URL for the audio player.

Add to `baysys_call_audit/views.py`:

```python
class RecordingSignedUrlView(APIView):
    """
    GET /audit/<S>/recordings/<recording_id>/signed-url/

    Returns a short-lived signed URL for audio playback.
    Auth: IsAuthenticated + AuditPermissionMixin (all roles).
    """
```

- Call `crm_adapter.get_signed_url(recording.recording_url)` and return `{"signed_url": "<url>", "expires_in_seconds": 300}`
- If `get_signed_url` raises → 503 with `{"error": "Could not generate signed URL"}`
- Add NR attribute: `add_custom_attributes([("endpoint", "signed_url"), ("recording_id", recording_id)])`

Register in `urls.py`:
```python
path("recordings/<int:recording_id>/signed-url/", RecordingSignedUrlView.as_view(), name="recording-signed-url"),
```

Add ~4 tests in `test_views.py`:
1. Admin gets signed URL → 200 with `signed_url` key
2. Unauthenticated → 403
3. Recording not found → 404
4. `get_signed_url` raises → 503

---

## Backend: Task 3 — Expose compliance flags on RecordingDetailView

The `CallDetailSerializer` should include compliance flags inline. Check if `ComplianceFlagSerializer` is already nested in `CallDetailSerializer`. If not, add `compliance_flags = ComplianceFlagSerializer(many=True, read_only=True)` and add `compliance_flags` to `RecordingDetailView`'s queryset with `prefetch_related("complianceflag_set")`.

No new tests needed if this is already wired — verify first.

---

## Frontend: Task 4 — DashboardPage

Replace the stub at `src/pages/audit/DashboardPage.tsx` with a working page.

### Pipeline status bar (top)
Fetch from `GET /audit/<S>/dashboard/summary/`. Show 5 stat cards in a row:

| Card | Value | Colour |
|------|-------|--------|
| Synced today | `recordings_today` from summary | Blue |
| Pending (not submitted) | `pending_count` | Grey |
| In queue (submitted) | `submitted_count` | Amber |
| Completed (scored) | `completed_count` | Green |
| Failed | `failed_count` | Red |

Below the stat cards, show a small "Pipeline health" row:
- Last sync: `last_sync_at` timestamp (from summary or status endpoint)
- Last scored: `last_completed_at` timestamp
- If `failed_count > 0`: orange warning banner "N calls failed — check logs"
- If `submitted_count > 50`: amber banner "N calls waiting for GreyLabs results"

This gives the product team a live read of pipeline health without needing the health check URL.

### Recordings table
Fetch from `GET /audit/<S>/recordings/` with pagination. Columns:

| Column | Source | Notes |
|--------|--------|-------|
| Call date | `recording_datetime` | Date + time |
| Agent | `agent_name` | — |
| Product | `product_type` | PL / CC / other |
| Bank | `bank_name` | — |
| Tier | `submission_tier` | Badge: immediate=red, normal=amber, off_peak=grey |
| Status | `status` | Badge: pending=grey, submitted=blue, completed=green, failed=red |
| Fatal level | `fatal_level` | 0=none, 1-2=low (yellow), 3-4=high (orange), 5=critical (red) |
| Action | — | "View" link → `/audit/call/<id>` |

Add basic filters: status dropdown, date picker (recording_datetime). Use query params `?status=&date_from=&date_to=`.

Pagination: simple prev/next using `?page=` from DRF paginated response.

---

## Frontend: Task 5 — CallDetailPage

Replace the stub at `src/pages/audit/CallDetailPage.tsx`.

Fetch from `GET /audit/<S>/recordings/<id>/` on mount.

### Layout (top to bottom)

**Header row**
- Agent name (large)
- Call date/time
- Status badge
- Tier badge
- Fatal level indicator (coloured chip: 0=none, 1-2=⚠ Low, 3-4=🔶 High, 5=🔴 Critical)
- Back link to dashboard

**Audio player card**
- The signed URL is generated server-side. On mount, fetch `GET /audit/<S>/recordings/<id>/signed-url/`
- Use HTML5 `<audio controls src={signedUrl}>` — the browser streams directly from S3
- Show "Loading audio…" while fetching, "Audio unavailable" if 503
- Show call metadata below player: duration, product type, bank, customer phone

**Compliance flags card**
- Title: "Metadata Compliance"
- List flags from `compliance_flags` array (already computed at ingestion)
- Each flag: severity badge (critical=red, high=orange, medium=yellow) + description + evidence if present
- If no flags: green "✓ No compliance issues detected"
- If status is pending/submitted: show flags that ARE known (metadata ones) — these are real data

**Transcript card**
- If `transcript` is null (status ≠ completed): grey placeholder card — "Transcript will appear here once the call has been processed by the speech provider."
- If transcript exists: show `transcript_text` in a scrollable box. Show duration stats (total, agent, customer talk time) in a small row above.

**Provider score card**
- If `provider_score` is null: grey placeholder — "Score will appear here once GreyLabs processing is complete."
- If exists: show `score_percentage`% with a coloured progress bar (≥85=green, 70-84=amber, <70=red). Show `category_data` as a simple table if present.

**Own LLM score card**
- Always show as placeholder for now: "BaySys AI scoring coming soon."

---

## Frontend: Task 6 — Auth wiring

The existing `MockAuthContext` sets `user_id=1, role_id=2`. Keep this for Phase 1 — real auth wiring (CRM JWT) is a later prompt. All API calls use `Authorization: Token <MOCK_TOKEN>` from env.

Add to `.env` / `vite.config.ts`:
```
VITE_API_BASE=http://localhost:8000
VITE_AUDIT_URL_SECRET=dev-secret
VITE_API_TOKEN=<dev admin token>
```

Centralise the base URL in `src/utils/Api.tsx`:
```typescript
const BASE = `${import.meta.env.VITE_API_BASE}/audit/${import.meta.env.VITE_AUDIT_URL_SECRET}`
```

---

## Frontend: Task 7 — Operations panel (Admin/Manager only)

Add an "Operations" section to the DashboardPage, visible only when `role_id` is 1 (Admin) or 2 (Manager). Regular agents see recordings and compliance flags only.

### Submit button
- "Submit pending calls to GreyLabs" — `POST /audit/<S>/recordings/submit/`
- Show spinner while running
- On success: toast "Submitted N calls, N failed"
- On error: toast "Submission failed — check logs"
- Disable button if `pending_count === 0`

### Poll stuck calls button
- "Recover stuck calls" — `POST /audit/<S>/recordings/poll/`
- Show "Checking…" spinner
- On success: toast "Polled N calls — N recovered, N still processing"
- On error: toast with error message
- Add `{"dry_run": true}` option as a checkbox before running ("Preview only — don't actually poll")

### Sync controls
- Date picker + "Sync this date" button — `POST /audit/<S>/recordings/sync/` with `{"date": "YYYY-MM-DD"}`
- On success: toast "Synced N calls, skipped N duplicates"

All three operations refresh the stats bar after completion.

Note: these controls call the same endpoints currently done via curl — no new backend code needed.

---

## Frontend: Task 8 — Build output for Django static files

Add to `vite.config.ts`:
```typescript
build: {
  outDir: "../baysys_call_audit_ui_dist",
  emptyOutDir: true,
}
```

After `npm run build`, Django serves from `STATIC_ROOT`. Add to `settings.py`:
```python
STATICFILES_DIRS = [BASE_DIR / "baysys_call_audit_ui_dist"]
```

This means `npm run build` in `baysys_call_audit_ui/` produces a deployable static bundle — no separate Node server needed in production.

---

## Acceptance criteria

**Backend:**
- `python -m pytest baysys_call_audit/tests/ -q` → ~310 tests, 0 failures
- `ruff check baysys_call_audit/` → 0 findings
- `curl http://localhost:8000/audit/dev-secret/recordings/1/signed-url/ -H "Authorization: Token <token>"` → `{"signed_url": "...", "expires_in_seconds": 300}`

**Frontend:**
- `npm run dev` in `baysys_call_audit_ui/` → compiles without errors
- Dashboard loads at `http://localhost:5173/audit` showing recordings list
- Clicking "View" on any row opens call detail page
- Audio player attempts to load and play the S3 audio
- Compliance flags section shows real data even for pending/submitted recordings
- Transcript and score sections show placeholder cards for non-completed recordings

---

## Files to touch

| File | Change |
|------|--------|
| `baysys_call_audit/views.py` | Add `RecordingSignedUrlView` |
| `baysys_call_audit/urls.py` | Add `recordings/<id>/signed-url/` |
| `baysys_call_audit/serializers.py` | Verify `compliance_flags` nested in `CallDetailSerializer` |
| `baysys_call_audit/tests/test_views.py` | Add ~4 signed URL tests |
| `baysys_call_audit_ui/src/pages/audit/DashboardPage.tsx` | Full implementation |
| `baysys_call_audit_ui/src/pages/audit/CallDetailPage.tsx` | Full implementation |
| `baysys_call_audit_ui/src/utils/Api.tsx` | Base URL from env vars |
| `baysys_call_audit_ui/.env.example` | Add `VITE_API_BASE`, `VITE_AUDIT_URL_SECRET`, `VITE_API_TOKEN` |
| `baysys_call_audit_ui/vite.config.ts` | Add build outDir |
| `baysys_call_audit/settings.py` | Add `STATICFILES_DIRS` for UI dist |
| `MANIFEST.md` | Update views list, test count |
| `BUILD_LOG.md` | Add Prompt M entry |
| `CLAUDE.md` | Update test gate count |

Phase 2 (post-UAT): real CRM JWT auth wiring, individual call re-submission, bulk actions, agent performance trends, scorecard parameter drill-down.
