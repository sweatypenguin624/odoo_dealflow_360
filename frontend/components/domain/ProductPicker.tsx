"use client";
import { useEffect, useState } from "react";
import { catalog, type Product, type ProductPricing } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useDebounce } from "@/lib/hooks/useApi";
import { formatCurrency, formatPct } from "@/lib/format";
import { Button, Field, FormError, Input, Select } from "@/components/ui";

export interface NewLine {
  product_id: number;
  quantity: number;
  discount_pct: number;
  variant_id?: number | null;
  subscription_plan_id?: number | null;
}

/** Debounced server-side product search + quantity/discount entry. Never loads the whole catalog. */
export function ProductPicker({ customerId, onAdd, busy }: { customerId: number; onAdd: (line: NewLine) => Promise<void>; busy?: boolean }) {
  const [q, setQ] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [categories, setCategories] = useState<{ id: number; name: string }[]>([]);
  const [results, setResults] = useState<Product[]>([]);
  const [selected, setSelected] = useState<Product | null>(null);
  const [pricing, setPricing] = useState<ProductPricing | null>(null);
  const [plans, setPlans] = useState<{ id: number; name: string; interval: string; price_per_interval: number }[]>([]);
  const [variants, setVariants] = useState<{ id: number; name: string; sku: string }[]>([]);
  const [variantId, setVariantId] = useState("");
  const [planId, setPlanId] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [discount, setDiscount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const debounced = useDebounce(q, 300);

  useEffect(() => {
    catalog.categories({ page_size: 100 }).then((p) => setCategories(p.items)).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!debounced.trim() && !categoryId) return;
    let cancel = false;
    catalog.products({ q: debounced, category_id: categoryId || undefined, page_size: 8, is_active: true })
      .then((p) => { if (!cancel) setResults(p.items); })
      .catch(() => undefined);
    return () => { cancel = true; };
  }, [debounced, categoryId]);

  useEffect(() => {
    if (!selected) return;
    let cancel = false;
    catalog.pricing(selected.id, { customer_id: customerId, quantity, variant_id: variantId || undefined })
      .then((p) => { if (!cancel) setPricing(p); })
      .catch(() => undefined);
    catalog.product(selected.id)
      .then((d) => { if (!cancel) { setPlans(d.subscription_plans.filter((p) => p.is_active)); setVariants(d.variants.filter((v) => v.is_active)); } })
      .catch(() => undefined);
    return () => { cancel = true; };
  }, [selected, customerId, quantity, variantId]);

  async function add() {
    if (!selected) return;
    setError(null);
    try {
      await onAdd({
        product_id: selected.id,
        quantity,
        discount_pct: discount,
        variant_id: variantId ? Number(variantId) : null,
        subscription_plan_id: planId ? Number(planId) : null,
      });
      setSelected(null); setQ(""); setQuantity(1); setDiscount(0); setVariantId(""); setPlanId("");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  // Derived rather than reset in an effect, so nothing from a previous
  // search or selection is shown after it is cleared.
  const visible = debounced.trim() || categoryId ? results : [];
  // Guard against a flash of the previous product's price while the new
  // one is still in flight.
  const shownPricing = selected && pricing?.product_id === selected.id ? pricing : null;
  const shownPlans = selected ? plans : [];
  const shownVariants = selected ? variants : [];
  const overLimit = !!shownPricing && discount > Number(shownPricing.allowed_discount_pct);

  return (
    <div className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-[1fr_200px]">
        <Input type="search" placeholder="Search products by name or SKU…" value={q} onChange={(e) => { setQ(e.target.value); setSelected(null); }} aria-label="Product search" />
        <Select value={categoryId} onChange={(e) => setCategoryId(e.target.value)} aria-label="Category filter">
          <option value="">All categories</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
      </div>

      {!selected && visible.length > 0 && (
        <ul className="max-h-60 divide-y divide-zinc-100 overflow-y-auto rounded-md border border-zinc-200">
          {visible.map((p) => (
            <li key={p.id}>
              <button type="button" onClick={() => { setSelected(p); setPlans([]); setVariants([]); setVariantId(""); setPlanId(""); }} className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-blue-50">
                <span><span className="font-medium">{p.name}</span> <span className="text-xs text-zinc-500">{p.sku} · {p.category_name}</span></span>
                <span className="tabular-nums text-zinc-700">{formatCurrency(p.price)}{p.product_type !== "one_time" ? " / period" : ""}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {selected && (
        <div className="rounded-md border border-blue-200 bg-blue-50/50 p-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="font-medium text-zinc-900">{selected.name} <span className="text-xs text-zinc-500">{selected.sku}</span></p>
              {shownPricing && (
                <p className="text-xs text-zinc-600">
                  {formatCurrency(shownPricing.unit_price)} each ({shownPricing.price_source}) · allowed discount {formatPct(shownPricing.allowed_discount_pct, 0)} ({shownPricing.discount_limit_source})
                  {selected.is_stocked ? ` · ${shownPricing.stock_available} in stock` : " · not stocked"}
                </p>
              )}
            </div>
            <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>Change</Button>
          </div>

          <div className="mt-2 grid gap-2 sm:grid-cols-4">
            <Field label="Quantity"><Input type="number" min={1} value={quantity} onChange={(e) => setQuantity(Math.max(1, Number(e.target.value)))} /></Field>
            <Field label="Discount %"><Input type="number" min={0} max={100} step={0.5} value={discount} onChange={(e) => setDiscount(Number(e.target.value))} invalid={overLimit} /></Field>
            {shownVariants.length > 0 && (
              <Field label="Variant">
                <Select value={variantId} onChange={(e) => setVariantId(e.target.value)}>
                  <option value="">Base product</option>
                  {shownVariants.map((v) => <option key={v.id} value={v.id}>{v.name} ({v.sku})</option>)}
                </Select>
              </Field>
            )}
            {shownPlans.length > 0 && (
              <Field label="Billing">
                <Select value={planId} onChange={(e) => setPlanId(e.target.value)}>
                  <option value="">{selected.product_type === "recurring" ? "Default plan" : "One-time purchase"}</option>
                  {shownPlans.map((p) => <option key={p.id} value={p.id}>{p.name} · {formatCurrency(p.price_per_interval)}</option>)}
                </Select>
              </Field>
            )}
          </div>

          {overLimit && shownPricing && (
            <p className="mt-1 text-xs text-amber-700">Above the {formatPct(shownPricing.allowed_discount_pct, 0)} limit — this line will need approval.</p>
          )}
          <FormError message={error} />
          <div className="mt-2 flex justify-end"><Button onClick={add} loading={busy} size="sm">Add to quote</Button></div>
        </div>
      )}
    </div>
  );
}
