"use client";
import Link from "next/link";
import { useState } from "react";
import { portalApi } from "@/lib/api/portal";
import { useApi } from "@/lib/hooks/useApi";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatCurrency, formatDate } from "@/lib/format";
import { Badge, EmptyState, ErrorState, PageHeader, Pagination, Skeleton, StatusBadge } from "@/components/ui";

export default function PortalHomePage() {
  const { user, logout } = useAuth();
  const [page, setPage] = useState(1);
  const { data, error, loading, reload } = useApi(() => portalApi.myQuotes(page), [page]);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Your quotations"
        subtitle={user ? `Signed in as ${user.full_name}` : undefined}
        actions={user && <button onClick={() => logout()} className="rounded-md border border-zinc-300 px-2.5 py-1 text-xs text-zinc-700 hover:bg-zinc-50">Sign out</button>}
      />

      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data && <Skeleton className="h-40" />}
      {data && data.items.length === 0 && <EmptyState title="No quotations yet" description="When your sales contact sends a quotation, it will appear here." />}

      {data && data.items.length > 0 && (
        <ul className="card divide-y divide-zinc-100">
          {data.items.map((q) => (
            <li key={q.quote_id}>
              <Link href={`/portal/quotes/${q.quote_id}`} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 hover:bg-zinc-50">
                <div>
                  <p className="font-medium text-zinc-900">
                    {q.quote_number}
                    {q.order_number && <Badge tone="green" className="ml-2">Order {q.order_number}</Badge>}
                  </p>
                  <p className="text-xs text-zinc-500">
                    Issued {formatDate(q.created_at)}
                    {q.valid_until ? ` · valid until ${formatDate(q.valid_until)}` : ""}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <StatusBadge status={q.status} />
                  <span className="font-semibold tabular-nums text-zinc-900">{formatCurrency(q.total, q.currency)}</span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {data && <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} />}
    </div>
  );
}
