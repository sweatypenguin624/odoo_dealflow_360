"use client";
import Link from "next/link";
import { use } from "react";
import { quotes } from "@/lib/api";
import { useApi } from "@/lib/hooks/useApi";
import { formatCurrency, formatDateTime, formatPct } from "@/lib/format";
import { Card, ErrorState, PageHeader, Skeleton, StatusBadge } from "@/components/ui";
import { ApprovalPanel } from "@/components/domain/ApprovalPanel";
import { RiskPanel } from "@/components/domain/RiskPanel";
import { Timeline } from "@/components/domain/Timeline";

export default function ApprovalDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const quoteId = Number(use(params).id);
  const { data: quote, error, reload } = useApi(() => quotes.get(quoteId), [quoteId]);
  const history = useApi(() => quotes.history(quoteId), [quoteId, quote?.status, quote?.version]);
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!quote) return <Skeleton className="h-64" />;
  return (
    <div className="space-y-5">
      <PageHeader breadcrumb={{ href: "/workspace/approvals", label: "Approvals" }} title={<span className="flex items-center gap-2">{quote.quote_number} <StatusBadge status={quote.status} /></span>} subtitle={<>{quote.customer_name} ({quote.customer_tier}) · rep {quote.owner_name} · <Link href={`/workspace/quotations/${quote.id}`} className="link">open full quotation</Link></>} />
      <div className="grid gap-4 lg:grid-cols-2">
        <ApprovalPanel quote={quote} onChanged={reload} />
        <RiskPanel risk={quote.risk} />
      </div>
      <Card title="Lines under review" padded={false}>
        <table className="w-full text-sm">
          <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500"><tr><th className="px-4 py-2">Product</th><th className="px-2 py-2 text-right">Qty</th><th className="px-2 py-2 text-right">Unit price</th><th className="px-2 py-2 text-right">Requested</th><th className="px-2 py-2 text-right">Allowed</th><th className="px-2 py-2">Limit source</th><th className="px-2 py-2 text-right">Line total</th><th className="px-2 py-2 text-right">Margin</th></tr></thead>
          <tbody className="divide-y divide-zinc-100">
            {quote.lines.map((l) => (
              <tr key={l.id} className={l.line_status === "over_limit" ? "bg-red-50/40" : ""}>
                <td className="px-4 py-2">{l.description ?? l.product_name}<span className="block text-xs text-zinc-500">{l.sku}</span></td>
                <td className="px-2 py-2 text-right">{l.quantity}</td><td className="px-2 py-2 text-right">{formatCurrency(l.unit_price)}</td>
                <td className={`px-2 py-2 text-right font-medium ${l.line_status === "over_limit" ? "text-red-700" : ""}`}>{formatPct(l.discount_pct)}</td>
                <td className="px-2 py-2 text-right">{formatPct(l.allowed_discount_pct, 0)}</td><td className="px-2 py-2 text-xs text-zinc-500">{l.limit_source}</td>
                <td className="px-2 py-2 text-right">{formatCurrency(l.line_total)}</td><td className="px-2 py-2 text-right">{formatPct(l.margin_pct)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot className="bg-zinc-50 text-sm font-medium"><tr><td className="px-4 py-2" colSpan={6}>Total {formatCurrency(quote.total)} · margin {formatPct(quote.margin_pct)}</td><td className="px-2 py-2 text-right" colSpan={2}>{formatCurrency(quote.margin_amount)}</td></tr></tfoot>
        </table>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Previous decisions">{history.data?.approval_actions.length ? <ul className="space-y-1 text-sm">{history.data.approval_actions.map((a) => <li key={a.id}><StatusBadge status={a.action === "approved" ? "approved" : a.action === "rejected" ? "rejected" : "returned"} /> {a.actor} · {a.step} · {formatDateTime(a.timestamp)}{a.reason && <span className="block text-zinc-600">{a.reason}</span>}</li>)}</ul> : <p className="text-sm text-zinc-500">None yet.</p>}</Card>
        <Card title="Audit trail">{history.data ? <Timeline entries={history.data.audit_logs.slice().reverse().slice(0, 12)} /> : <Skeleton className="h-24" />}</Card>
      </div>
    </div>
  );
}
