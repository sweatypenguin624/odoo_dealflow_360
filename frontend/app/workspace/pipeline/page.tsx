"use client";
import Link from "next/link";
import { quotes, type QuoteListItem } from "@/lib/api";
import { useApi } from "@/lib/hooks/useApi";
import { formatCurrency } from "@/lib/format";
import { ErrorState, PageHeader, Skeleton, StatusBadge } from "@/components/ui";

const COLUMNS: { status: string; label: string }[] = [
  { status: "draft", label: "Draft" }, { status: "pending_approval", label: "Pending approval" }, { status: "approved", label: "Approved" },
  { status: "sent,under_negotiation", label: "With customer" }, { status: "confirmed", label: "Confirmed" },
];

export default function PipelinePage() {
  const { data, error, loading, reload } = useApi(() => quotes.list({ status: COLUMNS.map((c) => c.status).join(","), page_size: 100, sort: "-last_activity_at" }), []);
  const byColumn = (status: string) => (data?.items ?? []).filter((q) => status.split(",").includes(q.status));
  return (
    <div className="space-y-4">
      <PageHeader title="Pipeline" subtitle="Most recently active 100 open quotations, grouped by stage." />
      {error && <ErrorState message={error} onRetry={reload} />}
      <div className="grid gap-3 md:grid-cols-5">
        {COLUMNS.map((c) => {
          const items = byColumn(c.status);
          const value = items.reduce((s, q) => s + Number(q.total), 0);
          return (
            <div key={c.status} className="flex flex-col gap-2 rounded-lg bg-zinc-100 p-2">
              <div className="flex items-center justify-between px-1 text-xs"><span className="font-semibold uppercase tracking-wide text-zinc-600">{c.label}</span><span className="text-zinc-500">{items.length} · {formatCurrency(value)}</span></div>
              {loading && !data ? <Skeleton className="h-20" /> : items.map((q: QuoteListItem) => (
                <Link key={q.id} href={`/workspace/quotations/${q.id}`} className="card block p-3 text-sm hover:border-blue-400">
                  <div className="flex items-start justify-between gap-1"><span className="font-medium text-zinc-900">{q.customer_name}</span><StatusBadge status={q.status} /></div>
                  <p className="text-xs text-zinc-500">{q.quote_number} · {q.owner_name ?? "unassigned"}</p>
                  <p className="mt-1 font-semibold tabular-nums">{formatCurrency(q.total)}</p>
                </Link>
              ))}
              {!loading && items.length === 0 && <p className="px-1 py-4 text-center text-xs text-zinc-400">Empty</p>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
