# Prompt R — OwnLLM Score UI

**Repo:** `crm` (frontend)
**File:** `crm/src/pages/audit/AuditCallDetailPage.tsx`
**Depends on:** Prompt Q complete and deployed (OwnLLMScore records exist in DB)
**Goal:** Replace the "Compliance Score" widget with OwnLLMScore as the primary score.
Demote GreyLabs' ProviderScore to a collapsible "GreyLabs Analytics" section.

**Test gate:** `npm run build` → 0 TypeScript errors. Visual check: call detail page shows
UVARCL score ring for a completed call.

---

## Context

Currently `AuditCallDetailPage.tsx` line ~437:
```tsx
<Section title="Compliance Score">
  <ScoreSection scores={detail.provider_scores} />
</Section>
```

`ScoreSection` reads `ProviderScore` which is GreyLabs' own internal template score —
not our UVARCL scorecard. After Prompt Q, `detail.own_llm_scores` contains the actual
UVARCL scorecard results from our own LLM scoring.

The `OwnLLMScore` type is already defined in `crm/src/types/audit.ts`:
```typescript
export interface OwnLLMScore {
  score_template_name: string;
  total_score: number | null;
  max_score: number | null;
  score_percentage: string | null;
  score_breakdown: Record<string, unknown> | null;
  model_used: string | null;
  created_at: string;
}
```
And `detail.own_llm_scores: OwnLLMScore[]` is already in `CallDetail`.

---

## Changes

### 1 — Add `LLMScoreSection` component

Add this component to `AuditCallDetailPage.tsx` after the existing `ScoreSection` component:

```tsx
// ── OwnLLM Score card ──────────────────────────────────────────────────────────

interface LLMParam {
  id: number;
  name: string;
  score: number;
  max_score: number;
  justification?: string;
}

function LLMScoreSection({ scores }: { scores: OwnLLMScore[] }) {
  if (scores.length === 0) {
    return (
      <div className="d-flex align-items-center gap-2 text-muted small">
        <Spinner animation="border" size="sm" />
        <span>Scoring in progress…</span>
      </div>
    );
  }

  const score = scores[0];
  const breakdown = (score.score_breakdown ?? {}) as Record<string, unknown>;
  const callType = breakdown.call_type as string | undefined;

  // Not-scoreable calls (WPC, voicemail, no answer)
  if (callType === 'not_scoreable') {
    const disposition = breakdown.disposition as string | undefined;
    return (
      <div className="text-muted small p-2 rounded" style={{ background: '#f8f9fa' }}>
        <span className="fw-medium">Not scoreable</span>
        {disposition && <> — {disposition}</>}
        <div className="mt-1" style={{ fontSize: '0.8rem' }}>
          No agent–customer interaction to evaluate.
        </div>
      </div>
    );
  }

  const pct = score.score_percentage ? parseFloat(score.score_percentage) : null;
  const fatalTriggered = breakdown.fatal_triggered as boolean | undefined;
  const fatalName = breakdown.fatal_parameter_name as string | undefined;
  const params = (breakdown.parameters ?? []) as LLMParam[];

  return (
    <>
      {/* Score ring + summary */}
      <div className="d-flex align-items-center gap-3 mb-3">
        <div
          className="rounded-circle d-flex align-items-center justify-content-center fw-bold"
          style={{
            width: 72,
            height: 72,
            fontSize: '1.1rem',
            flexShrink: 0,
            background: fatalTriggered
              ? '#f8d7da'
              : pct == null ? '#eee'
              : pct >= 85 ? '#d1e7dd'
              : pct >= 70 ? '#cfe2ff'
              : pct >= 55 ? '#fff3cd'
              : '#f8d7da',
            color: fatalTriggered
              ? '#842029'
              : pct == null ? '#888'
              : pct >= 85 ? '#0f5132'
              : pct >= 70 ? '#084298'
              : pct >= 55 ? '#664d03'
              : '#842029',
          }}
        >
          {fatalTriggered ? 'FAIL' : pct != null ? `${pct.toFixed(0)}%` : '—'}
        </div>
        <div>
          <div className="fw-medium">{score.score_template_name}</div>
          <div className="small text-muted">
            {score.total_score ?? '—'} / {score.max_score ?? '—'} points
          </div>
          {fatalTriggered && (
            <Badge bg="danger" className="mt-1">
              FATAL: {fatalName ?? 'Auto-fail'}
            </Badge>
          )}
        </div>
      </div>

      {/* Per-parameter breakdown */}
      {params.length > 0 && (
        <div>
          {params.map((p) => (
            <div key={p.id} className="mb-2">
              <div className="d-flex justify-content-between small">
                <span className="fw-medium">{p.name}</span>
                <span className="text-muted">{p.score}/{p.max_score}</span>
              </div>
              <div className="progress mb-1" style={{ height: 5 }}>
                <div
                  className="progress-bar"
                  style={{
                    width: `${p.max_score > 0 ? (p.score / p.max_score) * 100 : 0}%`,
                    background:
                      p.max_score > 0 && p.score / p.max_score >= 0.7
                        ? '#198754'
                        : p.score === 0
                        ? '#dc3545'
                        : '#ffc107',
                  }}
                />
              </div>
              {p.justification && (
                <div className="text-muted" style={{ fontSize: '0.75rem' }}>
                  {p.justification}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
```

