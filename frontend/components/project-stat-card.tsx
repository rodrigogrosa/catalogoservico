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
    <div className="portal-metric">
      <p className="info-label">{label}</p>
      <p className={`mt-3 text-5xl font-semibold ${toneClass}`}>{value}</p>
      {helper ? <p className="mt-3 text-sm leading-7 text-slate-500">{helper}</p> : null}
    </div>
  );
}
