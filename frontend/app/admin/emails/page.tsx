"use client";
import { Suspense, useEffect, useState } from "react";
import { audit, type EmailMessage } from "@/lib/api";
import { useApi, useDebounce } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { formatDateTime, titleCase } from "@/lib/format";
import { Badge, DataTable, ErrorState, FilterBar, Modal, PageHeader, Pagination, SearchInput, Select, type Column } from "@/components/ui";

function Inner() {
  const { state, set, page, setPage } = useListState();
  const [q, setQ] = useState(state.q ?? "");
  const debounced = useDebounce(q);
  useEffect(() => { if (debounced !== (state.q ?? "")) set({ q: debounced }); }, [debounced]); // eslint-disable-line react-hooks/exhaustive-deps
  const { data, error, loading, reload } = useApi(() => audit.emails({ q: state.q, status: state.status, page, page_size: 25 }), [JSON.stringify(state), page]);
  const [selected, setSelected] = useState<EmailMessage | null>(null);

  const columns: Column<EmailMessage>[] = [
    { key: "when", header: "Sent", render: (r) => formatDateTime(r.created_at) },
    { key: "to", header: "To", render: (r) => r.to_address },
    { key: "subject", header: "Subject", render: (r) => <span className="line-clamp-1 max-w-sm">{r.subject}</span> },
    { key: "template", header: "Template", render: (r) => <Badge tone="neutral">{titleCase(r.template)}</Badge> },
    { key: "status", header: "Status", render: (r) => <Badge tone={r.status === "sent" ? "green" : r.status === "failed" ? "red" : "amber"}>{titleCase(r.status)}</Badge> },
    { key: "provider", header: "Provider", render: (r) => r.provider },
    { key: "entity", header: "Related to", render: (r) => r.entity_type ? `${r.entity_type}${r.entity_id ? ` #${r.entity_id}` : ""}` : "—" },
  ];

  return (
    <div className="space-y-4">
      <PageHeader title="Email Log" subtitle="Every outbound message and its delivery status. In development the console provider records mail here without sending it." />
      <FilterBar>
        <SearchInput value={q} onChange={setQ} placeholder="Recipient or subject" className="w-72" />
        <Select value={state.status ?? ""} onChange={(e) => set({ status: e.target.value })} className="w-40" aria-label="Status">
          <option value="">All statuses</option>
          <option value="sent">Sent</option>
          <option value="failed">Failed</option>
          <option value="skipped">Skipped</option>
        </Select>
      </FilterBar>
      {error && <ErrorState message={error} onRetry={reload} />}
      <DataTable columns={columns} rows={data?.items} keyOf={(r) => r.id} loading={loading} onRowClick={setSelected} emptyTitle="No emails logged" dense />
      {data && <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} />}

      {selected && (
        <Modal open onClose={() => setSelected(null)} title={selected.subject} size="lg">
          <div className="space-y-3">
            <p className="text-sm text-zinc-600">
              To <strong>{selected.to_address}</strong> · {formatDateTime(selected.created_at)} · {selected.provider} ·{" "}
              <Badge tone={selected.status === "sent" ? "green" : selected.status === "failed" ? "red" : "amber"}>{titleCase(selected.status)}</Badge>
            </p>
            {selected.error && <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{selected.error}</p>}
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-md bg-zinc-50 p-3 text-sm text-zinc-800">{selected.body_text}</pre>
          </div>
        </Modal>
      )}
    </div>
  );
}

export default function EmailLogPage() {
  return <Suspense><Inner /></Suspense>;
}
