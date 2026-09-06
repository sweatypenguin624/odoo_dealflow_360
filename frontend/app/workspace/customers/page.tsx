"use client";
import { useRouter } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { catalog, customers, type Customer } from "@/lib/api";
import { useApi, useDebounce } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatCurrency, formatPct } from "@/lib/format";
import { Badge, Button, DataTable, ErrorState, FilterBar, PageHeader, Pagination, SearchInput, Select, type Column } from "@/components/ui";
import { CustomerFormModal } from "@/components/domain/CustomerForm";

function CustomersInner() {
  const { state, set, page, setPage } = useListState();
  const { can } = useAuth();
  const router = useRouter();
  const [q, setQ] = useState(state.q ?? "");
  const debounced = useDebounce(q);
  useEffect(() => { if (debounced !== (state.q ?? "")) set({ q: debounced }); }, [debounced]); // eslint-disable-line react-hooks/exhaustive-deps
  const tiers = useApi(() => catalog.tiers(), []);
  const { data, error, loading, reload } = useApi(() => customers.list({ q: state.q, tier_id: state.tier_id, is_active: state.is_active ?? "true", mine: state.mine, page, page_size: 25 }), [JSON.stringify(state), page]);
  const [showNew, setShowNew] = useState(false);
  const columns: Column<Customer>[] = [
    { key: "name", header: "Customer", render: (r) => <><span className="font-medium">{r.name}</span><span className="block text-xs text-zinc-500">{r.code} · {r.industry ?? "—"}</span></> },
    { key: "tier", header: "Tier", render: (r) => <Badge tone="blue">{r.tier_name}</Badge> },
    { key: "max", header: "Max discount", align: "right", render: (r) => formatPct(r.max_discount_pct, 0) },
    { key: "contact", header: "Contact", render: (r) => <>{r.contact_name ?? "—"}<span className="block text-xs text-zinc-500">{r.email}</span></> },
    { key: "owner", header: "Owner", render: (r) => r.owner_name ?? "—" },
    { key: "open", header: "Open quotes", align: "right", render: (r) => r.open_quote_count },
    { key: "outstanding", header: "Outstanding", align: "right", render: (r) => <span className={Number(r.outstanding_balance) > 0 ? "text-amber-700" : ""}>{formatCurrency(r.outstanding_balance)}</span> },
  ];
  return (
    <div className="space-y-4">
      <PageHeader title="Customers" subtitle={data ? `${data.total.toLocaleString()} accounts` : undefined} actions={can("customer:manage") && <Button onClick={() => setShowNew(true)}>+ New customer</Button>} />
      <FilterBar>
        <SearchInput value={q} onChange={setQ} placeholder="Name, code, email or contact" className="w-72" />
        <Select value={state.tier_id ?? ""} onChange={(e) => set({ tier_id: e.target.value })} className="w-40" aria-label="Tier"><option value="">All tiers</option>{tiers.data?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select>
        <Select value={state.mine ?? ""} onChange={(e) => set({ mine: e.target.value })} className="w-40" aria-label="Ownership"><option value="">All owners</option><option value="true">My accounts</option></Select>
        <Select value={state.is_active ?? "true"} onChange={(e) => set({ is_active: e.target.value })} className="w-40" aria-label="Status"><option value="true">Active</option><option value="false">Archived</option></Select>
      </FilterBar>
      {error && <ErrorState message={error} onRetry={reload} />}
      <DataTable columns={columns} rows={data?.items} keyOf={(r) => r.id} loading={loading} onRowClick={(r) => router.push(`/workspace/customers/${r.id}`)} emptyTitle="No customers found" />
      {data && <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} />}
      <CustomerFormModal open={showNew} onClose={() => setShowNew(false)} onSaved={(c) => router.push(`/workspace/customers/${c.id}`)} />
    </div>
  );
}
export default function CustomersPage() { return <Suspense><CustomersInner /></Suspense>; }
