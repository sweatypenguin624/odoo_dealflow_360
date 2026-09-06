"use client";
import { Suspense, useState } from "react";
import { catalog, reports, users } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useApi } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { formatCurrency, formatNumber, titleCase } from "@/lib/format";
import { Button, Card, EmptyState, ErrorState, Field, FilterBar, Input, PageHeader, Select, Skeleton, Tabs } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";

const REPORTS = [
  { name: "sales", title: "Sales", blurb: "Pipeline and won value by rep, customer and month." },
  { name: "discounts", title: "Discounts", blurb: "Discount depth, policy breaches and approval outcomes." },
  { name: "fulfillment", title: "Fulfillment", blurb: "Shipment timeliness, backorders and warehouse load." },
  { name: "billing", title: "Billing", blurb: "Invoicing, collections and recurring revenue." },
  { name: "deal-health", title: "Deal Health", blurb: "Alert volume by type and rep." },
];

// Money-ish columns are right-aligned and currency formatted; everything else
// falls back to a plain string so a new report column still renders sensibly.
const MONEY = /(value|amount|total|revenue|price|paid|outstanding|mrr|margin_amount)/i;
const PERCENT = /(pct|percent|rate)$/i;

function cell(column: string, value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") {
    if (MONEY.test(column)) return formatCurrency(value);
    if (PERCENT.test(column)) return `${value.toFixed(1)}%`;
    return formatNumber(value, Number.isInteger(value) ? 0 : 2);
  }
  return String(value);
}

function Inner() {
  const { state, set } = useListState({ report: "sales" });
  const toast = useToast();
  const name = state.report ?? "sales";
  const filters = {
    date_from: state.date_from,
    date_to: state.date_to,
    owner_user_id: state.owner_user_id,
    customer_id: state.customer_id,
    tier_id: state.tier_id,
    category_id: state.category_id,
    quote_status: state.quote_status,
    fulfillment_status: state.fulfillment_status,
    invoice_status: state.invoice_status,
  };
  const reps = useApi(() => users.reps(), []);
  const tiers = useApi(() => catalog.tiers(), []);
  const categories = useApi(() => catalog.categories({ page_size: 100 }), []);
  const { data, error, loading, reload } = useApi(() => reports.run(name, filters), [name, JSON.stringify(filters)]);
  const [exporting, setExporting] = useState<string | null>(null);

  async function download(format: string) {
    setExporting(format);
    try {
      const blob = await reports.exportFile(name, format, filters);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${name}-report.${format === "xlsx" ? "xlsx" : format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setExporting(null);
    }
  }

  const active = REPORTS.find((r) => r.name === name);
  const breakdowns: { title: string; rows: Record<string, unknown>[] }[] = data
    ? [
        { title: "By status", rows: (data.by_status ?? []) as unknown as Record<string, unknown>[] },
        { title: "By month", rows: (data.by_month ?? []) as unknown as Record<string, unknown>[] },
        { title: "By rep", rows: data.by_rep ?? [] },
        { title: "By customer", rows: data.by_customer ?? [] },
        { title: "By category", rows: data.by_category ?? [] },
        { title: "By type", rows: data.by_type ?? [] },
      ].filter((b) => b.rows.length > 0)
    : [];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Reporting"
        subtitle={active?.blurb}
        actions={
          <>
            <Button variant="secondary" onClick={() => download("csv")} loading={exporting === "csv"}>Export CSV</Button>
            <Button variant="secondary" onClick={() => download("xlsx")} loading={exporting === "xlsx"}>Export Excel</Button>
            <Button variant="secondary" onClick={() => download("pdf")} loading={exporting === "pdf"}>Export PDF</Button>
          </>
        }
      />

      <Tabs tabs={REPORTS.map((r) => ({ key: r.name, label: r.title }))} active={name} onChange={(k) => set({ report: k })} />

      <FilterBar>
        <Field label="From" className="w-40"><Input type="date" value={state.date_from ?? ""} onChange={(e) => set({ date_from: e.target.value })} /></Field>
        <Field label="To" className="w-40"><Input type="date" value={state.date_to ?? ""} onChange={(e) => set({ date_to: e.target.value })} /></Field>
        <Field label="Rep" className="w-44">
          <Select value={state.owner_user_id ?? ""} onChange={(e) => set({ owner_user_id: e.target.value })}>
            <option value="">All reps</option>
            {reps.data?.map((r) => <option key={r.id} value={r.id}>{r.full_name}</option>)}
          </Select>
        </Field>
        <Field label="Tier" className="w-40">
          <Select value={state.tier_id ?? ""} onChange={(e) => set({ tier_id: e.target.value })}>
            <option value="">All tiers</option>
            {tiers.data?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </Select>
        </Field>
        <Field label="Category" className="w-44">
          <Select value={state.category_id ?? ""} onChange={(e) => set({ category_id: e.target.value })}>
            <option value="">All categories</option>
            {categories.data?.items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
        </Field>
        {(state.date_from || state.date_to || state.owner_user_id || state.tier_id || state.category_id) && (
          <Button variant="ghost" size="sm" onClick={() => set({ date_from: "", date_to: "", owner_user_id: "", tier_id: "", category_id: "" })}>Clear</Button>
        )}
      </FilterBar>

      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data && <Skeleton className="h-64" />}

      {data && (
        <>
          <p className="text-xs text-zinc-500">{data.filters}</p>

          {Object.keys(data.summary).length > 0 && (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {Object.entries(data.summary).map(([k, v]) => (
                <div key={k} className="card p-3">
                  <p className="text-xs uppercase tracking-wide text-zinc-500">{titleCase(k)}</p>
                  <p className="text-lg font-semibold tabular-nums text-zinc-900">{cell(k, v)}</p>
                </div>
              ))}
            </div>
          )}

          {breakdowns.map((b) => (
            <Card key={b.title} title={b.title} padded={false}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500">
                    <tr>{Object.keys(b.rows[0]).map((c) => <th key={c} className={`px-4 py-2 ${typeof b.rows[0][c] === "number" ? "text-right" : ""}`}>{titleCase(c)}</th>)}</tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-100">
                    {b.rows.map((row, i) => (
                      <tr key={i}>
                        {Object.keys(b.rows[0]).map((c) => <td key={c} className={`px-4 py-2 ${typeof row[c] === "number" ? "text-right tabular-nums" : ""}`}>{cell(c, row[c])}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ))}

          <Card title="Detail" padded={false}>
            {data.rows.length === 0 ? (
              <EmptyState title="No rows" description="No data matches these filters." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500">
                    <tr>{data.columns.map((c) => <th key={c} className={`px-4 py-2 ${MONEY.test(c) ? "text-right" : ""}`}>{titleCase(c)}</th>)}</tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-100">
                    {data.rows.map((row, i) => (
                      <tr key={i} className="hover:bg-zinc-50">
                        {data.columns.map((c) => <td key={c} className={`px-4 py-2 ${typeof row[c] === "number" ? "text-right tabular-nums" : ""}`}>{cell(c, row[c])}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

export default function ReportsPage() {
  return <Suspense><Inner /></Suspense>;
}
