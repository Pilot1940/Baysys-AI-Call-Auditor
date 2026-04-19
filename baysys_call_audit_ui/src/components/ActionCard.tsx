interface ActionCardProps {
  title: string;
  description?: string;
  children: React.ReactNode;
}

export default function ActionCard({ title, description, children }: ActionCardProps) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg p-5 shadow-sm">
      <h3 className="text-[15px] font-semibold text-slate-900 mb-1">{title}</h3>
      {description && (
        <p className="text-[13px] text-slate-500 mb-4">{description}</p>
      )}
      <div>{children}</div>
    </div>
  );
}
