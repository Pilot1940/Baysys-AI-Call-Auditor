/** Compliance flags display — scaffold only. */

import type { ComplianceFlag } from "../../../types/audit";

interface ComplianceFlagsProps {
  flags: ComplianceFlag[];
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-red-100 text-red-800",
  high: "bg-orange-100 text-orange-800",
  medium: "bg-yellow-100 text-yellow-800",
  low: "bg-blue-100 text-blue-800",
};

export default function ComplianceFlags({ flags }: ComplianceFlagsProps) {
  if (!flags.length) {
    return <p className="text-sm text-gray-500">No compliance flags.</p>;
  }
  return (
    <div className="space-y-2">
      {flags.map((flag) => (
        <div key={flag.id} className="flex items-start gap-2 p-2 rounded border">
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${SEVERITY_COLORS[flag.severity] || ""}`}>
            {flag.severity}
          </span>
          <span className="text-sm text-gray-700">{flag.description}</span>
        </div>
      ))}
    </div>
  );
}
