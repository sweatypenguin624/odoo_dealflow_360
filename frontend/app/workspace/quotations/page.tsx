"use client";
import { useRouter } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { customers, quotes, users, type Customer, type QuoteListItem } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useApi, useDebounce } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatCurrency, formatDate, formatPct, relativeTime, todayIso } from "@/lib/format";
import { Button, DataTable, ErrorState, Field, FilterBar, FormError, Input, LinkButton, Modal, PageHeader, Pagination, SearchInput, Select, StatusBadge, type Column } from "@/components/ui";

const STATUSES = ["draft", "pending_approval", "approved", "revision_required", "sent", "under_negotiation", "confirmed", "rejected", "expired", "cancelled"];
const DEFAULTS = { sort: "-created_at" };

export function NewQuoteModal({ open, onClose, customerId: presetCustomer }: { open: boolean; onClose: () => void; customerId?: number }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const debounced = useDebounce(q, 300);
  const [options, setOptions] = useState<Customer[]>([]);
  const [customerId, setCustomerId] = useState<number | "">(presetCustomer ?? "");
  const [validUntil, setValidUntil] = useState(todayIso(30));
  const [promised, setPromised] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!open || presetCustomer) return; customers.list({ q: debounced, page_size: 10 }).then((p) => setOptions(p.items)).catch(() => undefined); }, [debounced, open, presetCustomer]);

  async function create() {
    if (customerId === "") return;
    setBusy(true); setError(null);
    try {
      const quote = await quotes.create({ customer_id: customerId, lines: [], valid_until: validUntil || undefined, promised_delivery_date: promised || undefined });
      router.push(`/workspace/quotations/${quote.id}`);
    } catch (err) { setError(errorMessage(err)); setBusy(false); }
  }

  return (
    <Modal open={open} onClose={onClose} title="New quotation" footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={create} loading={busy} disabled={customerId === ""} data-testid="create-quote">Create draft</Button></>}>
      <div className="space-y-3">
        <FormError message={error} />
        {!presetCustomer && (
          <>
            <Field label="Customer" required hint="Type to search by name, code or contact.">
              <Input value={q} onChange={(e) => { setQ(e.target.value); setCustomerId(""); }} placeholder="Search customers…" autoFocus data-testid="customer-search" />
            </Field>
            {customerId === "" && options.length > 0 && (
              <ul className="max-h-48 divide-y divide-zinc-100 overflow-y-auto rounded-md border border-zinc-200">
                {options.map((c) => <li key={c.id}><button type="button" className="flex w-full justify-between px-3 py-2 text-left text-sm hover:bg-blue-50" onClick={() => { setCustomerId(c.id); setQ(c.name); }}><span>{c.name} <span className="text-xs text-zinc-500">{c.code}</span></span><span className="text-xs text-zinc-500">{c.tier_name} · max {formatPct(c.max_discount_pct, 0)}</span></button></li>)}
              </ul>
            )}
          </>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Valid until"><Input type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} /></Field>
          <Field label="Promised delivery"><Input type="date" value={promised} onChange={(e) => setPromised(e.target.value)} /></Field>
        </div>
      </div>
    </Modal>
  );
}

