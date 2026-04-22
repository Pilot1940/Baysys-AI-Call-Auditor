# BaySys Call Audit AI — Build Log

**Project:** BaySys Call Audit AI
**Repo:** `Pilot1940/Baysys-AI-Call-Auditor` (backend) · `bsfg-finance/crm` branch `call-audit-frontend-embed` (UI)
**Build start:** 2026-04-01
**Last updated:** 2026-04-22 (Session 30 — collapsible agency accordion, default collapsed)
**Build method:** Claude Code (Opus 4.6)

---

## Prompt Build Order

| Prompt | Scope | Session date | Issues closed |
|--------|-------|-------------|---------------|
| A | Full scaffold: Django + React + models + tests | 2026-04-01 | — |
| B | Ingestion pipeline: call_logs sync + CSV upload | 2026-04-01 | #4, #5 |
| C | Sync API + RBI COC compliance engine + fatal level | 2026-04-01 | #7 |
| D | S3 URL re-signing + submission tier system | 2026-04-01 | #6 |
| E | S3 raw key storage + IST timezone compliance | 2026-04-01 | #8, #9 |
| F | Bulk dedup pre-fetch: O(1) per row sync performance | 2026-04-01 | #10 |
| G | Webhook recovery polling + call duration + max calls thresholds | 2026-04-01 | #11, #12, #13 |
| Perf-1 | pgbouncer fix: cursor.fetchall() before ORM loop | 2026-04-01 | — |
| Perf-2 | O(1) max_calls_per_customer via pre-fetched call counts dict | 2026-04-01 | — |
| **H** | **New Relic APM instrumentation** | **2026-04-05** | — |
| **I** | **Submit & Poll HTTP endpoints** | **2026-04-07** | — |
| **K** | **URL secret prefix** | **2026-04-07** | — |
| **L** | **System status / health check endpoint** | **2026-04-07** | — |
| **M** | **Phase 1 UI backend: signed-url, flag review, retry + dashboard extended** | **2026-04-07** | — |
| **N** | **CRM React embed: call-audit-frontend-embed branch in crm repo** | **2026-04-07** | — |
| **P** | **crm_apis sync: Prompt M views + serializer + urls + tests → arc/baysys_call_audit** | **2026-04-07** | — |
| **Session 25** | **Live production UAT: 12+ hotfixes, GreyLabs pipeline operational** | **2026-04-07** | — |
| **Q** | **OwnLLM Scoring Backend (designed, not yet executed)** | **2026-04-07** | — |
| **R** | **OwnLLM Score UI swap (designed, not yet executed)** | **2026-04-07** | — |
| **Session 26** | **CRM UI redesign — wine palette, 3-tab IA, privilege-gated Ops, review fixes applied** | **2026-04-20** | — |
| **Session 27** | **Trainer Action Board primitives, compact column-header filters, CallDrawer flyout, customer_id search** | **2026-04-21** | crm #72, #73 merged, #74 open |
| **Session 28** | **Agents/Recordings agency grouping, Active Only toggle, inline agent-ID pill** | **2026-04-21** | crm #75 merged |
| **Session 30** | **Collapsible agency accordion (default collapsed) on both tabs** | **2026-04-22** | crm #77 open |

---

## Session 28 — Agents/Recordings agency grouping, Active Only toggle, inline ID pill

**Date:** 2026-04-21
**Scope:** Third UI pass on the `crm` production frontend. Agent and Recording tables now group by agency with a subtle header row, AgentsTab gets an "Active Only" default-on toggle with an "N active · M total" counter, and the agent cell collapses to a single line with a small slate pill for the agent ID. Backend untouched.

### Repos & branches
- `bsfg-finance/crm` · base branch `master`
- **PR #75** — `audit-ui/agency-grouping-and-active-toggle` → `master` — MERGED.

