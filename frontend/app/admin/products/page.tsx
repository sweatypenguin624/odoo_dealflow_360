"use client";
import { Suspense, useEffect, useState } from "react";
import { catalog, type Product } from "@/lib/api";
import { useApi, useDebounce } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatCurrency, formatPct } from "@/lib/format";
import { Badge, Button, FilterBar, Pagination, SearchInput, Select, type Column } from "@/components/ui";
import { CrudPage, clean, type FormField } from "@/components/domain/CrudPage";
import { useToast } from "@/components/ui/Toast";
import { errorMessage } from "@/lib/api/client";

function Inner() {
  const { state, set, page, setPage } = useListState();
  const { can } = useAuth();
  const toast = useToast();
  const [q, setQ] = useState(state.q ?? "");
  const debounced = useDebounce(q);
  useEffect(() => { if (debounced !== (state.q ?? "")) set({ q: debounced }); }, [debounced]); // eslint-disable-line react-hooks/exhaustive-deps
  const categories = useApi(() => catalog.categories({ page_size: 100 }), []);
  const { data, error, loading, reload } = useApi(
    () => catalog.products({ q: state.q, category_id: state.category_id, product_type: state.product_type, is_active: state.is_active, page, page_size: 25 }),
    [JSON.stringify(state), page],
  );
  const manage = can("catalog:manage");

  async function toggleArchive(p: Product) {
    try {
      await (p.is_archived || !p.is_active ? catalog.restoreProduct(p.id) : catalog.archiveProduct(p.id));
      toast.success(p.is_active ? "Product archived." : "Product restored.");
      reload();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const columns: Column<Product>[] = [
    { key: "name", header: "Product", render: (r) => <><span className="font-medium">{r.name}</span><span className="block text-xs text-zinc-500">{r.sku} · {r.category_name}</span></> },
    { key: "type", header: "Type", render: (r) => <Badge tone={r.product_type === "recurring" ? "purple" : r.product_type === "both" ? "blue" : "neutral"}>{r.product_type.replaceAll("_", " ")}</Badge> },
    { key: "price", header: "Price", align: "right", render: (r) => formatCurrency(r.price) },
    { key: "cost", header: "Cost", align: "right", render: (r) => formatCurrency(r.cost) },
    { key: "margin", header: "Margin", align: "right", render: (r) => formatPct(r.unit_margin_pct, 0) },
    { key: "stocked", header: "Stocked", render: (r) => r.is_stocked ? "Yes" : "No" },
    { key: "status", header: "Status", render: (r) => <Badge tone={r.is_active ? "green" : "slate"}>{r.is_active ? "Active" : "Archived"}</Badge> },
    { key: "actions", header: "", render: (r) => manage ? <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); toggleArchive(r); }}>{r.is_active ? "Archive" : "Restore"}</Button> : null },
  ];

  const catOptions = (categories.data?.items ?? []).map((c) => ({ value: c.id, label: c.name }));
  const fields: FormField<Product>[] = [
    { name: "name", label: "Name", type: "text", required: true },
    { name: "sku", label: "SKU", type: "text", required: true },
    { name: "category_id", label: "Category", type: "select", required: true, options: catOptions },
    { name: "product_type", label: "Type", type: "select", required: true, options: [{ value: "one_time", label: "One-time" }, { value: "recurring", label: "Recurring" }, { value: "both", label: "Both" }] },
    { name: "price", label: "List price", type: "number", required: true, step: "0.01", min: 0 },
    { name: "cost", label: "Unit cost", type: "number", required: true, step: "0.01", min: 0 },
    { name: "unit", label: "Unit", type: "text", hint: "e.g. unit, seat, hour" },
    { name: "tax_rate_pct", label: "Tax rate %", type: "number", step: "0.1", min: 0, max: 100 },
    { name: "is_stocked", label: "Track stock for this product", type: "checkbox" },
    { name: "is_active", label: "Active", type: "checkbox" },
    { name: "description", label: "Description", type: "textarea", full: true },
  ];

  return (
    <CrudPage
      config={{
        title: "Products",
        subtitle: "Catalog items, pricing basis and stock behaviour.",
        addLabel: "+ New product",
        columns,
        fields,
        keyOf: (r) => r.id,
        canManage: manage,
        toForm: (r) => ({
          name: r.name, sku: r.sku ?? "", category_id: String(r.category_id), product_type: r.product_type,
          price: String(r.price), cost: String(r.cost), unit: r.unit, tax_rate_pct: String(r.tax_rate_pct),
          is_stocked: String(r.is_stocked), is_active: String(r.is_active), description: r.description ?? "",
        }),
        toBody: (f) => clean({
          name: f.name, sku: f.sku, category_id: Number(f.category_id), product_type: f.product_type,
          price: Number(f.price), cost: Number(f.cost), unit: f.unit,
          tax_rate_pct: f.tax_rate_pct === "" ? undefined : Number(f.tax_rate_pct),
          is_stocked: f.is_stocked === "true", is_active: f.is_active === "true", description: f.description,
        }),
        create: (body) => catalog.createProduct(body),
        update: (row, body) => catalog.updateProduct(row.id, body),
      }}
      defaults={{ product_type: "one_time", unit: "unit", is_stocked: "true", is_active: "true", tax_rate_pct: "0" }}
      rows={data?.items}
      loading={loading}
      error={error}
      reload={reload}
      filters={
        <FilterBar>
          <SearchInput value={q} onChange={setQ} placeholder="Name or SKU" className="w-72" />
          <Select value={state.category_id ?? ""} onChange={(e) => set({ category_id: e.target.value })} className="w-48" aria-label="Category">
            <option value="">All categories</option>
            {catOptions.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </Select>
          <Select value={state.product_type ?? ""} onChange={(e) => set({ product_type: e.target.value })} className="w-40" aria-label="Type">
            <option value="">All types</option>
            <option value="one_time">One-time</option>
            <option value="recurring">Recurring</option>
            <option value="both">Both</option>
          </Select>
          <Select value={state.is_active ?? ""} onChange={(e) => set({ is_active: e.target.value })} className="w-40" aria-label="Status">
            <option value="">All</option>
            <option value="true">Active</option>
            <option value="false">Archived</option>
          </Select>
        </FilterBar>
      }
      pagination={data ? <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} /> : null}
    />
  );
}

export default function AdminProductsPage() {
  return <Suspense><Inner /></Suspense>;
}
