type Props = {
  status: string;
};

const toneMap: Record<string, string> = {
  uploaded: "border-sky-500/20 bg-sky-500/10 text-sky-900",
  analyzed: "border-blue-500/20 bg-blue-500/10 text-blue-900",
  processing: "border-amber-500/20 bg-amber-500/15 text-amber-950",
  awaiting_user: "border-orange-500/20 bg-orange-500/15 text-orange-950",
  completed: "border-emerald-500/20 bg-emerald-500/15 text-emerald-950",
  failed: "border-red-500/20 bg-red-500/15 text-red-900",
};

export function StatusBadge({ status }: Props) {
  return (
    <span className={`rounded-full border px-4 py-2 text-sm font-semibold capitalize ${toneMap[status] ?? "border-slate-300 bg-white/70 text-slate-900"}`}>
      {status.replaceAll("_", " ")}
    </span>
  );
}
