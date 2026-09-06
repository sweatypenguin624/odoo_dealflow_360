"use client";
import { Suspense } from "react";
import { catalog, type Pairing } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useApi } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatDate } from "@/lib/format";
import { Badge, Button, Pagination, type Column } from "@/components/ui";
import { CrudPage, clean, type FormField } from "@/components/domain/CrudPage";
import { ProductSelect } from "@/components/domain/ProductSelect";
import { useToast } from "@/components/ui/Toast";

function Inner() {
  const { page, setPage } = useListState();
  const { can } = useAuth();
  const toast = useToast();
  const { data, error, loading, reload } = useApi(() => catalog.pairings({ page, page_size: 25 }), [page]);
  const manage = can("catalog:manage");

  async function remove(p: Pairing) {
    try {
      await catalog.deletePairing(p.id);
      toast.success("Pairing deleted.");
      reload();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const columns: Column<Pairing>[] = [
    { key: "base", header: "When the quote contains", render: (r) => <span className="font-medium">{r.base_product_name}</span> },
    { key: "suggested", header: "Suggest", render: (r) => r.suggested_product_name },
    { key: "score", header: "Co-purchase score", align: "right", render: (r) => Number(r.co_purchase_score).toFixed(1) },
    { key: "promo", header: "Promotion", render: (r) => r.is_promoted ? <><Badge tone="amber">{r.promotion_label ?? "Promoted"}</Badge>{(r.promotion_start || r.promotion_end) && <span className="block text-xs text-zinc-500">{formatDate(r.promotion_start)} – {formatDate(r.promotion_end)}</span>}</> : <span className="text-zinc-400">—</span> },
    { key: "status", header: "Status", render: (r) => <Badge tone={r.is_active ? "green" : "slate"}>{r.is_active ? "Active" : "Inactive"}</Badge> },
    { key: "actions", header: "", render: (r) => manage ? <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); remove(r); }}>Delete</Button> : null },
  ];

  const fields: FormField<Pairing>[] = [
    { name: "base_product_id", label: "Base product", type: "custom", required: true, createOnly: true, render: (value, set) => <ProductSelect value={Number(value) || 0} onChange={(id) => set(id ? String(id) : "")} /> },
    { name: "suggested_product_id", label: "Suggested product", type: "custom", required: true, createOnly: true, render: (value, set) => <ProductSelect value={Number(value) || 0} onChange={(id) => set(id ? String(id) : "")} /> },
    { name: "co_purchase_score", label: "Co-purchase score", type: "number", step: "0.5", min: 0, max: 100, hint: "Higher scores rank the suggestion above others." },
    { name: "is_promoted", label: "Promote this pairing", type: "checkbox" },
    { name: "promotion_label", label: "Promotion label", type: "text" },
    { name: "promotion_start", label: "Promotion starts", type: "date" },
    { name: "promotion_end", label: "Promotion ends", type: "date" },
    { name: "is_active", label: "Active", type: "checkbox" },
  ];

  return (
    <CrudPage
      config={{
        title: "Upsell Rules",
        subtitle: "Product pairings behind the cross-sell suggestions reps see while building a quotation.",
        addLabel: "+ New pairing",
        columns,
        fields,
        keyOf: (r) => r.id,
        canManage: manage,
        toForm: (r) => ({
          base_product_id: String(r.base_product_id), suggested_product_id: String(r.suggested_product_id),
          co_purchase_score: String(r.co_purchase_score), is_promoted: String(r.is_promoted),
          promotion_label: r.promotion_label ?? "", promotion_start: r.promotion_start ?? "", promotion_end: r.promotion_end ?? "",
          is_active: String(r.is_active),
        }),
        toBody: (f, isEdit) => clean({
          base_product_id: isEdit ? undefined : Number(f.base_product_id),
          suggested_product_id: isEdit ? undefined : Number(f.suggested_product_id),
          co_purchase_score: f.co_purchase_score === "" ? undefined : Number(f.co_purchase_score),
          is_promoted: f.is_promoted === "true",
          promotion_label: f.promotion_label,
          promotion_start: f.promotion_start,
          promotion_end: f.promotion_end,
          is_active: f.is_active === "true",
        }),
        create: (body) => catalog.createPairing(body),
        update: (row, body) => catalog.updatePairing(row.id, body),
      }}
      defaults={{ co_purchase_score: "50", is_promoted: "false", is_active: "true" }}
      rows={data?.items}
      loading={loading}
      error={error}
      reload={reload}
      pagination={data ? <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} /> : null}
    />
  );
}

export default function PairingsPage() {
  return <Suspense><Inner /></Suspense>;
}
