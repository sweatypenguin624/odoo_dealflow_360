"use client";
import Link from "next/link";
import { use, useState } from "react";
import { invoices, subscriptions } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useApi } from "@/lib/hooks/useApi";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatCurrency, formatDate, titleCase, todayIso } from "@/lib/format";
import { Badge, Button, Card, ConfirmDialog, DescriptionList, ErrorState, Field, FormError, Input, Modal, PageHeader, Skeleton, StatusBadge, Textarea } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";

export default function SubscriptionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const id = Number(use(params).id);
  const { can } = useAuth();
  const toast = useToast();
  const { data: sub, error, reload } = useApi(() => subscriptions.get(id), [id]);
  const [dialog, setDialog] = useState<"quantity" | "cancel" | "advance" | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [qty, setQty] = useState({ new_quantity: 1, change_date: todayIso() });
  const [cancel, setCancel] = useState({ cancellation_date: todayIso(), reason: "" });

  async function run(name: string, fn: () => Promise<unknown>, ok: string) {
    setBusy(name);
    setFormError(null);
    try {
      await fn();
      toast.success(ok);
      setDialog(null);
      reload();
    } catch (err) {
      const msg = errorMessage(err);
      if (dialog) setFormError(msg); else toast.error(msg);
    } finally {
      setBusy(null);
    }
  }

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!sub) return <Skeleton className="h-64" />;
  const actions = sub.available_actions;
  const manage = can("subscription:manage");

  return (
    <div className="space-y-5">
      <PageHeader
        breadcrumb={{ href: "/workspace/subscriptions", label: "Subscriptions" }}
        title={<span className="flex flex-wrap items-center gap-2">{sub.plan_name} <StatusBadge status={sub.status} /><Badge tone="purple">{titleCase(sub.interval)}</Badge></span>}
        subtitle={<>{sub.customer_id ? <Link href={`/workspace/customers/${sub.customer_id}`} className="link">{sub.customer_name}</Link> : sub.customer_name} · {sub.product_name}{sub.quote_id ? <> · <Link href={`/workspace/quotations/${sub.quote_id}`} className="link">{sub.quote_number}</Link></> : null}</>}
        actions={
          <>
            {manage && actions.includes("change_quantity") && <Button variant="secondary" onClick={() => { setQty({ new_quantity: sub.quantity, change_date: todayIso() }); setFormError(null); setDialog("quantity"); }}>Change quantity</Button>}
            {manage && actions.includes("pause") && <Button variant="secondary" loading={busy === "pause"} onClick={() => run("pause", () => subscriptions.pause(id), "Subscription paused.")}>Pause</Button>}
            {manage && actions.includes("resume") && <Button variant="success" loading={busy === "resume"} onClick={() => run("resume", () => subscriptions.resume(id), "Subscription resumed.")}>Resume</Button>}
            {manage && actions.includes("advance_cycle") && <Button loading={busy === "advance"} onClick={() => setDialog("advance")}>Advance cycle</Button>}
            {manage && actions.includes("generate_invoice") && <Button variant="secondary" loading={busy === "invoice"} onClick={() => run("invoice", () => invoices.generateRecurring(id), "Invoice generated for the current cycle.")}>Generate invoice</Button>}
            {manage && actions.includes("cancel") && <Button variant="ghost" onClick={() => { setCancel({ cancellation_date: todayIso(), reason: "" }); setFormError(null); setDialog("cancel"); }}>Cancel</Button>}
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <div className="card p-3"><p className="text-xs uppercase tracking-wide text-zinc-500">Quantity</p><p className="text-lg font-semibold tabular-nums">{sub.quantity}</p></div>
        <div className="card p-3"><p className="text-xs uppercase tracking-wide text-zinc-500">Unit price</p><p className="text-lg font-semibold tabular-nums">{formatCurrency(sub.unit_price)}</p></div>
        <div className="card p-3"><p className="text-xs uppercase tracking-wide text-zinc-500">Per cycle</p><p className="text-lg font-semibold tabular-nums">{formatCurrency(sub.cycle_amount)}</p></div>
        <div className="card p-3"><p className="text-xs uppercase tracking-wide text-zinc-500">Current cycle</p><p className="text-sm font-medium">{formatDate(sub.current_cycle_start)} – {formatDate(sub.current_cycle_end)}</p></div>
        <div className="card p-3"><p className="text-xs uppercase tracking-wide text-zinc-500">Next billing</p><p className="text-sm font-medium">{formatDate(sub.next_billing_date)}</p></div>
      </div>

      <Card title="Billing events" padded={false}>
        {sub.billing_events.length === 0 ? <p className="p-4 text-sm text-zinc-500">No billing events yet.</p> : (
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500">
              <tr><th className="px-4 py-2">Date</th><th className="px-2 py-2">Event</th><th className="px-2 py-2">Description</th><th className="px-2 py-2 text-right">Amount</th><th className="px-2 py-2">Invoice</th></tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {sub.billing_events.map((e) => (
                <tr key={e.id}>
                  <td className="px-4 py-2">{formatDate(e.event_date)}</td>
                  <td className="px-2 py-2"><Badge tone={e.event_type.includes("credit") || Number(e.amount) < 0 ? "amber" : "neutral"}>{titleCase(e.event_type)}</Badge></td>
                  <td className="px-2 py-2 text-zinc-700">{e.description}</td>
                  <td className={`px-2 py-2 text-right tabular-nums ${Number(e.amount) < 0 ? "text-amber-700" : ""}`}>{formatCurrency(e.amount)}</td>
                  <td className="px-2 py-2 text-xs">{e.invoice_id ? <Link href={`/workspace/invoices/${e.invoice_id}`} className="link">#{e.invoice_id}</Link> : e.applied_to_invoice_id ? <span className="text-zinc-500">applied to #{e.applied_to_invoice_id}</span> : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card title="Invoices" padded={false}>
        {sub.invoices.length === 0 ? <p className="p-4 text-sm text-zinc-500">No invoices yet.</p> : (
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500">
              <tr><th className="px-4 py-2">Invoice</th><th className="px-2 py-2">Status</th><th className="px-2 py-2">Period</th><th className="px-2 py-2 text-right">Amount</th><th className="px-2 py-2 text-right">Paid</th><th className="px-2 py-2">Due</th></tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {sub.invoices.map((i) => (
                <tr key={i.id}>
                  <td className="px-4 py-2"><Link href={`/workspace/invoices/${i.id}`} className="link font-medium">{i.invoice_number}</Link></td>
                  <td className="px-2 py-2"><StatusBadge status={i.status} /></td>
                  <td className="px-2 py-2 text-xs">{i.billing_period_start ? `${formatDate(i.billing_period_start)} – ${formatDate(i.billing_period_end)}` : "—"}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{formatCurrency(i.amount)}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{formatCurrency(i.amount_paid)}</td>
                  <td className="px-2 py-2 text-xs">{formatDate(i.due_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card title="Details">
        <DescriptionList columns={3} items={[
          { label: "Started", value: formatDate(sub.start_date) },
          { label: "Paused at", value: formatDate(sub.paused_at) },
          { label: "Cancelled at", value: formatDate(sub.cancelled_at) },
        ]} />
      </Card>

      <Modal
        open={dialog === "quantity"}
        onClose={() => setDialog(null)}
        title="Change quantity"
        size="sm"
        footer={<><Button variant="secondary" onClick={() => setDialog(null)} disabled={busy === "quantity"}>Cancel</Button><Button loading={busy === "quantity"} onClick={() => run("quantity", () => subscriptions.changeQuantity(id, qty), "Quantity changed — a prorated billing event was recorded.")}>Apply change</Button></>}
      >
        <div className="space-y-3">
          <FormError message={formError} />
          <p className="text-sm text-zinc-600">Current quantity: <strong>{sub.quantity}</strong>. The change is prorated over the remainder of the cycle ending {formatDate(sub.current_cycle_end)}.</p>
          <Field label="New quantity" required><Input type="number" min={1} value={qty.new_quantity} onChange={(e) => setQty({ ...qty, new_quantity: Math.max(1, Number(e.target.value)) })} /></Field>
          <Field label="Effective date" required><Input type="date" value={qty.change_date} onChange={(e) => setQty({ ...qty, change_date: e.target.value })} /></Field>
        </div>
      </Modal>

      <Modal
        open={dialog === "cancel"}
        onClose={() => setDialog(null)}
        title="Cancel subscription"
        size="sm"
        footer={<><Button variant="secondary" onClick={() => setDialog(null)} disabled={busy === "cancel"}>Keep it</Button><Button variant="danger" loading={busy === "cancel"} onClick={() => run("cancel", () => subscriptions.cancel(id, cancel), "Subscription cancelled.")}>Cancel subscription</Button></>}
      >
        <div className="space-y-3">
          <FormError message={formError} />
          <p className="text-sm text-zinc-600">A credit is recorded for the unused part of the current cycle.</p>
          <Field label="Cancellation date" required><Input type="date" value={cancel.cancellation_date} onChange={(e) => setCancel({ ...cancel, cancellation_date: e.target.value })} /></Field>
          <Field label="Reason"><Textarea rows={2} value={cancel.reason} onChange={(e) => setCancel({ ...cancel, reason: e.target.value })} /></Field>
        </div>
      </Modal>

      <ConfirmDialog
        open={dialog === "advance"}
        onClose={() => setDialog(null)}
        onConfirm={() => run("advance", () => subscriptions.advance(id), "Cycle advanced.")}
        title="Advance to the next cycle?"
        message={`This renews the subscription past ${formatDate(sub.current_cycle_end)} and raises the next invoice. Running it twice for the same cycle is safe — the second run is ignored.`}
        confirmLabel="Advance cycle"
        loading={busy === "advance"}
      />
    </div>
  );
}
