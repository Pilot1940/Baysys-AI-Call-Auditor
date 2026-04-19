import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import AuditShell from "./components/AuditShell";
import KpiCard from "../../components/KpiCard";
import RecordingsTab from "./components/RecordingsTab";
import AgentsTab from "./components/AgentsTab";
import OpsTab from "./components/OpsTab";
import { api } from "../../utils/Api";
import type { DashboardSummary } from "../../types/audit";

type Tab = "recordings" | "agents" | "ops";
type Period = "week" | "month" | "mtd";

export default function DashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState<Tab>((searchParams.get("tab") as Tab) ?? "recordings");
  const [agency, setAgency] = useState(searchParams.get("agency") ?? "");
  const [period, setPeriod] = useState<Period>((searchParams.get("mode") as Period) ?? "month");
  const [periodValue, setPeriodValue] = useState(searchParams.get("value") ?? "");
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const syncParams = useCallback(() => {
    const p: Record<string, string> = { tab, mode: period };
    if (agency) p.agency = agency;
    if (periodValue) p.value = periodValue;
    setSearchParams(p, { replace: true });
  }, [tab, agency, period, periodValue, setSearchParams]);

  useEffect(() => { syncParams(); }, [syncParams]);

  const fetchSummary = useCallback(async () => {
    const params: Record<string, string> = {};
    if (agency) params.agency_id = agency;
    try {
      const data = await api.getDashboardSummary(params);
      setSummary(data);
    } catch {
      // silently fail — show stale data
    }
  }, [agency]);

  useEffect(() => { fetchSummary(); }, [fetchSummary, refreshKey]);

  function refresh() { setRefreshKey(k => k + 1); }

  // Compute exception count from available data (backend gaps B1–B4 would refine this)
  const exceptionCount = summary
    ? summary.critical_flags + (summary.failed > 0 ? summary.failed : 0)
    : null;

  const pipelineLabel = summary
    ? `${summary.completed.toLocaleString()} / ${summary.total_recordings.toLocaleString()}`
    : "—";

  const pipelineSubLabel = summary
    ? (
      <span>
        scored / total
        {summary.failed > 0 && (
          <span className="text-red-600 ml-2">● {summary.failed} failed</span>
        )}
      </span>
    )
    : null;

  return (
    <AuditShell
      activeTab={tab}
      onTabChange={setTab}
      agency={agency}
      onAgencyChange={a => { setAgency(a); refresh(); }}
      period={period}
      onPeriodChange={p => { setPeriod(p); refresh(); }}
      periodValue={periodValue}
      onPeriodValueChange={setPeriodValue}
      onRefresh={refresh}
    >
      {/* KPI row */}
      <div className="flex gap-4 mb-6">
        <KpiCard
          label="Compliance Score"
          accent="wine"
          value={
            summary?.avg_compliance_score != null
              ? <span className="text-brand-wine">{summary.avg_compliance_score.toFixed(1)}%</span>
              : <span className="text-slate-400">—</span>
          }
          subLabel={
            <span>
              <span className="inline-flex items-center gap-1 text-[11px] bg-slate-100 text-slate-400 px-1.5 py-0.5 rounded mr-1">
                via GreyLabs
              </span>
              of scored calls
            </span>
          }
        />
        <KpiCard
          label="Exceptions"
          accent="amber"
          value={
            <span className="text-amber-600">
              {exceptionCount != null ? exceptionCount.toLocaleString() : "—"}
            </span>
          }
          subLabel={
            summary ? (
              <span>
                Critical flags {summary.critical_flags}
                {summary.failed > 0 && <span className="ml-2">· Failed {summary.failed}</span>}
              </span>
            ) : null
          }
        />
        <KpiCard
          label="Critical Flags"
          accent="red"
          value={
            <span className={summary?.critical_flags ? "text-red-600" : "text-slate-900"}>
              {summary?.critical_flags ?? "—"}
            </span>
          }
          subLabel="Unreviewed critical + high severity"
        />
        <KpiCard
          label="Pipeline"
          accent="slate"
          value={pipelineLabel}
          subLabel={pipelineSubLabel}
        />
      </div>

      {/* Tab content */}
      {tab === "recordings" && <RecordingsTab key={refreshKey} />}
      {tab === "agents"     && (
        <AgentsTab agents={summary?.agent_summary ?? []} />
      )}
      {tab === "ops"        && <OpsTab summary={summary} onRefresh={refresh} />}
    </AuditShell>
  );
}
