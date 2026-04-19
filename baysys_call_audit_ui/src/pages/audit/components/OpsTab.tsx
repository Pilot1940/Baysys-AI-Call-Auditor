import { useState } from "react";
import ActionCard from "../../../components/ActionCard";
import { api } from "../../../utils/Api";
import type { DashboardSummary, OpsResult } from "../../../types/audit";
import { formatDateTime } from "../../../types/audit";

interface OpsTabProps {
  summary: DashboardSummary | null;
  onRefresh: () => void;
}

export default function OpsTab({ summary, onRefresh }: OpsTabProps) {
  const [dryRun, setDryRun] = useState(false);
  const [syncDate, setSyncDate] = useState("");
  const [syncResult, setSyncResult] = useState<OpsResult | null>(null);
  const [syncLoading, setSyncLoading] = useState(false);
  const [submitResult, setSubmitResult] = useState<OpsResult | null>(null);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [pollResult, setPollResult] = useState<OpsResult | null>(null);
  const [pollLoading, setPollLoading] = useState(false);

  async function handleSync() {
    setSyncLoading(true);
    setSyncResult(null);
    try {
      const res = await api.syncCallLogs({ date: syncDate || undefined, dry_run: dryRun });
      setSyncResult(res);
      if (!dryRun) onRefresh();
    } catch (e) {
      setSyncResult({ errors: -1 });
    } finally {
      setSyncLoading(false);
    }
  }

  async function handleSubmit() {
    setSubmitLoading(true);
    setSubmitResult(null);
    try {
      const res = await api.submitRecordings({});
      setSubmitResult(res);
      onRefresh();
    } catch (e) {
      setSubmitResult({ errors: -1 });
    } finally {
      setSubmitLoading(false);
    }
  }

  async function handlePoll() {
    setPollLoading(true);
    setPollResult(null);
    try {
      const res = await api.pollStuckRecordings({ dry_run: dryRun });
      setPollResult(res);
      onRefresh();
    } catch (e) {
      setPollResult({ errors: -1 });
    } finally {
      setPollLoading(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-4">
      {/* Pipeline status */}
      <ActionCard title="Pipeline Status">
        <div className="grid grid-cols-3 gap-4 mb-3">
          <div>
            <p className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold">Last Sync</p>
            <p className="text-[13px] text-slate-700 mt-0.5">{formatDateTime(summary?.last_sync_at)}</p>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold">Last Scored</p>
            <p className="text-[13px] text-slate-700 mt-0.5">{formatDateTime(summary?.last_completed_at)}</p>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold">Queue</p>
            <p className="text-[13px] text-slate-700 mt-0.5">
              <span>{summary?.pending ?? "—"} pending</span>
              {summary?.submitted != null && summary.submitted > 0 && (
                <span className="text-blue-600 ml-2">{summary.submitted} submitted</span>
              )}
              {summary?.failed != null && summary.failed > 0 && (
                <span className="text-red-600 ml-2">{summary.failed} failed</span>
              )}
            </p>
          </div>
        </div>
      </ActionCard>

      {/* Dry run toggle */}
      <ActionCard title="Dry Run Mode" description="When on, operations preview without writing to the DB or calling GreyLabs.">
        <label className="flex items-center gap-3 cursor-pointer">
          <div
            onClick={() => setDryRun(d => !d)}
            className={`relative w-10 h-5 rounded-full transition-colors ${dryRun ? "bg-brand-wine" : "bg-slate-300"}`}
          >
            <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${dryRun ? "translate-x-5" : "translate-x-0.5"}`} />
          </div>
          <span className="text-[13px] text-slate-700">{dryRun ? "Dry run ON" : "Dry run OFF"}</span>
        </label>
      </ActionCard>

      {/* Sync */}
      <ActionCard title="Sync Call Logs" description="Pull calls from the live call_logs table into the audit pipeline.">
        <div className="flex items-end gap-3">
          <div>
            <label className="block text-[11px] text-slate-500 mb-1">Date (leave blank for yesterday)</label>
            <input
              type="date"
              value={syncDate}
              onChange={e => setSyncDate(e.target.value)}
              className="text-[13px] border border-slate-300 rounded px-2 py-1.5 focus:outline-none focus:border-brand-wine"
            />
          </div>
          <button
            onClick={handleSync}
            disabled={syncLoading}
            className="px-4 py-1.5 border-2 border-brand-wine text-brand-wine text-[13px] font-semibold rounded hover:bg-brand-wine-light transition-colors disabled:opacity-50"
          >
            {syncLoading ? "Syncing…" : "Run Sync"}
          </button>
        </div>
        {syncResult && <OpsResultBanner result={syncResult} type="sync" />}
      </ActionCard>

      {/* Submit */}
      <ActionCard title="Submit Pending Recordings" description="Submit pending recordings to the speech provider for transcription and scoring.">
        <button
          onClick={handleSubmit}
          disabled={submitLoading}
          className="px-4 py-1.5 bg-brand-wine text-white text-[13px] font-semibold rounded hover:bg-brand-wine-dark transition-colors disabled:opacity-50"
        >
          {submitLoading ? "Submitting…" : "Submit Now"}
        </button>
        {submitResult && <OpsResultBanner result={submitResult} type="submit" />}
      </ActionCard>

      {/* Poll */}
      <ActionCard title="Poll Stuck Recordings" description="Check the provider for recordings stuck in submitted status.">
        <button
          onClick={handlePoll}
          disabled={pollLoading}
          className="px-4 py-1.5 border-2 border-slate-400 text-slate-700 text-[13px] font-semibold rounded hover:border-slate-600 transition-colors disabled:opacity-50"
        >
          {pollLoading ? "Polling…" : "Poll Now"}
        </button>
        {pollResult && <OpsResultBanner result={pollResult} type="poll" />}
      </ActionCard>
    </div>
  );
}

function OpsResultBanner({ result, type }: { result: OpsResult; type: "sync" | "submit" | "poll" }) {
  const isError = result.errors === -1;
  return (
    <div className={`mt-3 px-3 py-2 rounded text-[12px] ${isError ? "bg-red-50 text-red-700" : "bg-emerald-50 text-emerald-700"}`}>
      {isError && "Request failed. Check network or server logs."}
      {!isError && type === "sync" && (
        <span>✓ Fetched {result.total_fetched} · Created {result.created} · Skipped {result.skipped_dedup} dedup · {result.duration_seconds?.toFixed(1)}s</span>
      )}
      {!isError && type === "submit" && (
        <span>✓ Submitted {result.submitted} · {result.failed} failed</span>
      )}
      {!isError && type === "poll" && (
        <span>✓ Poll complete</span>
      )}
    </div>
  );
}
