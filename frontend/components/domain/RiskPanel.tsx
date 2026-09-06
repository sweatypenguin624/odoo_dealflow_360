import type { RiskResult } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import { StatusBadge } from "@/components/ui/Badge";

export function RiskPanel({ risk, compact }: { risk: RiskResult; compact?: boolean }) {
  const level = risk.required_approval_level;
  const tone = level === "none" ? "border-emerald-200 bg-emerald-50" : level === "manager" ? "border-amber-200 bg-amber-50" : "border-red-200 bg-red-50";
  return (
    <div className={`rounded-lg border p-4 ${tone}`} data-testid="risk-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold text-zinc-900">{level === "none" ? "Within discount policy" : `Approval required: ${risk.level_label}`}</p>
        <StatusBadge status={level} label={risk.level_label} />
      </div>
      <p className="mt-1 text-sm text-zinc-700">{risk.summary}</p>
      {!compact && (
        <dl className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
          <div><dt className="text-zinc-500">Blended score</dt><dd className="font-medium">{Number(risk.blended_score).toFixed(2)} pts</dd></div>
          <div><dt className="text-zinc-500">Worst line</dt><dd className="font-medium">{Number(risk.worst_points_over).toFixed(2)} pts over</dd></div>
          <div><dt className="text-zinc-500">Value-weighted excess</dt><dd className="font-medium">{Number(risk.weighted_excess_pct).toFixed(2)}%</dd></div>
          <div><dt className="text-zinc-500">Excess discount</dt><dd className="font-medium">{formatCurrency(risk.excess_discount_amount)}</dd></div>
        </dl>
      )}
      {risk.line_results.length > 0 && !compact && (
        <ul className="mt-3 space-y-1 text-sm">
          {risk.line_results.map((l) => (
            <li key={l.line_id} className="flex items-start gap-2">
              <StatusBadge status={l.status} label={l.status === "within_limit" ? "Within limit" : "Over limit"} />
              <span className="text-zinc-700">{l.explanation}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
