"use client";
import { useRouter } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { invoices, type Invoice } from "@/lib/api";
import { useApi, useDebounce } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { formatCurrency, formatDate } from "@/lib/format";
import { Badge, DataTable, ErrorState, FilterBar, PageHeader, Pagination, SearchInput, Select, StatusBadge, type Column } from "@/components/ui";

const STATUSES = ["issued", "partially_paid", "paid", "overdue", "void"];

function Inner() {
  const { state, set, page, setPage } = useListState();
  const router = useRouter();
  const [q, setQ] = useState(state.q ?? "");
  const debounced = useDebounce(q);
  useEffect(() => { if (debounced !== (state.q ?? "")) set({ q: debounced }); }, [debounced]); // eslint-disable-line react-hooks/exhaustive-deps
  const { data, error, loading, reload } = useApi(
    () => invoices.list({ q: state.q, status: state.status, invoice_type: state.invoice_type, due_before: state.due_before, page, page_size: 25 }),
    [JSON.stringify(state), page],
  );

  const columns: Column<Invoice>[] = [
    { key: "number", header: "Invoice", render: (r) => <><span className="font-medium">{r.invoice_number}</span><span className="block text-xs text-zinc-500">{r.order_number ?? r.quote_number}</span></> },
    { key: "customer", header: "Customer", render: (r) => r.customer_name },
    { key: "type", header: "Type", render: (r) => <Badge tone={r.invoice_type === "recurring" ? "purple" : "neutral"}>{r.invoice_type.replaceAll("_", " ")}</Badge> },
    { key: "status", header: "Status", render: (r) => <><StatusBadge status={r.status} />{r.is_overdue && r.status !== "void" && <Badge tone="red" className="ml-1">{r.days_overdue} d late</Badge>}</> },
    { key: "amount", header: "Amount", align: "right", render: (r) => formatCurrency(r.amount, r.currency) },
    { key: "paid", header: "Paid", align: "right", render: (r) => formatCurrency(r.amount_paid, r.currency) },
    { key: "outstanding", header: "Outstanding", align: "right", render: (r) => <span className={Number(r.outstanding) > 0 ? "font-medium text-amber-700" : "text-zinc-500"}>{formatCurrency(r.outstanding, r.currency)}</span> },
    { key: "due", header: "Due", render: (r) => <span className={r.is_overdue ? "text-red-700" : ""}>{formatDate(r.due_date)}</span> },
    { key: "issued", header: "Issued", render: (r) => formatDate(r.issued_at) },
  ];

  return (
    <div className="space-y-4">
      <PageHeader title="Invoices" subtitle={data ? `${data.total.toLocaleString()} invoices` : undefined} />
      <FilterBar>
        <SearchInput value={q} onChange={setQ} placeholder="Invoice #, quote # or customer" className="w-72" />
        <Select value={state.status ?? ""} onChange={(e) => set({ status: e.target.value })} className="w-44" aria-label="Status">
          <option value="">All statuses</option>
          <option value="unpaid">Unpaid (any)</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
        </Select>
        <Select value={state.invoice_type ?? ""} onChange={(e) => set({ invoice_type: e.target.value })} className="w-44" aria-label="Type">
          <option value="">All types</option>
          <option value="one_time">One-time</option>
          <option value="recurring">Recurring</option>
        </Select>
      </FilterBar>
      {error && <ErrorState message={error} onRetry={reload} />}
      <DataTable columns={columns} rows={data?.items} keyOf={(r) => r.id} loading={loading} onRowClick={(r) => router.push(`/workspace/invoices/${r.id}`)} emptyTitle="No invoices match" />
      {data && <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} />}
    </div>
  );
}

export default function InvoicesPage() {
  return <Suspense><Inner /></Suspense>;
}