### What shipped (UI)
- **AgentsTab**
  - Dropped the serial-number (#) column.
  - New **Active Only** wine pill in the header, default ON. "Active" is a frontend heuristic of `calls > 0` — no `is_active` field exists on `AgentSummaryRow` and no backend change was made.
  - **N active · M total** counter rendered alongside the toggle.
  - Rows grouped by `agency_id` with a subtle `bg-slate-50` group-header row (alphabetical, "Unassigned" last). In-group sort preserved.
  - Inline agent-ID pill: Agent cell collapses to a single line with a small slate pill carrying the ID.
- **RecordingsTab**
  - Rows grouped by `agency_id` with the same subtle header pattern.
  - Same inline agent-ID pill on the Agent cell.

### Backend
No change. PR #75 relied entirely on the existing `agency_id` field already on `AgentSummaryRow` / recording payloads. The H-8 gap (filter query params not honoured server-side) is unchanged and still open — unrelated to this session.

### Files touched (crm repo)
- `src/pages/audit/components/AgentsTab.tsx` — Active Only pill, counter, agency grouping, inline ID pill, # column removed.
- `src/pages/audit/components/RecordingsTab.tsx` — agency grouping, inline ID pill.

### Docs
- This `BUILD_LOG.md` entry.
- `MANIFEST.md` — AgentsTab/RecordingsTab rows updated to note Session 28 features.
- `docs/OPERATIONS.md` — no change.

---

## Session 27 — Trainer-primitive adoption, compact filters, CallDrawer flyout

**Date:** 2026-04-21
**Scope:** Second UI pass on the `crm` production frontend to align the Call Audit surface with the Voice Trainer Action Board vocabulary, tighten the recordings triage flow, and replace the full-page call detail route with a right-side flyout. Backend untouched. All work shipped via three PRs on the `crm` repo.

### Repos & branches
- `bsfg-finance/crm` · base branch `master`
- **PR #72** — `call-audit-frontend-embed` → `master` — MERGED. Topbar realignment (`490e1b1`) + Agents-tab Trainer-pattern primitives (`ed9d310`).
- **PR #73** — `audit-ui/compact-filters-and-density` → `master` — MERGED. Compact filter row + denser Ops/Agents layout (`d47af1d`), drop View column row-click nav (`9632ca1`), filter chips folded into column headers (`1fe37df`).
- **PR #74** — `audit-ui/call-flyout-and-customer-search` → `master` — OPEN. Customer ID filter (`839671b`), Call Detail flyout drawer (`2ccebfe`).

### What shipped (UI)
- **Trainer Action Board vocabulary** adopted across AgentsTab and AgentDrawer — new shared primitives `BandStatusPill`, `LevelBadge`, `ScoreBar`, `TrendArrow` co-located in `src/pages/audit/components/primitives.tsx` alongside the earlier `KpiCard` / `StatusPill` / `FatalBadge` / `ScoreCell` / `FilterChip` set.
- **Compact filter row inside column headers** (RecordingsTab): status, agent_id, customer_id, date-range, FATAL ≥3, critical, unreviewed, score <50% chips all live under the column they filter. Old top-of-page filter bar removed.
- **View column removed** — the whole row is now clickable/keyboard-navigable.
- **OpsTab 2×2 tile grid** — denser layout, tighter spacing, no behavioural change.
- **CallDrawer flyout** — replaces the full-page `/call-audit/call/:id` route with a right-side drawer (`src/pages/audit/components/CallDrawer.tsx`) mounted from `App.tsx`. Consistent with AgentDrawer (ESC to close, `role="dialog"`, `aria-modal`). Full-page route still exists for deep linking but Recordings table now opens the drawer by default.
- **Customer ID search** added as a column-header filter (frontend-only — see backend gap below).

### Backend gap (flagged, not fixed in this session)
The recording list backend (`RecordingListView`) does NOT yet honour these query params, which the new UI sends:
- `customer_id`
- `fatal_level_gte`
- `score_lt`
- `has_critical_flags`
- `has_unreviewed_flags`

This affects both the production backend (`crm_apis` branch `call-auditor`, `arc/baysys_call_audit/views.py`) and the standalone reference repo (`Baysys-AI-Call-Auditor/baysys_call_audit/views.py`). A separate task has been spawned to wire these filters through the serializer/view + add tests. Until that lands, the frontend chips will appear to do nothing server-side.

### Branch hygiene
All three session PRs cleanly branched off `master`, merged or are open cleanly, and no stray local commits remain. `call-audit-frontend-embed` was used as the staging branch for PR #72 only — subsequent UI work correctly used dedicated `audit-ui/*` topic branches.

### Files touched (crm repo)
- `src/pages/audit/components/primitives.tsx` — new Trainer-pattern primitives.
- `src/pages/audit/components/AgentsTab.tsx` — adopt BandStatusPill / LevelBadge / ScoreBar / TrendArrow; denser layout.
- `src/pages/audit/components/AgentDrawer.tsx` — same primitive set; layout tightening.
- `src/pages/audit/components/RecordingsTab.tsx` — column-header filters, drop View column, customer_id filter.
- `src/pages/audit/components/OpsTab.tsx` — 2×2 tile grid.
- `src/pages/audit/components/CallDrawer.tsx` — new flyout component (replaces page route usage).
- `src/pages/audit/components/callDetailParts.tsx` — shared detail fragments used by both the drawer and the legacy full-page route.
- `src/App.tsx` — drawer mount.

### Docs
- This `BUILD_LOG.md` entry.
- `MANIFEST.md` updated — new primitives + `CallDrawer.tsx` + `callDetailParts.tsx` listed under "Production UI — `bsfg-finance/crm` repo".
- `docs/OPERATIONS.md` — no change required (no route contract change from an ops perspective; the `/call-audit/call/:id` route still exists for deep linking).

---

## Session 26 — CRM Call Audit UI Redesign (Collexa wine theme)

**Date:** 2026-04-20
**Scope:** Port the Collexa UI redesign from the standalone `Baysys-AI-Call-Auditor` reference into the production `crm` frontend on branch `call-audit-frontend-embed`. Merge with master's privilege-gating changes. Apply pc-code-review findings in the same branch. **Backend untouched.**

### Repos & branches
- `bsfg-finance/crm` · branch `call-audit-frontend-embed` · PR [#68](https://github.com/bsfg-finance/crm/pull/68)
- Commits: `2c1cec7` (redesign) → `acf20e7` (merge origin/master) → `1309a75` (code-review fixes)

### What shipped
- **3-tab IA:** Recordings / Agents / Ops — wine brand palette (`#7d0552`), KPI strip (Compliance Score · Exceptions · Unreviewed Flags · Pipeline).
- **Call Detail page:** 2-column layout with sticky score hero, wine top-border, transcript with amber-highlighted flag evidence, inline flag review round-trip, audio signed-URL with retry.
- **Privilege gating** (layered): Ops tab hidden via `showOpsTab` prop, individual sync/submit/poll buttons disabled via `canWrite` prop, stale `tab==='ops'` state redirected to Recordings. Uses `Privilege.callAudit.edit()` (level ≥ 3).
- **Agency filter** derived from live `summary.agent_summary[].agency_id` — no hardcoded list.
- **Accessibility:** `role="dialog"`, `aria-modal="true"`, `aria-label` on drawer and close button; ESC closes the agent drawer; removed non-keyboard row-click in recordings table (users use the "View →" button).
- **Error handling:** surfaced flag-review PATCH failures to the user instead of silent ignore.

### CRM repo files created (9)
- `src/pages/audit/components/AuditShell.tsx` — header + agency/period filters + tab strip (accepts `agencies` and `showOpsTab` props).
- `src/pages/audit/components/primitives.tsx` — `KpiCard`, `StatusPill`, `FatalBadge`, `ScoreCell`, `FilterChip`.
- `src/pages/audit/components/RecordingsTab.tsx` — filter chips (FATAL ≥3 / score <50 / critical / unreviewed), status/agent/date filters, paged table.
- `src/pages/audit/components/AgentsTab.tsx` — sortable table, opens drawer on row click.
- `src/pages/audit/components/AgentDrawer.tsx` — slide-in panel, Overview + Call History tabs.
- `src/pages/audit/components/OpsTab.tsx` — pipeline status, dry-run toggle, sync/submit/poll action cards.
- `src/pages/audit/components/ScoreTrendChart.tsx` — recharts LineChart with 85/70/55 reference lines (kept for future per-call-score backend endpoint).

### CRM repo files modified
- `src/pages/audit/AuditDashboardPage.tsx` — rewritten on top of `AuditShell`; derives agency options from summary; applies `Privilege.callAudit.edit()` gate + redirect guard.
- `src/pages/audit/AuditCallDetailPage.tsx` — full 2-column rewrite.
- `src/types/audit.ts` — added `OpsResult`, `SignedUrlResponse`, `ScoreBand`, `AgentSummaryRow` (adds `unreviewed_flags`, `agency_id`), `compliance_flag_count?` on `CallRecording`. Helpers: `scoreBand()`, `scoreBandLabel()`, `formatDuration()`, `formatDateTime()`.
- `tailwind.config.js` — added `brand.wine`/`wine-dark`/`wine-light`; disabled Tailwind preflight (master) to avoid Bootstrap reset clash.

### Code review (pc-code-review) findings — all applied in commit `1309a75`
- 🟠 **H-1:** Removed the dead Score Trend chart in AgentDrawer (all-null data by construction). Replaced with plain "Recent Activity" summary until a backend endpoint returns per-call scores.
- 🟠 **H-2:** Noted — no vitest runner in `crm/`. Deferred for a separate test-infra PR.
- 🟡 **M-1:** Flag review PATCH failures now surface via `setRetryMsg` instead of silent ignore.
- 🟡 **M-2:** AgentDrawer has ESC handler, `role="dialog"`, `aria-modal`, `aria-label`, and accessible close button.
- 🟡 **M-3:** Removed non-keyboard `<tr onClick>` in RecordingsTab; "View →" button is the single interaction path.
- 🟡 **M-4:** Removed spurious `eslint-disable react-hooks/exhaustive-deps` comments. Added `fetchSignedUrl` to effect deps in AuditCallDetailPage.
- 🟡 **M-5:** `AuditShell` accepts `agencies: AgencyOption[]` prop; `AuditDashboardPage` derives options from `summary.agent_summary[].agency_id`.
- 🔵 Minor: dropped unused `useNavigate` + `void navigate` hack; guarded `recordingId` against NaN/≤0; dropped unused `refreshKey` prop (parent `key=` forces remount).

### Test gate
- `npx tsc --noEmit` — 0 errors.
- `npx eslint src/pages/audit src/types/audit.ts --max-warnings=0` — 0 errors, 0 warnings.
- `npm run build` — succeeds (8.9s). Main chunk 2.88 MB / 785 kB gzip — pre-existing, not caused by this PR.
- Backend untouched; standalone `Baysys-AI-Call-Auditor` test count unchanged at 320.

### Key decisions
1. **Tailwind over React-Bootstrap** for the redesign to match the Collexa standalone reference. The existing crm shell still uses React-Bootstrap — coexistence works because preflight is disabled, so Bootstrap's reset remains authoritative.
2. **Privilege check is belt-and-braces** — tab hidden + button disabled + route-state redirect. Defence in depth against stale state or direct tab mutation.
3. **Agency list lives with the dashboard data, not the shell.** `AuditShell` now has no knowledge of which agencies exist.
4. **Score Trend deferred** rather than faked. The label on a zero-data chart is worse than its absence.
5. **`crm_adapter.py` / `speech_provider.py` rules untouched.** This PR is frontend-only; the backend single-seam invariants are not affected.

### Code review output
Saved to `BaySysAI/DOCUMENTATION/Code-Reviews/code-review-crm-call-audit-ui-redesign-2026-04-19.md`.

---

## Session 25 — Live Production UAT

**Date:** 2026-04-07
**Scope:** First live production UAT with GreyLabs webhooks processing real calls. 12+ hotfixes discovered and committed during live testing. OwnLLM scoring architecture designed (Prompts Q + R written to disk). Deep code review completed.

### Production hotfixes (all committed to standalone + crm_apis `call-auditor` branch)

| # | Fix | File(s) | Root cause |
|---|-----|---------|------------|
| 1 | axios timeout 60s + sync date picker | `auditAxios.ts`, `AuditDashboardPage.tsx` | UI timeout too short for sync |
| 2 | batch_size silently ignored after pgbouncer fix | `ingestion.py` | batch_size param not threaded through |
| 3 | bulk_create (was N individual ORM creates) | `ingestion.py` | Slow inserts over pooler connection |
| 4 | IST timezone fix (naive call_start_time → IST-aware) | `ingestion.py` | `make_aware()` defaulted to UTC |
| 5 | GreyLabs: `data=` → `json=` in submit_recording | `speech_provider.py` | Wrong requests param → empty body |
| 6 | GreyLabs: E009 missing customer_id | `services.py`, `speech_provider.py` | Required field not in submission payload |
| 7 | Webhook: defensive JSON parse (non-JSON Content-Type) | `views.py` | GreyLabs webhook sent non-standard Content-Type |
| 8 | Webhook: unwrap `details[0]` from GreyLabs payload | `services.py`, `speech_provider.py` | Payload nested in `{"details":[{...}]}` |
| 9 | SYNC/SUBMIT/POLL_BATCH_SIZE from Django settings | `services.py`, `views.py`, `.env.example` | Hardcoded batch sizes |
| 10 | `compliance_rules.yaml` content_hash auto-sync | `compliance.py` | Hash mismatch on config edit |
| 11 | `add_custom_attributes`: dict → list of tuples | `services.py` | NR API requires `[(name, value)]`, not `{name: value}` — caused ValueError on every webhook |
| 12 | UI: STATUS_LABEL map, phone masking, evidence fmt, dry-run toggle | `AuditDashboardPage.tsx`, `AuditCallDetailPage.tsx` | UI polish for production readiness |

### Architecture decision: OwnLLM Scoring (Option C)

**Problem:** GreyLabs returns its own internal score (e.g. 100% for Wrong Party Connect calls) which does not correspond to the UVARCL 19-parameter scorecard. Their `category_data` field is structured differently than expected (`insights` nesting vs root level). Showing GreyLabs' score as "Compliance Score" is misleading.

**Decision:** Implement own LLM scoring (`run_own_llm_scoring()`) using Anthropic API + UVARCL scorecard. GreyLabs provides transcription + analytics; our LLM scores against the 19-parameter rubric. `OwnLLMScore` becomes primary compliance score; `ProviderScore` demoted to "GreyLabs Analytics" collapsible section.

**Prompts designed:**
- `docs/prompts/prompt-Q-own-llm-scoring.md` — Backend: scoring YAML, Anthropic API integration, services.py, compliance.py handler, tests
- `docs/prompts/prompt-R-own-llm-score-ui.md` — Frontend: `LLMScoreSection` component, score ring, parameter breakdown, GreyLabs collapsible

**New env vars (for Prompt Q):**
- `OWN_LLM_ENABLED=true`
- `OWN_LLM_API_KEY=<anthropic-key>`
- `OWN_LLM_MODEL=claude-haiku-4-5-20251001`
- `OWN_LLM_SCORING_TEMPLATE=scoring_template_uvarcl_v2`

### Code review (session 25)

Full review saved to `Documentation/Code-Reviews/code-review-call-auditor-session25-2026-04-07.md`.

- **0 CRITICAL / 8 HIGH / 9 MEDIUM / 4 MINOR**
- Top concerns: webhook retry idempotency (H-1, H-2), non-atomic webhook pipeline (H-3), `category_data` extraction from wrong location (H-4)
- Build rules compliance: 8/10 (violated: Rule 3 crm_apis ruff, Rule 10 docs freshness)
- All fixes have Claude Code prompts ready in the review report

### Key learnings from live UAT

1. **GreyLabs webhook payload:** `{"status":"success","details":[{...}]}` — data always nested in `details[0]`. Not documented in their API reference.
2. **GreyLabs `category_data`:** List at root level, NOT nested in `insights`. Code was reading from wrong location → stored as None.
3. **`newrelic.agent.add_custom_attributes()`:** Requires list of tuples `[(name, value)]`, NOT a dict. Dict iteration yields keys as strings → `ValueError: too many values to unpack (expected 2)`.
4. **pgbouncer transaction mode:** `cursor.fetchall()` must complete before any ORM write on the same connection, otherwise the cursor becomes invalid.
5. **GreyLabs score ≠ UVARCL compliance score:** Their template score is an internal metric. Must score independently against our 19-parameter rubric.

### Pending (must do next session, in order)

1. Run Prompt Q (OwnLLM Scoring Backend) — HIGH PRIORITY
2. Run Prompt R (OwnLLM Score UI) — depends on Q
3. Apply H-1, H-2, H-3 fixes (idempotency + atomic pipeline)
4. `ruff check --fix` on crm_apis (58 auto-fixable errors)
5. Push crm_apis commits from terminal (SSH blocked in sandbox)
6. Re-sync corrected IST timestamps for affected dates
7. Poll Stuck recordings after deploy

### Test count at end of session: 317 passing (standalone), 0 ruff findings (standalone)

---

## Session 25 (cont.) — GreyLabs Webhook Integration Fix

**Date:** 2026-04-08
**Scope:** Diagnosed and fixed the complete GreyLabs webhook pipeline after live UAT confirmed all webhook callbacks were being silently dropped. Root cause identified via comparison of API documentation vs actual live payload format. Architecture corrected. 3 new model fields added. 320 tests passing.

### Root cause

The webhook handler assumed the live payload matched the GreyLabs documentation format (`{"details": [{id, transcript, scores, ...}]}`). Confirmed from GreyLabs (Kanishk Gunsola) that:
1. The webhook delivers a **flat notification only**: `{"id": <int>, "category_data": [...], "subjective_data": [...]}`
2. The `details[]` wrapper format is for the **GET Insights API only** — not webhooks
3. `"id"` is the `resource_id` — matches `provider_resource_id` stored at submission
4. Full data (transcript, durations, `audit_template_parameters`, scoring) only available via GET Insights API

Consequence: every webhook callback returned silent 404 — recordings stayed `status=submitted` indefinitely. Poll recovery also broken (checked `transcript` at wrong level in GET response).

### Fixes (commit `93a2d01`)

| # | Change | File |
|---|--------|------|
| 1 | `process_provider_webhook()`: webhook treated as completion signal only. After resource_id lookup via `record.get("id")`, calls `speech_provider.get_results()` to fetch full data. Extracts `details[0]`. Guards on `progress < 100`. Passes full record to all downstream helpers. | `services.py` |
| 2 | `run_poll_stuck_recordings()`: fixed "still processing" check — unwraps `details[0]` before checking `transcript`/`progress`, matching actual GET Insights response shape. | `services.py` |
| 3 | Added `audit_template_parameters` (JSONField) + `function_calling_parameters` (JSONField) to `ProviderScore`; added `default_prompt_response` (TextField) to `CallTranscript`. Migration `0005`. | `models.py` |
| 4 | `_create_provider_score()` + `_create_transcript()` read new fields from GET response record. `audit_template_parameters` stores per-parameter Yes/No answers, scores, max scores, justifications from the UVARCL template. | `services.py` |

### New fields now stored per scored call

| Field | Model | Source | Purpose |
|-------|-------|--------|---------|
| `audit_template_parameters` | `ProviderScore` | GET response top-level | Per-parameter scores: answer, score, max_score, is_fatal_score, justification |
| `function_calling_parameters` | `ProviderScore` | GET response top-level | Binary feature detection: greeting, closing, dead air, hold time, rate of speech |
| `default_prompt_response` | `CallTranscript` | GET response top-level | LLM-generated call narrative and audit report |

### Recovery plan (execute after deploy)

- 2 recordings stuck in `status=submitted` from UAT: recover via `POST /recordings/poll/ {"batch_size": 5}`
- 100 recordings currently in-flight with GreyLabs: will be processed correctly as webhooks arrive
- 1000 recordings in `status=pending`: unaffected — not yet submitted

### IST timezone fix — create_recording_from_row() + settings.py

**Commit:** pushed 2026-04-08 (after Session 25 cont.)

Two gaps missed in the Session 25 IST hotfix:

1. `create_recording_from_row()` in `ingestion.py` — `make_aware()` was called without specifying `ZoneInfo("Asia/Kolkata")`. Django fell back to `settings.TIME_ZONE` (default `'America/Chicago'`) — 10.5 hours off from IST. Fixed to match `run_sync_for_date()` pattern.

2. `settings.py` — no `TIME_ZONE` or `USE_TZ` defined. Added `TIME_ZONE = "Asia/Kolkata"` and `USE_TZ = True` explicitly.

**Data fix pending:** Harshit to run check query on prod DB to confirm scope and magnitude of existing wrong-timezone records, then PC to confirm offset before UPDATE is run.

### Pending (unchanged from Session 25)

1. Run Prompt Q (OwnLLM Scoring Backend) — HIGH PRIORITY
2. Run Prompt R (OwnLLM Score UI) — depends on Q
3. Apply H-1, H-2, H-3 fixes (idempotency + atomic pipeline)
4. `ruff check --fix` on crm_apis (58 auto-fixable errors)
5. Push crm_apis commits from terminal
6. Re-sync corrected IST timestamps for affected dates
7. Confirm webhook fix with live UAT results (Harshit to report 2026-04-09)

### Test count: 320 passing (standalone), 0 ruff findings

---

## Session 14 (cont.) — Prompt P: crm_apis Sync (Prompt M → arc/baysys_call_audit)

**Date:** 2026-04-07
**Scope:** Brought `arc/baysys_call_audit` in crm_apis to full parity with standalone at Prompt M. Previously merged at Prompt J (302 tests); missing 3 views, extended dashboard, serializer fields.

### Files modified (crm_apis `call-auditor` branch, commit f131991)

| File | Changes |
|------|---------|
| `arc/baysys_call_audit/views.py` | Added `Q` + `crm_adapter` imports; extended `DashboardSummaryView.get()` with `submitted`, `last_sync_at`, `last_completed_at`, `agent_summary`; inserted `RecordingSignedUrlView`, `FlagReviewView`, `RecordingRetryView` |
| `arc/baysys_call_audit/serializers.py` | Added `submitted`, `last_sync_at`, `last_completed_at`, `agent_summary` to `DashboardSummarySerializer` |
| `arc/baysys_call_audit/urls.py` | 3 new imports + 3 new URL routes (`signed-url`, `retry`, `flag-review`) |
| `arc/baysys_call_audit/tests/test_views.py` | Added `APIRequestFactory`/`patch` imports + 4 new test classes (14 tests) |

### Notes

- ruff: 0 findings
- Tests not run locally (crm_apis connects to production RDS — cannot create test DB without remote access). Identical logic passes 317/317 in standalone.
- PR `call-auditor → master` in crm_apis is now unblocked.

---

## Session 14 (cont.) — Prompt N: CRM React Embed + Code Review

**Date:** 2026-04-07
**Scope:** Full admin-only Call Audit UI embedded in the CRM React repo on branch `call-audit-frontend-embed`. Standalone repo received Prompt M fixes and code review. ESLint clean (7 errors fixed across pre-existing + new).

### CRM repo files created (branch: `call-audit-frontend-embed`)

| File | Purpose |
|------|---------|
| `src/hooks/useAuditAuth.ts` | Auth adapter — mirrors `useTrainerAuth`, returns `{ user, isAdmin, isLoading }` |
| `src/utils/auditAxios.ts` | Axios instance — `VITE_AUDIT_URL_SECRET` sourced URL prefix, cookie + Bearer fallback |
| `src/utils/auditApi.ts` | Typed endpoint constants for all 10 audit endpoints |
| `src/types/audit.ts` | TypeScript interfaces for all backend response shapes |
| `src/pages/audit/AuditDashboardPage.tsx` | Stats cards, recordings table (filters), agents leaderboard, ops panel |
| `src/pages/audit/AuditCallDetailPage.tsx` | Audio player, flags (mark reviewed), scorecard, transcript, retry |

### CRM repo files modified

| File | Changes |
|------|---------|
| `src/App.tsx` | Added `AdminRoute` guard + 2 audit routes; eslint-disable for pre-existing `TrainerRoute` dead code |
| `src/components/Header.tsx` | Added `ClipboardCheck` icon + "Call Audit" nav item (admin only); fixed 4 pre-existing ESLint issues |
| `src/layouts/DashboardLayout.tsx` | Added `isAuditPage` to remove container padding for audit pages |

### Code review findings (2026-04-07)

- 0 CRITICAL / 1 HIGH / 1 MEDIUM / 1 MINOR
- **H-1 (BLOCK):** crm_apis `arc/baysys_call_audit` missing Prompt M (3 views + dashboard extensions). Prompt P needed before merging PR `call-auditor → master`.
- **M-1:** crm_apis `.envs` changes uncommitted — commit before closing branch.
- **MINOR (fixed):** 7 ESLint errors resolved — `fmtPct` unused (Prompt N), `TrainerRoute` unused (pre-existing), `catch(err)` unused (pre-existing), 4× `any` (pre-existing).

### Automated checks (post-review)

- tsc: 0 errors
- eslint: 0 errors, 0 warnings (all 9 Prompt N files + App.tsx + Header.tsx + DashboardLayout.tsx)
- ruff (standalone + crm_apis): 0 findings
- pytest: 317/317 (from Prompt M — not re-run this session)

### Pending

- Prompt P: sync Prompt M to crm_apis before merging PR
- Merge PR `call-auditor → master` in crm_apis
- Set production env vars and run migrations
- GreyLabs UAT

---

## Session 14 — Prompt L: System Status / Health Check Endpoint

**Date:** 2026-04-07
**Scope:** `GET /audit/<URL_SECRET>/admin/status/?token=<AUDIT_STATUS_SECRET>` — read-only health snapshot with token auth, migration state, recording activity, env var presence, NR event.

### Files created

- `baysys_call_audit/tests/test_system_status.py` — 8 tests covering token auth, top-level keys, DB query, env_vars, migrations

### Files modified

| File | Changes |
|------|---------|
| `views.py` | Added `_build_recording_activity()` (uses `completed_at`/`status=completed`), `_AUDIT_ENV_VAR_KEYS`, `_fire_nr_audit_status_event()`, `SystemStatusView` (Django `View`, hmac token auth, migrations, backend, frontend, NR event); added imports: `hmac`, `json`, `os`, `Count`, `JsonResponse`, `timezone`, `View` |
| `urls.py` | Added `admin/status/` → `SystemStatusView`; imported `SystemStatusView` |
| `settings.py` | Added `AUDIT_STATUS_SECRET = config("AUDIT_STATUS_SECRET", default="dev-status-secret")` |
| `.env.example` | Added `AUDIT_STATUS_SECRET=dev-status-secret` with comment |
| `MANIFEST.md` | Updated views.py + urls.py rows; added test_system_status.py row; total 294 → 302 |
| `BUILD_LOG.md` | This entry |
| `CLAUDE.md` | Updated test gate + current state |

### Notes

- Auth uses `getattr(settings, "AUDIT_STATUS_SECRET", "")` (not `os.environ.get`) so `override_settings` works in tests. NR helpers still use `os.environ.get` since they short-circuit when keys are absent.
- `_build_recording_activity` uses `completed_at` / `status=completed` — there is no `scored_at` or `scored` status in the Call Auditor model.
- Endpoint is a plain Django `View` (not DRF `APIView`) to avoid DRF auth overhead on a monitoring endpoint.

---

## Session 13 — Prompt K: URL Secret Prefix

**Date:** 2026-04-07
**Scope:** All audit endpoints hidden behind a configurable secret URL segment (`AUDIT_URL_SECRET`). No changes to app-level URL patterns.

### Files modified

| File | Changes |
|------|---------|
| `settings.py` | Added `AUDIT_URL_SECRET = config("AUDIT_URL_SECRET", default="dev-secret")` |
| `urls.py` (root) | Path prefix changed from `"audit/"` to `f"audit/{settings.AUDIT_URL_SECRET}/"` |
| `.env.example` | Added `AUDIT_URL_SECRET=dev-secret`; updated `SPEECH_PROVIDER_CALLBACK_URL` comment to note secret must be included |
| `tests/test_views.py` | Replaced hardcoded `/audit/...` paths with `reverse("baysys_call_audit:<name>")` |
| `tests/test_webhook.py` | Replaced hardcoded `/audit/webhook/provider/` with `reverse("baysys_call_audit:provider-webhook")` |
| `MANIFEST.md` | Updated `.env.example` row to note `AUDIT_URL_SECRET` |
| `BUILD_LOG.md` | This entry |
| `CLAUDE.md` | Added `AUDIT_URL_SECRET` note |

### Notes

- `baysys_call_audit/urls.py` is untouched — prefix applied at root level only.
- Tests using `APIRequestFactory` + direct view calls (test_sync_api, test_import_recordings, test_submit_api, test_poll_stuck_recordings) were not modified — the URL string in `factory.post(...)` is metadata only, not used for routing.
- Tests using `APIClient` (test_views, test_webhook) now use `reverse()` so they remain correct regardless of the prefix value.
- `settings.py` already had `import os` (unused, pre-existing). Out of ruff scope (`baysys_call_audit/`).

---

## Session 12 — Prompt I: Submit & Poll HTTP Endpoints

**Date:** 2026-04-07
**Scope:** Extract `run_poll_stuck_recordings()` into services.py; add `SubmitRecordingsView` and `PollStuckRecordingsView` endpoints; 11 new tests.

### Files created

- `baysys_call_audit/tests/test_submit_api.py` — 11 tests for both new views

### Files modified

| File | Changes |
|------|---------|
| `services.py` | Added `run_poll_stuck_recordings(batch_size, dry_run)` with `@background_task` decorator; updated module docstring |
| `management/commands/poll_stuck_recordings.py` | Refactored `handle()` to call `run_poll_stuck_recordings()` — all logic moved to services; removed now-unused `speech_provider`, `CallRecording`, `_normalise_provider_payload`, `process_provider_webhook` imports |
| `views.py` | Added `SubmitRecordingsView` (`POST /audit/recordings/submit/`), `PollStuckRecordingsView` (`POST /audit/recordings/poll/`); imported `IsAuthenticated`, `submit_pending_recordings`, `run_poll_stuck_recordings`; updated module docstring |
| `urls.py` | Added `recordings/submit/` and `recordings/poll/` routes; imported both new views |
| `tests/test_poll_stuck_recordings.py` | Updated all patch paths from command module to `baysys_call_audit.services.*` (logic moved to services.py) |
| `MANIFEST.md` | Updated services.py, views.py, urls.py rows; added test_submit_api.py row; total 283 → 294 |
| `BUILD_LOG.md` | This entry |
| `CLAUDE.md` | Test gate 283 → 294 |

### Notes

- DRF coerces `NotAuthenticated` (401) → 403 when no `WWW-Authenticate` header is provided (`MockCrmAuth` has no `authenticate_header()`). Tests assert 403 for the unauthenticated case and include an inline comment explaining the behaviour.
- `run_poll_stuck_recordings()` calling `process_provider_webhook()` (also `@background_task`) is safe — NR agent nests transactions without creating a new root transaction.

---

## Session 11 — Prompt H: New Relic APM Instrumentation

**Date:** 2026-04-05
**Scope:** New Relic APM instrumentation — full implementation.

### Files created

- `newrelic.ini.example` — APM config template (no secrets; env-var-first; development/staging/production stanzas)
- `baysys_call_audit/tests/test_newrelic_instrumentation.py` — 8 tests verifying `@background_task` decorators + no-op safety

### Files modified

| File | Changes |
|------|---------|
| `services.py` | `import newrelic.agent`; `@background_task` on `submit_pending_recordings`, `process_provider_webhook`, `run_own_llm_scoring`; `add_custom_attributes` in submission loop and webhook lookup; `record_custom_metric` for `Submitted`, `SubmitFailed`, `Webhooks/Processed`, `Webhooks/IdempotencySkip` |
| `ingestion.py` | `import newrelic.agent`; `@background_task` on `run_sync_for_date`; `record_custom_event('SyncCompleted', {...})` at end of sync including target_date, fetched, created, skipped_dedup, skipped_validation, duration_seconds |
| `compliance.py` | `import newrelic.agent`; `record_custom_metric('Custom/Compliance/MetadataFlags/{flag_type}', 1)` per metadata flag; `record_custom_metric('Custom/Compliance/ProviderFlags/{flag_type}', 1)` per provider flag; `record_custom_metric('Custom/Compliance/FatalLevel', fatal_level)` in `compute_fatal_level` |
| `speech_provider.py` | `import newrelic.agent`; `record_custom_event('ProviderError', {'endpoint', 'status_code', 'message'})` on HTTP errors in `submit_recording` and `get_results` |
| `views.py` | `import newrelic.agent`; `add_custom_attributes({'webhook_source': 'provider'})` in `ProviderWebhookView`; `add_custom_attributes({'recording_id', 'agent_id'})` in `RecordingDetailView`; `add_custom_attributes({'sync_date', 'dry_run'})` in `SyncCallLogsView` |
| `CLAUDE.md` | Added Observability — New Relic APM section (9 build rules) |
| `docs/OPERATIONS.md` | Added New Relic APM section (env vars, cron wrappers, custom metrics table, K8s migration note) |
| `requirements.txt` | Added `newrelic>=10.0` |
| `.env.example` | Added `NEW_RELIC_LICENSE_KEY`, `NEW_RELIC_APP_NAME`, `NEW_RELIC_ENVIRONMENT` |
| `.gitignore` | Added `newrelic.ini` |
| `docs/new-relic-telemetry-plan.md` | Created — 4-phase implementation plan with alert definitions |
| `docs/prompts/prompt-H-new-relic.md` | Created — Claude Code prompt spec (8 tasks, acceptance criteria) |

### Test results

```
Ran 283 tests in 0.242s — OK
ruff check baysys_call_audit/ — 0 findings
```

---

## Session 1 — Prompt A: Project Scaffold

**Date:** 2026-04-01
**Scope:** Complete project scaffold — Django app, React UI scaffold, full test suite, documentation.

### Files created

**Root:**
- `manage.py` — Django CLI entry point
- `settings.py` — flat Django settings with python-decouple, Supabase DB, CORS, provider env vars
- `settings_test.py` — SQLite in-memory override for tests
- `urls.py` — root URL config (admin + audit app)
- `requirements.txt` — Django, DRF, psycopg2-binary, requests, python-decouple, ruff
- `.env.example` — template for all env vars
- `.gitignore` — Python, Node, Django, OS ignores

**Django app (`baysys_call_audit/`):**
- `__init__.py`, `apps.py` — app config
- `models.py` — 5 models: CallRecording, CallTranscript, ProviderScore, ComplianceFlag, OwnLLMScore
- `admin.py` — all 5 models registered
- `auth.py` — MockUser, MockCrmAuth, get_auth_backend(), AuditPermissionMixin
- `crm_adapter.py` — 6 functions with mock/prod branching
- `speech_provider.py` — 6 public functions + ProviderError, implements GreyLabs
- `services.py` — submit_pending_recordings(), process_provider_webhook(), check_compliance(), run_own_llm_scoring() (placeholder)
- `serializers.py` — 7 serializers
- `views.py` — 5 views (webhook, recording list/detail, dashboard summary, compliance flags)
- `urls.py` — 5 URL patterns
- `migrations/0001_initial.py` — auto-generated

**Tests (`baysys_call_audit/tests/`):**
- `test_models.py` — 18 tests
- `test_speech_provider.py` — 12 tests
- `test_webhook.py` — 8 tests
- `test_services.py` — 13 tests
- `test_views.py` — 14 tests
- `test_crm_adapter.py` — 7 tests

**React scaffold (`baysys_call_audit_ui/`):**
- Full Vite + TypeScript + Tailwind config
- 2 pages (Dashboard, CallDetail), 4 components (ScoreCard, ComplianceFlags, AgentTable, TrendChart)
- Types, API client, mock auth context

**Documentation:**
- `CLAUDE.md`, `README.md`, `MANIFEST.md`, `BUILD_LOG.md`
- `docs/OPERATIONS.md`, `docs/speech-provider/api-reference.md`, `docs/testing/test-guide.md`

### Key decisions

1. **Provider abstraction via `speech_provider.py`** — all GreyLabs-specific code isolated in one file. Model fields use generic names (`provider_resource_id` not `greylabs_id`). Swapping providers requires changing only this file.

2. **Webhook idempotency on `provider_resource_id`** — if a recording is already `completed`, the webhook returns 200 without reprocessing. Prevents duplicate transcripts/scores from provider retries.

3. **Compliance as separate model** — `ComplianceFlag` is a standalone table (not embedded in scores) to support multiple flag types per recording, independent review workflow, and severity-based alerting.

4. **OwnLLMScore as placeholder** — schema created with minimal fields. `run_own_llm_scoring()` returns None. Implementation deferred to a future prompt.

5. **Same RBAC as Trainer** — role IDs 1-5, `AuditPermissionMixin` with `get_user_filter()` that scopes queries by role. Agents see own calls, TLs see agency, admins see all.

6. **Recording URL max_length=2000** — S3 signed URLs with presigned params can be very long.

7. **Separate schema, same Supabase instance** — `DB_SCHEMA=baysys_call_audit` in settings. No FK relationships to Trainer tables. Comparison happens at dashboard layer.

### Test count at end of session: 72 passing, 0 ruff findings

---

## Session 2 — Prompt B: Ingestion Pipeline

**Date:** 2026-04-01
**Scope:** Two ingestion paths to populate CallRecording: daily sync from uvarcl_live.call_logs + CSV/Excel upload.
**Issues closed:** #4, #5

### Files created

- `baysys_call_audit/ingestion.py` — shared ingestion logic: `create_recording_from_row()`, `validate_row()`, `parse_datetime_flexible()`, `normalize_column_name()`
- `baysys_call_audit/management/__init__.py`
- `baysys_call_audit/management/commands/__init__.py`
- `baysys_call_audit/management/commands/sync_call_logs.py` — daily sync from `uvarcl_live.call_logs` LEFT JOIN `uvarcl_live.users`, raw SQL via `django.db.connection`, args: `--date`, `--batch-size`, `--dry-run`
- `baysys_call_audit/management/commands/import_recordings.py` — CSV/Excel upload via `csv` + `openpyxl`, normalized column headers, args: `file_path`, `--sheet`, `--dry-run`
- `baysys_call_audit/tests/test_ingestion.py` — 28 tests
- `baysys_call_audit/tests/test_sync_call_logs.py` — 11 tests
- `baysys_call_audit/tests/test_import_recordings.py` — 24 tests

### Files modified

- `baysys_call_audit/views.py` — added `RecordingImportView` (POST /audit/recordings/import/, Admin/Manager only)
- `baysys_call_audit/urls.py` — added `recordings/import/` route
- `requirements.txt` — added `openpyxl>=3.1`
- `MANIFEST.md` — updated with new files, test counts
- `BUILD_LOG.md` — this entry
- `docs/OPERATIONS.md` — added sync + import usage sections

### Key decisions

1. **Raw SQL for call_logs/users** — these are CRM-owned tables in `uvarcl_live` schema. No Django models created. Raw SQL with `django.db.connection.cursor()` keeps us read-only.

2. **Single JOIN, not two-pass** — agent name resolved in the same query via LEFT JOIN to `users`. No second enrichment step. `agent_name` defaults to `'Unknown'` if user lookup fails.

3. **Dedup on `recording_url`** — `create_recording_from_row()` checks for existing rows before creating. Running sync twice for the same date is safe.

4. **Shared ingestion layer** — `ingestion.py` contains all validation, dedup, datetime parsing, and column normalization. Both the sync command and import command use the same core function.

5. **DRF import endpoint** — convenience API at `/audit/recordings/import/`. Restricted to role_id 1 (Admin) and 2 (Manager/TL). Management command is the primary mechanism.

6. **Column name normalization** — `normalize_column_name()` handles spaces, camelCase, hyphens, so CSV headers like "Agent ID" or "agentId" both map to `agent_id`.

7. **openpyxl for Excel** — added to requirements.txt. Only imported inside function bodies to avoid import errors if not installed.

### Test count at end of session: 135 passing, 0 ruff findings

---

## Session 3 — Prompt C: Sync API + Compliance Engine + Fatal Level

**Date:** 2026-04-01
**Scope:** Failsafe sync API endpoint, config-driven RBI COC compliance engine (YAML), fatal level weighted boolean scoring.
**Issues closed:** #7

### Files created

- `baysys_call_audit/compliance.py` — config-driven compliance engine: metadata rules (call_window, blocked_weekday, gazette_holiday, max_calls_per_customer), provider rules (fatal_level_threshold, provider_score_threshold, provider_transcript_field), fatal level computation from provider boolean scores, content hash verification
- `config/compliance_rules.yaml` — 4 metadata rules + 3 provider rules
- `config/fatal_level_rules.yaml` — 6 boolean parameters with weights, content hash
- `config/gazette_holidays_2026.txt` — 22 India gazette holidays
- `baysys_call_audit/migrations/0002_callrecording_fatal_level.py` — adds `fatal_level` IntegerField
- `baysys_call_audit/management/commands/update_fatal_level_hash.py` — computes SHA-256 content hash for fatal_level_rules.yaml
- `baysys_call_audit/tests/test_compliance.py` — 38 tests
- `baysys_call_audit/tests/test_fatal_level.py` — 14 tests
- `baysys_call_audit/tests/test_sync_api.py` — 9 tests

### Files modified

- `baysys_call_audit/models.py` — added `fatal_level` field to CallRecording
- `baysys_call_audit/services.py` — removed old `check_compliance()` + `_check_call_timing()`, integrated `compliance.py` (compute_fatal_level + check_provider_compliance) into webhook processing
- `baysys_call_audit/ingestion.py` — factored `run_sync_for_date()` as shared sync core, added `check_metadata_compliance()` call after recording creation
- `baysys_call_audit/views.py` — added `SyncCallLogsView` (POST /audit/recordings/sync/, Admin/Supervisor only)
- `baysys_call_audit/urls.py` — added `recordings/sync/` route
- `baysys_call_audit/management/commands/sync_call_logs.py` — thin wrapper calling `run_sync_for_date()`
- `settings.py` — added `COMPLIANCE_MAX_CALLS_PER_CUSTOMER_PER_DAY`, `COMPLIANCE_FATAL_THRESHOLD`, `SYNC_ALLOWED_ROLES`
- `requirements.txt` — added `pyyaml>=6.0`
- `baysys_call_audit/tests/test_services.py` — updated: removed `check_compliance` import, mocked compliance in webhook tests
- `baysys_call_audit/tests/test_webhook.py` — updated: mocked compliance engine, adjusted outside_hours test
- `baysys_call_audit/tests/test_sync_call_logs.py` — updated: imports from `ingestion.py` instead of command module

### Key decisions

1. **Config-driven compliance** — rules in `config/compliance_rules.yaml`. Adding a rule of an existing check_type = YAML-only change, no code.

2. **Metadata rules at ingestion, provider rules at webhook** — clear separation. Metadata compliance runs when CallRecording is created; provider compliance runs when webhook delivers results.

3. **Fatal level from boolean scores** — `config/fatal_level_rules.yaml` maps provider boolean parameters to weighted scores. `fatal_level = min(sum_triggered_weights, 5)`. Ops edits weights, runs `update_fatal_level_hash`, commits to git.

4. **Content hash for audit integrity** — SHA-256 of YAML content (excluding hash line) stored in `content_hash` field. Mismatch logs WARNING but does not block scoring.

5. **Settings override YAML params** — Django settings (`COMPLIANCE_CALL_WINDOW_START_HOUR`, etc.) take precedence over YAML defaults.

6. **Sync logic factored into `ingestion.py`** — `run_sync_for_date()` is the single implementation. Management command and API view are both thin wrappers.

7. **Restricted keywords preserved in provider compliance** — carried over from the old engine as a hardcoded check alongside config-driven rules.

### Test count at end of session: 186 passing, 0 ruff findings

---

## Session 4 — Prompt D: S3 URL Re-signing + Submission Tier System

**Date:** 2026-04-01
**Scope:** Fix S3 URL expiry problem; add config-driven submission tier system (immediate/normal/off_peak).
**Issues closed:** #6

### Files created

- `config/submission_priority.yaml` — tier assignment config: agency_ids, bank_names, product_types per tier
- `baysys_call_audit/migrations/0003_callrecording_submission_tier.py` — adds `submission_tier` CharField
- `baysys_call_audit/management/commands/submit_recordings.py` — submit pending recordings. Args: `--tier`, `--batch-size`, `--dry-run`
- `baysys_call_audit/tests/test_submission_tiers.py` — 35 tests

### Files modified

- `baysys_call_audit/crm_adapter.py` — added `get_signed_url(s3_path)` (mock: returns path unchanged; prod: calls `arc.s3.service.s3_download()`)
- `baysys_call_audit/models.py` — added `submission_tier` CharField(20, default=normal, db_index=True) with TIER_CHOICES
- `baysys_call_audit/ingestion.py` — added `_load_submission_priority()` (lru_cache), `_tier_matches()`, `_determine_submission_tier()`; set `submission_tier` in `create_recording_from_row()`
- `baysys_call_audit/services.py` — added `tiers` parameter to `submit_pending_recordings()`; added `get_signed_url()` call immediately before each provider submission with fallback to stored URL
- `baysys_call_audit/tests/test_crm_adapter.py` — added 3 tests for `get_signed_url` in mock mode
- `MANIFEST.md`, `BUILD_LOG.md`, `docs/OPERATIONS.md` — updated

### Key decisions

1. **Re-sign immediately before submission, never store** — `get_signed_url()` is called per-recording inside the submission loop. The `recording_url` in DB always holds the raw S3 path, never a signed URL.

2. **Fallback on re-sign failure** — if `get_signed_url()` raises, log a warning and fall back to the stored URL. Submission is still attempted (may fail at provider, but doesn't block the batch).

3. **Config-driven tier assignment at ingestion** — `_determine_submission_tier()` reads `config/submission_priority.yaml` via `_load_submission_priority()` (lru_cache). Config errors (missing file, malformed YAML) default to `normal` and log a warning — never fail ingestion.

4. **OR logic within tier, immediate > off_peak > normal precedence** — a recording matches a tier if ANY rule matches. Tiers are checked in order: immediate first, then off_peak, else normal.

5. **Integer vs string agency_id** — config stores `agency_ids` as integers; `CallRecording.agency_id` is CharField. `_tier_matches()` converts both sides to str before comparing.

6. **submit_recordings command as thin wrapper** — delegates to `submit_pending_recordings()`. Supports `--tier` (repeatable), `--batch-size`, `--dry-run`.

### Test count at end of session: 224 passing, 0 ruff findings

---

## Session 5 — Prompt E: S3 Raw Key Storage + IST Timezone Compliance

**Date:** 2026-04-01
**Scope:** Three bugs found during live DB validation against `uvarcl_live.call_logs`.
**Issues closed:** #8 (recording_url field type), #9 (IST timezone in compliance)

### Files created

- `baysys_call_audit/migrations/0004_recording_url_charfield.py` — AlterField recording_url URLField → CharField

### Files modified

- `baysys_call_audit/models.py` — `recording_url`: `URLField` → `CharField`. S3 object keys have no URL scheme.
- `baysys_call_audit/ingestion.py` — `validate_row()`: removed URL format check, non-empty only. `SYNC_QUERY` + `SYNC_COLUMN_NAMES` + `map_sync_row()`: `created_at` → `call_start_time`.
- `baysys_call_audit/compliance.py` — added `_IST = ZoneInfo("Asia/Kolkata")`; all four metadata handlers now convert `recording_datetime` (UTC) to IST before extracting hour/weekday/date.
- `baysys_call_audit/tests/test_models.py` — 2 new tests: raw S3 key saves without error, round-trip unchanged
- `baysys_call_audit/tests/test_ingestion.py` — updated `test_bad_url_prefix` → accepts any non-empty path; added 5 new tests (raw S3 key, SYNC_QUERY strings, map_sync_row)
- `baysys_call_audit/tests/test_compliance.py` — updated 2 call_window tests (now use UTC times matching IST window boundary); added 9 IST-aware tests (call window, blocked weekday, gazette holiday)
- `baysys_call_audit/tests/test_sync_call_logs.py` — renamed `created_at` → `call_start_time` in `_make_db_row()`
- `MANIFEST.md`, `BUILD_LOG.md`, `CLAUDE.md`, `docs/OPERATIONS.md` — updated

### Bug source

Live DB validation against `uvarcl_live.call_logs` revealed:
1. `recording_s3_path` stores raw S3 object keys (no `http://` prefix) — URLField rejected them
2. All compliance time checks were UTC-based; RBI rules are IST (+5:30) → 23% of calls misclassified
3. `created_at` is DB insert timestamp (erratic); `call_start_time` is actual call start (reliable)

### Key decisions

1. **CharField not URLField** — S3 object keys like `Konex/recordings/call.mp3` have no URL scheme. Validation is non-empty only. Signing happens at submission time.

2. **`_IST` module-level constant** — `ZoneInfo("Asia/Kolkata")` computed once, reused in all four compliance handlers. Python 3.9+ stdlib, no new dependency.

3. **UTC stored, IST for compliance** — `recording_datetime` stays as UTC in the DB. All four metadata handlers call `.astimezone(_IST)` at check time. No DB schema change.

4. **`call_start_time` not `created_at`** — filter, sort, and `recording_datetime` mapping all use `call_start_time`. No `created_at` in SYNC_QUERY.

5. **Existing tests updated** — `CallWindowTests` tests adjusted to use UTC times that correctly map to the intended IST hours. `test_sync_call_logs.py` helper renamed to reflect the column change.

### Test count at end of session: 241 passing, 0 ruff findings

---

## Session 6 — Prompt F: Sync Performance — Bulk Dedup Pre-fetch

**Date:** 2026-04-01
**Scope:** Fix N-query dedup performance bug discovered during first real sync run against Supabase.
**Issues closed:** #10

### Bug source

First live sync of a single date (11,429 rows) issued one `SELECT` per row to check for duplicates over a Supabase pooler connection. At 50–100ms per round trip, a single date took 10–20 minutes — unacceptable for a nightly cron job.

### Fix

`run_sync_for_date()` now pre-fetches all existing `recording_url` values for the target date in **one** ORM query before the loop:

```python
existing_urls: set[str] = set(
    CallRecording.objects.filter(recording_datetime__date=target_date)
    .values_list("recording_url", flat=True)
)
```

Dedup inside the loop is then an O(1) `in` check. `existing_urls` is updated after each successful create for correct intra-batch dedup.

`create_recording_from_row()` accepts an optional `existing_urls: set[str] | None = None` parameter — fast path when provided, DB-query fallback when None (CSV/Excel import path unchanged).

### Performance impact

| | Before | After |
|---|---|---|
| DB queries for 11K row sync | ~11,429 | 1 pre-fetch + N creates |
| Duration for one date | 10–20 min | < 30 seconds |
| CSV import path | unchanged | unchanged |

### Files modified

- `baysys_call_audit/ingestion.py` — `run_sync_for_date()` pre-fetch + intra-batch dedup; `create_recording_from_row()` `existing_urls` parameter
- `baysys_call_audit/tests/test_ingestion.py` — 5 new tests for `existing_urls` parameter
- `baysys_call_audit/tests/test_sync_call_logs.py` — 3 new tests for pre-fetch + intra-batch dedup
- `CLAUDE.md`, `MANIFEST.md`, `BUILD_LOG.md`, `docs/OPERATIONS.md` — updated

### Key decisions

1. **Pre-fetch scoped to target date** — filters on `recording_datetime__date=target_date`. Avoids loading the entire table into memory for large historical datasets.

2. **Loop check before calling `create_recording_from_row()`** — dedup counter (`skipped_dedup`) is incremented cleanly in the loop via `continue`, not inside the function. Function's fast path is belt-and-suspenders.

3. **`existing_urls` is optional, defaults to None** — CSV/Excel import callers pass no argument. DB fallback path is untouched.

4. **Intra-batch dedup via set update** — after a successful create, the URL is added to `existing_urls` so a duplicate in the same batch is caught without a DB round trip.

### Test count at end of session: 249 passing, 0 ruff findings

---

## Session 7 — Prompt G: Poll Recovery + Config Fixes

**Date:** 2026-04-01
**Scope:** Three targeted fixes discovered during live validation: webhook recovery polling, call duration threshold, max calls threshold.
**Issues closed:** #11 (webhook recovery), #12 (call duration), #13 (max calls)

### Files created

- `baysys_call_audit/management/commands/poll_stuck_recordings.py` — polls provider every run for submitted recordings with no webhook delivery after `POLL_STUCK_AFTER_MINUTES` (default 30). Args: `--batch-size`, `--dry-run`. Reuses `process_provider_webhook()` for zero code duplication.
- `baysys_call_audit/tests/test_poll_stuck_recordings.py` — 8 tests

### Files modified

- `settings.py` — `COMPLIANCE_MAX_CALLS_PER_CUSTOMER_PER_DAY` default 3 → 15; added `SYNC_MIN_CALL_DURATION=20`; added `POLL_STUCK_AFTER_MINUTES=30`
- `config/compliance_rules.yaml` — M4 `max_calls: 3` → `max_calls: 15`
- `baysys_call_audit/ingestion.py` — `SYNC_QUERY` call duration `> 10` → `> %s`; `cursor.execute` passes `SYNC_MIN_CALL_DURATION` as second param; added `from django.conf import settings`
- `baysys_call_audit/services.py` — added `_normalise_provider_payload(raw, resource_id)` (ensures `resource_insight_id` is present in poll responses)
- `baysys_call_audit/tests/test_ingestion.py` — 2 new tests (SYNC_QUERY param count, no hardcoded duration)
- `baysys_call_audit/tests/test_sync_call_logs.py` — 2 new tests (min_duration default, override)
- `baysys_call_audit/tests/test_compliance.py` — 3 new tests (15-call no flag, 16-call flag, override to 5)
- `.env.example` — added `COMPLIANCE_MAX_CALLS_PER_CUSTOMER_PER_DAY=15`, `SYNC_MIN_CALL_DURATION=20`, `POLL_STUCK_AFTER_MINUTES=30`
- `CLAUDE.md`, `MANIFEST.md`, `BUILD_LOG.md`, `docs/OPERATIONS.md` — updated

### Key decisions

1. **`SYNC_MIN_CALL_DURATION` as second query param** — SYNC_QUERY now has two `%s` placeholders. `run_sync_for_date()` passes `[str(target_date), min_duration]`. No f-string template substitution — keeps the query safe from SQL injection.

2. **max_calls default 15** — live DB validation showed customers receiving up to 86 calls/day. The old default of 3 would flag virtually every active account. 15 matches operational reality while still catching genuine violations.

3. **poll_stuck_recordings reuses `process_provider_webhook()`** — no duplicate processing logic. The only addition is `_normalise_provider_payload()` to ensure the resource_id is present in poll responses (which may omit it).

4. **"Still processing" detection** — `get_results()` returns empty `transcript` when processing is not complete. The poll command skips these (increments `still_processing`, not `errors`). `retry_count` is only incremented on `ProviderError`.

5. **Scheduled every 30 minutes** — matches `POLL_STUCK_AFTER_MINUTES` default. Recordings that miss their webhook are recovered within 30–60 minutes.

### Test count at end of session: 265 passing, 0 ruff findings

---

## Session 8 — Perf Fix 1: pgbouncer Connection Fix

**Date:** 2026-04-01
**Scope:** `sync_call_logs` failing mid-run with `django.db.utils.InterfaceError: connection already closed`.

### Root cause

`run_sync_for_date()` opened a raw `connection.cursor()`, then called `CallRecording.objects.create()` inside the `while fetchmany()` loop. Supabase uses pgbouncer in **transaction-mode** pooling — after each ORM commit, pgbouncer returns the underlying TCP connection to the pool, invalidating the open raw cursor. The next `fetchmany()` hit `connection already closed`.

### Fix

Replaced `while True: fetchmany()` loop with a single `cursor.fetchall()` inside the `with connection.cursor()` block. All rows are fetched into memory before the cursor closes and before any ORM write touches the connection.

### Files modified

- `baysys_call_audit/ingestion.py` — `run_sync_for_date()`: `fetchmany` loop → `fetchall` + iterate list
- `baysys_call_audit/tests/test_sync_call_logs.py` — all `fetchmany` mock calls → `fetchall`; `test_batch_size_passed_to_fetchmany` → `test_batch_size_accepted_fetchall_used`

### Key decisions

1. **fetchall acceptable for daily sync volume** — 8–13K rows at ~100 bytes = ~1MB peak memory. Not a concern.
2. **batch_size retained for API compatibility** — parameter still accepted; docstring updated to note it no longer controls the raw fetch.

### Test count: 265 passing, 0 ruff findings (no new tests — mock changes only)

---

## Session 9 — Perf Fix 2: O(1) max_calls_per_customer Compliance Check

**Date:** 2026-04-01
**Scope:** `sync_call_logs` completing but taking 40 minutes for 3,563 inserts (2421s total). Root cause: N+1 DB queries in compliance engine.

### Root cause

`_check_max_calls_per_customer()` in `compliance.py` issued a `CallRecording.objects.filter(...).count()` DB query for every new recording created. Over Supabase pooler (~300ms round-trip), 3,563 inserts × 300ms compliance check = ~18 minutes in compliance alone, plus ~300ms per INSERT = ~40 minutes total.

### Fix (same pattern as Prompt F dedup pre-fetch)

`run_sync_for_date()` pre-fetches a `dict[customer_id → int]` of existing call counts for the target date in **one** annotated query before the loop. Passed through `create_recording_from_row()` → `check_metadata_compliance()` → `_check_max_calls_per_customer()`. Count is incremented in-memory after each new create. Webhook path (no pre-computed dict) falls back to DB query unchanged.

### Performance impact

| | Before | After |
|---|---|---|
| DB queries per new recording | 1 INSERT + 1 COUNT | 1 INSERT |
| DB queries for compliance (3,563 rows) | 3,563 | 0 |
| Sync duration (3,563 new + 4,070 dedup) | 2421s (40 min) | 0.7s |

0.7 seconds confirmed on a fully-deduped re-run. Real insert benchmark (new date) expected < 2 minutes for a full day.

### Files modified

- `baysys_call_audit/compliance.py` — `check_metadata_compliance(recording, call_counts_cache=None)`. All metadata handlers updated. `_check_max_calls_per_customer` uses `call_counts_cache.get(cid, 0)` when cache provided; DB query fallback otherwise.
- `baysys_call_audit/ingestion.py` — `run_sync_for_date()` pre-fetches `dict[customer_id → count]` (annotated query). `create_recording_from_row(row, existing_urls, call_counts_cache)` accepts + increments cache after create; passes to compliance.
- `baysys_call_audit/tests/test_compliance.py` — 4 new tests: cache no-flag, cache flag, null customer, DB fallback
- `baysys_call_audit/tests/test_ingestion.py` — 2 new tests: pre-seeded cache, intra-batch increment

### Key decisions

1. **Same pattern as Prompt F** — pre-fetch once, O(1) lookup per row, increment in-memory after create for intra-batch correctness.
2. **Webhook path unchanged** — no cache passed at webhook time. DB query fallback ensures correctness for isolated recordings.
3. **`call_counts_cache` is optional** — defaults to None. CSV/Excel import callers pass nothing; behaviour unchanged.

### Test count: 271 passing, 0 ruff findings (commit: 55fd923)

---

## Session 30 — Collapsible agency accordion (default collapsed)

**Date:** 2026-04-22
**Scope:** UI-only. The agency group headers on both Agents and Recordings tabs become clickable accordions — all collapsed by default so the initial view is just a list of agencies with counts. Backend untouched.

### Repos & branches
- `bsfg-finance/crm` · base `master` · branch `audit-ui/accordion-agency-groups`
- **PR #77** — open, not merged.

### What shipped
- `useState<Set<string>>` per tab (AgentsTab, RecordingsTab). Empty set = everything collapsed.
- Agency header row: `cursor-pointer`, `hover:bg-slate-100`, `role="button"`, `aria-expanded`, `tabIndex={0}`, keyboard `Enter`/`Space` toggle. Chevron `›` collapsed / `⌄` expanded. Count always visible.
- Data rows are a render gate on `expanded.has(group.key)`. Grouping and sort logic unchanged.
- Unassigned sentinel unified to `'__unassigned__'` (was `'—'`) so it participates in the expand-all set.
- "Expand all" / "Collapse all" text button next to the existing Active Only / Score <50% controls. Flips between empty set and set-of-all-group-ids.

### Files touched
- `src/pages/audit/components/AgentsTab.tsx`
- `src/pages/audit/components/RecordingsTab.tsx` (grouping logic hoisted out of the tbody IIFE so the top-bar toggle can see the group list)

### Verification
- `npx tsc --noEmit` clean.
- `npx eslint src/pages/audit/ --max-warnings=50` — 0 errors; only the 2 pre-existing react-refresh warnings in `callDetailParts.tsx`.

### Nothing else changed
No dependency added, no backend touched, no API change. Filter chips, sort keys, row onClick → drawer, inline ID pill, pagination all preserved.
