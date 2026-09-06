"use client";
import { Suspense } from "react";
import { catalog, pricing, type DiscountRule } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useApi } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatDate, formatPct, titleCase } from "@/lib/format";
import { Badge, Button, Pagination, type Column } from "@/components/ui";
import { CrudPage, clean, type FormField } from "@/components/domain/CrudPage";
import { ProductSelect } from "@/components/domain/ProductSelect";
import { useToast } from "@/components/ui/Toast";

const SCOPES = ["tier", "category", "tier_category", "product"];

function Inner() {
  const { page, setPage } = useListState();
  const { can } = useAuth();
  const toast = useToast();
  const tiers = useApi(() => catalog.tiers(), []);
  const categories = useApi(() => catalog.categories({ page_size: 100 }), []);
  const { data, error, loading, reload } = useApi(() => pricing.discountRules({ page, page_size: 25 }), [page]);
  const manage = can("discount_rules:manage");

  async function remove(rule: DiscountRule) {
    try {
      await pricing.deleteDiscountRule(rule.id);
      toast.success("Rule deleted.");
      reload();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const columns: Column<DiscountRule>[] = [
    { key: "name", header: "Rule", render: (r) => <><span className="font-medium">{r.name}</span><span className="block text-xs text-zinc-500">{[r.tier_name, r.category_name, r.product_name].filter(Boolean).join(" · ") || "—"}</span></> },
    { key: "scope", header: "Scope", render: (r) => <Badge tone="blue">{titleCase(r.scope)}</Badge> },
    { key: "max", header: "Max discount", align: "right", render: (r) => formatPct(r.max_discount_pct, 0) },
    { key: "validity", header: "Valid", render: (r) => <span className="text-xs">{r.valid_from || r.valid_to ? `${formatDate(r.valid_from)} – ${formatDate(r.valid_to)}` : "Always"}</span> },
    { key: "priority", header: "Priority", align: "right", render: (r) => r.priority },
    { key: "status", header: "Status", render: (r) => <Badge tone={r.is_active ? "green" : "slate"}>{r.is_active ? "Active" : "Inactive"}</Badge> },
    { key: "actions", header: "", render: (r) => manage ? <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); remove(r); }}>Delete</Button> : null },
  ];

  const fields: FormField<DiscountRule>[] = [
    { name: "name", label: "Rule name", type: "text", required: true },
    { name: "scope", label: "Scope", type: "select", required: true, createOnly: true, options: SCOPES.map((s) => ({ value: s, label: titleCase(s) })) },
    { name: "tier_id", label: "Tier", type: "select", createOnly: true, options: (tiers.data ?? []).map((t) => ({ value: t.id, label: t.name })), hint: "Required for tier and tier+category scopes." },
    { name: "category_id", label: "Category", type: "select", createOnly: true, options: (categories.data?.items ?? []).map((c) => ({ value: c.id, label: c.name })), hint: "Required for category and tier+category scopes." },
    { name: "product_id", label: "Product", type: "custom", createOnly: true, hint: "Required for product scope.", render: (value, set) => <ProductSelect value={Number(value) || 0} onChange={(id) => set(id ? String(id) : "")} /> },
    { name: "max_discount_pct", label: "Max discount %", type: "number", required: true, step: "0.5", min: 0, max: 100 },
    { name: "priority", label: "Priority", type: "number", hint: "Higher priority wins when several rules match." },
    { name: "valid_from", label: "Valid from", type: "date" },
    { name: "valid_to", label: "Valid to", type: "date" },
    { name: "is_active", label: "Active", type: "checkbox" },
  ];

  return (
    <CrudPage
      config={{
        title: "Discount Rules",
        subtitle: "Ceilings evaluated per line. The most specific matching rule wins; ties are broken by priority.",
        addLabel: "+ New rule",
        columns,
        fields,
        keyOf: (r) => r.id,
        canManage: manage,
        toForm: (r) => ({
          name: r.name, scope: r.scope, tier_id: r.tier_id ? String(r.tier_id) : "", category_id: r.category_id ? String(r.category_id) : "",
          product_id: r.product_id ? String(r.product_id) : "", max_discount_pct: String(r.max_discount_pct),
          priority: String(r.priority), valid_from: r.valid_from ?? "", valid_to: r.valid_to ?? "", is_active: String(r.is_active),
        }),
        toBody: (f, isEdit) => clean({
          name: f.name,
          scope: isEdit ? undefined : f.scope,
          tier_id: isEdit || !f.tier_id ? undefined : Number(f.tier_id),
          category_id: isEdit || !f.category_id ? undefined : Number(f.category_id),
          product_id: isEdit || !f.product_id ? undefined : Number(f.product_id),
          max_discount_pct: Number(f.max_discount_pct),
          priority: f.priority === "" ? undefined : Number(f.priority),
          valid_from: f.valid_from,
          valid_to: f.valid_to,
          is_active: f.is_active === "true",
        }),
        create: (body) => pricing.createDiscountRule(body),
        update: (row, body) => pricing.updateDiscountRule(row.id, body),
      }}
      defaults={{ scope: "tier", priority: "0", is_active: "true" }}
      rows={data?.items}
      loading={loading}
      error={error}
      reload={reload}
      pagination={data ? <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} /> : null}
    />
  );
}

export default function DiscountRulesPage() {
  return <Suspense><Inner /></Suspense>;
}
