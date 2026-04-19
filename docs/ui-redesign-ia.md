# Call Auditor UI — Information Architecture & Design Spec
# Session: 2026-04-19 · Owner: PC

---

## 1. Design Principles (locked)

- **Collexa theme wins over SPEC** — white shell, wine (`#7C3AED` / Collexa magenta) as primary accent, coloured-top-accent KPI cards, cream background (`#F8FAFC`)
- **Auditor is distinguished from Trainer by accent colour** — Trainer uses coral/orange; Auditor uses wine/magenta (matches Collexa logo — same product family, different app)
- **Three jobs, three tabs** — exception triage (Recordings) · agent analytics (Agents) · pipeline ops (Ops)
- **Desktop-primary** — tablet acceptable; mobile not designed for
- **No real-time** — manual refresh + filter-change re-fetch
- **Score slot** — Provider score (GreyLabs) now, OwnLLM later; UI label is always "Compliance Score" + small "via GreyLabs" source pill

---

## 2. Shell / Chrome

### Global nav (Collexa shell — not owned by Auditor)
Collexa top nav already exists: `Dashboard · AI Trainer · Dialer · Agencies · Support · Notification · WhatsApp`

Auditor is a page within Collexa at `/call-audit`. The Auditor shell sits below the Collexa nav and owns everything beneath it.

