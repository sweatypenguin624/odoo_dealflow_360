"use client";
import { Suspense } from "react";
import { catalog, type Category } from "@/lib/api";
import { useApi } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatPct } from "@/lib/format";
import { Badge, Pagination, type Column } from "@/components/ui";
import { CrudPage, clean, type FormField } from "@/components/domain/CrudPage";

function Inner() {
  const { page, setPage } = useListState();
  const { can } = useAuth();
  const { data, error, loading, reload } = useApi(() => catalog.categories({ page, page_size: 25 }), [page]);

  const columns: Column<Category>[] = [
    { key: "name", header: "Category", render: (r) => <><span className="font-medium">{r.name}</span>{r.description && <span className="block text-xs text-zinc-500">{r.description}</span>}</> },
    { key: "max", header: "Category discount ceiling", align: "right", render: (r) => r.max_discount_pct === null ? <span className="text-zinc-400">Not set</span> : formatPct(r.max_discount_pct, 0) },
    { key: "products", header: "Products", align: "right", render: (r) => r.product_count },
    { key: "status", header: "Status", render: (r) => <Badge tone={r.is_active ? "green" : "slate"}>{r.is_active ? "Active" : "Inactive"}</Badge> },
  ];

  const fields: FormField<Category>[] = [
    { name: "name", label: "Name", type: "text", required: true },
    { name: "max_discount_pct", label: "Max discount %", type: "number", step: "0.5", min: 0, max: 100, hint: "Leave blank to fall back to the tier ceiling." },
    { name: "is_active", label: "Active", type: "checkbox" },
    { name: "description", label: "Description", type: "textarea", full: true },
  ];

  return (
    <CrudPage
      config={{
        title: "Categories",
        subtitle: "Product grouping. A category ceiling narrows the discount a tier would otherwise allow.",
        addLabel: "+ New category",
        columns,
        fields,
        keyOf: (r) => r.id,
        canManage: can("catalog:manage"),
        toForm: (r) => ({ name: r.name, max_discount_pct: r.max_discount_pct === null ? "" : String(r.max_discount_pct), is_active: String(r.is_active), description: r.description ?? "" }),
        toBody: (f, isEdit) => {
          const body = clean({
            name: f.name,
            max_discount_pct: f.max_discount_pct === "" ? undefined : Number(f.max_discount_pct),
            is_active: f.is_active === "true",
            description: f.description,
          });
          // The API needs an explicit flag to unset an existing ceiling.
          if (isEdit && f.max_discount_pct === "") body.clear_max_discount = true;
          return body;
        },
        create: (body) => catalog.createCategory(body),
        update: (row, body) => catalog.updateCategory(row.id, body),
      }}
      defaults={{ is_active: "true" }}
      rows={data?.items}
      loading={loading}
      error={error}
      reload={reload}
      pagination={data ? <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} /> : null}
    />
  );
}

export default function CategoriesPage() {
  return <Suspense><Inner /></Suspense>;
}