function QuotationsInner() {
  const { state, set, page, setPage } = useListState(DEFAULTS);
  const { can, user } = useAuth();
  const router = useRouter();
  const [q, setQ] = useState(state.q ?? "");
  const debounced = useDebounce(q);
  useEffect(() => { if (debounced !== (state.q ?? "")) set({ q: debounced }); }, [debounced]); // eslint-disable-line react-hooks/exhaustive-deps
  const reps = useApi(() => users.reps(), [], { enabled: user?.role !== "sales_rep" });
  const { data, error, loading, reload } = useApi(() => quotes.list({ ...state, new: undefined, page, page_size: 25 }), [JSON.stringify(state), page]);
  const [showNew, setShowNew] = useState(state.new === "1");

  const columns: Column<QuoteListItem>[] = [
    { key: "number", header: "Quote", render: (r) => <><span className="font-medium text-zinc-900">{r.quote_number}</span>{r.order_number && <span className="block text-xs text-zinc-500">{r.order_number}</span>}</> },
    { key: "customer", header: "Customer", render: (r) => r.customer_name },
    { key: "owner", header: "Owner", render: (r) => r.owner_name ?? "—" },
    { key: "status", header: "Status", render: (r) => <><StatusBadge status={r.status} />{r.current_approval_step && <span className="ml-1 text-xs text-zinc-500">({r.current_approval_step})</span>}</> },
    { key: "total", header: "Total", align: "right", render: (r) => formatCurrency(r.total) },
    { key: "margin", header: "Margin", align: "right", render: (r) => formatPct(r.margin_pct) },
    { key: "risk", header: "Risk", align: "right", render: (r) => (r.risk_score ?? 0) > 0 ? <span className="text-amber-700">{Number(r.risk_score).toFixed(1)} pts</span> : <span className="text-emerald-700">OK</span> },
    { key: "ops", header: "Fulfillment / Billing", render: (r) => r.status === "confirmed" ? <span className="flex gap-1"><StatusBadge status={r.fulfillment_status} /><StatusBadge status={r.billing_status} /></span> : <span className="text-zinc-400">—</span> },
    { key: "activity", header: "Last activity", render: (r) => <span title={formatDate(r.last_activity_at)}>{relativeTime(r.last_activity_at)}</span> },
  ];

  return (
    <div className="space-y-4">
      <PageHeader title="Quotations" subtitle={data ? `${data.total.toLocaleString()} quotations` : undefined} actions={<><LinkButton href="/workspace/pipeline">Pipeline view</LinkButton>{can("quote:create") && <Button onClick={() => setShowNew(true)} data-testid="new-quote">+ New quotation</Button>}</>} />
      <FilterBar>
        <SearchInput value={q} onChange={setQ} placeholder="Quote #, order # or customer" className="w-72" />
        <Select value={state.status ?? ""} onChange={(e) => set({ status: e.target.value })} aria-label="Status" className="w-44"><option value="">All statuses</option>{STATUSES.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}</Select>
        {user?.role !== "sales_rep" && <Select value={state.owner_user_id ?? ""} onChange={(e) => set({ owner_user_id: e.target.value })} aria-label="Owner" className="w-44"><option value="">All owners</option>{reps.data?.map((r) => <option key={r.id} value={r.id}>{r.full_name}</option>)}</Select>}
        <Select value={state.has_recurring ?? ""} onChange={(e) => set({ has_recurring: e.target.value })} aria-label="Type" className="w-40"><option value="">All types</option><option value="true">With subscriptions</option><option value="false">One-time only</option></Select>
        <Select value={state.sort} onChange={(e) => set({ sort: e.target.value })} aria-label="Sort" className="w-44"><option value="-created_at">Newest first</option><option value="created_at">Oldest first</option><option value="-total">Highest value</option><option value="-last_activity_at">Recent activity</option></Select>
        {(state.q || state.status || state.owner_user_id || state.has_recurring) && <Button variant="ghost" size="sm" onClick={() => { setQ(""); set({ q: "", status: "", owner_user_id: "", has_recurring: "" }); }}>Clear</Button>}
      </FilterBar>
      {error && <ErrorState message={error} onRetry={reload} />}
      <DataTable columns={columns} rows={data?.items} keyOf={(r) => r.id} loading={loading} onRowClick={(r) => router.push(`/workspace/quotations/${r.id}`)} emptyTitle="No quotations match" emptyDescription="Adjust the filters or create a new quotation." />
      {data && <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} />}
      <NewQuoteModal open={showNew} onClose={() => setShowNew(false)} />
    </div>
  );
}

export default function QuotationsPage() {
  return <Suspense><QuotationsInner /></Suspense>;
}
