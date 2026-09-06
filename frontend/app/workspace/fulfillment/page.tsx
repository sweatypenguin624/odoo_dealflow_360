"use client";
import { useRouter } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { fulfillment, type Backorder, type FulfillmentListItem } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useApi, useDebounce } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatCurrency, formatDate, formatDateTime } from "@/lib/format";
import { Badge, Button, DataTable, ErrorState, FilterBar, PageHeader, Pagination, SearchInput, Select, StatusBadge, Tabs, type Column } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";

function Inner() {
  const { state, set, page, setPage } = useListState();
  const router = useRouter();
  const { can } = useAuth();
  const toast = useToast();
  const tab = state.tab ?? "orders";
  const [q, setQ] = useState(state.q ?? "");
  const debounced = useDebounce(q);
  useEffect(() => { if (debounced !== (state.q ?? "")) set({ q: debounced }); }, [debounced]); // eslint-disable-line react-hooks/exhaustive-deps
  const orders = useApi(() => fulfillment.list({ q: state.q, fulfillment_status: state.fulfillment_status, only_backorders: state.only_backorders, page, page_size: 25 }), [JSON.stringify(state), page], { enabled: tab === "orders" });
  const backorders = useApi(() => fulfillment.backorders({ page, page_size: 25 }), [page, tab], { enabled: tab === "backorders" });
  const [busy, setBusy] = useState<number | null>(null);
  async function consolidate(quoteId: number) {
    setBusy(quoteId);
    try { const r = await fulfillment.consolidate(quoteId); toast.success(`${r.units_reserved} unit(s) reserved from incoming stock; ${r.units_still_backordered} still backordered.`); backorders.reload(); } catch (err) { toast.error(errorMessage(err)); } finally { setBusy(null); }
  }
  const cols: Column<FulfillmentListItem>[] = [
    { key: "order", header: "Order", render: (r) => <><span className="font-medium">{r.order_number ?? r.quote_number}</span><span className="block text-xs text-zinc-500">{r.quote_number}</span></> },
    { key: "customer", header: "Customer", render: (r) => r.customer_name },
    { key: "status", header: "Fulfillment", render: (r) => <><StatusBadge status={r.fulfillment_status} />{r.units_backordered > 0 && <Badge tone="red" className="ml-1">{r.units_backordered} backordered</Badge>}</> },
    { key: "plan", header: "Plan", render: (r) => r.plan_status ? <StatusBadge status={r.plan_status} /> : <span className="text-zinc-400">not planned</span> },
    { key: "ship", header: "Shipments", align: "right", render: (r) => r.shipment_count },
    { key: "promised", header: "Promised", render: (r) => <span className={r.promised_delivery_date && new Date(r.promised_delivery_date) < new Date() && r.fulfillment_status !== "delivered" ? "text-red-700" : ""}>{formatDate(r.promised_delivery_date)}</span> },
    { key: "total", header: "Value", align: "right", render: (r) => formatCurrency(r.total) },
    { key: "confirmed", header: "Confirmed", render: (r) => formatDateTime(r.confirmed_at) },
  ];
  const bcols: Column<Backorder>[] = [
    { key: "order", header: "Order", render: (r) => <><span className="font-medium">{r.order_number}</span><span className="block text-xs text-zinc-500">{r.customer_name}</span></> },
    { key: "product", header: "Product", render: (r) => <>{r.product_name}<span className="block text-xs text-zinc-500">{r.sku}</span></> },
    { key: "qty", header: "Backordered", align: "right", render: (r) => r.quantity },
    { key: "avail", header: "Available now", align: "right", render: (r) => <span className={r.available_now > 0 ? "font-medium text-emerald-700" : "text-zinc-400"}>{r.available_now}</span> },
    { key: "promised", header: "Promised", render: (r) => formatDate(r.promised_delivery_date) },
    { key: "action", header: "", render: (r) => can("fulfillment:manage") ? <Button size="sm" disabled={!r.can_consolidate} loading={busy === r.quote_id} onClick={(e) => { e.stopPropagation(); consolidate(r.quote_id); }}>Consolidate</Button> : null },
  ];
  return (
    <div className="space-y-4">
      <PageHeader title="Fulfillment" subtitle="Confirmed orders, warehouse allocation and backorders." />
      <Tabs tabs={[{ key: "orders", label: "Orders" }, { key: "backorders", label: "Open backorders" }]} active={tab} onChange={(t) => set({ tab: t })} />
      {tab === "orders" && (
        <>
          <FilterBar>
            <SearchInput value={q} onChange={setQ} placeholder="Order #, quote # or customer" className="w-72" />
            <Select value={state.fulfillment_status ?? ""} onChange={(e) => set({ fulfillment_status: e.target.value })} className="w-44" aria-label="Status"><option value="">All statuses</option>{["not_started", "planned", "reserved", "partially_shipped", "shipped", "delivered"].map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}</Select>
            <Select value={state.only_backorders ?? ""} onChange={(e) => set({ only_backorders: e.target.value })} className="w-44" aria-label="Backorders"><option value="">All orders</option><option value="true">With backorders</option></Select>
          </FilterBar>
          {orders.error && <ErrorState message={orders.error} onRetry={orders.reload} />}
          <DataTable columns={cols} rows={orders.data?.items} keyOf={(r) => r.quote_id} loading={orders.loading} onRowClick={(r) => router.push(`/workspace/quotations/${r.quote_id}/fulfillment`)} emptyTitle="No orders to fulfil" />
          {orders.data && <Pagination page={orders.data.page} totalPages={orders.data.total_pages} total={orders.data.total} pageSize={orders.data.page_size} onChange={setPage} />}
        </>
      )}
      {tab === "backorders" && (
        <>
          {backorders.error && <ErrorState message={backorders.error} onRetry={backorders.reload} />}
          <DataTable columns={bcols} rows={backorders.data?.items} keyOf={(r) => r.split_id} loading={backorders.loading} onRowClick={(r) => router.push(`/workspace/quotations/${r.quote_id}/fulfillment`)} emptyTitle="No open backorders" emptyDescription="Every confirmed order is fully allocated." />
          {backorders.data && <Pagination page={backorders.data.page} totalPages={backorders.data.total_pages} total={backorders.data.total} pageSize={backorders.data.page_size} onChange={setPage} />}
        </>
      )}
    </div>
  );
}
export default function FulfillmentPage() { return <Suspense><Inner /></Suspense>; }
