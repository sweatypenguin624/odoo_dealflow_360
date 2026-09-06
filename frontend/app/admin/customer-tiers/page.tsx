"use client";
import { catalog, type Tier } from "@/lib/api";
import { useApi } from "@/lib/hooks/useApi";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatPct } from "@/lib/format";
import { Badge, type Column } from "@/components/ui";
import { CrudPage, clean, type FormField } from "@/components/domain/CrudPage";

export default function CustomerTiersPage() {
  const { can } = useAuth();
  const { data, error, loading, reload } = useApi(() => catalog.tiers(true), []);

  const columns: Column<Tier>[] = [
    { key: "name", header: "Tier", render: (r) => <><span className="font-medium">{r.name}</span>{r.description && <span className="block text-xs text-zinc-500">{r.description}</span>}</> },
    { key: "max", header: "Max discount", align: "right", render: (r) => formatPct(r.max_discount_pct, 0) },
    { key: "customers", header: "Customers", align: "right", render: (r) => r.customer_count },
    { key: "order", header: "Sort order", align: "right", render: (r) => r.sort_order },
    { key: "status", header: "Status", render: (r) => <Badge tone={r.is_active ? "green" : "slate"}>{r.is_active ? "Active" : "Inactive"}</Badge> },
  ];

  const fields: FormField<Tier>[] = [
    { name: "name", label: "Name", type: "text", required: true },
    { name: "max_discount_pct", label: "Max discount %", type: "number", required: true, step: "0.5", min: 0, max: 100 },
    { name: "sort_order", label: "Sort order", type: "number", hint: "Lower numbers appear first." },
    { name: "is_active", label: "Active", type: "checkbox" },
    { name: "description", label: "Description", type: "textarea", full: true },
  ];

  return (
    <CrudPage
      config={{
        title: "Customer Tiers",
        subtitle: "The baseline discount ceiling for every customer on the tier. Category and product rules can narrow it further.",
        addLabel: "+ New tier",
        columns,
        fields,
        keyOf: (r) => r.id,
        canManage: can("discount_rules:manage"),
        toForm: (r) => ({ name: r.name, max_discount_pct: String(r.max_discount_pct), sort_order: String(r.sort_order), is_active: String(r.is_active), description: r.description ?? "" }),
        toBody: (f) => clean({
          name: f.name,
          max_discount_pct: Number(f.max_discount_pct),
          sort_order: f.sort_order === "" ? undefined : Number(f.sort_order),
          is_active: f.is_active === "true",
          description: f.description,
        }),
        create: (body) => catalog.createTier(body),
        update: (row, body) => catalog.updateTier(row.id, body),
      }}
      defaults={{ is_active: "true", sort_order: "0" }}
      rows={data ?? undefined}
      loading={loading}
      error={error}
      reload={reload}
    />
  );
}
