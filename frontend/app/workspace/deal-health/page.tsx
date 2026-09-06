"use client";
import Link from "next/link";
import { Suspense, useState } from "react";
import { dealHealth, type Alert, type AlertDetail } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useApi } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatDateTime, relativeTime, titleCase } from "@/lib/format";
import { Badge, Button, Card, DataTable, ErrorState, Field, FilterBar, KpiTile, Modal, PageHeader, Pagination, Select, Skeleton, StatusBadge, Textarea, type Column } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";

const ALERT_TYPES = ["stalled", "discount_anomaly", "delivery_slippage", "approval_aging", "negotiation_aging", "payment_overdue", "backorder_risk"];
const ACTION_LABELS: Record<string, string> = {
  nudge: "Nudge rep",
  escalate: "Escalate to manager",
  remind: "Remind customer",
  acknowledge: "Acknowledge",
  resolve: "Resolve",
};

function AlertDrawer({ alertId, onClose, onChanged }: { alertId: number; onClose: () => void; onChanged: () => void }) {
  const { data, error, reload } = useApi(() => dealHealth.alert(alertId), [alertId]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const toast = useToast();

  async function act(action: string) {
    setBusy(action);
    try {
      await dealHealth.act(alertId, { action_type: action, note: note || undefined });
      toast.success(`${ACTION_LABELS[action] ?? titleCase(action)} recorded.`);
      setNote("");
      reload();
      onChanged();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  const alert: AlertDetail | null = data;
  return (
    <Modal open onClose={onClose} title={alert ? titleCase(alert.alert_type) : "Alert"} size="lg">
      {error && <ErrorState message={error} onRetry={reload} />}
      {!alert ? <Skeleton className="h-40" /> : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={alert.severity} />
            <StatusBadge status={alert.status} />
            <Link href={alert.link} className="link text-sm">{alert.quote_number ?? `Quote ${alert.quote_id}`}</Link>
            <span className="text-sm text-zinc-500">{alert.customer_name} · rep {alert.owner_name ?? "unassigned"}</span>
          </div>
          <p className="text-sm text-zinc-800">{alert.message}</p>
          <p className="text-xs text-zinc-500">Raised {formatDateTime(alert.created_at)}{alert.acknowledged_at ? ` · acknowledged ${formatDateTime(alert.acknowledged_at)}` : ""}{alert.resolved_at ? ` · resolved ${formatDateTime(alert.resolved_at)}` : ""}</p>
          {alert.details && Object.keys(alert.details).length > 0 && (
            <dl className="grid grid-cols-2 gap-2 rounded-md bg-zinc-50 p-3 text-xs sm:grid-cols-3">
              {Object.entries(alert.details).map(([k, v]) => (
                <div key={k}>
                  <dt className="text-zinc-500">{titleCase(k)}</dt>
                  <dd className="font-medium text-zinc-900">{String(v)}</dd>
                </div>
              ))}
            </dl>
          )}

          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Actions taken</h3>
            {alert.actions.length === 0 ? <p className="mt-1 text-sm text-zinc-500">Nothing yet.</p> : (
              <ol className="mt-1 space-y-1 text-sm">
                {alert.actions.map((a) => (
                  <li key={a.id} className="rounded-md border border-zinc-200 px-2 py-1">
                    <span className="font-medium">{ACTION_LABELS[a.action_type] ?? titleCase(a.action_type)}</span>
                    <span className="text-zinc-500"> by {a.actor_label} · {formatDateTime(a.created_at)}</span>
                    {a.note && <p className="text-zinc-600">{a.note}</p>}
                    {a.recipients && a.recipients.length > 0 && <p className="text-xs text-zinc-400">Notified: {a.recipients.join(", ")}</p>}
                  </li>
                ))}
              </ol>
            )}
          </div>

          {alert.available_actions.length > 0 && (
            <div className="space-y-2 border-t border-zinc-100 pt-3">
              <Field label="Note"><Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional context recorded with the action" /></Field>
              <div className="flex flex-wrap gap-2">
                {alert.available_actions.map((a) => (
                  <Button key={a} size="sm" variant={a === "resolve" ? "success" : a === "escalate" ? "danger" : "secondary"} loading={busy === a} onClick={() => act(a)}>
                    {ACTION_LABELS[a] ?? titleCase(a)}
                  </Button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

function Inner() {
  const { state, set, page, setPage } = useListState({ status: "open" });
  const { can, user } = useAuth();
  const toast = useToast();
  const summary = useApi(() => dealHealth.summary(), []);
  const { data, error, loading, reload } = useApi(
    () => dealHealth.alerts({ status: state.status, alert_type: state.alert_type, severity: state.severity, mine: state.mine, page, page_size: 25 }),
    [JSON.stringify(state), page],
  );
  const [selected, setSelected] = useState<number | null>(null);
  const [running, setRunning] = useState(false);

  async function runEngine() {
    setRunning(true);
    try {
      const r = await dealHealth.run();
      toast.success(`Engine run: ${r.created} new, ${r.updated} updated, ${r.resolved} auto-resolved. ${r.open} open.`);
      reload();
      summary.reload();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setRunning(false);
    }
  }

  const columns: Column<Alert>[] = [
    { key: "severity", header: "Severity", render: (r) => <StatusBadge status={r.severity} /> },
    { key: "type", header: "Type", render: (r) => <Badge tone="neutral">{titleCase(r.alert_type)}</Badge> },
    { key: "message", header: "What happened", render: (r) => <span className="block max-w-lg text-zinc-800">{r.message}</span> },
    { key: "quote", header: "Deal", render: (r) => <><span className="font-medium">{r.quote_number ?? `Quote ${r.quote_id}`}</span><span className="block text-xs text-zinc-500">{r.customer_name}</span></> },
    { key: "owner", header: "Rep", render: (r) => r.owner_name ?? "—" },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
    { key: "age", header: "Raised", render: (r) => <span title={formatDateTime(r.created_at)}>{relativeTime(r.created_at)}</span> },
  ];

  const byType = summary.data?.by_type ?? {};
  const bySeverity = summary.data?.by_severity ?? {};

  return (
    <div className="space-y-4">
      <PageHeader
        title="Deal Health"
        subtitle="Deals that need attention — stalled negotiations, discount anomalies, slipping deliveries and overdue payments."
        actions={can("deal_health:read") && <Button variant="secondary" onClick={runEngine} loading={running}>Re-run engine</Button>}
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiTile label="Open alerts" value={summary.data?.open ?? "…"} tone={summary.data?.open ? "warn" : "good"} />
        <KpiTile label="Critical" value={bySeverity.critical ?? 0} tone={bySeverity.critical ? "danger" : "good"} />
        <KpiTile label="Warnings" value={bySeverity.warning ?? 0} tone={bySeverity.warning ? "warn" : "neutral"} />
        <KpiTile label="Informational" value={bySeverity.info ?? 0} />
      </div>

      {Object.keys(byType).length > 0 && (
        <Card title="By type">
          <div className="flex flex-wrap gap-2">
            {Object.entries(byType).map(([type, count]) => (
              <button key={type} onClick={() => set({ alert_type: state.alert_type === type ? "" : type })} className={`rounded-full border px-3 py-1 text-xs ${state.alert_type === type ? "border-blue-500 bg-blue-50 text-blue-800" : "border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-50"}`}>
                {titleCase(type)} <span className="font-semibold">{count}</span>
              </button>
            ))}
          </div>
        </Card>
      )}

      <FilterBar>
        <Select value={state.status ?? "open"} onChange={(e) => set({ status: e.target.value })} className="w-44" aria-label="Status">
          <option value="open">Open</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="active">Open + acknowledged</option>
          <option value="resolved">Resolved</option>
          <option value="all">All statuses</option>
        </Select>
        <Select value={state.alert_type ?? ""} onChange={(e) => set({ alert_type: e.target.value })} className="w-52" aria-label="Alert type">
          <option value="">All types</option>
          {ALERT_TYPES.map((t) => <option key={t} value={t}>{titleCase(t)}</option>)}
        </Select>
        <Select value={state.severity ?? ""} onChange={(e) => set({ severity: e.target.value })} className="w-40" aria-label="Severity">
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </Select>
        {user?.role !== "sales_rep" && (
          <Select value={state.mine ?? ""} onChange={(e) => set({ mine: e.target.value })} className="w-40" aria-label="Ownership">
            <option value="">All reps</option>
            <option value="true">My deals</option>
          </Select>
        )}
      </FilterBar>

      {error && <ErrorState message={error} onRetry={reload} />}
      <DataTable
        columns={columns}
        rows={data?.items}
        keyOf={(r) => r.id}
        loading={loading}
        onRowClick={(r) => setSelected(r.id)}
        emptyTitle="No alerts"
        emptyDescription="Nothing needs attention with these filters."
      />
      {data && <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} />}

      {selected !== null && <AlertDrawer alertId={selected} onClose={() => setSelected(null)} onChanged={() => { reload(); summary.reload(); }} />}
    </div>
  );
}

export default function DealHealthPage() {
  return <Suspense><Inner /></Suspense>;
}
