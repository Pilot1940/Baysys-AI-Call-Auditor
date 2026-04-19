import { type ReactNode } from "react";

type Tab = "recordings" | "agents" | "ops";
type Period = "week" | "month" | "mtd";

interface AuditShellProps {
  activeTab: Tab;
  onTabChange: (t: Tab) => void;
  agency: string;
  onAgencyChange: (a: string) => void;
  period: Period;
  onPeriodChange: (p: Period) => void;
  periodValue: string;
  onPeriodValueChange: (v: string) => void;
  onRefresh: () => void;
  children: ReactNode;
}

const AGENCIES = [
  { id: "", label: "All Agencies" },
  { id: "prolynk", label: "Prolynk" },
  { id: "mba", label: "MBA" },
  { id: "callflex", label: "Callflex" },
  { id: "konex", label: "Konex" },
  { id: "comtel", label: "Comtel" },
];

const PERIODS: { key: Period; label: string }[] = [
  { key: "week", label: "WEEK" },
  { key: "month", label: "MONTH" },
  { key: "mtd", label: "MTD" },
];

const TABS: { key: Tab; label: string }[] = [
  { key: "recordings", label: "Recordings" },
  { key: "agents",     label: "Agents" },
  { key: "ops",        label: "Ops" },
];

export default function AuditShell({
  activeTab, onTabChange,
  agency, onAgencyChange,
  period, onPeriodChange,
  onRefresh,
  children,
}: AuditShellProps) {
  return (
    <div className="min-h-screen bg-slate-50">
      {/* Page header */}
      <div className="bg-white border-b border-slate-200 px-6 pt-5 pb-0">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-[22px] font-bold text-brand-wine leading-tight">Call Audit</h1>
            <p className="text-[12px] text-slate-500 mt-0.5">AI-powered compliance monitoring</p>
          </div>
          <button
            onClick={onRefresh}
            className="mt-1 px-3 py-1.5 text-[12px] text-slate-600 border border-slate-300 rounded hover:border-slate-400 transition-colors"
          >
            Refresh
          </button>
        </div>

        {/* Agency + period filter bar */}
        <div className="flex items-center gap-6 pb-3">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-semibold tracking-widest uppercase text-slate-400">Agency</span>
            <select
              value={agency}
              onChange={e => onAgencyChange(e.target.value)}
              className="text-[13px] text-slate-700 border border-slate-300 rounded px-2 py-1 bg-white focus:outline-none focus:border-brand-wine"
            >
              {AGENCIES.map(a => (
                <option key={a.id} value={a.id}>{a.label}</option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[11px] font-semibold tracking-widest uppercase text-slate-400">Period</span>
            <div className="flex rounded overflow-hidden border border-slate-300">
              {PERIODS.map(p => (
                <button
                  key={p.key}
                  onClick={() => onPeriodChange(p.key)}
                  className={`px-3 py-1 text-[11px] font-semibold transition-colors ${
                    period === p.key
                      ? "bg-brand-wine text-white"
                      : "bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Tab bar */}
        <div className="flex gap-0">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => onTabChange(t.key)}
              className={`px-5 py-2.5 text-[13px] font-medium border-b-2 transition-colors ${
                activeTab === t.key
                  ? "border-brand-wine text-brand-wine"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="px-6 py-6 max-w-[1400px] mx-auto">
        {children}
      </div>
    </div>
  );
}
