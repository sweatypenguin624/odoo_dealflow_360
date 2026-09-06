"use client";
import Link from "next/link";
import { use, useState } from "react";
import { invoices, quotes } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useApi } from "@/lib/hooks/useApi";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatCurrency, formatDate, titleCase } from "@/lib/format";
import { Badge, Button, Card, ErrorState, LinkButton, PageHeader, Skeleton, StatusBadge } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";

export default function QuoteBillingPage({ params }: { params: Promise<{ id: string }> }) {
  const quoteId = Number(use(params).id);
  const { can } = useAuth();
  const toast = useToast();
  const quote = useApi(() => quotes.get(quoteId), [quoteId]);
  const summary = useApi(() => quotes.billingSummary(quoteId), [quoteId]);
  const [busy, setBusy] = useState(false);

  async function generate() {
    setBusy(true);
    try {
      const inv = await invoices.generate(quoteId);
      toast.success(`Invoice ${inv.invoice_number} created.`);
      summary.reload();
      quote.reload();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (quote.error) return <ErrorState message={quote.error} onRetry={quote.reload} />;
  if (!quote.data) return <Skeleton className="h-64" />;
  const q = quote.data;
  const s = summary.data;

  return (
    <div className="space-y-5">
      <PageHeader
        breadcrumb={{ href: `/workspace/quotations/${quoteId}`, label: "Quotation" }}
        title={<span className="flex flex-wrap items-center gap-2">{q.order_number ?? q.quote_number} <StatusBadge status={q.billing_status} /></span>}
        subtitle={<><Link href={`/workspace/customers/${q.customer_id}`} className="link">{q.customer_name}</Link> · order total {formatCurrency(q.total)}</>}
        actions={
          <>
            {can("invoice:manage") && q.status === "confirmed" && <Button onClick={generate} loading={busy}>Invoice shipped items</Button>}
            <LinkButton href={`/workspace/quotations/${quoteId}/fulfillment`}>Fulfillment →</LinkButton>
          </>
        }
      />

      {q.status !== "confirmed" && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          This quotation isn&apos;t confirmed yet, so nothing can be invoiced. Confirm the order first.
        </div>
      )}

      {summary.error && <ErrorState message={summary.error} onRetry={summary.reload} />}
      {!s && !summary.error && <Skeleton className="h-40" />}

      {s && (
        <>
          <Card title="One-time lines" padded={false}>
            {s.one_time_lines.length === 0 ? <p className="p-4 text-sm text-zinc-500">No one-time products on this order.</p> : (
              <table className="w-full text-sm">
                <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500">
                  <tr><th className="px-4 py-2">Product</th><th className="px-2 py-2 text-right">Qty</th><th className="px-2 py-2 text-right">Discount</th><th className="px-2 py-2 text-right">Line value</th><th className="px-2 py-2 text-right">Line total</th></tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {s.one_time_lines.map((l) => (
                    <tr key={l.quote_line_id}>
                      <td className="px-4 py-2">{l.product_name}</td>
                      <td className="px-2 py-2 text-right">{l.quantity}</td>
                      <td className="px-2 py-2 text-right">{Number(l.discount_pct).toFixed(1)}%</td>
                      <td className="px-2 py-2 text-right tabular-nums">{formatCurrency(l.line_value)}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{formatCurrency(l.line_total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>

          <Card title="Recurring lines">
            {s.recurring_lines.length === 0 ? <p className="text-sm text-zinc-500">No subscriptions on this order.</p> : (
              <ul className="space-y-3">
                {s.recurring_lines.map((r) => (
                  <li key={r.quote_line_id} className="rounded-md border border-zinc-200 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="font-medium text-zinc-900">
                          <Link href={`/workspace/subscriptions/${r.subscription_id}`} className="link">{r.plan_name}</Link>
                          <span className="ml-1 text-xs text-zinc-500">{r.product_name} · {r.quantity} ×</span>
                        </p>
                        <p className="text-xs text-zinc-500">
                          Cycle {formatDate(r.current_cycle_start)} – {formatDate(r.current_cycle_end)} · next billing {formatDate(r.next_billing_date)}
                        </p>
                      </div>
                      <StatusBadge status={r.status} />
                    </div>
                    {r.billing_events.length > 0 && (
                      <ul className="mt-2 space-y-0.5 text-xs text-zinc-600">
                        {r.billing_events.map((e) => (
                          <li key={e.id} className="flex justify-between gap-2">
                            <span><Badge tone="neutral">{titleCase(e.event_type)}</Badge> {e.description}</span>
                            <span className="tabular-nums">{formatCurrency(e.amount)} · {formatDate(e.event_date)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Invoices" padded={false}>
            {s.invoices.length === 0 ? <p className="p-4 text-sm text-zinc-500">Nothing invoiced yet.</p> : (
              <table className="w-full text-sm">
                <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500">
                  <tr><th className="px-4 py-2">Invoice</th><th className="px-2 py-2">Status</th><th className="px-2 py-2">Period</th><th className="px-2 py-2 text-right">Amount</th><th className="px-2 py-2 text-right">Paid</th><th className="px-2 py-2">Due</th></tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {s.invoices.map((i) => (
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
        </>
      )}
    </div>
  );
}