### 2 — Replace the Compliance Score section

Find this block in the right column (~line 436):
```tsx
            {/* Score */}
            <Section title="Compliance Score">
              <ScoreSection scores={detail.provider_scores} />
            </Section>
```

Replace with:
```tsx
            {/* UVARCL Compliance Score — own LLM */}
            <Section title="Compliance Score">
              <LLMScoreSection scores={detail.own_llm_scores} />
            </Section>
```

### 3 — Add collapsible GreyLabs Analytics section

Add a `useState` for the GreyLabs collapse toggle near the top of the `AuditCallDetailPage`
component (alongside existing state declarations):
```tsx
const [showGreylabs, setShowGreylabs] = useState(false);
```

Then add this section immediately after the Compliance Score section:
```tsx
            {/* GreyLabs Analytics — collapsible */}
            <div className="mb-4 border rounded bg-white">
              <button
                className="w-100 d-flex justify-content-between align-items-center p-3 border-0 bg-transparent fw-bold"
                style={{ cursor: 'pointer', fontSize: '0.95rem' }}
                onClick={() => setShowGreylabs((v) => !v)}
              >
                <span>GreyLabs Analytics</span>
                <span className="text-muted small">{showGreylabs ? '▲ hide' : '▼ show'}</span>
              </button>
              {showGreylabs && (
                <div className="px-3 pb-3">
                  <ScoreSection scores={detail.provider_scores} />
                </div>
              )}
            </div>
```

### 4 — Import `OwnLLMScore` type if not already imported

Check the import at line 8:
```tsx
import type { CallDetail, ComplianceFlag, ProviderScore } from '../../types/audit';
```

Add `OwnLLMScore` to the import:
```tsx
import type { CallDetail, ComplianceFlag, OwnLLMScore, ProviderScore } from '../../types/audit';
```

---

## After completion

Run `npm run build` in the `crm/` directory — 0 TypeScript errors required.

Then build and deploy the frontend Docker container (or hot-reload if in dev).

Visual verification checklist:
- [ ] Completed call with OwnLLMScore → ring shows %, parameter breakdown visible
- [ ] Not-scoreable call (WPC/voicemail) → shows "Not scoreable — Wrong Party Connect" in grey
- [ ] Call in progress (no OwnLLMScore yet) → shows spinner + "Scoring in progress…"
- [ ] GreyLabs Analytics section collapsed by default, expands on click
- [ ] FATAL triggered → ring shows "FAIL" in red, FATAL badge names the parameter
