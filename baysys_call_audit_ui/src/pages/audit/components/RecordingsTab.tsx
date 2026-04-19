import { useState, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import FilterChip from "../../../components/FilterChip";
import DataTable from "../../../components/DataTable";
import StatusPill from "../../../components/StatusPill";
import FatalBadge from "../../../components/FatalBadge";
import { api } from "../../../utils/Api";
import type { CallRecording } from "../../../types/audit";
import { formatDateTime } from "../../../types/audit";

const PAGE_SIZE = 25;

export default function RecordingsTab() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Exception filter chips
  const [chips, setChips] = useState({
    fatal: searchParams.get("fatal") === "1",
    low_score: searchParams.get("low_score") === "1",
    critical_flags: searchParams.get("critical_flags") === "1",
    unreviewed: searchParams.get("unreviewed") === "1",
    neg_sentiment: searchParams.get("neg_sentiment") === "1",
  });

  // Additional filters
  const [status, setStatus] = useState(searchParams.get("status") ?? "");
  const [agentId, setAgentId] = useState(searchParams.get("agent_id") ?? "");
  const [dateFrom, setDateFrom] = useState(searchParams.get("date_from") ?? "");
  const [dateTo, setDateTo] = useState(searchParams.get("date_to") ?? "");

  const [recordings, setRecordings] = useState<CallRecording[]>([]);
  const [pagination, setPagination] = useState({ page: 1, total_pages: 1, total_count: 0 });
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(Number(searchParams.get("page") ?? 1));

  const anyChipActive = Object.values(chips).some(Boolean);

  const fetchRecordings = useCallback(async (p: number) => {
    setLoading(true);
    const params: Record<string, string> = {
      page: String(p),
      page_size: String(PAGE_SIZE),
      ordering: "-recording_datetime",
    };
    if (status) params.status = status;
    if (agentId) params.agent_id = agentId;
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    // Chips map to backend filters (backend gaps noted — pass what exists)
    if (chips.fatal) params.fatal_level_gte = "3";
    if (chips.low_score) params.score_lt = "50";
    if (status === "" && !anyChipActive) {
      // default: show completed + exceptions only
      params.status = "completed";
    }

    try {
      const res = await api.getRecordings(params);
      setRecordings(res.results);
      setPagination(res.pagination);
    } catch {
      setRecordings([]);
    } finally {
      setLoading(false);
    }
  }, [chips, status, agentId, dateFrom, dateTo, anyChipActive]);

  useEffect(() => {
    fetchRecordings(page);
  }, [fetchRecordings, page]);

  function toggleChip(key: keyof typeof chips) {
    setChips(prev => ({ ...prev, [key]: !prev[key] }));
    setPage(1);
  }

  function clearFilters() {
    setChips({ fatal: false, low_score: false, critical_flags: false, unreviewed: false, neg_sentiment: false });
    setStatus("");
    setAgentId("");
    setDateFrom("");
    setDateTo("");
    setPage(1);
  }

  const columns = [
    {
      key: "agent_name",
      label: "Agent",
      sortable: true,
      render: (_: unknown, row: CallRecording) => (
        <div>
          <span className="text-blue-600 font-medium">{row.agent_name}</span>
          <div className="text-[11px] text-slate-400">{row.agent_id}</div>
        </div>
      ),
    },
    {
      key: "customer_id",
      label: "Customer",
      render: (v: unknown) => v ? String(v) : <span className="text-slate-400">—</span>,
    },
    {
      key: "recording_datetime",
      label: "Date (IST)",
      sortable: true,
      render: (v: unknown) => (
        <span className="text-slate-600 whitespace-nowrap">{formatDateTime(v as string)}</span>
      ),
    },
    {
      key: "status",
      label: "Status",
      sortable: true,
      render: (v: unknown) => <StatusPill status={v as CallRecording["status"]} />,
    },
    {
      key: "fatal_level",
      label: "FATAL",
      sortable: true,
      render: (v: unknown) => <FatalBadge level={v as number | undefined} />,
    },
    {
      key: "compliance_flag_count",
      label: "Flags",
      sortable: true,
      render: (v: unknown) => {
        const n = v as number;
        return n > 0
          ? <span className="font-semibold text-red-600">{n}</span>
          : <span className="text-slate-400">0</span>;
      },
    },
    {
      key: "id",
      label: "",
      render: (_: unknown, row: CallRecording) => (
        <button
          onClick={e => { e.stopPropagation(); navigate(`/audit/call/${row.id}`); }}
          className="text-[12px] text-blue-600 hover:underline whitespace-nowrap"
        >
          View →
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      {/* Exception chips + filters */}
      <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm">
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mr-1">Exceptions:</span>
          <FilterChip label="⚡ FATAL ≥3"       active={chips.fatal}          onToggle={() => toggleChip("fatal")} />
          <FilterChip label="Score <50%"         active={chips.low_score}      onToggle={() => toggleChip("low_score")} />
          <FilterChip label="Critical flags"     active={chips.critical_flags} onToggle={() => toggleChip("critical_flags")} />
          <FilterChip label="Unreviewed flags"   active={chips.unreviewed}     onToggle={() => toggleChip("unreviewed")} />
          <FilterChip label="Negative sentiment" active={chips.neg_sentiment}  onToggle={() => toggleChip("neg_sentiment")} />
        </div>

        <div className="flex flex-wrap items-end gap-3 pt-3 border-t border-slate-100">
          <div>
            <label className="block text-[11px] text-slate-500 mb-1">Status</label>
            <select
              value={status}
              onChange={e => { setStatus(e.target.value); setPage(1); }}
              className="text-[12px] border border-slate-300 rounded px-2 py-1 bg-white focus:outline-none focus:border-brand-wine"
            >
              <option value="">All</option>
              <option value="completed">Completed</option>
              <option value="pending">Pending</option>
              <option value="submitted">Submitted</option>
              <option value="failed">Failed</option>
              <option value="skipped">Skipped</option>
            </select>
          </div>
          <div>
            <label className="block text-[11px] text-slate-500 mb-1">Agent ID</label>
            <input
              type="text"
              placeholder="e.g. 42"
              value={agentId}
              onChange={e => { setAgentId(e.target.value); setPage(1); }}
              className="text-[12px] border border-slate-300 rounded px-2 py-1 w-28 focus:outline-none focus:border-brand-wine"
            />
          </div>
          <div>
            <label className="block text-[11px] text-slate-500 mb-1">From</label>
            <input
              type="date"
              value={dateFrom}
              onChange={e => { setDateFrom(e.target.value); setPage(1); }}
              className="text-[12px] border border-slate-300 rounded px-2 py-1 focus:outline-none focus:border-brand-wine"
            />
          </div>
          <div>
            <label className="block text-[11px] text-slate-500 mb-1">To</label>
            <input
              type="date"
              value={dateTo}
              onChange={e => { setDateTo(e.target.value); setPage(1); }}
              className="text-[12px] border border-slate-300 rounded px-2 py-1 focus:outline-none focus:border-brand-wine"
            />
          </div>
          <button
            onClick={clearFilters}
            className="text-[12px] text-slate-500 hover:text-slate-800 underline"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
          <p className="text-[12px] text-slate-500">
            {loading ? "Loading…" : `${pagination.total_count.toLocaleString()} recordings`}
          </p>
        </div>

        <DataTable
          columns={columns as never}
          data={recordings as never}
          onRowClick={(row) => navigate(`/audit/call/${(row as unknown as CallRecording).id}`)}
          keyField="id"
          emptyMessage={loading ? "Loading…" : "No recordings match the current filters."}
        />

        {/* Pagination */}
        {pagination.total_pages > 1 && (
          <div className="px-4 py-3 border-t border-slate-100 flex items-center justify-between">
            <p className="text-[12px] text-slate-500">
              Page {pagination.page} of {pagination.total_pages}
            </p>
            <div className="flex gap-1">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1 text-[12px] border border-slate-300 rounded hover:bg-slate-50 disabled:opacity-40"
              >
                ← Prev
              </button>
              <button
                onClick={() => setPage(p => Math.min(pagination.total_pages, p + 1))}
                disabled={page === pagination.total_pages}
                className="px-3 py-1 text-[12px] border border-slate-300 rounded hover:bg-slate-50 disabled:opacity-40"
              >
                Next →
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
