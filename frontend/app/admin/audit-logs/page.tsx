"use client";
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { audit, type AuditEntry } from "@/lib/api";
import { useApi, useDebounce } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { formatDateTime, titleCase } from "@/lib/format";
import { Badge, Button, DataTable, ErrorState, Field, FilterBar, Input, Modal, PageHeader, Pagination, SearchInput, type Column } from "@/components/ui";

function DiffModal({ entry, onClose }: { entry: AuditEntry; onClose: () => void }) {
  const render = (label: string, value: unknown) => (
    <div className="min-w-0 flex-1">
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">{label}</p>
      <pre className="max-h-72 overflow-auto rounded-md bg-zinc-900 p-3 text-xs text-zinc-100">{value ? JSON.stringify(value, null, 2) : "—"}</pre>
    </div>
  );
  return (
    <Modal open onClose={onClose} title={titleCase(entry.action)} size="lg">
      <div className="space-y-3">
        <p className="text-sm text-zinc-600">
          {entry.user} · {formatDateTime(entry.timestamp)}
          {entry.entity_type ? ` · ${entry.entity_type}${entry.entity_id ? ` #${entry.entity_id}` : ""}` : ""}
        </p>
        {entry.reason && <p className="rounded-md bg-zinc-50 px-3 py-2 text-sm text-zinc-700">{entry.reason}</p>}
        <div className="flex flex-col gap-3 sm:flex-row">
          {render("Before", entry.before_data)}
          {render("After", entry.after_data)}
        </div>
      </div>
    </Modal>
  );
}

function Inner() {
  const { state, set, page, setPage } = useListState();
  const [q, setQ] = useState(state.q ?? "");
  const debounced = useDebounce(q);
  useEffect(() => { if (debounced !== (state.q ?? "")) set({ q: debounced }); }, [debounced]); // eslint-disable-line react-hooks/exhaustive-deps
  const { data, error, loading, reload } = useApi(
    () => audit.list({ q: state.q, action: state.action, entity_type: state.entity_type, date_from: state.date_from, date_to: state.date_to, page, page_size: 25 }),
    [JSON.stringify(state), page],
  );
  const [selected, setSelected] = useState<AuditEntry | null>(null);

  const columns: Column<AuditEntry>[] = [
    { key: "when", header: "When", render: (r) => formatDateTime(r.timestamp) },
    { key: "user", header: "Who", render: (r) => r.user },
    { key: "action", header: "Action", render: (r) => <Badge tone="neutral">{titleCase(r.action)}</Badge> },
    { key: "entity", header: "Entity", render: (r) => r.entity_type ? `${r.entity_type}${r.entity_id ? ` #${r.entity_id}` : ""}` : "—" },
    { key: "quote", header: "Quote", render: (r) => r.quote_id ? <Link href={`/workspace/quotations/${r.quote_id}`} className="link" onClick={(e) => e.stopPropagation()}>{r.quote_number ?? `#${r.quote_id}`}</Link> : "—" },
    { key: "customer", header: "Customer", render: (r) => r.customer_name ?? "—" },
    { key: "reason", header: "Reason", render: (r) => <span className="line-clamp-2 max-w-sm text-xs text-zinc-600">{r.reason ?? "—"}</span> },
  ];

  return (
    <div className="space-y-4">
      <PageHeader title="Audit Logs" subtitle="Every state change with the actor, reason and before/after payload. Select a row to inspect the diff." />
      <FilterBar>
        <SearchInput value={q} onChange={setQ} placeholder="Action, user, reason, quote or customer" className="w-80" />
        <Field label="Entity type" className="w-44"><Input value={state.entity_type ?? ""} onChange={(e) => set({ entity_type: e.target.value })} placeholder="quote, invoice…" /></Field>
        <Field label="From" className="w-44"><Input type="date" value={state.date_from ?? ""} onChange={(e) => set({ date_from: e.target.value })} /></Field>
        <Field label="To" className="w-44"><Input type="date" value={state.date_to ?? ""} onChange={(e) => set({ date_to: e.target.value })} /></Field>
        {(state.q || state.entity_type || state.date_from || state.date_to) && (
          <Button variant="ghost" size="sm" onClick={() => { setQ(""); set({ q: "", entity_type: "", date_from: "", date_to: "" }); }}>Clear</Button>
        )}
      </FilterBar>
      {error && <ErrorState message={error} onRetry={reload} />}
      <DataTable columns={columns} rows={data?.items} keyOf={(r) => r.id} loading={loading} onRowClick={setSelected} emptyTitle="No audit entries match" dense />
      {data && <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} />}
      {selected && <DiffModal entry={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

export default function AuditLogsPage() {
  return <Suspense><Inner /></Suspense>;
}
