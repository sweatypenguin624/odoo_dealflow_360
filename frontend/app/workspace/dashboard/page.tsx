"use client";
import Link from "next/link";
import { useState } from "react";
import { dashboard } from "@/lib/api";
import { useApi } from "@/lib/hooks/useApi";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatCurrency, formatPct, relativeTime, titleCase } from "@/lib/format";
import { Card, ErrorState, KpiTile, LinkButton, PageHeader, Select, Skeleton } from "@/components/ui";

type Tone = "neutral" | "warn" | "danger" | "good";
interface Tile { label: string; value: string | number; hint?: string; href?: string; tone?: Tone }

export default function DashboardPage() {
  const { user, can } = useAuth();
  const [period, setPeriod] = useState(30);
  const { data, error, loading, reload } = useApi(() => dashboard.summary(period), [period]);
  const k = data?.kpis;
  const role = user?.role;
  const tiles: Tile[] = !k ? [] :
    role === "finance" ? [
      { label: "My approval queue", value: k.pending_approvals, href: "/workspace/approvals", tone: k.pending_approvals ? "warn" : "neutral" },
      { label: "Outstanding invoices", value: formatCurrency(k.outstanding_invoices), hint: `${k.outstanding_invoice_count} open`, href: "/workspace/invoices?status=unpaid" },
      { label: "Overdue invoices", value: k.overdue_invoices, href: "/workspace/invoices?status=overdue", tone: k.overdue_invoices ? "danger" : "good" },
      { label: "Revenue collected", value: formatCurrency(k.revenue_collected), hint: `last ${period} days` },
      { label: "Orders in fulfillment", value: k.orders_in_fulfillment, href: "/workspace/fulfillment" },
      { label: "Fulfillment delays", value: k.fulfillment_delays, href: "/workspace/deal-health?alert_type=delivery_slippage", tone: k.fulfillment_delays ? "warn" : "good" },
      { label: "Monthly recurring revenue", value: formatCurrency(k.subscription_mrr), hint: `${k.active_subscriptions} active subscriptions`, href: "/workspace/subscriptions" },
      { label: "Open alerts", value: k.open_alerts, href: "/workspace/deal-health" },
    ] : role === "sales_manager" ? [
      { label: "My approval queue", value: k.pending_approvals, href: "/workspace/approvals", tone: k.pending_approvals ? "warn" : "neutral" },
      { label: "Pipeline value", value: formatCurrency(k.pipeline_value), hint: `${k.open_quotes} open quotes`, href: "/workspace/pipeline" },
      { label: "Conversion rate", value: formatPct(k.conversion_rate, 0), hint: `${formatCurrency(k.won_value)} won in ${period} days` },
      { label: "Stalled deals", value: k.stalled_deals, href: "/workspace/deal-health?alert_type=stalled", tone: k.stalled_deals ? "warn" : "good" },
      { label: "Discount anomalies", value: k.discount_anomalies, href: "/workspace/deal-health?alert_type=discount_anomaly", tone: k.discount_anomalies ? "danger" : "good" },
      { label: "Fulfillment delays", value: k.fulfillment_delays, href: "/workspace/deal-health?alert_type=delivery_slippage" },
      { label: "Revenue collected", value: formatCurrency(k.revenue_collected), hint: `last ${period} days` },
      { label: "Outstanding invoices", value: formatCurrency(k.outstanding_invoices), href: "/workspace/invoices?status=unpaid" },
    ] : role === "admin" ? [
      { label: "Pipeline value", value: formatCurrency(k.pipeline_value), hint: `${k.open_quotes} open quotes`, href: "/workspace/pipeline" },
      { label: "Pending approvals", value: k.pending_approvals, href: "/workspace/approvals" },
      { label: "Conversion rate", value: formatPct(k.conversion_rate, 0), hint: `${period}-day window` },
      { label: "Revenue collected", value: formatCurrency(k.revenue_collected) },
      { label: "Outstanding invoices", value: formatCurrency(k.outstanding_invoices), hint: `${k.overdue_invoices} overdue`, href: "/workspace/invoices?status=unpaid", tone: k.overdue_invoices ? "danger" : "neutral" },
      { label: "Monthly recurring revenue", value: formatCurrency(k.subscription_mrr), href: "/workspace/subscriptions" },
      { label: "Open alerts", value: k.open_alerts, hint: `${k.stalled_deals} stalled · ${k.discount_anomalies} anomalies`, href: "/workspace/deal-health", tone: k.open_alerts ? "warn" : "good" },
      { label: "Orders in fulfillment", value: k.orders_in_fulfillment, href: "/workspace/fulfillment" },
    ] : [
      { label: "My pipeline", value: formatCurrency(k.pipeline_value), hint: `${k.open_quotes} open quotes`, href: "/workspace/quotations?mine=true" },
      { label: "Awaiting approval", value: k.pending_approvals, href: "/workspace/quotations?status=pending_approval", tone: k.pending_approvals ? "warn" : "neutral" },
      { label: "Won this period", value: formatCurrency(k.won_value), hint: `${formatPct(k.conversion_rate, 0)} conversion` },
      { label: "Stalled deals", value: k.stalled_deals, href: "/workspace/deal-health", tone: k.stalled_deals ? "warn" : "good" },
      { label: "Orders in fulfillment", value: k.orders_in_fulfillment, href: "/workspace/fulfillment" },
      { label: "Outstanding invoices", value: formatCurrency(k.outstanding_invoices), href: "/workspace/invoices" },
    ];

  return (
    <div className="space-y-6">
      <PageHeader title={`Good ${new Date().getHours() < 12 ? "morning" : "afternoon"}, ${user?.full_name.split(" ")[0] ?? ""}`} subtitle="Live figures from your data — nothing here is estimated." actions={
        <>
          <Select value={period} onChange={(e) => setPeriod(Number(e.target.value))} aria-label="Period" className="w-36"><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option><option value={365}>Last year</option></Select>
          {can("quote:create") && <LinkButton href="/workspace/quotations?new=1" variant="primary">+ New quotation</LinkButton>}
        </>
      } />
      {error && <ErrorState message={error} onRetry={reload} />}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4" data-testid="kpi-grid">
        {loading && !data ? Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-24" />) : tiles.map((t) => <KpiTile key={t.label} label={t.label} value={t.value} hint={t.hint} href={t.href} tone={t.tone ?? "neutral"} />)}
      </div>
      <Card title="Recent activity">
        {data && data.recent_activity.length === 0 && <p className="text-sm text-zinc-500">Nothing yet.</p>}
        <ol className="divide-y divide-zinc-100">
          {data?.recent_activity.map((a) => (
            <li key={a.id} className="flex items-start justify-between gap-3 py-2 text-sm">
              <div>
                {a.quote_id ? <Link href={`/workspace/quotations/${a.quote_id}`} className="font-medium text-zinc-900 hover:underline">{a.quote_number ?? `Quote ${a.quote_id}`}{a.customer_name ? ` · ${a.customer_name}` : ""}</Link> : <span className="font-medium text-zinc-900">{titleCase(a.action)}</span>}
                <p className="text-zinc-600">{titleCase(a.action)}{a.reason ? ` — ${a.reason}` : ""}</p>
              </div>
              <span className="whitespace-nowrap text-xs text-zinc-400">{a.user} · {relativeTime(a.timestamp)}</span>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
