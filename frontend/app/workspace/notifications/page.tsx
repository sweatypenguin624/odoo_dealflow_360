"use client";
import Link from "next/link";
import { Suspense, useState } from "react";
import { notifications, type Notification } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useApi } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { formatDateTime, relativeTime, titleCase } from "@/lib/format";
import { Badge, Button, EmptyState, ErrorState, FilterBar, PageHeader, Pagination, Select, TableSkeleton } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";

// Notifications carry an entity reference rather than a URL; map it to a page.
function linkFor(n: Notification): string | null {
  if (!n.entity_id) return null;
  switch (n.entity_type) {
    case "quote": return `/workspace/quotations/${n.entity_id}`;
    case "invoice": return `/workspace/invoices/${n.entity_id}`;
    case "subscription": return `/workspace/subscriptions/${n.entity_id}`;
    case "customer": return `/workspace/customers/${n.entity_id}`;
    default: return null;
  }
}

function Inner() {
  const { state, set, page, setPage } = useListState();
  const toast = useToast();
  const unreadOnly = state.unread_only === "true";
  const { data, error, loading, reload } = useApi(() => notifications.list({ unread_only: unreadOnly, page, page_size: 25 }), [unreadOnly, page]);
  const [busy, setBusy] = useState(false);

  async function markRead(ids?: number[]) {
    setBusy(true);
    try {
      const r = await notifications.markRead(ids);
      if (!ids) toast.success(`${r.marked} notification(s) marked as read.`);
      reload();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Notifications"
        subtitle="Approvals, negotiations, fulfillment and billing events routed to you."
        actions={<Button variant="secondary" onClick={() => markRead()} loading={busy}>Mark all as read</Button>}
      />
      <FilterBar>
        <Select value={state.unread_only ?? ""} onChange={(e) => set({ unread_only: e.target.value })} className="w-44" aria-label="Filter">
          <option value="">All notifications</option>
          <option value="true">Unread only</option>
        </Select>
      </FilterBar>

      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data && <TableSkeleton rows={8} cols={2} />}
      {data && data.items.length === 0 && <EmptyState title={unreadOnly ? "Nothing unread" : "No notifications"} description="You're all caught up." />}

      {data && data.items.length > 0 && (
        <ul className="card divide-y divide-zinc-100">
          {data.items.map((n) => {
            const href = linkFor(n);
            const body = (
              <div className="flex items-start justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <p className={`text-sm ${n.is_read ? "text-zinc-700" : "font-medium text-zinc-900"}`}>
                    {!n.is_read && <span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-blue-600 align-middle" aria-label="Unread" />}
                    {n.title}
                  </p>
                  {n.body && <p className="mt-0.5 text-sm text-zinc-600">{n.body}</p>}
                  <p className="mt-0.5 text-xs text-zinc-400">
                    <Badge tone="neutral">{titleCase(n.type)}</Badge> <span title={formatDateTime(n.created_at)}>{relativeTime(n.created_at)}</span>
                  </p>
                </div>
                {!n.is_read && (
                  <Button size="sm" variant="ghost" onClick={(e) => { e.preventDefault(); e.stopPropagation(); markRead([n.id]); }}>Mark read</Button>
                )}
              </div>
            );
            return <li key={n.id} className={n.is_read ? "" : "bg-blue-50/30"}>{href ? <Link href={href} className="block hover:bg-zinc-50">{body}</Link> : body}</li>;
          })}
        </ul>
      )}
      {data && <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} />}
    </div>
  );
}

export default function NotificationsPage() {
  return <Suspense><Inner /></Suspense>;
}
