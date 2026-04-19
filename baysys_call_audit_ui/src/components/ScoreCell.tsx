import { scoreBand } from "../types/audit";

const colorMap = {
  excellent:         "text-emerald-600",
  good:              "text-yellow-600",
  "needs-improvement": "text-orange-600",
  critical:          "text-red-600",
};

export default function ScoreCell({ pct }: { pct: number | null | undefined }) {
  if (pct == null) return <span className="text-slate-400">—</span>;
  const band = scoreBand(pct);
  const cls = band ? colorMap[band] : "text-slate-600";
  return <span className={`font-semibold ${cls}`}>{pct.toFixed(1)}%</span>;
}
