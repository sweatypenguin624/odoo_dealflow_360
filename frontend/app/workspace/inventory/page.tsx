"use client";
import { Suspense, useEffect, useState } from "react";
import { inventory, type Movement, type Stock } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useApi, useDebounce } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatDateTime, titleCase } from "@/lib/format";
import { Badge, Button, DataTable, ErrorState, Field, FilterBar, FormError, Input, Modal, PageHeader, Pagination, SearchInput, Select, Tabs, Textarea, type Column } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { ProductSelect } from "@/components/domain/ProductSelect";

function Inner() {
  const { state, set, page, setPage } = useListState();
  const { can } = useAuth();
  const toast = useToast();
  const tab = state.tab ?? "stock";
  const [q, setQ] = useState(state.q ?? "");
  const debounced = useDebounce(q);
  useEffect(() => { if (debounced !== (state.q ?? "")) set({ q: debounced }); }, [debounced]); // eslint-disable-line react-hooks/exhaustive-deps
  const warehouses = useApi(() => inventory.warehouses({ page_size: 100 }), []);
  const stock = useApi(() => inventory.stock({ q: state.q, warehouse_id: state.warehouse_id, low_stock: state.low_stock, page, page_size: 25 }), [JSON.stringify(state), page], { enabled: tab === "stock" });
  const moves = useApi(() => inventory.movements({ warehouse_id: state.warehouse_id, movement_type: state.movement_type, page, page_size: 25 }), [JSON.stringify(state), page], { enabled: tab === "movements" });
  const [modal, setModal] = useState<"receipt" | "adjust" | null>(null);
  const [form, setForm] = useState({ warehouse_id: "", product_id: 0, quantity: "", quantity_on_hand: "", reorder_point: "", reason: "", note: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const manage = can("inventory:manage");

  async function submit() {
    setBusy(true); setError(null);
    try {
      if (modal === "receipt") await inventory.receive(Number(form.warehouse_id), { product_id: form.product_id, quantity: Number(form.quantity), note: form.note || undefined });
      else await inventory.adjust(Number(form.warehouse_id), { product_id: form.product_id, quantity_on_hand: Number(form.quantity_on_hand), reason: form.reason, reorder_point: form.reorder_point ? Number(form.reorder_point) : undefined });
      toast.success(modal === "receipt" ? "Stock received." : "Stock adjusted."); setModal(null); stock.reload();
    } catch (err) { setError(errorMessage(err)); } finally { setBusy(false); }
  }
  const openFor = (kind: "receipt" | "adjust", s?: Stock) => { setForm({ warehouse_id: s ? String(s.warehouse_id) : "", product_id: s?.product_id ?? 0, quantity: "", quantity_on_hand: s ? String(s.quantity_on_hand) : "", reorder_point: s ? String(s.reorder_point) : "", reason: "", note: "" }); setError(null); setModal(kind); };

  const cols: Column<Stock>[] = [
    { key: "product", header: "Product", render: (r) => <><span className="font-medium">{r.product_name}</span><span className="block text-xs text-zinc-500">{r.sku}</span></> },
    { key: "wh", header: "Warehouse", render: (r) => r.warehouse_name },
    { key: "onhand", header: "On hand", align: "right", render: (r) => r.quantity_on_hand },
    { key: "reserved", header: "Reserved", align: "right", render: (r) => r.quantity_reserved },
    { key: "available", header: "Available", align: "right", render: (r) => <span className={r.quantity_available <= 0 ? "font-medium text-red-700" : ""}>{r.quantity_available}</span> },
    { key: "reorder", header: "Reorder point", align: "right", render: (r) => <>{r.reorder_point}{r.needs_replenishment && <Badge tone="amber" className="ml-1">replenish</Badge>}</> },
    { key: "actions", header: "", render: (r) => manage ? <span className="flex justify-end gap-1"><Button size="sm" variant="secondary" onClick={() => openFor("receipt", r)}>Receive</Button><Button size="sm" variant="ghost" onClick={() => openFor("adjust", r)}>Adjust</Button></span> : null },
  ];
  const mcols: Column<Movement>[] = [
    { key: "when", header: "When", render: (r) => formatDateTime(r.created_at) },
    { key: "type", header: "Type", render: (r) => <Badge tone={r.movement_type === "receipt" ? "green" : r.movement_type === "consumption" ? "purple" : r.movement_type === "reservation" ? "amber" : "neutral"}>{titleCase(r.movement_type)}</Badge> },
    { key: "product", header: "Product", render: (r) => r.product_name },
    { key: "wh", header: "Warehouse", render: (r) => r.warehouse_name },
    { key: "qty", header: "Qty", align: "right", render: (r) => r.quantity },
    { key: "after", header: "On hand / reserved after", align: "right", render: (r) => `${r.on_hand_after} / ${r.reserved_after}` },
    { key: "ref", header: "Reference", render: (r) => r.reference_type ? `${r.reference_type} #${r.reference_id ?? ""}` : r.note ?? "—" },
  ];
  return (
    <div className="space-y-4">
      <PageHeader title="Inventory" subtitle="On-hand, reserved and available stock across warehouses." actions={manage && <><Button onClick={() => openFor("receipt")}>+ Receive stock</Button><Button variant="secondary" onClick={() => openFor("adjust")}>Adjust count</Button></>} />
      <Tabs tabs={[{ key: "stock", label: "Stock levels" }, { key: "movements", label: "Movements" }]} active={tab} onChange={(t) => set({ tab: t })} />
      <FilterBar>
        {tab === "stock" && <SearchInput value={q} onChange={setQ} placeholder="Product name or SKU" className="w-72" />}
        <Select value={state.warehouse_id ?? ""} onChange={(e) => set({ warehouse_id: e.target.value })} className="w-52" aria-label="Warehouse"><option value="">All warehouses</option>{warehouses.data?.items.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</Select>
        {tab === "stock" && <Select value={state.low_stock ?? ""} onChange={(e) => set({ low_stock: e.target.value })} className="w-44" aria-label="Low stock"><option value="">All levels</option><option value="true">Below reorder point</option></Select>}
        {tab === "movements" && <Select value={state.movement_type ?? ""} onChange={(e) => set({ movement_type: e.target.value })} className="w-44" aria-label="Type"><option value="">All types</option>{["receipt", "adjustment", "reservation", "release", "consumption"].map((t) => <option key={t} value={t}>{t}</option>)}</Select>}
      </FilterBar>
      {tab === "stock" && <>{stock.error && <ErrorState message={stock.error} onRetry={stock.reload} />}<DataTable columns={cols} rows={stock.data?.items} keyOf={(r) => r.id} loading={stock.loading} emptyTitle="No stock records" />{stock.data && <Pagination page={stock.data.page} totalPages={stock.data.total_pages} total={stock.data.total} pageSize={stock.data.page_size} onChange={setPage} />}</>}
      {tab === "movements" && <>{moves.error && <ErrorState message={moves.error} onRetry={moves.reload} />}<DataTable columns={mcols} rows={moves.data?.items} keyOf={(r) => r.id} loading={moves.loading} emptyTitle="No movements" />{moves.data && <Pagination page={moves.data.page} totalPages={moves.data.total_pages} total={moves.data.total} pageSize={moves.data.page_size} onChange={setPage} />}</>}
      <Modal open={modal !== null} onClose={() => setModal(null)} title={modal === "receipt" ? "Receive stock" : "Adjust stock count"} footer={<><Button variant="secondary" onClick={() => setModal(null)}>Cancel</Button><Button onClick={submit} loading={busy} disabled={!form.warehouse_id || !form.product_id}>{modal === "receipt" ? "Receive" : "Adjust"}</Button></>}>
        <div className="space-y-3">
          <FormError message={error} />
          <Field label="Warehouse" required><Select value={form.warehouse_id} onChange={(e) => setForm({ ...form, warehouse_id: e.target.value })}><option value="">Select…</option>{warehouses.data?.items.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</Select></Field>
          <Field label="Product" required><ProductSelect value={form.product_id} onChange={(id) => setForm({ ...form, product_id: id })} stockedOnly /></Field>
          {modal === "receipt" ? <><Field label="Quantity received" required><Input type="number" min={1} value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></Field><Field label="Note (PO number, supplier…)"><Input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></Field></>
            : <><Field label="New on-hand count" required><Input type="number" min={0} value={form.quantity_on_hand} onChange={(e) => setForm({ ...form, quantity_on_hand: e.target.value })} /></Field><Field label="Reorder point"><Input type="number" min={0} value={form.reorder_point} onChange={(e) => setForm({ ...form, reorder_point: e.target.value })} /></Field><Field label="Reason" required><Textarea rows={2} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} /></Field></>}
        </div>
      </Modal>
    </div>
  );
}
export default function InventoryPage() { return <Suspense><Inner /></Suspense>; }
