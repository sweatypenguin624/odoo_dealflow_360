"use client";
import Link from "next/link";
import { use, useState } from "react";
import { invoices, type InvoiceDetail } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useApi } from "@/lib/hooks/useApi";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatCurrency, formatDate, formatDateTime, titleCase } from "@/lib/format";
import { Badge, Button, Card, ConfirmDialog, DescriptionList, ErrorState, Field, FormError, Input, Modal, PageHeader, Select, Skeleton, StatusBadge, Textarea } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";

const METHODS = ["bank_transfer", "credit_card", "ach", "check", "cash", "wire"];

export default function InvoiceDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const invoiceId = Number(use(params).id);
  const { can } = useAuth();
  const toast = useToast();
  const { data: invoice, error, reload, setData } = useApi(() => invoices.get(invoiceId), [invoiceId]);
  const [dialog, setDialog] = useState<"pay" | "refund" | "void" | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [pay, setPay] = useState({ amount: "", method: "bank_transfer", reference: "", notes: "" });
  const [refund, setRefund] = useState({ amount: "", method: "bank_transfer", reference: "", reason: "" });
  const [voidReason, setVoidReason] = useState("");
  // A fresh key per dialog opening: retrying a failed payment must not reuse a
  // key the server may have already recorded.
  const [idemKey, setIdemKey] = useState("");

  function openPay() {
    if (!invoice) return;
    setPay({ amount: String(invoice.outstanding), method: "bank_transfer", reference: "", notes: "" });
    setIdemKey(crypto.randomUUID());
    setFormError(null);
    setDialog("pay");
  }

  async function submit(kind: "pay" | "refund" | "void") {
    setBusy(true);
    setFormError(null);
    try {
      let updated: InvoiceDetail;
      if (kind === "pay") {
        updated = await invoices.pay(invoiceId, { amount: Number(pay.amount), method: pay.method, reference: pay.reference || undefined, notes: pay.notes || undefined }, idemKey);
        toast.success("Payment recorded.");
      } else if (kind === "refund") {
        updated = await invoices.refund(invoiceId, { amount: Number(refund.amount), method: refund.method, reference: refund.reference || undefined, reason: refund.reason || undefined });
        toast.success("Refund recorded.");
      } else {
        updated = await invoices.void(invoiceId, voidReason);
        toast.success("Invoice voided.");
      }
      setData(() => updated);
      setDialog(null);
      setVoidReason("");
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!invoice) return <Skeleton className="h-64" />;
  const actions = invoice.available_actions;
  const manage = can("invoice:manage");

  return (
    <div className="space-y-5">
      <PageHeader
        breadcrumb={{ href: "/workspace/invoices", label: "Invoices" }}
        title={<span className="flex flex-wrap items-center gap-2">{invoice.invoice_number} <StatusBadge status={invoice.status} /><Badge tone={invoice.invoice_type === "recurring" ? "purple" : "neutral"}>{invoice.invoice_type.replaceAll("_", " ")}</Badge>{invoice.is_overdue && invoice.status !== "void" && <Badge tone="red">{invoice.days_overdue} days overdue</Badge>}</span>}
        subtitle={<>{invoice.customer_id ? <Link href={`/workspace/customers/${invoice.customer_id}`} className="link">{invoice.customer_name}</Link> : invoice.customer_name} · <Link href={`/workspace/quotations/${invoice.quote_id}`} className="link">{invoice.order_number ?? invoice.quote_number}</Link> · issued {formatDate(invoice.issued_at)}</>}
        actions={
          <>
            {manage && actions.includes("pay") && <Button variant="success" onClick={openPay}>Record payment</Button>}
            {manage && actions.includes("refund") && <Button variant="secondary" onClick={() => { setRefund({ amount: String(invoice.amount_paid), method: "bank_transfer", reference: "", reason: "" }); setFormError(null); setDialog("refund"); }}>Refund</Button>}
            {manage && actions.includes("void") && <Button variant="ghost" onClick={() => { setFormError(null); setDialog("void"); }}>Void</Button>}
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {[["Subtotal", formatCurrency(invoice.subtotal, invoice.currency)], ["Discounts", `−${formatCurrency(invoice.discount_total, invoice.currency)}`], ["Tax", formatCurrency(invoice.tax_total, invoice.currency)], ["Total", formatCurrency(invoice.amount, invoice.currency)], ["Outstanding", formatCurrency(invoice.outstanding, invoice.currency)]].map(([l, v]) => (
          <div key={l} className="card p-3"><p className="text-xs uppercase tracking-wide text-zinc-500">{l}</p><p className="text-lg font-semibold tabular-nums text-zinc-900">{v}</p></div>
        ))}
      </div>

      {invoice.status === "void" && (
        <div className="rounded-md border border-zinc-300 bg-zinc-50 p-3 text-sm text-zinc-700">
          Voided {formatDateTime(invoice.voided_at)}{invoice.void_reason ? ` — ${invoice.void_reason}` : ""}.
        </div>
      )}

      <Card title="Invoice lines" padded={false}>
        <table className="w-full text-sm">
          <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500">
            <tr><th className="px-4 py-2">Description</th><th className="px-2 py-2 text-right">Qty</th><th className="px-2 py-2 text-right">Unit price</th><th className="px-2 py-2 text-right">Discount</th><th className="px-2 py-2 text-right">Tax</th><th className="px-2 py-2 text-right">Line total</th></tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {invoice.lines.map((l) => (
              <tr key={l.id}>
                <td className="px-4 py-2">{l.description}</td>
                <td className="px-2 py-2 text-right">{l.quantity}</td>
                <td className="px-2 py-2 text-right tabular-nums">{formatCurrency(l.unit_price, invoice.currency)}</td>
                <td className="px-2 py-2 text-right">{Number(l.discount_pct).toFixed(1)}%</td>
                <td className="px-2 py-2 text-right tabular-nums">{formatCurrency(l.tax_amount, invoice.currency)}</td>
                <td className="px-2 py-2 text-right tabular-nums">{formatCurrency(l.line_total, invoice.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Payments & refunds" padded={false}>
        {invoice.payments.length === 0 ? <p className="p-4 text-sm text-zinc-500">Nothing recorded yet.</p> : (
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500">
              <tr><th className="px-4 py-2">Reference</th><th className="px-2 py-2">Direction</th><th className="px-2 py-2">Method</th><th className="px-2 py-2 text-right">Amount</th><th className="px-2 py-2">Status</th><th className="px-2 py-2">Recorded</th></tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {invoice.payments.map((p) => (
                <tr key={p.id}>
                  <td className="px-4 py-2">{p.payment_number ?? "—"}<span className="block text-xs text-zinc-500">{p.reference ?? ""}</span></td>
                  <td className="px-2 py-2"><StatusBadge status={p.direction} /></td>
                  <td className="px-2 py-2">{titleCase(p.method)}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{formatCurrency(p.amount, invoice.currency)}</td>
                  <td className="px-2 py-2"><StatusBadge status={p.status} /></td>
                  <td className="px-2 py-2 text-xs">{formatDateTime(p.paid_at)}<span className="block text-zinc-400">{p.recorded_by}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card title="Details">
        <DescriptionList columns={3} items={[
          { label: "Billing period", value: invoice.billing_period_start ? `${formatDate(invoice.billing_period_start)} – ${formatDate(invoice.billing_period_end)}` : "—" },
          { label: "Due date", value: formatDate(invoice.due_date) },
          { label: "Paid at", value: formatDateTime(invoice.paid_at) },
          { label: "Pipeline stage", value: titleCase(invoice.pipeline_stage) },
          { label: "Subscription", value: invoice.subscription_id ? <Link href={`/workspace/subscriptions/${invoice.subscription_id}`} className="link">#{invoice.subscription_id}</Link> : "—" },
          { label: "Notes", value: invoice.notes },
        ]} />
      </Card>

      <Modal open={dialog === "pay"} onClose={() => setDialog(null)} title="Record payment" size="sm" footer={<><Button variant="secondary" onClick={() => setDialog(null)} disabled={busy}>Cancel</Button><Button variant="success" onClick={() => submit("pay")} loading={busy}>Record payment</Button></>}>
        <div className="space-y-3">
          <FormError message={formError} />
          <p className="text-sm text-zinc-600">Outstanding: <strong>{formatCurrency(invoice.outstanding, invoice.currency)}</strong>. Partial payments are allowed.</p>
          <Field label="Amount" required><Input type="number" min={0.01} step={0.01} value={pay.amount} onChange={(e) => setPay({ ...pay, amount: e.target.value })} /></Field>
          <Field label="Method" required><Select value={pay.method} onChange={(e) => setPay({ ...pay, method: e.target.value })}>{METHODS.map((m) => <option key={m} value={m}>{titleCase(m)}</option>)}</Select></Field>
          <Field label="Reference"><Input value={pay.reference} onChange={(e) => setPay({ ...pay, reference: e.target.value })} placeholder="Transaction or cheque number" /></Field>
          <Field label="Notes"><Textarea rows={2} value={pay.notes} onChange={(e) => setPay({ ...pay, notes: e.target.value })} /></Field>
        </div>
      </Modal>

      <Modal open={dialog === "refund"} onClose={() => setDialog(null)} title="Record refund" size="sm" footer={<><Button variant="secondary" onClick={() => setDialog(null)} disabled={busy}>Cancel</Button><Button variant="danger" onClick={() => submit("refund")} loading={busy}>Record refund</Button></>}>
        <div className="space-y-3">
          <FormError message={formError} />
          <p className="text-sm text-zinc-600">Paid to date: <strong>{formatCurrency(invoice.amount_paid, invoice.currency)}</strong>.</p>
          <Field label="Amount" required><Input type="number" min={0.01} step={0.01} value={refund.amount} onChange={(e) => setRefund({ ...refund, amount: e.target.value })} /></Field>
          <Field label="Method" required><Select value={refund.method} onChange={(e) => setRefund({ ...refund, method: e.target.value })}>{METHODS.map((m) => <option key={m} value={m}>{titleCase(m)}</option>)}</Select></Field>
          <Field label="Reference"><Input value={refund.reference} onChange={(e) => setRefund({ ...refund, reference: e.target.value })} /></Field>
          <Field label="Reason"><Textarea rows={2} value={refund.reason} onChange={(e) => setRefund({ ...refund, reason: e.target.value })} /></Field>
        </div>
      </Modal>

      <ConfirmDialog
        open={dialog === "void"}
        onClose={() => setDialog(null)}
        onConfirm={() => submit("void")}
        title="Void this invoice?"
        message="Voiding cancels the invoice. It stays on record for audit but no longer counts towards outstanding revenue."
        confirmLabel="Void invoice"
        danger
        loading={busy}
      >
        <div className="mt-2 space-y-2">
          <FormError message={formError} />
          <Field label="Reason" required><Textarea rows={2} value={voidReason} onChange={(e) => setVoidReason(e.target.value)} /></Field>
        </div>
      </ConfirmDialog>
    </div>
  );
}
