interface FilterChipProps {
  label: string;
  active: boolean;
  onToggle: () => void;
}

export default function FilterChip({ label, active, onToggle }: FilterChipProps) {
  return (
    <button
      onClick={onToggle}
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[12px] font-semibold border transition-colors ${
        active
          ? "bg-brand-wine text-white border-brand-wine"
          : "bg-white text-slate-600 border-slate-300 hover:border-brand-wine hover:text-brand-wine"
      }`}
    >
      {label}
      {active && <span className="text-[10px] opacity-80">×</span>}
    </button>
  );
}
