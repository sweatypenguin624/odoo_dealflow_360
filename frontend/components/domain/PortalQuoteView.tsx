"use client";
import { useState } from "react";
import { portalApi } from "@/lib/api/portal";
import type { PortalQuote } from "@/lib/api/types";
import { errorMessage } from "@/lib/api/client";
import { formatCurrency, formatDate, formatDateTime, titleCase } from "@/lib/format";
import { Badge, Button, Card, ConfirmDialog, Field, FormError, Input, Modal, StatusBadge, Textarea } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";

/**
 * The customer-facing quotation. Works for both entry points: a tokenised
 * email link (token set) and a signed-in customer (quoteId set).
 */
export function PortalQuoteView({ quote, token, quoteId, onChanged }: { quote: PortalQuote; token: string | null; quoteId?: number; onChanged: () => void }) {
  const toast = useToast();
  const [commentFor, setCommentFor] = useState<number | null>(null);
  const [commentText, setCommentText] = useState("");
  const [counterOpen, setCounterOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [proposals, setProposals] = useState<Record<number, { discount: string; quantity: string }>>({});
  const [confirmed, setConfirmed] = useState<{ order_number: string | null } | null>(null);

  async function sendComment() {
    if (commentFor === null) return;
    setBusy(true);
    setFormError(null);
    try {
      await portalApi.comment(token, quoteId, commentFor, commentText);
      toast.success("Comment sent to your sales contact.");
      setCommentFor(null);
      setCommentText("");
      onChanged();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function sendCounter() {
    const lines = Object.entries(proposals)
      .filter(([, v]) => v.discount !== "" || v.quantity !== "")
      .map(([id, v]) => ({
        quote_line_id: Number(id),
        ...(v.discount !== "" ? { proposed_discount_pct: Number(v.discount) } : {}),
        ...(v.quantity !== "" ? { proposed_quantity: Number(v.quantity) } : {}),
      }));
    if (lines.length === 0) {
      setFormError("Change the discount or quantity on at least one line.");
      return;
    }
    setBusy(true);
    setFormError(null);
    try {
      await portalApi.counter(token, quoteId, lines, message || undefined);
      toast.success("Your proposal has been sent for review.");
      setCounterOpen(false);
      setProposals({});
      setMessage("");
      onChanged();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function confirmQuote() {
    setBusy(true);
    try {
      const r = await portalApi.confirm(token, quoteId);
      setConfirmed({ order_number: r.order_number });
      setConfirmOpen(false);
      onChanged();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const setProposal = (lineId: number, key: "discount" | "quantity", value: string) =>
    setProposals((p) => ({ ...p, [lineId]: { ...{ discount: "", quantity: "" }, ...p[lineId], [key]: value } }));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">Quotation {quote.quote_number}</h1>
          <p className="mt-0.5 text-sm text-zinc-500">
            Prepared for {quote.customer_name}
            {quote.rep_name ? ` by ${quote.rep_name}` : ""}
            {quote.valid_until ? ` · valid until ${formatDate(quote.valid_until)}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={quote.status} />
          {quote.order_number && <Badge tone="green">Order {quote.order_number}</Badge>}
          {quote.can_negotiate && <Button variant="secondary" onClick={() => { setFormError(null); setCounterOpen(true); }}>Propose changes</Button>}
          {quote.can_confirm && <Button variant="success" onClick={() => setConfirmOpen(true)} data-testid="portal-confirm">Accept quotation</Button>}
        </div>
      </div>

      {confirmed && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
          <p className="font-medium">Thank you — your order is confirmed.</p>
          {confirmed.order_number && <p>Your order reference is <strong>{confirmed.order_number}</strong>. Your sales contact will follow up with delivery details.</p>}
        </div>
      )}

      {quote.pending_review && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          Your proposed changes are with the sales team for review. We&apos;ll be in touch shortly.
        </div>
      )}

      <Card title="Your quotation" padded={false}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500">
              <tr>
                <th className="px-4 py-2">Item</th>
                <th className="px-2 py-2 text-right">Qty</th>
                <th className="px-2 py-2 text-right">Unit price</th>
                <th className="px-2 py-2 text-right">Discount</th>
                <th className="px-2 py-2 text-right">Total</th>
                <th className="px-2 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {quote.lines.map((l) => (
                <tr key={l.id}>
                  <td className="px-4 py-2">
                    <p className="font-medium text-zinc-900">{l.description ?? l.product_name}</p>
                    <p className="text-xs text-zinc-500">
                      {l.sku}
                      {l.is_recurring && <Badge tone="purple" className="ml-1">Billed {l.billing_interval ?? "recurring"}</Badge>}
                    </p>
                    {l.comments.length > 0 && (
                      <ul className="mt-1 space-y-1">
                        {l.comments.map((c) => (
                          <li key={c.id} className={`rounded px-2 py-1 text-xs ${c.author_type === "customer" ? "bg-blue-50 text-blue-900" : "bg-zinc-100 text-zinc-700"}`}>
                            <span className="font-medium">{c.author_name}</span> · {formatDateTime(c.created_at)}
                            <span className="block">{c.comment}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                  <td className="px-2 py-2 text-right">{l.quantity}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{formatCurrency(l.unit_price, quote.currency)}</td>
                  <td className="px-2 py-2 text-right">{Number(l.discount_pct) > 0 ? `${Number(l.discount_pct).toFixed(1)}%` : "—"}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{formatCurrency(l.line_total, quote.currency)}</td>
                  <td className="px-2 py-2 text-right">
                    <Button size="sm" variant="ghost" onClick={() => { setCommentFor(l.id); setCommentText(""); setFormError(null); }}>Comment</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="flex justify-end">
        <dl className="w-full max-w-xs space-y-1 text-sm">
          <div className="flex justify-between"><dt className="text-zinc-500">Subtotal</dt><dd className="tabular-nums">{formatCurrency(quote.subtotal, quote.currency)}</dd></div>
          <div className="flex justify-between"><dt className="text-zinc-500">Discounts</dt><dd className="tabular-nums">−{formatCurrency(quote.discount_total, quote.currency)}</dd></div>
          <div className="flex justify-between"><dt className="text-zinc-500">Tax</dt><dd className="tabular-nums">{formatCurrency(quote.tax_total, quote.currency)}</dd></div>
          <div className="flex justify-between border-t border-zinc-200 pt-1 text-base font-semibold"><dt>Total</dt><dd className="tabular-nums">{formatCurrency(quote.total, quote.currency)}</dd></div>
          {quote.promised_delivery_date && <p className="pt-1 text-xs text-zinc-500">Estimated delivery {formatDate(quote.promised_delivery_date)}</p>}
        </dl>
      </div>

      {quote.history.length > 0 && (
        <Card title="Your previous proposals">
          <ul className="space-y-2 text-sm">
            {quote.history.map((h) => (
              <li key={h.id} className="rounded-md border border-zinc-200 p-2">
                <div className="flex items-center justify-between">
                  <StatusBadge status={h.status} />
                  <span className="text-xs text-zinc-500">{formatDateTime(h.created_at)}</span>
                </div>
                {h.message && <p className="mt-1 italic text-zinc-700">“{h.message}”</p>}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Modal
        open={commentFor !== null}
        onClose={() => setCommentFor(null)}
        title="Add a comment"
        size="sm"
        footer={<><Button variant="secondary" onClick={() => setCommentFor(null)} disabled={busy}>Cancel</Button><Button onClick={sendComment} loading={busy} disabled={!commentText.trim()}>Send</Button></>}
      >
        <div className="space-y-2">
          <FormError message={formError} />
          <Field label="Your comment"><Textarea rows={3} value={commentText} onChange={(e) => setCommentText(e.target.value)} placeholder="Ask a question or explain what you need on this line" /></Field>
        </div>
      </Modal>

      <Modal
        open={counterOpen}
        onClose={() => setCounterOpen(false)}
        title="Propose changes"
        size="lg"
        footer={<><Button variant="secondary" onClick={() => setCounterOpen(false)} disabled={busy}>Cancel</Button><Button onClick={sendCounter} loading={busy}>Send proposal</Button></>}
      >
        <div className="space-y-3">
          <FormError message={formError} />
          <p className="text-sm text-zinc-600">Leave a field blank to keep the current value. Your sales contact reviews every proposal before it takes effect.</p>
          <div className="space-y-2">
            {quote.lines.map((l) => (
              <div key={l.id} className="grid grid-cols-[1fr_120px_120px] items-end gap-2">
                <div>
                  <p className="text-sm font-medium text-zinc-900">{l.description ?? l.product_name}</p>
                  <p className="text-xs text-zinc-500">Now: {l.quantity} × {formatCurrency(l.unit_price, quote.currency)} at {Number(l.discount_pct).toFixed(1)}%</p>
                </div>
                <Field label="Discount %"><Input type="number" min={0} max={100} step={0.5} value={proposals[l.id]?.discount ?? ""} onChange={(e) => setProposal(l.id, "discount", e.target.value)} /></Field>
                <Field label="Quantity"><Input type="number" min={1} value={proposals[l.id]?.quantity ?? ""} onChange={(e) => setProposal(l.id, "quantity", e.target.value)} /></Field>
              </div>
            ))}
          </div>
          <Field label="Message"><Textarea rows={2} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Anything the team should know about this request" /></Field>
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        onConfirm={confirmQuote}
        title="Accept this quotation?"
        message={`Accepting confirms the order for ${formatCurrency(quote.total, quote.currency)} and starts fulfillment. This can't be undone online.`}
        confirmLabel="Accept quotation"
        loading={busy}
      />
    </div>
  );
}

export function PortalTotals({ quote }: { quote: PortalQuote }) {
  return <p className="text-sm text-zinc-500">{titleCase(quote.status)} · {formatCurrency(quote.total, quote.currency)}</p>;
}
