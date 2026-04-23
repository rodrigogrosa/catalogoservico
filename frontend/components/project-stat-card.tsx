type Props = {
  label: string;
  value: string;
  helper?: string;
  tone?: "neutral" | "success" | "warning" | "danger";
};

export function ProjectStatCard({ label, value, helper, tone = "neutral" }: Props) {
  const toneClass = {
    danger: "text-red-700",
    neutral: "text-slate-950",
    success: "text-emerald-700",
    warning: "text-orange-700",
  }[tone];

  return (
    <div className="border-l border-slate-900/10 px-5 py-3 first:border-l-0">
      <p className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-500">{label}</p>
      <p className={`mt-2 text-5xl font-semibold ${toneClass}`}>{value}</p>
      {helper ? <p className="mt-2 text-base leading-6 text-slate-500">{helper}</p> : null}
    </div>
  );
}
