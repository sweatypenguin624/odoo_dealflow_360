"use client";
import Link from "next/link";
import { use, useState } from "react";
import { quotes, type QuoteDetail } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useApi } from "@/lib/hooks/useApi";
import { formatCurrency, formatDate, formatDateTime, formatPct, titleCase } from "@/lib/format";
import { Badge, Button, Card, ConfirmDialog, DescriptionList, ErrorState, Field, Input, LinkButton, Modal, PageHeader, Skeleton, StatusBadge, Tabs, Textarea } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { ProductPicker } from "@/components/domain/ProductPicker";
import { QuoteLinesTable } from "@/components/domain/QuoteLinesTable";
import { RiskPanel } from "@/components/domain/RiskPanel";
import { UpsellPanel } from "@/components/domain/UpsellPanel";
import { ApprovalPanel } from "@/components/domain/ApprovalPanel";
import { Timeline } from "@/components/domain/Timeline";
import { NegotiationPanel } from "@/components/domain/NegotiationPanel";

export default function QuoteDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const quoteId = Number(use(params).id);
  const toast = useToast();
  const { data: quote, error, loading, reload, setData } = useApi(() => quotes.get(quoteId), [quoteId]);
  const [tab, setTab] = useState("builder");
  const history = useApi(() => quotes.history(quoteId), [quoteId, quote?.version, quote?.status], { enabled: tab === "history" });
  const negotiation = useApi(() => quotes.negotiation(quoteId), [quoteId, quote?.status], { enabled: tab === "negotiation" });
  const [saving, setSaving] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [dialog, setDialog] = useState<"cancel" | "revise" | "confirm" | null>(null);
  const [reason, setReason] = useState("");
  const [sendResult, setSendResult] = useState<{ portal_url: string; email_status: string; email_to: string | null } | null>(null);
  const [header, setHeader] = useState<{ order_discount_pct: string; valid_until: string; promised_delivery_date: string; notes: string } | null>(null);

  const apply = (q: QuoteDetail) => setData(() => q);

  async function run(action: string, fn: () => Promise<QuoteDetail | void>, ok: string) {
    setBusy(action);
    try {
      const q = await fn();
      if (q) apply(q); else reload();
      toast.success(ok);
    } catch (err) {
      toast.error(errorMessage(err));
      reload();
    } finally {
      setBusy(null); setDialog(null); setReason("");
    }
  }

  async function updateLine(lineId: number, patch: { quantity?: number; discount_pct?: number }) {
    setSaving((s) => new Set(s).add(lineId));
    try {
      await quotes.updateLine(quoteId, lineId, patch);
      apply(await quotes.get(quoteId));
    } catch (err) {
      toast.error(errorMessage(err)); reload();
    } finally {
      setSaving((s) => { const n = new Set(s); n.delete(lineId); return n; });
    }
  }

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!quote || loading && !quote) return <div className="space-y-3"><Skeleton className="h-8 w-64" /><Skeleton className="h-40" /></div>;
  const actions = quote.available_actions;
  const canConfirm = ["approved", "sent", "under_negotiation"].includes(quote.status) && (actions.includes("send") || actions.includes("resend")) && quote.approval_valid;

  return (
    <div className="space-y-5">
      <PageHeader
        breadcrumb={{ href: "/workspace/quotations", label: "Quotations" }}
        title={<span className="flex flex-wrap items-center gap-2">{quote.quote_number} <StatusBadge status={quote.status} /> <Badge tone="neutral">v{quote.version}</Badge>{quote.order_number && <Badge tone="green">{quote.order_number}</Badge>}</span>}
        subtitle={<><Link href={`/workspace/customers/${quote.customer_id}`} className="link">{quote.customer_name}</Link> · {quote.customer_tier} tier · owner {quote.owner_name ?? "unassigned"} · valid until {formatDate(quote.valid_until)}</>}
        actions={
          <>
            {actions.includes("submit") && <Button onClick={() => run("submit", async () => (await quotes.submit(quoteId)).quote, "Submitted — routing evaluated by the risk engine.")} loading={busy === "submit"} disabled={quote.lines.length === 0} data-testid="submit-btn">Submit for approval</Button>}
            {(actions.includes("send") || actions.includes("resend")) && <Button onClick={() => run("send", async () => { const r = await quotes.send(quoteId); setSendResult(r); return r.quote; }, "Quotation sent to the customer.")} loading={busy === "send"} data-testid="send-btn">{actions.includes("send") ? "Send to customer" : "Resend link"}</Button>}
            {canConfirm && <Button variant="success" onClick={() => setDialog("confirm")} data-testid="confirm-btn">Confirm order</Button>}
            {actions.includes("revise") && <Button variant="secondary" onClick={() => setDialog("revise")}>Revise</Button>}
            {actions.includes("cancel") && <Button variant="ghost" onClick={() => setDialog("cancel")}>Cancel</Button>}
            {quote.status === "confirmed" && <LinkButton href={`/workspace/quotations/${quoteId}/fulfillment`} variant="primary">Fulfillment →</LinkButton>}
            {quote.status === "confirmed" && <LinkButton href={`/workspace/quotations/${quoteId}/billing`}>Billing →</LinkButton>}
          </>
        }
      />

      {sendResult && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900" data-testid="send-result">
          Portal link {sendResult.email_status === "sent" ? `emailed to ${sendResult.email_to}` : `created (email ${sendResult.email_status}${sendResult.email_to ? "" : " — customer has no email on file"})`}: <a href={sendResult.portal_url} target="_blank" rel="noreferrer" className="link break-all">{sendResult.portal_url}</a>
        </div>
      )}
      {!quote.approval_valid && quote.approved_version !== null && !["draft", "revision_required", "pending_approval"].includes(quote.status) && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">This version changed after approval — it must be re-submitted before it can be sent or confirmed.</div>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-6" data-testid="totals">
        {[["Subtotal", formatCurrency(quote.subtotal)], ["Discounts", `−${formatCurrency(quote.discount_total)}`], ["Tax", formatCurrency(quote.tax_total)], ["Total", formatCurrency(quote.total)], ["Margin", `${formatCurrency(quote.margin_amount)} (${formatPct(quote.margin_pct)})`], ["Risk", quote.risk.required_approval_level === "none" ? "Within policy" : quote.risk.level_label]].map(([l, v]) => (
          <div key={l} className="card p-3"><p className="text-xs uppercase tracking-wide text-zinc-500">{l}</p><p className="text-lg font-semibold tabular-nums text-zinc-900">{v}</p></div>
        ))}
      </div>

      <Tabs active={tab} onChange={setTab} tabs={[{ key: "builder", label: "Lines & pricing" }, { key: "approval", label: "Approval" }, { key: "negotiation", label: `Negotiation${quote.counter_proposals.length ? ` (${quote.counter_proposals.length})` : ""}` }, { key: "history", label: "History" }, { key: "details", label: "Details" }]} />

      {tab === "builder" && (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]">
          <div className="space-y-4">
            {quote.can_edit && <Card title="Add products"><ProductPicker customerId={quote.customer_id} busy={busy === "add"} onAdd={async (line) => { setBusy("add"); try { apply(await quotes.addLine(quoteId, line)); } finally { setBusy(null); } }} /></Card>}
            {quote.lines.length === 0 ? <div className="card p-8 text-center text-sm text-zinc-500">No lines yet. Search the catalog above to add products.</div> : <QuoteLinesTable quote={quote} saving={saving} onUpdate={updateLine} onRemove={async (id) => run("remove", () => quotes.deleteLine(quoteId, id), "Line removed.")} />}
            {quote.lines.length > 0 && <RiskPanel risk={quote.risk} />}
            {!quote.can_edit && !["confirmed", "cancelled", "expired", "rejected"].includes(quote.status) && <p className="text-xs text-zinc-500">Lines are locked while the quotation is {titleCase(quote.status).toLowerCase()}. Use “Revise” to open a new version.</p>}
          </div>
          <div className="space-y-4">
            <UpsellPanel quoteId={quoteId} canEdit={quote.can_edit} version={quote.version * 1000 + quote.lines.length} onAdded={reload} />
          </div>
        </div>
      )}

      {tab === "approval" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <ApprovalPanel quote={quote} onChanged={reload} />
          <RiskPanel risk={quote.risk} />
        </div>
      )}

      {tab === "negotiation" && (negotiation.data ? <NegotiationPanel quote={quote} comments={negotiation.data.comments} proposals={negotiation.data.counter_proposals} onChanged={() => { negotiation.reload(); reload(); }} /> : <Skeleton className="h-40" />)}

      {tab === "history" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Approval decisions">
            {history.data?.approval_actions.length ? <ul className="space-y-2 text-sm">{history.data.approval_actions.map((a) => <li key={a.id} className="rounded-md border border-zinc-200 p-2"><StatusBadge status={a.action === "approved" ? "approved" : a.action === "rejected" ? "rejected" : "returned"} /> <span className="font-medium">{a.actor}</span> at the {a.step} step · {formatDateTime(a.timestamp)}{a.reason && <p className="text-zinc-600">{a.reason}</p>}</li>)}</ul> : <p className="text-sm text-zinc-500">No approval decisions recorded.</p>}
            <h3 className="mt-4 text-xs font-semibold uppercase text-zinc-500">Approval requests</h3>
            <ul className="mt-1 space-y-1 text-sm">{history.data?.requests.map((r) => <li key={r.id}>v{r.quote_version} · <StatusBadge status={r.status} /> {titleCase(r.required_level)} · {formatDateTime(r.created_at)}</li>)}</ul>
          </Card>
          <Card title="Audit trail">{history.data ? <Timeline entries={history.data.audit_logs.slice().reverse()} /> : <Skeleton className="h-40" />}</Card>
        </div>
      )}

      {tab === "details" && (
        <Card title="Quotation details" actions={!["cancelled", "confirmed"].includes(quote.status) && <Button size="sm" variant="secondary" onClick={() => setHeader({ order_discount_pct: String(quote.order_discount_pct), valid_until: quote.valid_until ?? "", promised_delivery_date: quote.promised_delivery_date ?? "", notes: quote.notes ?? "" })}>Edit</Button>}>
          <DescriptionList columns={3} items={[
            { label: "Customer", value: <Link href={`/workspace/customers/${quote.customer_id}`} className="link">{quote.customer_name}</Link> }, { label: "Customer email", value: quote.customer_email }, { label: "Owner", value: quote.owner_name },
            { label: "Order discount", value: formatPct(quote.order_discount_pct) }, { label: "Valid until", value: formatDate(quote.valid_until) }, { label: "Promised delivery", value: formatDate(quote.promised_delivery_date) },
            { label: "Expected delivery", value: formatDate(quote.expected_delivery_date) }, { label: "Actual delivery", value: formatDate(quote.actual_delivery_date) }, { label: "Fulfillment", value: <StatusBadge status={quote.fulfillment_status} /> },
            { label: "Billing", value: <StatusBadge status={quote.billing_status} /> }, { label: "Sent", value: formatDateTime(quote.sent_at) }, { label: "Confirmed", value: formatDateTime(quote.confirmed_at) },
            { label: "Portal link", value: quote.portal_link_active ? "Active" : "None" }, { label: "Approved version", value: quote.approved_version ?? "—" }, { label: "Created", value: formatDateTime(quote.created_at) },
            { label: "Notes", value: quote.notes },
          ]} />
        </Card>
      )}

      <ConfirmDialog open={dialog === "cancel"} onClose={() => setDialog(null)} danger confirmLabel="Cancel quotation" title="Cancel this quotation?" loading={busy === "cancel"} onConfirm={() => run("cancel", () => quotes.cancel(quoteId, reason), "Quotation cancelled.")}>
        <Field label="Reason" className="mt-2"><Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </ConfirmDialog>
      <ConfirmDialog open={dialog === "revise"} onClose={() => setDialog(null)} confirmLabel="Open new version" title="Revise this quotation?" message="A new version opens for editing. Any existing approval is invalidated and the quotation must be re-submitted." loading={busy === "revise"} onConfirm={() => run("revise", () => quotes.revise(quoteId, reason), "New version opened for editing.")}>
        <Field label="Reason" className="mt-2"><Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </ConfirmDialog>
      <ConfirmDialog open={dialog === "confirm"} onClose={() => setDialog(null)} confirmLabel="Confirm order" title="Confirm on the customer's behalf?" message="Use this when the customer accepted outside the portal (signed PO, email). An order number is created, subscriptions start and fulfillment can begin." loading={busy === "confirm"} onConfirm={() => run("confirm", () => quotes.confirm(quoteId, reason), "Order created.")}>
        <Field label="Reference (PO number, email…)" className="mt-2"><Input value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </ConfirmDialog>
      <Modal open={header !== null} onClose={() => setHeader(null)} title="Edit quotation details" footer={<><Button variant="secondary" onClick={() => setHeader(null)}>Cancel</Button><Button loading={busy === "header"} onClick={() => header && run("header", () => quotes.update(quoteId, { order_discount_pct: quote.can_edit ? Number(header.order_discount_pct) : undefined, valid_until: header.valid_until || undefined, promised_delivery_date: header.promised_delivery_date || undefined, notes: header.notes }), "Details saved.").then(() => setHeader(null))}>Save</Button></>}>
        {header && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Order discount %" hint={quote.can_edit ? undefined : "Only editable while the quotation is a draft."}><Input type="number" min={0} max={100} step={0.5} value={header.order_discount_pct} disabled={!quote.can_edit} onChange={(e) => setHeader({ ...header, order_discount_pct: e.target.value })} /></Field>
            <Field label="Valid until"><Input type="date" value={header.valid_until} onChange={(e) => setHeader({ ...header, valid_until: e.target.value })} /></Field>
            <Field label="Promised delivery date"><Input type="date" value={header.promised_delivery_date} onChange={(e) => setHeader({ ...header, promised_delivery_date: e.target.value })} /></Field>
            <Field label="Notes" className="sm:col-span-2"><Textarea rows={3} value={header.notes} onChange={(e) => setHeader({ ...header, notes: e.target.value })} /></Field>
          </div>
        )}
      </Modal>
    </div>
  );
}
