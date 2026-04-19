import { useState } from "react";
import DataTable from "../../../components/DataTable";
import ScoreCell from "../../../components/ScoreCell";
import AgentDrawer from "./AgentDrawer";
import type { AgentSummaryRow } from "../../../types/audit";

interface AgentsTabProps {
  agents: AgentSummaryRow[];
}

export default function AgentsTab({ agents }: AgentsTabProps) {
  const [selected, setSelected] = useState<AgentSummaryRow | null>(null);

  const columns = [
    {
      key: "#",
      label: "#",
      render: (_: unknown, row: AgentSummaryRow) => (
        <span className="text-slate-400">{agents.indexOf(row) + 1}</span>
      ),
    },
    {
      key: "agent_name",
      label: "Agent",
      sortable: true,
      render: (_: unknown, row: AgentSummaryRow) => (
        <div>
          <span className="text-blue-600 font-medium">{row.agent_name}</span>
          <span className="ml-2 text-[11px] text-slate-400">{row.agent_id}</span>
        </div>
      ),
    },
    {
      key: "calls",
      label: "Calls Scored",
      sortable: true,
      render: (v: unknown) => <span className="text-slate-700">{String(v)}</span>,
    },
    {
      key: "avg_score",
      label: "Avg Score",
      sortable: true,
      render: (v: unknown) => <ScoreCell pct={v as number | null} />,
    },
    {
      key: "fatals",
      label: "FATAL",
      sortable: true,
      render: (v: unknown) => {
        const n = v as number;
        return n > 0
          ? <span className="text-red-600 font-semibold">{n}</span>
          : <span className="text-slate-400">0</span>;
      },
    },
    {
      key: "unreviewed_flags",
      label: "Unreviewed Flags",
      render: (v: unknown) => {
        const n = v as number | undefined;
        return n != null && n > 0
          ? <span className="text-amber-600 font-semibold">{n}</span>
          : <span className="text-slate-400">—</span>;
      },
    },
  ];

  return (
    <div>
      <p className="text-[12px] text-slate-400 mb-4">
        {agents.length} agents · sorted by avg score (worst first)
      </p>

      <div className="bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden">
        <DataTable
          columns={columns as never}
          data={agents.sort((a, b) => {
            if (a.avg_score == null && b.avg_score == null) return 0;
            if (a.avg_score == null) return 1;
            if (b.avg_score == null) return -1;
            return a.avg_score - b.avg_score;
          }) as never}
          onRowClick={(row) => setSelected(row as unknown as AgentSummaryRow)}
          keyField="agent_id"
          emptyMessage="No scored agents in this period."
        />
      </div>

      {selected && (
        <AgentDrawer agent={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
