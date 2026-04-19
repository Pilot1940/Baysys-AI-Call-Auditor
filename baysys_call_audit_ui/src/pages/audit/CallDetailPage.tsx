import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import StatusPill from "../../components/StatusPill";
import FatalBadge from "../../components/FatalBadge";
import { api } from "../../utils/Api";
import type { CallDetail, ComplianceFlag } from "../../types/audit";
import {
  formatDateTime, formatDuration, scoreBand, scoreBandLabel,
} from "../../types/audit";

export default function CallDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  void navigate; // used in retry flow via Link
  const [call, setCall] = useState<CallDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [signedUrl, setSignedUrl] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [flags, setFlags] = useState<ComplianceFlag[]>([]);
  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    api.getRecordingDetail(Number(id))
      .then(data => {
        setCall(data);
        setFlags(data.compliance_flags ?? []);
        // Fetch signed URL for audio
        return api.getSignedUrl(data.id);
      })
      .then(res => setSignedUrl(res.signed_url))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  async function handleRetry() {
    if (!call) return;
    setRetrying(true);
    try {
      await api.retryRecording(call.id);
      const updated = await api.getRecordingDetail(call.id);
      setCall(updated);
    } catch { /* ignore */ }
    setRetrying(false);
  }

  async function handleReviewFlag(flag: ComplianceFlag) {
    if (!call) return;
    const updated = await api.reviewFlag(call.id, flag.id, !flag.reviewed);
    setFlags(prev => prev.map(f => f.id === flag.id ? updated : f));
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <p className="text-slate-400">Loading call #{id}…</p>
      </div>
    );
  }

  if (error || !call) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-600 mb-2">{error ?? "Call not found."}</p>
          <Link to="/audit" className="text-blue-600 hover:underline text-sm">← Back to Call Audit</Link>
        </div>
      </div>
    );
  }

  const primaryScore = call.provider_scores?.[0];
  const pct = primaryScore?.score_percentage ?? null;
  const band = scoreBand(pct);
  const transcript = call.transcript;

  const agentTalkPct = transcript && transcript.total_call_duration
    ? Math.round(((transcript.agent_talk_duration ?? 0) / transcript.total_call_duration) * 100)
    : null;

  const bandColor = {
    excellent:          "text-emerald-600",
    good:               "text-yellow-600",
    "needs-improvement":"text-orange-600",
    critical:           "text-red-600",
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Page header */}
      <div className="bg-white border-b border-slate-200 px-6 py-4">
        {/* Breadcrumb */}
        <nav className="text-[12px] text-slate-400 mb-3 flex items-center gap-1.5">
          <Link to="/audit" className="text-blue-600 hover:underline">Call Audit</Link>
          <span>/</span>
          <span className="text-slate-600">{call.agent_name}</span>
          <span>/</span>
          <span>Call #{call.id}</span>
        </nav>

        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-[20px] font-bold text-slate-900">{call.agent_name}</h1>
              <span className="text-slate-400 font-normal text-[15px]">#{call.id}</span>
              <StatusPill status={call.status} />
              {call.fatal_level != null && call.fatal_level > 0 && (
                <FatalBadge level={call.fatal_level} />
              )}
              {call.status === "failed" && (
                <button
                  onClick={handleRetry}
                  disabled={retrying}
                  className="px-3 py-1 text-[12px] text-red-600 border border-red-300 rounded hover:bg-red-50 transition-colors disabled:opacity-50"
                >
                  {retrying ? "Retrying…" : "↻ Retry"}
                </button>
              )}
            </div>
            <p className="text-[13px] text-slate-500 mt-1">
              {formatDateTime(call.recording_datetime)}
              {call.agency_id && <span className="mx-2">·</span>}
              {call.agency_id && <span>{call.agency_id}</span>}
              {transcript?.total_call_duration && (
                <><span className="mx-2">·</span>{formatDuration(transcript.total_call_duration)}</>
              )}
            </p>
          </div>

          <Link to="/audit" className="text-[13px] text-slate-500 hover:text-slate-800">
            ← Call Audit
          </Link>
        </div>
      </div>

      {/* 2-column body */}
      <div className="px-6 py-6 max-w-[1400px] mx-auto grid grid-cols-[1fr_400px] gap-6 items-start">

        {/* LEFT COLUMN */}
        <div className="space-y-5">

          {/* Audio player */}
          <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm">
            <h3 className="text-[12px] font-semibold uppercase tracking-wider text-slate-500 mb-3">Recording</h3>
            {signedUrl ? (
              <audio
                ref={audioRef}
                controls
                src={signedUrl}
                className="w-full"
                style={{ height: 40 }}
              />
            ) : (
              <p className="text-[13px] text-slate-400">
                {call.status === "completed" ? "Audio unavailable." : "Recording not yet processed."}
              </p>
            )}
          </div>

          {/* AI Summary */}
          {transcript?.summary && (
            <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
              <h3 className="text-[12px] font-semibold uppercase tracking-wider text-slate-500 mb-2">AI Summary</h3>
              <p className="text-[13px] text-slate-700 italic">{transcript.summary}</p>
              {transcript.next_actionable && (
                <p className="text-[12px] text-brand-wine mt-2 font-medium">
                  Next action: {transcript.next_actionable}
                </p>
              )}
            </div>
          )}

          {/* Transcript */}
          <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm">
            <h3 className="text-[12px] font-semibold uppercase tracking-wider text-slate-500 mb-3">Transcript</h3>
            {transcript?.transcript_text ? (
              <TranscriptView text={transcript.transcript_text} flags={flags} />
            ) : (
              <p className="text-[13px] text-slate-400">
                {call.status === "completed" ? "Transcript unavailable." : "Transcript not yet available."}
              </p>
            )}
          </div>

          {/* Compliance Flags */}
          <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm">
            <h3 className="text-[12px] font-semibold uppercase tracking-wider text-slate-500 mb-3">
              Compliance Flags
              {flags.length > 0 && (
                <span className="ml-2 bg-red-100 text-red-700 text-[11px] px-1.5 py-0.5 rounded font-bold">
                  {flags.length}
                </span>
              )}
            </h3>
            {flags.length === 0 ? (
              <p className="text-[13px] text-emerald-600">✓ No compliance flags.</p>
            ) : (
              <div className="space-y-3">
                {flags.map(flag => (
                  <FlagCard key={flag.id} flag={flag} onReview={handleReviewFlag} />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* RIGHT COLUMN */}
        <div className="space-y-4 sticky top-6">

          {/* Score hero */}
          <div className="bg-white border border-slate-200 border-t-4 border-t-brand-wine rounded-lg p-5 shadow-sm">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-2">Compliance Score</p>
            {pct != null ? (
              <>
                <div className={`text-[40px] font-bold leading-none mb-1 ${band ? bandColor[band] : "text-slate-900"}`}>
                  {pct.toFixed(1)}%
                </div>
                <div className={`text-[13px] font-semibold mb-2 ${band ? bandColor[band] : "text-slate-600"}`}>
                  {scoreBandLabel(band)}
                </div>
                <div className="text-[11px] text-slate-400">
                  {primaryScore?.audit_compliance_score} / {primaryScore?.max_compliance_score} points
                </div>
                <div className="mt-2">
                  <span className="text-[11px] bg-slate-100 text-slate-400 px-1.5 py-0.5 rounded">via GreyLabs</span>
                </div>
              </>
            ) : (
              <p className="text-[13px] text-slate-400">
                {call.status === "completed" ? "Score unavailable." : "Not yet scored."}
              </p>
            )}

            {/* Restricted keywords */}
            {primaryScore?.detected_restricted_keyword && (
              <div className="mt-3 bg-red-50 border border-red-200 rounded p-2">
                <p className="text-[12px] text-red-700 font-semibold">⚠ Restricted keywords detected</p>
                {primaryScore.restricted_keywords.length > 0 && (
                  <p className="text-[11px] text-red-600 mt-0.5">{primaryScore.restricted_keywords.join(", ")}</p>
                )}
              </div>
            )}
          </div>

          {/* Sentiment + talk time */}
          {transcript && (
            <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-3">Sentiment & Talk Time</p>

              <div className="flex gap-3 mb-4">
                {transcript.customer_sentiment && (
                  <SentimentPill label="Customer" sentiment={transcript.customer_sentiment} />
                )}
                {transcript.agent_sentiment && (
                  <SentimentPill label="Agent" sentiment={transcript.agent_sentiment} />
                )}
              </div>

              {agentTalkPct != null && (
                <div>
                  <div className="flex justify-between text-[11px] text-slate-500 mb-1">
                    <span>AGENT {agentTalkPct}%</span>
                    <span>CUSTOMER {100 - agentTalkPct}%</span>
                  </div>
                  <div className="h-2 bg-slate-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-brand-wine rounded-full"
                      style={{ width: `${agentTalkPct}%` }}
                    />
                  </div>
                  {transcript.total_non_speech_duration != null && transcript.total_call_duration != null && (
                    <p className="text-[11px] text-slate-400 mt-1">
                      {Math.round((transcript.total_non_speech_duration / transcript.total_call_duration) * 100)}% silence
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Call details */}
          <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-3">Call Details</p>
            <dl className="space-y-2">
              <DetailRow label="Agent ID"    value={call.agent_id} />
              <DetailRow label="Customer"    value={call.customer_id} />
              <DetailRow label="Phone"       value={call.customer_phone} />
              <DetailRow label="Product"     value={call.product_type} />
              <DetailRow label="Bank"        value={call.bank_name} />
              <DetailRow label="Portfolio"   value={call.portfolio_id} />
              <DetailRow label="Tier"        value={call.submission_tier} />
              <DetailRow label="Retries"     value={String(call.retry_count ?? 0)} />
              <DetailRow label="Submitted"   value={formatDateTime(call.submitted_at)} />
              <DetailRow label="Completed"   value={formatDateTime(call.completed_at)} />
            </dl>
          </div>

          {/* Provider details (collapsible) */}
          {primaryScore && (
            <ProviderDetails score={primaryScore} />
          )}

          {/* Error message */}
          {call.error_message && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <p className="text-[11px] font-semibold text-red-700 mb-1">Pipeline Error</p>
              <p className="text-[12px] text-red-600 font-mono break-words">{call.error_message}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function TranscriptView({ text, flags }: { text: string; flags: ComplianceFlag[] }) {
  const evidenceSnippets = flags
    .filter(f => f.evidence)
    .map(f => f.evidence!.substring(0, 60).toLowerCase());

  const lines = text.split("\n").filter(l => l.trim());

  return (
    <div className="space-y-2 max-h-[400px] overflow-y-auto pr-1">
      {lines.map((line, i) => {
        const isAgent = /^(agent|a):/i.test(line);
        const isCustomer = /^(customer|c|caller):/i.test(line);
        const lineLower = line.toLowerCase();
        const hasEvidence = evidenceSnippets.some(e => lineLower.includes(e));

        return (
          <div
            key={i}
            className={`text-[13px] leading-relaxed px-2 py-1 rounded ${
              hasEvidence ? "bg-amber-50 border-l-2 border-amber-400" : ""
            }`}
          >
            {isAgent && <span className="text-[10px] font-bold text-blue-500 mr-2 uppercase tracking-wider">Agent</span>}
            {isCustomer && <span className="text-[10px] font-bold text-slate-400 mr-2 uppercase tracking-wider">Customer</span>}
            <span className="text-slate-700">{isAgent || isCustomer ? line.replace(/^[^:]+:\s*/, "") : line}</span>
          </div>
        );
      })}
    </div>
  );
}

function FlagCard({ flag, onReview }: { flag: ComplianceFlag; onReview: (f: ComplianceFlag) => void }) {
  const sevColor = {
    critical: "bg-red-100 text-red-700 border-red-200",
    high:     "bg-orange-100 text-orange-700 border-orange-200",
    medium:   "bg-amber-100 text-amber-700 border-amber-200",
    low:      "bg-slate-100 text-slate-600 border-slate-200",
  };

  return (
    <div className={`border rounded-lg p-3 ${sevColor[flag.severity]}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[11px] font-bold uppercase tracking-wider">{flag.severity}</span>
            <span className="text-[11px] text-current opacity-70">{flag.flag_type.replace(/_/g, " ")}</span>
            {flag.auto_detected && (
              <span className="text-[10px] opacity-60">auto-detected</span>
            )}
          </div>
          <p className="text-[13px]">{flag.description}</p>
          {flag.evidence && (
            <pre className="mt-2 text-[11px] bg-white/60 rounded p-2 whitespace-pre-wrap font-mono opacity-80">
              {flag.evidence}
            </pre>
          )}
        </div>
        <button
          onClick={() => onReview(flag)}
          className={`shrink-0 text-[11px] px-2 py-1 rounded border transition-colors ${
            flag.reviewed
              ? "bg-emerald-100 text-emerald-700 border-emerald-300"
              : "bg-white/60 border-current hover:bg-white/80"
          }`}
        >
          {flag.reviewed ? "✓ Reviewed" : "Mark reviewed"}
        </button>
      </div>
      {flag.reviewed && flag.reviewed_by && (
        <p className="text-[11px] opacity-60 mt-1">
          by {flag.reviewed_by} · {formatDateTime(flag.reviewed_at)}
        </p>
      )}
    </div>
  );
}

function SentimentPill({ label, sentiment }: { label: string; sentiment: string }) {
  const isNeg = ["negative", "very_negative", "angry"].includes(sentiment);
  const isPos = ["positive", "very_positive"].includes(sentiment);
  return (
    <div className={`flex-1 text-center rounded px-2 py-1.5 text-[12px] font-medium ${
      isNeg ? "bg-red-50 text-red-700" : isPos ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"
    }`}>
      <div className="text-[10px] opacity-70 mb-0.5">{label}</div>
      <div className="capitalize">{sentiment.replace(/_/g, " ")}</div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex justify-between text-[13px]">
      <dt className="text-slate-500 font-medium">{label}</dt>
      <dd className="text-slate-700 text-right">{value || "—"}</dd>
    </div>
  );
}

function ProviderDetails({ score }: { score: NonNullable<CallDetail["provider_scores"]>[0] }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow-sm">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-[12px] font-semibold text-slate-500 hover:text-slate-800"
      >
        <span>Provider Details</span>
        <span>{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="px-4 pb-4 border-t border-slate-100 pt-3 space-y-2">
          <DetailRow label="Template"    value={score.template_name} />
          <DetailRow label="Resource ID" value={score.template_id} />
          {score.category_data && (
            <div className="mt-2">
              <p className="text-[11px] uppercase tracking-wider text-slate-400 mb-1.5">Parameter Breakdown</p>
              <div className="space-y-1">
                {Object.entries(score.category_data).map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between text-[12px]">
                    <span className="text-slate-600">{k.replace(/_/g, " ")}</span>
                    <span className={`font-semibold ${v === 1 ? "text-emerald-600" : v === 0 ? "text-red-600" : "text-slate-400"}`}>
                      {v === 1 ? "✓" : v === 0 ? "✗" : String(v)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
