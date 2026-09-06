"use client";
import Link from "next/link";
import { use, useState } from "react";
import { fulfillment, inventory, quotes, type FulfillmentPlan, type Warehouse } from "@/lib/api";
import { ApiError, errorMessage } from "@/lib/api/client";
import { useApi } from "@/lib/hooks/useApi";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatDate, formatDateTime } from "@/lib/format";
import { Badge, Button, Card, ConfirmDialog, ErrorState, Field, Input, LinkButton, Modal, PageHeader, Skeleton, StatusBadge, Select } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";

export default function FulfillmentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const quoteId = Number(use(params).id);
  const { can } = useAuth();
  const toast = useToast();
  const quote = useApi(() => quotes.get(quoteId), [quoteId]);
  const plan = useApi(() => fulfillment.plan(quoteId).catch((e) => { if (e instanceof ApiError && e.status === 404) return null; throw e; }), [quoteId]);
  const warehouses = useApi(() => inventory.warehouses({ page_size: 100 }), []);
  const [busy, setBusy] = useState<string | null>(null);
  const [shipDialog, setShipDialog] = useState(false);
  const [ship, setShip] = useState({ expected_date: "", tracking_reference: "", warehouse_id: "" });
  const [override, setOverride] = useState<{ quote_line_id: number; warehouse_id: string; quantity_fulfilled: number }[] | null>(null);
  const manage = can("fulfillment:manage");

  async function run(name: string, fn: () => Promise<FulfillmentPlan | unknown>, ok: string) {
    setBusy(name);
    try { await fn(); toast.success(ok); plan.reload(); quote.reload(); } catch (err) { toast.error(errorMessage(err)); plan.reload(); } finally { setBusy(null); setShipDialog(false); setOverride(null); }
  }

  if (quote.error) return <ErrorState message={quote.error} onRetry={quote.reload} />;
  if (!quote.data) return <Skeleton className="h-64" />;
  const q = quote.data;
  const p = plan.data;
  const acts = p?.available_actions ?? [];
  const physical = q.lines.filter((l) => !l.is_recurring && l.stock_available !== null);
  const whName = (id: number | null) => warehouses.data?.items.find((w) => w.id === id)?.name ?? (id ? `Warehouse ${id}` : "Backorder");

  return (
    <div className="space-y-5">
      <PageHeader breadcrumb={{ href: "/workspace/fulfillment", label: "Fulfillment" }} title={<span className="flex items-center gap-2">{q.order_number ?? q.quote_number} <StatusBadge status={q.fulfillment_status} /></span>} subtitle={<>{q.customer_name} · <Link href={`/workspace/quotations/${q.id}`} className="link">{q.quote_number}</Link>{q.promised_delivery_date && ` · promised ${formatDate(q.promised_delivery_date)}`}{q.expected_delivery_date && ` · expected ${formatDate(q.expected_delivery_date)}`}</>} actions={
        <>
          {q.status !== "confirmed" && <Badge tone="amber">Order not confirmed yet</Badge>}
          {q.status === "confirmed" && manage && (!p || acts.includes("resuggest")) && <Button onClick={() => run("suggest", () => fulfillment.suggest(quoteId), "Warehouse split suggested.")} loading={busy === "suggest"} data-testid="suggest-btn">{p ? "Re-plan" : "Suggest warehouse split"}</Button>}
          {acts.includes("override") && manage && <Button variant="secondary" onClick={() => setOverride(p!.splits.filter((s) => s.status !== "cancelled").map((s) => ({ quote_line_id: s.quote_line_id, warehouse_id: s.warehouse_id ? String(s.warehouse_id) : "", quantity_fulfilled: s.quantity_fulfilled })))}>Override</Button>}
          {acts.includes("confirm") && manage && <Button variant="success" onClick={() => run("confirm", () => fulfillment.confirm(quoteId), "Stock reserved for this order.")} loading={busy === "confirm"} data-testid="reserve-btn">Confirm & reserve stock</Button>}
          {acts.includes("ship") && manage && <Button onClick={() => setShipDialog(true)} data-testid="ship-btn">Ship reserved units</Button>}
          {acts.includes("consolidate") && manage && <Button variant="secondary" onClick={() => run("consolidate", () => fulfillment.consolidate(quoteId), "Backorders consolidated against current stock.")} loading={busy === "consolidate"} data-testid="consolidate-btn">Consolidate remaining backorder</Button>}
          {acts.includes("release") && manage && <Button variant="ghost" onClick={() => run("release", () => fulfillment.release(quoteId, "Released by operations"), "Reservation released.")} loading={busy === "release"}>Release stock</Button>}
          <LinkButton href={`/workspace/quotations/${quoteId}/billing`}>Billing →</LinkButton>
        </>
      } />

      {plan.error && <ErrorState message={plan.error} onRetry={plan.reload} />}
      {q.status === "confirmed" && !p && !plan.loading && (
        <Card title="Order lines">
          <p className="mb-3 text-sm text-zinc-600">No fulfillment plan yet. The engine allocates stock across warehouses (cheapest shipping first, fewest shipments) and backorders any shortfall.</p>
          <ul className="text-sm">{physical.map((l) => <li key={l.id} className="flex justify-between border-b border-zinc-100 py-1"><span>{l.description}</span><span>{l.quantity} needed · {l.stock_available} available network-wide</span></li>)}</ul>
          {physical.length === 0 && <p className="text-sm text-zinc-500">This order has only services, licences or subscriptions — nothing to ship.</p>}
        </Card>
      )}

      {p && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            {[["Plan status", <StatusBadge key="s" status={p.status} />], ["Shipments", p.total_shipments], ["Reserved", p.units_reserved], ["Shipped", p.units_shipped], ["Backordered", <span key="b" className={p.units_backordered ? "text-red-700" : ""}>{p.units_backordered}</span>]].map(([l, v]) => <div key={String(l)} className="card p-3"><p className="text-xs uppercase text-zinc-500">{l}</p><p className="text-lg font-semibold">{v}</p></div>)}
          </div>
          {p.backorder_summary.length > 0 && <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"><p className="font-medium">Backorders</p><ul className="list-inside list-disc">{p.backorder_summary.map((b) => <li key={b}>{b}</li>)}</ul></div>}
          <Card title="Allocations" padded={false}>
            <table className="w-full text-sm" data-testid="splits">
              <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500"><tr><th className="px-4 py-2">Line</th><th className="px-2 py-2">Warehouse</th><th className="px-2 py-2 text-right">Units</th><th className="px-2 py-2">Status</th><th className="px-2 py-2">Shipment</th><th className="px-2 py-2">Expected</th></tr></thead>
              <tbody className="divide-y divide-zinc-100">{p.splits.map((s) => <tr key={s.id} className={s.is_backorder ? "bg-red-50/40" : ""}><td className="px-4 py-2">{s.product_name}</td><td className="px-2 py-2">{s.warehouse_name ?? <span className="text-red-700">Backorder</span>}{s.warning && <span className="block text-xs text-amber-700">{s.warning}</span>}</td><td className="px-2 py-2 text-right">{s.quantity_fulfilled}</td><td className="px-2 py-2"><StatusBadge status={s.status} /></td><td className="px-2 py-2 text-xs">{p.shipments.find((sh) => sh.id === s.shipment_id)?.shipment_number ?? "—"}</td><td className="px-2 py-2 text-xs">{formatDate(s.expected_date)}</td></tr>)}</tbody>
            </table>
          </Card>
          <Card title="Shipments" padded={false}>
            {p.shipments.length === 0 ? <p className="p-4 text-sm text-zinc-500">Nothing shipped yet.</p> : (
              <table className="w-full text-sm">
                <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500"><tr><th className="px-4 py-2">Shipment</th><th className="px-2 py-2">Warehouse</th><th className="px-2 py-2 text-right">Units</th><th className="px-2 py-2">Status</th><th className="px-2 py-2">Shipped</th><th className="px-2 py-2">Expected / delivered</th><th className="px-2 py-2">Tracking</th><th /></tr></thead>
                <tbody className="divide-y divide-zinc-100">{p.shipments.map((sh) => <tr key={sh.id}><td className="px-4 py-2 font-medium">{sh.shipment_number}</td><td className="px-2 py-2">{sh.warehouse_name}</td><td className="px-2 py-2 text-right">{sh.units}</td><td className="px-2 py-2"><StatusBadge status={sh.status} /></td><td className="px-2 py-2 text-xs">{formatDateTime(sh.shipped_at)}</td><td className="px-2 py-2 text-xs">{sh.delivered_at ? formatDateTime(sh.delivered_at) : formatDate(sh.expected_date)}{sh.promised_date && sh.expected_date && sh.expected_date > sh.promised_date && !sh.delivered_at && <Badge tone="red" className="ml-1">late</Badge>}</td><td className="px-2 py-2 text-xs">{sh.tracking_reference ?? "—"}</td><td className="px-2 py-2 text-right">{sh.status === "shipped" && manage && <Button size="sm" variant="secondary" loading={busy === `deliver${sh.id}`} onClick={() => run(`deliver${sh.id}`, () => fulfillment.deliver(quoteId, sh.id), `${sh.shipment_number} marked delivered.`)}>Mark delivered</Button>}</td></tr>)}</tbody>
              </table>
            )}
          </Card>
        </>
      )}

      <ConfirmDialog open={shipDialog} onClose={() => setShipDialog(false)} title="Ship reserved units" confirmLabel="Ship" loading={busy === "ship"} onConfirm={() => run("ship", () => fulfillment.ship(quoteId, { expected_date: ship.expected_date || undefined, tracking_reference: ship.tracking_reference || undefined, warehouse_id: ship.warehouse_id ? Number(ship.warehouse_id) : undefined }), "Shipment created and stock consumed.")}>
        <div className="mt-2 grid gap-3">
          <Field label="Warehouse" hint="Leave blank to ship everything that is reserved."><Select value={ship.warehouse_id} onChange={(e) => setShip({ ...ship, warehouse_id: e.target.value })}><option value="">All reserved warehouses</option>{p?.splits.filter((s) => s.status === "reserved").map((s) => s.warehouse_id).filter((v, i, a) => v && a.indexOf(v) === i).map((id) => <option key={id!} value={id!}>{whName(id)}</option>)}</Select></Field>
          <Field label="Expected delivery date"><Input type="date" value={ship.expected_date} onChange={(e) => setShip({ ...ship, expected_date: e.target.value })} /></Field>
          <Field label="Tracking reference"><Input value={ship.tracking_reference} onChange={(e) => setShip({ ...ship, tracking_reference: e.target.value })} /></Field>
        </div>
      </ConfirmDialog>

      <Modal open={override !== null} onClose={() => setOverride(null)} title="Override allocations" size="lg" footer={<><Button variant="secondary" onClick={() => setOverride(null)}>Cancel</Button><Button loading={busy === "override"} onClick={() => override && run("override", () => fulfillment.override(quoteId, { allocations: override.map((a) => ({ quote_line_id: a.quote_line_id, warehouse_id: a.warehouse_id ? Number(a.warehouse_id) : null, quantity_fulfilled: a.quantity_fulfilled, is_backorder: !a.warehouse_id })) }), "Allocations overridden.")}>Save allocations</Button></>}>
        {override && (
          <div className="space-y-2">
            <p className="text-sm text-zinc-600">Each line must total exactly its ordered quantity. Leave the warehouse empty to backorder units.</p>
            {override.map((a, i) => (
              <div key={i} className="grid grid-cols-[1fr_180px_100px_auto] items-end gap-2 text-sm">
                <span>{q.lines.find((l) => l.id === a.quote_line_id)?.description} <span className="text-xs text-zinc-500">(needs {q.lines.find((l) => l.id === a.quote_line_id)?.quantity})</span></span>
                <Select value={a.warehouse_id} onChange={(e) => setOverride(override.map((x, j) => j === i ? { ...x, warehouse_id: e.target.value } : x))}><option value="">Backorder</option>{warehouses.data?.items.map((w: Warehouse) => <option key={w.id} value={w.id}>{w.name}</option>)}</Select>
                <Input type="number" min={1} value={a.quantity_fulfilled} onChange={(e) => setOverride(override.map((x, j) => j === i ? { ...x, quantity_fulfilled: Number(e.target.value) } : x))} />
                <Button variant="ghost" size="sm" onClick={() => setOverride(override.filter((_, j) => j !== i))}>✕</Button>
              </div>
            ))}
            <Button variant="secondary" size="sm" onClick={() => setOverride([...override, { quote_line_id: physical[0]?.id ?? 0, warehouse_id: "", quantity_fulfilled: 1 }])}>+ Add allocation</Button>
            <Select value="" onChange={(e) => e.target.value && setOverride([...override, { quote_line_id: Number(e.target.value), warehouse_id: "", quantity_fulfilled: 1 }])} className="w-64"><option value="">Add allocation for line…</option>{physical.map((l) => <option key={l.id} value={l.id}>{l.description}</option>)}</Select>
          </div>
        )}
      </Modal>
    </div>
  );
}
