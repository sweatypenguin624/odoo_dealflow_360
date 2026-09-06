import { titleCase } from "@/lib/format";

const TONES = {
  neutral: "bg-zinc-100 text-zinc-700",
  blue: "bg-blue-100 text-blue-800",
  amber: "bg-amber-100 text-amber-800",
  green: "bg-emerald-100 text-emerald-800",
  red: "bg-red-100 text-red-800",
  purple: "bg-purple-100 text-purple-800",
  slate: "bg-slate-200 text-slate-700",
} as const;
type Tone = keyof typeof TONES;

const STATUS_TONE: Record<string, Tone> = {
  draft: "neutral", pending_approval: "amber", approved: "blue", rejected: "red", revision_required: "amber", sent: "purple", under_negotiation: "purple",
  confirmed: "green", expired: "slate", cancelled: "slate",
  not_started: "neutral", planned: "blue", reserved: "amber", partially_shipped: "amber", shipped: "green", delivered: "green", backordered: "red",
  suggested: "blue", manually_overridden: "amber",
  not_billed: "neutral", partially_billed: "amber", billed: "blue", paid: "green", issued: "blue", partially_paid: "amber", overdue: "red", void: "slate",
  active: "green", paused: "amber", pending: "amber", accepted: "green", superseded: "slate", returned: "amber",
  open: "amber", acknowledged: "blue", resolved: "green", critical: "red", warning: "amber", info: "blue",
  within_limit: "green", over_limit: "red", none: "green", manager: "amber", manager_then_finance: "red",
  completed: "green", failed: "red", refund: "purple", payment: "green", one_time: "neutral", recurring: "purple", both: "blue",
};

export function Badge({ children, tone = "neutral", className = "" }: { children: React.ReactNode; tone?: Tone; className?: string }) {
  return <span className={`inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${TONES[tone]} ${className}`}>{children}</span>;
}

export function StatusBadge({ status, label }: { status: string | null | undefined; label?: string }) {
  if (!status) return <span className="text-zinc-400">—</span>;
  return <Badge tone={STATUS_TONE[status] ?? "neutral"}>{label ?? titleCase(status)}</Badge>;
}
