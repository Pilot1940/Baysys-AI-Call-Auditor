type Status = "pending" | "submitted" | "processing" | "completed" | "failed" | "skipped";

const config: Record<Status, { dot: string; text: string; label: string }> = {
  completed:  { dot: "bg-emerald-500", text: "text-emerald-700", label: "Completed" },
  submitted:  { dot: "bg-blue-500",    text: "text-blue-700",    label: "Submitted" },
  processing: { dot: "bg-blue-400 animate-pulse", text: "text-blue-700", label: "Processing" },
  pending:    { dot: "bg-amber-500",   text: "text-amber-700",   label: "Pending" },
  failed:     { dot: "bg-red-500",     text: "text-red-700",     label: "Failed" },
  skipped:    { dot: "bg-slate-400",   text: "text-slate-600",   label: "Skipped" },
};

export default function StatusPill({ status }: { status: Status }) {
  const c = config[status] ?? config.pending;
  return (
    <span className={`inline-flex items-center gap-1.5 text-[12px] font-medium ${c.text}`}>
      <span className={`inline-block w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {c.label}
    </span>
  );
}
