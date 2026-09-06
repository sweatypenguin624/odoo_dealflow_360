"use client";
import { Suspense } from "react";
import { inventory, type Warehouse } from "@/lib/api";
import { useApi } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatNumber } from "@/lib/format";
import { Badge, Pagination, type Column } from "@/components/ui";
import { CrudPage, clean, type FormField } from "@/components/domain/CrudPage";

function Inner() {
  const { page, setPage } = useListState();
  const { can } = useAuth();
  const { data, error, loading, reload } = useApi(() => inventory.warehouses({ page, page_size: 25 }), [page]);

  const columns: Column<Warehouse>[] = [
    { key: "name", header: "Warehouse", render: (r) => <><span className="font-medium">{r.name}</span><span className="block text-xs text-zinc-500">{r.code}</span></> },
    { key: "location", header: "Location", render: (r) => [r.city, r.country].filter(Boolean).join(", ") || "—" },
    { key: "weight", header: "Shipping cost weight", align: "right", render: (r) => Number(r.shipping_cost_weight).toFixed(2) },
    { key: "skus", header: "SKUs", align: "right", render: (r) => r.sku_count },
    { key: "units", header: "Units on hand", align: "right", render: (r) => formatNumber(r.units_on_hand) },
    { key: "status", header: "Status", render: (r) => <Badge tone={r.is_active ? "green" : "slate"}>{r.is_active ? "Active" : "Inactive"}</Badge> },
  ];

  const fields: FormField<Warehouse>[] = [
    { name: "name", label: "Name", type: "text", required: true },
    { name: "code", label: "Code", type: "text", hint: "Short identifier used on shipment numbers." },
    { name: "shipping_cost_weight", label: "Shipping cost weight", type: "number", step: "0.1", min: 0, hint: "Lower weights are preferred when the engine allocates stock." },
    { name: "city", label: "City", type: "text" },
    { name: "country", label: "Country", type: "text" },
    { name: "is_active", label: "Active", type: "checkbox" },
  ];

  return (
    <CrudPage
      config={{
        title: "Warehouses",
        subtitle: "Stock locations. The cost weight decides which warehouse the fulfillment engine prefers.",
        addLabel: "+ New warehouse",
        columns,
        fields,
        keyOf: (r) => r.id,
        canManage: can("inventory:manage"),
        toForm: (r) => ({ name: r.name, code: r.code ?? "", shipping_cost_weight: String(r.shipping_cost_weight), city: r.city ?? "", country: r.country ?? "", is_active: String(r.is_active) }),
        toBody: (f) => clean({
          name: f.name,
          code: f.code,
          shipping_cost_weight: f.shipping_cost_weight === "" ? undefined : Number(f.shipping_cost_weight),
          city: f.city,
          country: f.country,
          is_active: f.is_active === "true",
        }),
        create: (body) => inventory.createWarehouse(body),
        update: (row, body) => inventory.updateWarehouse(row.id, body),
      }}
      defaults={{ is_active: "true", shipping_cost_weight: "1" }}
      rows={data?.items}
      loading={loading}
      error={error}
      reload={reload}
      pagination={data ? <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} /> : null}
    />
  );
}

export default function WarehousesPage() {
  return <Suspense><Inner /></Suspense>;
}
