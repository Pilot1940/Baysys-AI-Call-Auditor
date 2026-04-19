export default function FatalBadge({ level }: { level: number | undefined }) {
  if (!level || level === 0) return null;
  const isHigh = level >= 3;
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold ${
        isHigh
          ? "bg-red-100 text-red-700"
          : "bg-amber-100 text-amber-700"
      }`}
    >
      ⚡ F{level}
    </span>
  );
}
