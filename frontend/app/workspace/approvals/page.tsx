"use client";
import { useRouter } from "next/navigation";
import { Suspense } from "react";
import { approvals, type ApprovalQueueItem } from "@/lib/api";
import { useApi } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatCurrency, formatDateTime, formatPct } from "@/lib/format";
import { DataTable, ErrorState, FilterBar, PageHeader, Pagination, Select, StatusBadge, type Column } from "@/components/ui";

function ApprovalsInner() {
  const { state, set, page, setPage } = useListState();
  const { user } = useAuth();
  const router = useRouter();
  const { data, error, loading, reload } = useApi(() => approvals.queue({ step: state.step, page, page_size: 25 }), [state.step, page]);
  const columns: Column<ApprovalQueueItem>[] = [
    { key: "quote", header: "Quote", render: (r) => <><span className="font-medium">{r.quote_number}</span><span className="block text-xs text-zinc-500">v{r.quote_version}</span></> },
    { key: "customer", header: "Customer", render: (r) => r.customer_name },
    { key: "owner", header: "Rep", render: (r) => r.owner_name ?? "—" },
    { key: "level", header: "Required", render: (r) => <><StatusBadge status={r.required_level} /><span className="ml-1 text-xs text-zinc-500">step: {r.current_step}</span></> },
    { key: "risk", header: "Risk summary", render: (r) => <span className="line-clamp-2 max-w-md text-xs text-zinc-600">{r.risk_summary}</span> },
    { key: "total", header: "Total", align: "right", render: (r) => formatCurrency(r.total) },
    { key: "margin", header: "Margin", align: "right", render: (r) => formatPct(r.margin_pct) },
    { key: "waiting", header: "Waiting", render: (r) => <span className={r.waiting_days >= 3 ? "font-medium text-amber-700" : ""}>{r.waiting_days} d<span className="block text-xs font-normal text-zinc-400">{formatDateTime(r.created_at)}</span></span> },
  ];
  return (
    <div className="space-y-4">
      <PageHeader title="Approvals" subtitle={user?.role === "sales_manager" ? "Quotations waiting for your manager sign-off." : user?.role === "finance" ? "Quotations escalated to finance." : "All pending approval requests."} />
      {user?.role === "admin" && <FilterBar><Select value={state.step ?? ""} onChange={(e) => set({ step: e.target.value })} className="w-44" aria-label="Step"><option value="">All steps</option><option value="manager">Manager step</option><option value="finance">Finance step</option></Select></FilterBar>}
      {error && <ErrorState message={error} onRetry={reload} />}
      <DataTable columns={columns} rows={data?.items} keyOf={(r) => r.request_id} loading={loading} onRowClick={(r) => router.push(`/workspace/approvals/${r.quote_id}`)} emptyTitle="Nothing to approve" emptyDescription="Your queue is clear." />
      {data && <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} />}
    </div>
  );
}
export default function ApprovalsPage() { return <Suspense><ApprovalsInner /></Suspense>; }
