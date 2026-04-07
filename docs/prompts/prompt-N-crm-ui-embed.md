# Prompt N — Call Audit UI: CRM React Embed

**Project:** `crm` React repo (Baysys-AI-Web or equivalent CRM frontend)
**Branch:** `call-audit-frontend-embed` — create fresh from main; never work on main or master
**Depends on:** Prompt J (crm_apis merge) + Prompt M (backend endpoints) complete
**Pattern:** Mirrors Trainer embed on `trainer-frontend-embed`. Reference `useTrainerAuth.ts` for auth pattern.

---

## Access control — Admin only

**This page is accessible only to users with `role_id=1` (Admin).** No other role sees the Call Audit section. Gate at the route level, not per-component.

The business rationale: Call audit is an internal QA tool run by the operations team. Agents, TLs, and Supervisors do not interact with it.

---

## Step 0 — Read the existing Trainer integration FIRST

**Before writing a single line of code**, read these files in the crm repo:

```
src/hooks/useTrainerAuth.ts          ← auth adapter to copy pattern from
src/pages/trainer/                   ← Trainer page structure to mirror
```

Also read how routes and nav are wired for the Trainer — find the router config and nav config files. The exact file paths may differ from what's listed here; use the Trainer as the source of truth.

**Do not guess at auth patterns. Do not assume file paths. Read first, then write.**

---

## Step 1 — Create the branch

```bash
cd <crm-repo-root>
git checkout main && git pull
git checkout -b call-audit-frontend-embed
```

Never commit to main or master.

---

## Step 2 — Auth adapter

After reading `useTrainerAuth.ts`, create `src/hooks/useAuditAuth.ts` using the identical pattern.

Key facts about CRM auth (confirmed in crm_apis `f8552e6`):
- `CrmJWTAuthentication` is cookie-first: reads the `access_token` cookie automatically
- Bearer header is a fallback — not needed for browser sessions
- The cookie is set at CRM login and is available to all subpages
- No separate token or login needed for the audit pages

`useAuditAuth.ts` should return at minimum: `{ user, isAdmin, isLoading }` where `isAdmin = user.role_id === 1`.

Match the exact return shape and hook structure of `useTrainerAuth.ts` — do not add or remove fields without checking what the Trainer pages consume.

---

## Step 3 — Route setup

Find where the Trainer route is defined in the router config. Add the Call Audit route immediately after it, using the identical guard/protection pattern:

```typescript
// Add after Trainer route — exact syntax depends on what already exists
// Admin-only: role_id === 1
<AuditRoute path="/call-audit/*" element={<CallAuditApp />} />
```

`CallAuditApp` handles sub-routing:
- `/call-audit` → `AuditDashboardPage`
- `/call-audit/call/:id` → `AuditCallDetailPage`

If the router uses a different pattern (e.g. loader-based auth, nested routes), follow what exists — do not introduce a new routing style.

---

## Step 4 — Navigation

Find where the Trainer nav item is added to the sidebar/menu. Add "Call Audit" immediately after it, using the same component/pattern, visible only when `isAdmin === true`. Match the icon style and link style of the Trainer nav item.

---

## Step 5 — API client

After reading how the Trainer's API calls are structured (look at `src/pages/trainer/` and any `trainerApi.ts` or similar), create `src/utils/auditApi.ts` using the same fetch/axios pattern.

The audit API base URL:
```typescript
const AUDIT_BASE = `${import.meta.env.VITE_API_BASE}/audit/${import.meta.env.VITE_AUDIT_URL_SECRET}`
```

Add to `.env.example`:
```
VITE_AUDIT_URL_SECRET=<value from ops team — keep secret>
```

All fetch calls use the CRM's existing auth cookie automatically — no Authorization header needed for browser sessions. If the Trainer's API client does pass headers explicitly, match that pattern.

---

## Step 6 — AuditDashboardPage

File: `src/pages/audit/AuditDashboardPage.tsx`

### Pipeline stats bar

Fetch from `GET /audit/<S>/dashboard/summary/`. Five stat cards:

| Card | Field | Colour |
|------|-------|--------|
| Synced today | recordings created today | Blue |
| Pending | `pending` | Grey |
| In queue | `submitted` | Amber |
| Scored | `completed` | Green |
| Failed | `failed` | Red |

Below cards: "Last sync: <relative time>" · "Last scored: <relative time>".
- If `failed > 0`: orange banner "N calls failed"
- If `submitted > 50`: amber banner "N calls waiting for GreyLabs"

### Recordings table

Columns (all sortable — click header → `?ordering=<field>` or `?ordering=-<field>`):

