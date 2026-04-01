/** Score card component — scaffold only. */

interface ScoreCardProps {
  label: string;
  score: number | null;
  maxScore: number | null;
}

export default function ScoreCard({ label, score, maxScore }: ScoreCardProps) {
  const pct = score != null && maxScore ? Math.round((score / maxScore) * 100) : null;
  return (
    <div className="bg-white rounded-lg shadow p-4">
      <p className="text-sm text-gray-500">{label}</p>
      <p className="text-2xl font-bold text-gray-900">
        {pct != null ? `${pct}%` : "—"}
      </p>
      {score != null && maxScore && (
        <p className="text-xs text-gray-400">{score} / {maxScore}</p>
      )}
    </div>
  );
}
