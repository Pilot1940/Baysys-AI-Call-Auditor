import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer,
} from "recharts";

interface DataPoint {
  call: number;
  score: number | null;
}

interface ScoreTrendChartProps {
  data: DataPoint[];
  height?: number;
}

export default function ScoreTrendChart({ data, height = 200 }: ScoreTrendChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
        <XAxis
          dataKey="call"
          tick={{ fontSize: 11, fill: "#94A3B8" }}
          label={{ value: "Call #", position: "insideBottom", offset: -2, fontSize: 11, fill: "#94A3B8" }}
        />
        <YAxis
          domain={[0, 100]}
          tick={{ fontSize: 11, fill: "#94A3B8" }}
          tickFormatter={v => `${v}%`}
        />
        <Tooltip
          formatter={(v: number) => [`${v.toFixed(1)}%`, "Score"]}
          labelFormatter={l => `Call #${l}`}
          contentStyle={{ fontSize: 12, borderColor: "#E2E8F0" }}
        />
        {/* Band reference lines */}
        <ReferenceLine y={85} stroke="#10B981" strokeDasharray="4 3" label={{ value: "Excellent", position: "right", fontSize: 10, fill: "#10B981" }} />
        <ReferenceLine y={70} stroke="#3B82F6" strokeDasharray="4 3" label={{ value: "Good", position: "right", fontSize: 10, fill: "#3B82F6" }} />
        <ReferenceLine y={55} stroke="#F59E0B" strokeDasharray="4 3" label={{ value: "Needs Imp.", position: "right", fontSize: 10, fill: "#F59E0B" }} />
        <Line
          type="monotone"
          dataKey="score"
          stroke="#7C3AED"
          strokeWidth={2}
          dot={{ r: 4, fill: "#7C3AED", strokeWidth: 0 }}
          activeDot={{ r: 5 }}
          connectNulls={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