| Column | Source | Notes |
|--------|--------|-------|
| Call date | `recording_datetime` | Default: newest first |
| Agent | `agent_name` | — |
| Product | `product_type` | — |
| Bank | `bank_name` | — |
| Tier | `submission_tier` | Badge: immediate=red, normal=amber, off_peak=grey |
| Status | `status` | Badge colours: pending=grey, submitted=blue, completed=green, failed=red |
| Score | `provider_score.score_percentage` | Score band badge: ≥85 Excellent (green), 70–84 Good (amber), 55–69 Needs Improvement (orange), <55 Critical (red). "—" if null |
| Fatal | `fatal_level` | 0=none, 1-2=⚠, 3-4=🔶, 5=🔴 |
| — | — | "View" link |

Filters: status dropdown, date range, agent name text search.
Pagination: prev/next with "Showing X–Y of Z calls".

### Agent leaderboard tab

Second tab on the dashboard. Reads `agent_summary` from the summary response.

| Agent | Calls scored | Avg score | Score band | Fatal flags |
|-------|-------------|-----------|------------|-------------|

Sorted by avg score descending. Clicking a row filters the recordings table to that agent.

### Operations panel

Always visible (Admin-only page, so all users here are Admin):

- **"Submit pending calls"** → `POST .../recordings/submit/` — disabled if `pending === 0`. Toast result on completion.
- **"Recover stuck calls"** → `POST .../recordings/poll/` — dry-run checkbox. Toast result.
- **"Sync date"** → date picker + button → `POST .../recordings/sync/`. Toast result.

All refresh the stats bar on success.

---

## Step 7 — AuditCallDetailPage

File: `src/pages/audit/AuditCallDetailPage.tsx`

Fetch from `GET /audit/<S>/recordings/<id>/` on mount.

### Header

Agent name · Call date · Status badge · Score band badge · Fatal level chip · Back link to dashboard.

### Audio player card

Fetch `GET /audit/<S>/recordings/<id>/signed-url/` on mount.
HTML5 `<audio controls src={signedUrl}>`. Show "Loading audio…" during fetch, "Audio unavailable" on 503.
Below player: product type, bank, customer phone, call duration.

### Metadata compliance card ("Metadata Compliance")

Flags from `compliance_flags` — populated at ingestion, visible even for pending/submitted calls.
Each flag: severity badge + type label + description + evidence excerpt (if present).
"Mark reviewed" button → `PATCH .../recordings/<id>/flags/<flag_id>/review/` with `{"reviewed": true}`.
After success: show "✓ Reviewed by <name> at <time>". Clicking again un-reviews.
If no flags: green "✓ No compliance issues".

### Scorecard card ("Call Quality Score")

If `provider_score` null: grey placeholder — "Score will appear once GreyLabs processes this call."

If exists:
- Top: `score_percentage`% with coloured progress bar + score band label
- If any FATAL triggered (fatal_level > 0): red banner "FATAL — automatic fail"
- Four collapsible group sections (Introduction Quality / Call Quality / Compliance & RBI / Scam & Trust) showing group score/max
- Inside each group: parameter rows from `category_data` — name, score/max, FATAL badge if applicable
- If `category_data` null: total score only

The 19 parameters and their groups are defined in `docs/SCORECARD.md`. The UI should match that structure exactly.

### Transcript card ("Call Transcript")

If null: grey placeholder.
If exists: scrollable text area. Above: duration row — total call time, agent talk %, customer talk % as a small bar.

### Retry button

Shown only when `status === "failed"`. "Retry this call" → `POST .../recordings/<id>/retry/` → toast "Call queued for retry" + reload.

---

## Step 8 — Build and test

```bash
# TypeScript compile check
tsc --noEmit

# ESLint
eslint src/pages/audit/ src/hooks/useAuditAuth.ts src/utils/auditApi.ts

# Dev server
npm run dev
```

**Verify auth works correctly:**
- Log in to the CRM as an Admin user → navigate to `/call-audit` → dashboard loads, API calls succeed (no 401/403)
- Log in as a non-Admin → `/call-audit` route is not accessible (redirect or hidden from nav)
- Confirm API calls are going to `/audit/<AUDIT_URL_SECRET>/...` (check Network tab)
- Confirm the `access_token` cookie is being sent automatically with requests — no manual Authorization header in browser sessions
- Confirm the Trainer pages still work after the change (no regressions in auth wiring)

---

## Files to create/touch in the CRM repo

| File | Change |
|------|--------|
| `src/hooks/useAuditAuth.ts` | New — auth adapter for audit API |
| `src/utils/auditApi.ts` | New — typed API client for audit endpoints |
| `src/pages/audit/AuditDashboardPage.tsx` | New — full dashboard |
| `src/pages/audit/AuditCallDetailPage.tsx` | New — full call detail |
| Router config | Add `/call-audit/*` route with admin guard |
| Nav config | Add "Call Audit" menu item (admin only) |
| `.env.example` | Add `VITE_AUDIT_URL_SECRET` |

Do NOT modify any Trainer files. Do NOT commit to main or master.

---

## After PR is merged

1. Set `VITE_AUDIT_URL_SECRET=<production UUID>` in the CRM build environment
2. Rebuild and redeploy the CRM frontend
3. Admin users will see "Call Audit" in the nav
4. No other users see it
