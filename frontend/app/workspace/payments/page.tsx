"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { invoices, type Payment } from "@/lib/api";
import { useApi, useDebounce } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { formatCurrency, formatDateTime, titleCase } from "@/lib/format";
import { DataTable, ErrorState, FilterBar, PageHeader, Pagination, SearchInput, Select, StatusBadge, type Column } from "@/components/ui";

function Inner() {
  const { state, set, page, setPage } = useListState();
  const router = useRouter();
  const [q, setQ] = useState(state.q ?? "");
  const debounced = useDebounce(q);
  useEffect(() => { if (debounced !== (state.q ?? "")) set({ q: debounced }); }, [debounced]); // eslint-disable-line react-hooks/exhaustive-deps
  const { data, error, loading, reload } = useApi(() => invoices.payments({ q: state.q, direction: state.direction, page, page_size: 25 }), [JSON.stringify(state), page]);

  const columns: Column<Payment>[] = [
    { key: "number", header: "Payment", render: (r) => <><span className="font-medium">{r.payment_number ?? `#${r.id}`}</span><span className="block text-xs text-zinc-500">{r.reference ?? ""}</span></> },
    { key: "invoice", header: "Invoice", render: (r) => <Link href={`/workspace/invoices/${r.invoice_id}`} className="link" onClick={(e) => e.stopPropagation()}>{r.invoice_number ?? `#${r.invoice_id}`}</Link> },
    { key: "customer", header: "Customer", render: (r) => r.customer_name ?? "—" },
    { key: "direction", header: "Direction", render: (r) => <StatusBadge status={r.direction} /> },
    { key: "method", header: "Method", render: (r) => titleCase(r.method) },
    { key: "amount", header: "Amount", align: "right", render: (r) => <span className={r.direction === "refund" ? "text-amber-700" : ""}>{formatCurrency(r.amount)}</span> },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
    { key: "paid", header: "Recorded", render: (r) => <>{formatDateTime(r.paid_at)}<span className="block text-xs text-zinc-400">{r.recorded_by}</span></> },
  ];

  return (
    <div className="space-y-4">
      <PageHeader title="Payments" subtitle={data ? `${data.total.toLocaleString()} payments and refunds` : undefined} />
      <FilterBar>
        <SearchInput value={q} onChange={setQ} placeholder="Invoice #, payment # or reference" className="w-72" />
        <Select value={state.direction ?? ""} onChange={(e) => set({ direction: e.target.value })} className="w-40" aria-label="Direction">
          <option value="">All</option>
          <option value="payment">Payments</option>
          <option value="refund">Refunds</option>
        </Select>
      </FilterBar>
      {error && <ErrorState message={error} onRetry={reload} />}
      <DataTable columns={columns} rows={data?.items} keyOf={(r) => r.id} loading={loading} onRowClick={(r) => router.push(`/workspace/invoices/${r.invoice_id}`)} emptyTitle="No payments recorded" />
      {data && <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} />}
    </div>
  );
}

export default function PaymentsPage() {
  return <Suspense><Inner /></Suspense>;
}
