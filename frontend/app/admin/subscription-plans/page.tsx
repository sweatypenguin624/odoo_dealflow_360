"use client";
import { Suspense } from "react";
import { catalog, type SubscriptionPlan } from "@/lib/api";
import { useApi } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatCurrency, titleCase } from "@/lib/format";
import { Badge, Pagination, type Column } from "@/components/ui";
import { CrudPage, clean, type FormField } from "@/components/domain/CrudPage";
import { ProductSelect } from "@/components/domain/ProductSelect";

const INTERVALS = ["monthly", "quarterly", "yearly"];

function Inner() {
  const { page, setPage } = useListState();
  const { can } = useAuth();
  const { data, error, loading, reload } = useApi(() => catalog.plans({ page, page_size: 25 }), [page]);

  const columns: Column<SubscriptionPlan>[] = [
    { key: "name", header: "Plan", render: (r) => <><span className="font-medium">{r.name}</span><span className="block text-xs text-zinc-500">{r.product_name}</span></> },
    { key: "interval", header: "Interval", render: (r) => <Badge tone="purple">{titleCase(r.interval)}</Badge> },
    { key: "price", header: "Price per interval", align: "right", render: (r) => formatCurrency(r.price_per_interval) },
    { key: "proration", header: "Proration", render: (r) => r.proration_enabled ? "Enabled" : "Disabled" },
    { key: "status", header: "Status", render: (r) => <Badge tone={r.is_active ? "green" : "slate"}>{r.is_active ? "Active" : "Inactive"}</Badge> },
  ];

  const fields: FormField<SubscriptionPlan>[] = [
    { name: "name", label: "Plan name", type: "text", required: true },
    {
      name: "product_id",
      label: "Product",
      type: "custom",
      required: true,
      createOnly: true,
      render: (value, set) => <ProductSelect value={Number(value) || 0} onChange={(id) => set(id ? String(id) : "")} />,
    },
    { name: "interval", label: "Billing interval", type: "select", required: true, options: INTERVALS.map((i) => ({ value: i, label: titleCase(i) })) },
    { name: "price_per_interval", label: "Price per interval", type: "number", required: true, step: "0.01", min: 0 },
    { name: "proration_enabled", label: "Prorate mid-cycle changes", type: "checkbox" },
    { name: "is_active", label: "Active", type: "checkbox" },
  ];

  return (
    <CrudPage
      config={{
        title: "Subscription Plans",
        subtitle: "Recurring plans attached to catalog products. Proration governs mid-cycle quantity changes and cancellations.",
        addLabel: "+ New plan",
        columns,
        fields,
        keyOf: (r) => r.id,
        canManage: can("catalog:manage"),
        toForm: (r) => ({ name: r.name, product_id: String(r.product_id), interval: r.interval, price_per_interval: String(r.price_per_interval), proration_enabled: String(r.proration_enabled), is_active: String(r.is_active) }),
        toBody: (f, isEdit) => clean({
          name: f.name,
          product_id: isEdit ? undefined : Number(f.product_id),
          interval: f.interval,
          price_per_interval: Number(f.price_per_interval),
          proration_enabled: f.proration_enabled === "true",
          is_active: f.is_active === "true",
        }),
        create: (body) => catalog.createPlan(body),
        update: (row, body) => catalog.updatePlan(row.id, body),
      }}
      defaults={{ interval: "monthly", proration_enabled: "true", is_active: "true" }}
      rows={data?.items}
      loading={loading}
      error={error}
      reload={reload}
      pagination={data ? <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} /> : null}
    />
  );
}

export default function SubscriptionPlansPage() {
  return <Suspense><Inner /></Suspense>;
}
