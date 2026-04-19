import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import ScoreTrendChart from "./ScoreTrendChart";
import ScoreCell from "../../../components/ScoreCell";
import FatalBadge from "../../../components/FatalBadge";
import { api } from "../../../utils/Api";
import type { AgentSummaryRow, CallRecording } from "../../../types/audit";
import { formatDateTime } from "../../../types/audit";

type DrawerTab = "overview" | "calls";

interface AgentDrawerProps {
  agent: AgentSummaryRow;
  onClose: () => void;
}

export default function AgentDrawer({ agent, onClose }: AgentDrawerProps) {
  const [tab, setTab] = useState<DrawerTab>("overview");
  const [calls, setCalls] = useState<CallRecording[]>([]);
  const [loadingCalls, setLoadingCalls] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    setLoadingCalls(true);
    api.getRecordings({ agent_id: agent.agent_id, status: "completed", page_size: "20" })
      .then(r => setCalls(r.results))
      .catch(() => setCalls([]))
      .finally(() => setLoadingCalls(false));
  }, [agent.agent_id]);

  const trendData = calls
    .slice()
    .reverse()
    .map((_call, i) => ({
      call: i + 1,
      score: null as number | null,
    }));

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/20 z-40" onClick={onClose} />

      {/* Drawer */}
      <div className="fixed right-0 top-0 h-full w-[480px] bg-white shadow-2xl z-50 flex flex-col">
        {/* Dark header */}
        <div className="bg-slate-800 text-white px-5 py-4">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-[16px] font-bold">{agent.agent_name}</h2>
              <p className="text-[12px] text-slate-400 mt-0.5">Agent ID {agent.agent_id}</p>
            </div>
            <button onClick={onClose} className="text-slate-400 hover:text-white text-xl leading-none">×</button>
          </div>
          <div className="flex gap-3 mt-3">
            <span className="bg-slate-700 text-slate-300 text-[11px] px-2 py-0.5 rounded">
              {agent.calls} calls scored
            </span>
            {agent.fatals > 0 && (
              <span className="bg-red-900 text-red-300 text-[11px] px-2 py-0.5 rounded">
                ⚡ {agent.fatals} FATAL
              </span>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-slate-200">
          {(["overview", "calls"] as DrawerTab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-1 py-2.5 text-[13px] font-medium capitalize border-b-2 transition-colors ${
                tab === t
                  ? "border-brand-wine text-brand-wine"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {t === "overview" ? "Overview" : "Call History"}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5">
          {tab === "overview" && (
            <div className="space-y-5">
              <div>
                <p className="text-[11px] font-semibold tracking-widest uppercase text-slate-500 mb-3">
                  Score Trend (Last {Math.min(calls.length, 10)} Calls)
                </p>
                {trendData.length > 0
                  ? <ScoreTrendChart data={trendData} height={180} />
                  : <p className="text-[13px] text-slate-400">No scored calls yet.</p>}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <Stat label="Avg Score" value={<ScoreCell pct={agent.avg_score} />} />
                <Stat label="FATAL Calls" value={
                  agent.fatals > 0
                    ? <FatalBadge level={3} />
                    : <span className="text-emerald-600 font-semibold">None</span>
                } />
                <Stat label="Total Scored" value={String(agent.calls)} />
                <Stat label="Unreviewed Flags" value={String(agent.unreviewed_flags ?? "—")} />
              </div>
            </div>
          )}

          {tab === "calls" && (
            <div>
              {loadingCalls && <p className="text-[13px] text-slate-400">Loading…</p>}
              {!loadingCalls && calls.length === 0 && (
                <p className="text-[13px] text-slate-400">No completed calls found.</p>
              )}
              {!loadingCalls && calls.length > 0 && (
                <table className="min-w-full">
                  <thead>
                    <tr className="border-b border-slate-200">
                      <th className="pb-2 text-left text-[11px] uppercase tracking-wider text-slate-400 font-semibold">Date</th>
                      <th className="pb-2 text-left text-[11px] uppercase tracking-wider text-slate-400 font-semibold">Duration</th>
                      <th className="pb-2 text-left text-[11px] uppercase tracking-wider text-slate-400 font-semibold">FATAL</th>
                      <th className="pb-2 text-left text-[11px] uppercase tracking-wider text-slate-400 font-semibold">Flags</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {calls.map(c => (
                      <tr key={c.id} className="hover:bg-slate-50">
                        <td className="py-2.5 text-[12px] text-slate-700">
                          <div>{formatDateTime(c.recording_datetime)}</div>
                          <div className="text-slate-400">#{c.id}</div>
                        </td>
                        <td className="py-2.5 text-[12px] text-slate-600">—</td>
                        <td className="py-2.5"><FatalBadge level={c.fatal_level} /></td>
                        <td className="py-2.5 text-[12px]">
                          {c.compliance_flag_count > 0
                            ? <span className="text-red-600 font-semibold">{c.compliance_flag_count}</span>
                            : <span className="text-slate-400">0</span>}
                        </td>
                        <td className="py-2.5">
                          <button
                            onClick={() => navigate(`/audit/call/${c.id}`)}
                            className="text-[12px] text-blue-600 hover:underline"
                          >
                            View →
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="bg-slate-50 rounded-lg p-3">
      <p className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold mb-1">{label}</p>
      <div className="text-[15px]">{value}</div>
    </div>
  );
}