### Auditor page header
```
Call Audit                                              [Refresh]
AI-powered compliance monitoring
```
- "Call Audit" in wine/magenta bold (matches Trainer's page title colour)
- Subtitle in slate-500 12px

### Agency + Period filter bar (sticky, below page header)
Mirrors Trainer exactly:
```
AGENCY  [All Agencies ▼]     PERIOD   WEEK | MONTH | MTD   [April 2026 ▼]
```
- Active period button: wine background, white text (pill)
- Inactive: slate-200 bg, slate-600 text
- Agency dropdown: same component as Trainer
- Scoped users (Manager, Agency Admin): agency pre-selected + locked (no dropdown)
- Filter state in URL query params: `?agency=8&mode=month&value=2026-04`

### Tab bar (below filter bar)
```
  Recordings    Agents    Ops
```
- Active tab: wine underline (2px), wine text
- Inactive: slate-500 text
- No background change on active (matches Trainer's tab style)

---

## 3. KPI Row (all tabs share this row)

Four cards with Collexa's coloured-top-accent pattern (4px top border, white card, 1px slate-200 border, 8px radius, subtle shadow).

```
┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐
│ wine top border     │ │ amber top border    │ │ red top border      │ │ slate top border    │
│                     │ │                     │ │                     │ │                     │
│ COMPLIANCE SCORE    │ │ EXCEPTIONS          │ │ CRITICAL FLAGS      │ │ PIPELINE            │
│ 46.5%               │ │ 247                 │ │ 89                  │ │ 152 / 5142          │
│ via GreyLabs (pill) │ │ FATAL 12 · <50% 89  │ │ Unreviewed          │ │ scored / total      │
│ of scored calls     │ │ · Unreviewed 146    │ │ critical + high     │ │ ● 3 failed          │
└─────────────────────┘ └─────────────────────┘ └─────────────────────┘ └─────────────────────┘
```

**Card specs:**
- Label: 11px uppercase letterspaced, slate-500 (matches Trainer's `TOTAL CALLS THIS MONTH`)
- Primary value: 28px, 700 weight, wine for Compliance Score; colour-coded for others (amber for Exceptions, red for Critical Flags, slate-900 for Pipeline)
- Secondary line: 12px, slate-500
- "via GreyLabs" source pill: 11px, slate-400, slate-100 bg, 4px radius — disappears when OwnLLM replaces it
- Failed count in Pipeline card: red dot + red text, links to Ops tab

---

## 4. RECORDINGS TAB

### Purpose
Exception triage — show QA reviewers the calls that need a human ear. Default view is the exception queue, not a browse-all list.

### Filter bar (below KPI row, above table)
```
[FATAL ≥3 ×] [Score <50% ×] [Critical flags ×] [Unreviewed ×] [Neg. sentiment ×]     Status [All ▼]  Agent ID [____]  [From] → [To]  [Clear]
```
- Left: exception filter chips (toggleable pills, wine when active)
- Right: additional filters (status dropdown, agent ID text, date range)
- Default state: ALL exception chips active (FATAL ≥3 OR score<50% OR critical flag OR unreviewed OR negative sentiment)
- "Clear" resets to show all completed recordings (no exception filter)
- Filter state in URL params

### Recordings table

**Columns:**
| Column | Source | Notes |
|---|---|---|
| Agent | `agent_name` + `agent_id` (sub-label, slate-400) | Blue link colour, click → Call Detail |
| Customer | `customer_id` | slate-600 |
| Date (IST) | `recording_datetime` | "18 Apr 2026, 11:27" |
| Duration | `transcript.total_call_duration` | "2m 34s" — dash if unscored |
| Score | `score_percentage` | Colour-coded: ≥85 green · 70–84 yellow · 55–69 orange · <55 red. Dash if pending |
| FATAL | `fatal_level` | 0 = dash; 1–2 = amber badge; 3–5 = red badge with lightning icon |
| Flags | `compliance_flag_count` | Number in red if >0, dash if 0 |
| Status | `status` | Coloured dot + text pill (see below) |
| — | Actions | `View →` link (blue) + inline retry button (red, failed only) |

**Status pills (coloured dot + text):**
- `● completed` — emerald
- `● submitted` — blue
- `● processing` — blue (pulsing dot)
- `● pending` — amber
- `● failed` — red
- `● skipped` — slate

**Sorting:** click column header; default = `recording_datetime DESC`; secondary sort presets: Score ASC (worst first), FATAL DESC, Flags DESC

**Pagination:** 25 rows default, `[10 | 25 | 50]` selector bottom-right, page numbers bottom-centre

**Empty state:** "No exceptions found for this period. All calls are within compliance thresholds." with a "View all recordings" link that clears exception filters.

---

## 5. AGENTS TAB

### Purpose
Agency-level and agent-level compliance analytics. Builds on Trainer's Action Board grammar.

### Agency cards row (scrollable horizontal, like Trainer's Agency Overview)
One card per agency, scoped by the global Agency filter (Admins/Supervisors see all; others see one).

```
┌─────────────────────────────────┐
│ Prolynk               66 agents │  (agency name + agent count)
│ Avg Score          62.4%        │
│ Calls Scored     152 / 450      │
│ FATAL Calls           12        │
│ Critical Flags        34        │
└─────────────────────────────────┘
```
- Click agency card → agent table below filters to that agency

### Agent table (below agency cards)
Filtered to selected agency (or all if none selected).

**Columns:**
| Column | Notes |
|---|---|
| # | Row number |
| Agent | Name + ID sub-label, blue link |
| Calls Scored | `calls` from agent_summary |
| Avg Score | Colour-coded % (same bands as Recordings table). Dash if 0 scored |
| FATAL Count | Red if >0 |
| Unreviewed Flags | Amber if >0 |

Default sort: Avg Score ASC (worst agents first — exception-driven).

**Click agent row → Agent Drawer (right slide-out)**

### Agent Drawer
Mirrors Trainer's drawer structure — dark slate header, tabbed body.

**Header:**
```
[dark slate bg]
AGENT NAME         Agency Name     Agent ID 384
● On Track  (or exception status badge)
```

**Tabs: Overview · Call History**

**Overview tab:**
- Score trend line chart (last 10 scored calls) — purple line + dashed threshold bands (85% Excellent / 70% Good / 55% Needs Improvement), matching Trainer's chart
- Section score bars if OwnLLM is live (Introduction / Call Quality / Compliance & RBI / Scam & Trust) — with Agency avg reference tick
- Sentiment summary (% negative customer sentiment)
- FATAL breakdown (which fatal parameters triggered most)

**Call History tab:**
| Date | Duration | Score | FATAL | Status | — |
|---|---|---|---|---|---|
| 18 Apr 2026 #6000 | 2m 34s | 78% | — | completed | View → |

- `View →` opens Call Detail page for that recording

---

## 6. OPS TAB

### Purpose
Pipeline operations — sync, submit, poll, monitor failures. Admin/Manager only for actions; read-only metrics visible to Supervisors.

### Layout: action cards stack (keep current pattern, restyle)

**Card 1 — Pipeline Status (top, read-only)**
```
┌────────────────────────────────────────────────────┐
│ PIPELINE STATUS                                    │
│ Last sync      09 Apr 2026, 12:48                  │
│ Last scored    09 Apr 2026, 12:58                  │
│ Pending        4,990    Submitted  0    Failed  0  │
└────────────────────────────────────────────────────┘
```
- Failed count in red if >0
- Auto-refreshes on tab focus

**Card 2 — Dry Run toggle**
Keep as-is, restyle toggle to Collexa style (wine when ON).

**Card 3 — Sync Call Logs**
- Date picker (default: yesterday)
- "Run Sync" button → wine outline button → on click becomes loading state → shows result inline:
  `✓ Synced 1,247 calls · 3 skipped · 0 errors · 4.2s`

**Card 4 — Submit Recordings**
- Tier selector: `All · Immediate · Normal · Off-Peak`
- "Submit Now" button → wine filled button
- Result inline: `✓ Submitted 89 · 2 failed`
- Failed count links to recordings table filtered to `status=failed`

**Card 5 — Poll Stuck Recordings**
- "Poll Now" button
- Result inline: `✓ Polled 12 stuck recordings · 10 completed · 2 still stuck`

**Card 6 — Import Recordings (Admin/Manager only)**
- File upload dropzone (CSV / Excel)
- Dry-run toggle
- Result table inline on upload

---

## 7. CALL DETAIL PAGE

### Route
`/call-audit/recordings/<id>/`

### Breadcrumb
`← Call Audit  /  Pinki Pande  /  Call #6000`

### Page header
```
Pinki Pande  #6000   [● completed ▼]   [FATAL-3 ⚡]   [↻ Retry]   [← Prev]  [Next →]
08 Apr 2026, 11:27 IST  ·  Agent ID 384  ·  Prolynk  ·  2m 34s
```
- Status pill (colour-coded)
- FATAL badge: red if ≥3, amber if 1–2, hidden if 0
- Retry button: visible only if `status=failed`, Admin/Manager only
- Prev/Next navigation between calls in current filtered list (no re-navigating to list)

### 2-column layout (60/40 split)

**LEFT COLUMN (60%) — top to bottom:**

1. **Audio Player** (Collexa-style, matches Trainer's AudioPlayerBar)
   - Play/pause · scrub bar · timestamp · volume · download
   - Signed URL fetched on load via `/recordings/<id>/signed-url/`

2. **AI Summary** (if `transcript.summary` exists)
   - Slate-100 bg card, italic text
   - "Next action: `transcript.next_actionable`" below

3. **Transcript** (if `transcript.transcript_text` exists)
   - Speaker-labelled lines: `AGENT` (blue label) / `CUSTOMER` (slate label)
   - Lines with compliance flag evidence highlighted in amber background
   - "Transcript not yet available" placeholder if pending

4. **Compliance Flags** (if any)
   - One card per flag:
     - Severity badge (red=critical, orange=high, amber=medium, slate=low)
     - Flag type + description
     - Evidence text in code-style block (slate-100 bg)
     - "Mark Reviewed" button → toggles reviewed state (Admin/Manager/Supervisor)
     - Reviewed: green tick + reviewer name + timestamp

**RIGHT COLUMN (40%) — top to bottom:**

1. **Compliance Score card** (hero)
   - Large % in wine (or red if <55)
   - Score band label: "Excellent / Good / Needs Improvement / Critical"
   - `via GreyLabs` source pill
   - `X / Y` raw score sub-label

2. **Section Breakdown** (when OwnLLM live; placeholder card until then)
   - Horizontal bars per group (Introduction / Call Quality / Compliance & RBI / Scam & Trust)
   - Colour matches band (green/yellow/orange/red)
   - FATAL params shown with ⚡ icon

3. **Sentiment & Talk Time**
   - Customer sentiment: coloured pill (positive=green, neutral=slate, negative=red)
   - Agent sentiment pill
   - Talk time bar: `AGENT ██████░░░░ CUSTOMER` with % labels
   - Non-speech % sub-label

4. **Call Details** (metadata)
   - Agent ID · Customer ID · Phone (masked) · Portfolio · Bank · Product
   - Tier · Retries · Submitted at · Completed at

5. **Provider Details** (collapsed by default)
   - GreyLabs resource ID
   - Raw category_data boolean parameters (checklist style)
   - Restricted keywords detected (if any)

---

## 8. Component Library

| Component | Props | Notes |
|---|---|---|
| `KpiCard` | `label, value, subLabel, accent, topBorder` | Collexa coloured-top-accent pattern |
| `StatusPill` | `status` | Dot + text, colour-coded |
| `FatalBadge` | `level` | 0=hidden, 1–2=amber, 3–5=red+icon |
| `ScoreCell` | `pct` | Colour-coded number, dash if null |
| `AgencyCard` | `name, agents, avgScore, calls, fatals, flags` | Horizontal scroll row |
| `AgentDrawer` | `agentId` | Right slide-out, dark header, tabbed |
| `ScoreTrendChart` | `data[]` | Purple line + dashed threshold bands (Recharts) |
| `SectionBar` | `label, pct, agencyAvg` | Horizontal bar + reference tick |
| `AudioPlayer` | `recordingId` | Fetches signed URL, Trainer-compatible |
| `FlagCard` | `flag, onReview` | Evidence + mark-reviewed action |
| `FilterChip` | `label, active, onToggle` | Wine when active |
| `DataTable` | `columns, data, onRowClick, sortable` | Sortable headers, hover state |
| `ActionCard` | `title, description, children` | Ops tab card wrapper |

Chart library: **Recharts** (matches SPEC; confirm Trainer uses same before locking).

---

## 9. Backend Additions Required (small, targeted)

| # | What | Why |
|---|---|---|
| B1 | `fatal_level` filter on `/recordings/` | Exception chip "FATAL ≥3" |
| B2 | `score_lt` / `score_gte` filter on `/recordings/` | Exception chip "Score <50%" |
| B3 | `has_unreviewed_flags` filter on `/recordings/` | Exception chip |
| B4 | `agency_id` filter on `/recordings/` | Agency filter bar scoping |
| B5 | `flag_type` / `severity` filter on `/recordings/` | Flag-type chip |
| B6 | `customer_sentiment` filter on `/recordings/` | Negative sentiment chip |
| B7 | `/recordings/<id>/adjacent/` or prev/next IDs in list response | Prev/Next navigation on detail page |
| B8 | Score distribution endpoint (histogram buckets) | Analytics chart (if added later) |

All are query-param additions to existing views — no new endpoints needed except B7/B8.

---

## 10. Build Order (Phase 1 MVP)

1. `tailwind.config.js` — Collexa palette tokens
2. `components/` — KpiCard, StatusPill, FatalBadge, ScoreCell, FilterChip, DataTable, ActionCard, Badge
3. Shell — page header + agency/period filter bar + tab bar
4. KPI row (wired to `/dashboard/summary/`)
5. Recordings tab — filter chips + table (wired to `/recordings/`)
6. Agents tab — agency cards + agent table + drawer skeleton
7. Ops tab — restyled action cards (wired to existing endpoints)
8. Call Detail page — 2-column layout, all sections
9. Backend additions B1–B6 (small filter params)
10. Score trend chart in agent drawer (Recharts)

---

## 11. Future (not in scope now)

- OwnLLM score swap (swap data source, add section bars)
- Trainer agent drawer "Audit" tab (separate crm_apis session)
- Score distribution / histogram chart on Analytics view
- Export PDF (per-agent compliance report)
- Real-time pipeline updates via WebSocket
