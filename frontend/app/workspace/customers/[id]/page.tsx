"use client";
import Link from "next/link";
import { use, useState } from "react";
import { customers } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useApi } from "@/lib/hooks/useApi";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatCurrency, formatDate, formatDateTime, formatPct, titleCase } from "@/lib/format";
import { Badge, Button, Card, DescriptionList, ErrorState, KpiTile, PageHeader, Skeleton, StatusBadge, Tabs } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { CustomerFormModal } from "@/components/domain/CustomerForm";
import { NewQuoteModal } from "@/app/workspace/quotations/page";

export default function CustomerDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const id = Number(use(params).id);
  const { can } = useAuth();
  const toast = useToast();
  const { data: c, error, reload, setData } = useApi(() => customers.get(id), [id]);
  const history = useApi(() => customers.history(id), [id]);
  const [tab, setTab] = useState("quotes");
  const [edit, setEdit] = useState(false);
  const [newQuote, setNewQuote] = useState(false);
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!c) return <Skeleton className="h-64" />;
  const h = history.data;
  const addr = (p: "billing" | "shipping") => [c[`${p}_address_line1`], c[`${p}_city`], c[`${p}_state`], c[`${p}_postal_code`], c[`${p}_country`]].filter(Boolean).join(", ") || "—";
  async function toggleArchive() {
    try { setData(() => null); const updated = c!.is_active ? await customers.archive(id) : await customers.restore(id); setData(() => updated); toast.success(updated.is_active ? "Customer restored." : "Customer archived."); } catch (err) { toast.error(errorMessage(err)); reload(); }
  }
  const tabs = [{ key: "quotes", label: `Quotes (${h?.quotes.length ?? 0})` }, { key: "orders", label: `Orders (${h?.orders.length ?? 0})` }, { key: "invoices", label: `Invoices (${h?.invoices.length ?? 0})` }, { key: "payments", label: `Payments (${h?.payments.length ?? 0})` }, { key: "subscriptions", label: `Subscriptions (${h?.subscriptions.length ?? 0})` }, { key: "alerts", label: `Deal health (${h?.alerts.length ?? 0})` }, { key: "activity", label: "Activity" }];
  const row = "flex items-center justify-between gap-3 border-b border-zinc-100 py-2 text-sm last:border-0";
  return (
    <div className="space-y-5">
      <PageHeader breadcrumb={{ href: "/workspace/customers", label: "Customers" }} title={<span className="flex items-center gap-2">{c.name} <Badge tone="blue">{c.tier_name}</Badge>{!c.is_active && <Badge tone="slate">Archived</Badge>}</span>} subtitle={`${c.code} · ${c.industry ?? "—"} · owner ${c.owner_name ?? "unassigned"}`} actions={<>{can("quote:create") && c.is_active && <Button onClick={() => setNewQuote(true)}>+ New quotation</Button>}{can("customer:manage") && <><Button variant="secondary" onClick={() => setEdit(true)}>Edit</Button><Button variant="ghost" onClick={toggleArchive}>{c.is_active ? "Archive" : "Restore"}</Button></>}</>} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <KpiTile label="Open quotes" value={c.open_quote_count} /><KpiTile label="Orders" value={h?.totals.order_count ?? "…"} /><KpiTile label="Revenue collected" value={formatCurrency(h?.totals.revenue_collected)} /><KpiTile label="Outstanding" value={formatCurrency(c.outstanding_balance)} tone={Number(c.outstanding_balance) > 0 ? "warn" : "neutral"} /><KpiTile label="Open alerts" value={h?.totals.open_alerts ?? "…"} tone={h?.totals.open_alerts ? "warn" : "good"} />
      </div>
      <Card title="Account details"><DescriptionList columns={3} items={[{ label: "Contact", value: c.contact_name }, { label: "Email", value: c.email }, { label: "Phone", value: c.phone }, { label: "Website", value: c.website }, { label: "Payment terms", value: `${c.payment_terms_days} days` }, { label: "Currency", value: c.currency }, { label: "Max discount", value: `${formatPct(c.max_discount_pct, 0)} (${c.tier_name})` }, { label: "Billing address", value: addr("billing") }, { label: "Shipping address", value: addr("shipping") }, { label: "Customer since", value: formatDate(c.created_at) }, { label: "Notes", value: c.notes }]} /></Card>
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {!h ? <Skeleton className="h-40" /> : (
        <Card>
          {tab === "quotes" && (h.quotes.length ? h.quotes.map((q) => <div key={q.id} className={row}><Link href={`/workspace/quotations/${q.id}`} className="link font-medium">{q.quote_number}</Link><span className="text-zinc-500">{q.owner_name}</span><StatusBadge status={q.status} /><span className="tabular-nums">{formatCurrency(q.total)}</span><span className="text-xs text-zinc-400">{formatDate(q.created_at)}</span></div>) : <p className="text-sm text-zinc-500">No quotations yet.</p>)}
          {tab === "orders" && (h.orders.length ? h.orders.map((o) => <div key={o.id} className={row}><Link href={`/workspace/quotations/${o.id}/fulfillment`} className="link font-medium">{o.order_number}</Link><StatusBadge status={o.fulfillment_status} /><StatusBadge status={o.billing_status} /><span className="tabular-nums">{formatCurrency(o.total)}</span><span className="text-xs text-zinc-400">{formatDateTime(o.confirmed_at)}</span></div>) : <p className="text-sm text-zinc-500">No orders yet.</p>)}
          {tab === "invoices" && (h.invoices.length ? h.invoices.map((i) => <div key={i.id} className={row}><Link href={`/workspace/invoices/${i.id}`} className="link font-medium">{i.invoice_number}</Link><Badge>{i.invoice_type.replace("_", " ")}</Badge><StatusBadge status={i.status} /><span className="tabular-nums">{formatCurrency(i.amount_paid)} / {formatCurrency(i.amount)}</span><span className="text-xs text-zinc-400">due {formatDate(i.due_date)}</span></div>) : <p className="text-sm text-zinc-500">No invoices yet.</p>)}
          {tab === "payments" && (h.payments.length ? h.payments.map((p) => <div key={p.id} className={row}><Link href={`/workspace/invoices/${p.invoice_id}`} className="link">{p.invoice_number}</Link><StatusBadge status={p.direction} /><span>{p.method}</span><span className="tabular-nums">{formatCurrency(p.amount)}</span><span className="text-xs text-zinc-400">{formatDateTime(p.paid_at)}</span></div>) : <p className="text-sm text-zinc-500">No payments yet.</p>)}
          {tab === "subscriptions" && (h.subscriptions.length ? h.subscriptions.map((s) => <div key={s.id} className={row}><Link href={`/workspace/subscriptions/${s.id}`} className="link font-medium">{s.plan_name}</Link><span>{s.quantity} seats</span><StatusBadge status={s.status} /><span className="text-xs text-zinc-400">next bill {formatDate(s.next_billing_date)}</span></div>) : <p className="text-sm text-zinc-500">No subscriptions.</p>)}
          {tab === "alerts" && (h.alerts.length ? h.alerts.map((a) => <div key={a.id} className={row}><StatusBadge status={a.severity} /><span className="flex-1">{a.message}</span><StatusBadge status={a.status} /></div>) : <p className="text-sm text-zinc-500">No alerts.</p>)}
          {tab === "activity" && (h.activity.length ? h.activity.map((a) => <div key={a.id} className={row}><span><span className="font-medium">{titleCase(a.action)}</span> <span className="text-zinc-500">by {a.user}</span>{a.reason && <span className="block text-xs text-zinc-500">{a.reason}</span>}</span><span className="text-xs text-zinc-400">{formatDateTime(a.timestamp)}</span></div>) : <p className="text-sm text-zinc-500">No activity.</p>)}
        </Card>
      )}
      <CustomerFormModal open={edit} onClose={() => setEdit(false)} initial={c} onSaved={(u) => { setData(() => u); setEdit(false); toast.success("Customer updated."); }} />
      <NewQuoteModal open={newQuote} onClose={() => setNewQuote(false)} customerId={c.id} />
    </div>
  );
}
