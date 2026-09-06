"use client";
import { useRouter } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { subscriptions, type Subscription } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useApi, useDebounce } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatCurrency, formatDate, titleCase, todayIso } from "@/lib/format";
import { Badge, Button, ConfirmDialog, DataTable, ErrorState, Field, FilterBar, Input, PageHeader, Pagination, SearchInput, Select, StatusBadge, type Column } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";

function Inner() {
  const { state, set, page, setPage } = useListState();
  const router = useRouter();
  const { can } = useAuth();
  const toast = useToast();
  const [q, setQ] = useState(state.q ?? "");
  const debounced = useDebounce(q);
  useEffect(() => { if (debounced !== (state.q ?? "")) set({ q: debounced }); }, [debounced]); // eslint-disable-line react-hooks/exhaustive-deps
  const { data, error, loading, reload } = useApi(
    () => subscriptions.list({ q: state.q, status: state.status, due_before: state.due_before, page, page_size: 25 }),
    [JSON.stringify(state), page],
  );
  const [runDialog, setRunDialog] = useState(false);
  const [asOf, setAsOf] = useState(todayIso());
  const [busy, setBusy] = useState(false);

  async function runBilling() {
    setBusy(true);
    try {
      const r = await subscriptions.runBilling(asOf || undefined);
      toast.success(`Billing run for ${r.as_of}: ${r.invoices_created} invoice(s) created, ${r.already_billed} already billed, ${r.overdue_marked} marked overdue.`);
      setRunDialog(false);
      reload();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<Subscription>[] = [
    { key: "plan", header: "Plan", render: (r) => <><span className="font-medium">{r.plan_name}</span><span className="block text-xs text-zinc-500">{r.product_name}</span></> },
    { key: "customer", header: "Customer", render: (r) => r.customer_name ?? "—" },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
    { key: "interval", header: "Interval", render: (r) => <Badge tone="purple">{titleCase(r.interval)}</Badge> },
    { key: "qty", header: "Qty", align: "right", render: (r) => r.quantity },
    { key: "amount", header: "Per cycle", align: "right", render: (r) => formatCurrency(r.cycle_amount) },
    { key: "cycle", header: "Current cycle", render: (r) => <span className="text-xs">{formatDate(r.current_cycle_start)} – {formatDate(r.current_cycle_end)}</span> },
    { key: "next", header: "Next billing", render: (r) => <span className={r.next_billing_date && new Date(r.next_billing_date) <= new Date() && r.status === "active" ? "font-medium text-amber-700" : ""}>{formatDate(r.next_billing_date)}</span> },
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Subscriptions"
        subtitle={data ? `${data.total.toLocaleString()} subscriptions` : undefined}
        actions={can("subscription:manage") && <Button onClick={() => setRunDialog(true)}>Run billing</Button>}
      />
      <FilterBar>
        <SearchInput value={q} onChange={setQ} placeholder="Customer or plan name" className="w-72" />
        <Select value={state.status ?? ""} onChange={(e) => set({ status: e.target.value })} className="w-40" aria-label="Status">
          <option value="">All statuses</option>
          {["active", "paused", "cancelled"].map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
        </Select>
        <Field label="Due on or before" className="w-48"><Input type="date" value={state.due_before ?? ""} onChange={(e) => set({ due_before: e.target.value })} /></Field>
      </FilterBar>
      {error && <ErrorState message={error} onRetry={reload} />}
      <DataTable columns={columns} rows={data?.items} keyOf={(r) => r.id} loading={loading} onRowClick={(r) => router.push(`/workspace/subscriptions/${r.id}`)} emptyTitle="No subscriptions" />
      {data && <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} />}

      <ConfirmDialog
        open={runDialog}
        onClose={() => setRunDialog(false)}
        onConfirm={runBilling}
        title="Run recurring billing"
        message="Generates invoices for every subscription due on or before this date. The run is idempotent — subscriptions already billed for their cycle are skipped."
        confirmLabel="Run billing"
        loading={busy}
      >
        <Field label="As of date" className="mt-2"><Input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} /></Field>
      </ConfirmDialog>
    </div>
  );
}

export default function SubscriptionsPage() {
  return <Suspense><Inner /></Suspense>;
}
