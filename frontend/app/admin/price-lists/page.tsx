"use client";
import { Suspense, useState } from "react";
import { catalog, pricing, type PriceList } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useApi } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatCurrency, formatDate } from "@/lib/format";
import { Badge, Button, DataTable, ErrorState, Field, FormError, Input, Modal, PageHeader, Pagination, Select, Skeleton, type Column } from "@/components/ui";
import { ProductSelect } from "@/components/domain/ProductSelect";
import { useToast } from "@/components/ui/Toast";

function ItemsModal({ listId, onClose }: { listId: number; onClose: () => void }) {
  const toast = useToast();
  const { data, error, loading, reload } = useApi(() => pricing.priceList(listId), [listId]);
  const [item, setItem] = useState({ product_id: 0, min_quantity: "1", unit_price: "" });
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function add() {
    setBusy(true);
    setFormError(null);
    try {
      await pricing.addItem(listId, { product_id: item.product_id, min_quantity: Number(item.min_quantity), unit_price: Number(item.unit_price) });
      setItem({ product_id: 0, min_quantity: "1", unit_price: "" });
      reload();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(itemId: number) {
    try {
      await pricing.deleteItem(listId, itemId);
      toast.success("Item removed.");
      reload();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <Modal open onClose={onClose} title={data ? `Prices in “${data.name}”` : "Price list"} size="lg">
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data && <Skeleton className="h-40" />}
      {data && (
        <div className="space-y-4">
          <div className="overflow-x-auto rounded-md border border-zinc-200">
            <table className="w-full text-sm">
              <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500">
                <tr><th className="px-3 py-2">Product</th><th className="px-2 py-2 text-right">Min qty</th><th className="px-2 py-2 text-right">Unit price</th><th /></tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {(data.items ?? []).length === 0 && <tr><td colSpan={4} className="px-3 py-4 text-center text-zinc-500">No prices yet — quotes fall back to the product list price.</td></tr>}
                {(data.items ?? []).map((i) => (
                  <tr key={i.id}>
                    <td className="px-3 py-2">{i.product_name}<span className="block text-xs text-zinc-500">{i.product_sku}</span></td>
                    <td className="px-2 py-2 text-right">{i.min_quantity}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{formatCurrency(i.unit_price, data.currency)}</td>
                    <td className="px-2 py-2 text-right"><Button size="sm" variant="ghost" onClick={() => remove(i.id)}>Remove</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="rounded-md border border-blue-200 bg-blue-50/50 p-3">
            <p className="mb-2 text-sm font-medium text-zinc-800">Add a price</p>
            <FormError message={formError} />
            <div className="grid gap-2 sm:grid-cols-[1fr_110px_140px_auto] sm:items-end">
              <Field label="Product"><ProductSelect value={item.product_id} onChange={(id) => setItem({ ...item, product_id: id })} /></Field>
              <Field label="Min qty"><Input type="number" min={1} value={item.min_quantity} onChange={(e) => setItem({ ...item, min_quantity: e.target.value })} /></Field>
              <Field label="Unit price"><Input type="number" min={0} step="0.01" value={item.unit_price} onChange={(e) => setItem({ ...item, unit_price: e.target.value })} /></Field>
              <Button onClick={add} loading={busy} disabled={!item.product_id || item.unit_price === ""}>Add</Button>
            </div>
            <p className="mt-1 text-xs text-zinc-500">Quantity breaks: add several rows for the same product with different minimum quantities.</p>
          </div>
        </div>
      )}
    </Modal>
  );
}

function Inner() {
  const { page, setPage } = useListState();
  const { can } = useAuth();
  const toast = useToast();
  const tiers = useApi(() => catalog.tiers(), []);
  const { data, error, loading, reload } = useApi(() => pricing.priceLists({ page, page_size: 25 }), [page]);
  const manage = can("pricing:manage");
  const [editing, setEditing] = useState<PriceList | null>(null);
  const [open, setOpen] = useState(false);
  const [itemsFor, setItemsFor] = useState<number | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function openForm(row: PriceList | null) {
    setEditing(row);
    setForm(row
      ? { name: row.name, currency: row.currency, tier_id: row.tier_id ? String(row.tier_id) : "", valid_from: row.valid_from ?? "", valid_to: row.valid_to ?? "", priority: String(row.priority), is_active: String(row.is_active) }
      : { name: "", currency: "USD", tier_id: "", valid_from: "", valid_to: "", priority: "0", is_active: "true" });
    setFormError(null);
    setOpen(true);
  }

  async function save() {
    setBusy(true);
    setFormError(null);
    const body: Record<string, unknown> = {
      name: form.name,
      currency: form.currency,
      priority: Number(form.priority || 0),
      is_active: form.is_active === "true",
    };
    if (form.tier_id) body.tier_id = Number(form.tier_id);
    else if (editing) body.clear_tier = true;
    if (form.valid_from) body.valid_from = form.valid_from;
    if (form.valid_to) body.valid_to = form.valid_to;
    try {
      if (editing) await pricing.updatePriceList(editing.id, body);
      else await pricing.createPriceList({ ...body, items: [] });
      toast.success(editing ? "Price list updated." : "Price list created.");
      setOpen(false);
      reload();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<PriceList>[] = [
    { key: "name", header: "Price list", render: (r) => <><span className="font-medium">{r.name}</span><span className="block text-xs text-zinc-500">{r.currency}</span></> },
    { key: "tier", header: "Tier", render: (r) => r.tier_name ? <Badge tone="blue">{r.tier_name}</Badge> : <span className="text-zinc-400">All tiers</span> },
    { key: "items", header: "Prices", align: "right", render: (r) => r.item_count },
    { key: "validity", header: "Valid", render: (r) => <span className="text-xs">{r.valid_from || r.valid_to ? `${formatDate(r.valid_from)} – ${formatDate(r.valid_to)}` : "Always"}</span> },
    { key: "priority", header: "Priority", align: "right", render: (r) => r.priority },
    { key: "status", header: "Status", render: (r) => <Badge tone={r.is_active ? "green" : "slate"}>{r.is_active ? "Active" : "Inactive"}</Badge> },
    { key: "actions", header: "", render: (r) => <span className="flex justify-end gap-1"><Button size="sm" variant="secondary" onClick={(e) => { e.stopPropagation(); setItemsFor(r.id); }}>Prices</Button>{manage && <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); openForm(r); }}>Edit</Button>}</span> },
  ];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Price Lists"
        subtitle="Negotiated price books. The highest-priority active list that matches the customer's tier wins; otherwise the product list price applies."
        actions={manage && <Button onClick={() => openForm(null)}>+ New price list</Button>}
      />
      {error && <ErrorState message={error} onRetry={reload} />}
      <DataTable columns={columns} rows={data?.items} keyOf={(r) => r.id} loading={loading} emptyTitle="No price lists" />
      {data && <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} />}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editing ? "Edit price list" : "New price list"}
        footer={<><Button variant="secondary" onClick={() => setOpen(false)} disabled={busy}>Cancel</Button><Button onClick={save} loading={busy} disabled={!form.name}>{editing ? "Save changes" : "Create"}</Button></>}
      >
        <div className="space-y-3">
          <FormError message={formError} />
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Name" required><Input value={form.name ?? ""} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Currency" required><Input value={form.currency ?? ""} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} maxLength={3} /></Field>
            <Field label="Tier" hint="Leave blank to apply to every tier.">
              <Select value={form.tier_id ?? ""} onChange={(e) => setForm({ ...form, tier_id: e.target.value })}>
                <option value="">All tiers</option>
                {tiers.data?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </Select>
            </Field>
            <Field label="Priority" hint="Higher wins when several lists match."><Input type="number" value={form.priority ?? "0"} onChange={(e) => setForm({ ...form, priority: e.target.value })} /></Field>
            <Field label="Valid from"><Input type="date" value={form.valid_from ?? ""} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} /></Field>
            <Field label="Valid to"><Input type="date" value={form.valid_to ?? ""} onChange={(e) => setForm({ ...form, valid_to: e.target.value })} /></Field>
            <label className="flex items-center gap-2 text-sm text-zinc-700 sm:col-span-2">
              <input type="checkbox" className="h-4 w-4 rounded border-zinc-300 text-blue-600 focus:ring-blue-500" checked={form.is_active === "true"} onChange={(e) => setForm({ ...form, is_active: String(e.target.checked) })} />
              Active
            </label>
          </div>
          {!editing && <p className="text-xs text-zinc-500">Create the list first, then add prices to it from the list view.</p>}
        </div>
      </Modal>

      {itemsFor !== null && <ItemsModal listId={itemsFor} onClose={() => { setItemsFor(null); reload(); }} />}
    </div>
  );
}

export default function PriceListsPage() {
  return <Suspense><Inner /></Suspense>;
}
