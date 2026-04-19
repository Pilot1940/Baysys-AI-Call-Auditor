interface KpiCardProps {
  label: string;
  value: React.ReactNode;
  subLabel?: React.ReactNode;
  accent?: "wine" | "amber" | "red" | "slate" | "emerald";
}

const accentBorder: Record<string, string> = {
  wine:    "border-t-brand-wine",
  amber:   "border-t-amber-500",
  red:     "border-t-red-500",
  slate:   "border-t-slate-400",
  emerald: "border-t-emerald-500",
};

export default function KpiCard({ label, value, subLabel, accent = "slate" }: KpiCardProps) {
  return (
    <div className={`bg-white border border-slate-200 border-t-4 ${accentBorder[accent]} rounded-lg p-4 shadow-sm flex-1 min-w-0`}>
      <p className="text-[11px] font-semibold tracking-widest uppercase text-slate-500 mb-2">
        {label}
      </p>
      <div className="text-[28px] font-bold text-slate-900 leading-tight">
        {value}
      </div>
      {subLabel && (
        <div className="mt-1 text-[12px] text-slate-500">{subLabel}</div>
      )}
    </div>
  );
}
