/** Trend chart component — scaffold only. Charting library TBD in Prompt B. */

interface TrendDataPoint {
  date: string;
  value: number;
}

interface TrendChartProps {
  data: TrendDataPoint[];
  label: string;
}

export default function TrendChart({ data, label }: TrendChartProps) {
  return (
    <div className="bg-white rounded-lg shadow p-4">
      <p className="text-sm font-medium text-gray-700 mb-2">{label}</p>
      <p className="text-xs text-gray-400">
        Chart placeholder — {data.length} data points. Charting library added in Prompt B.
      </p>
    </div>
  );
}
