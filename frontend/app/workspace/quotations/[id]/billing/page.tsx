"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  cancelSubscription,
  changeSubscriptionQuantity,
  generateRecurringInvoice,
  getBillingSummary,
  listProducts,
} from "@/lib/api";
import type { BillingSummary, ProductRef, RecurringLine } from "@/lib/api";
import { useReload } from "@/lib/reload-context";

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);
}

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
}

interface ActionResult {
  amount: number;
  description: string;
}

function RecurringLineCard({
  line,
  productName,
  onChanged,
}: {
  line: RecurringLine;
  productName: string;
  onChanged: (result: ActionResult) => void;
}) {
  const [newQuantity, setNewQuantity] = useState(line.quantity);
  const [changeDate, setChangeDate] = useState(todayIsoDate);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generatedInvoiceId, setGeneratedInvoiceId] = useState<number | null>(null);

  async function handleQuantityChange() {
    setBusy(true);
    setError(null);
    try {
      const result = await changeSubscriptionQuantity(line.subscription_id, {
        new_quantity: newQuantity,
        change_date: changeDate,
      });
      onChanged({ amount: result.billing_event.amount, description: result.billing_event.description });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to change quantity");
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel() {
    setBusy(true);
    setError(null);
    try {
      const result = await cancelSubscription(line.subscription_id, { cancellation_date: changeDate });
      onChanged({ amount: result.billing_event.amount, description: result.billing_event.description });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to cancel subscription");
    } finally {
      setBusy(false);
    }
  }

  async function handleGenerateInvoice() {
    setBusy(true);
    setError(null);
    try {
      const invoice = await generateRecurringInvoice(line.subscription_id);
      setGeneratedInvoiceId(invoice.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to generate invoice");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-purple-200 bg-purple-50 p-4 dark:border-purple-900 dark:bg-purple-950/30">
      <div className="flex items-center justify-between">
        <p className="font-medium text-zinc-900 dark:text-zinc-50">{productName}</p>
        <span className="rounded-full bg-purple-100 px-2.5 py-0.5 text-xs font-medium text-purple-800 dark:bg-purple-900/40 dark:text-purple-300">
          {line.status}
        </span>
      </div>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        Quantity: {line.quantity} · Cycle: {line.current_cycle_start} → {line.current_cycle_end}
      </p>

      <div className="mt-3 overflow-x-auto rounded border border-zinc-200 dark:border-zinc-800">
        <table className="w-full text-xs">
          <thead className="bg-zinc-50 text-left uppercase text-zinc-500 dark:bg-zinc-900 dark:text-zinc-400">
            <tr>
              <th className="px-3 py-1.5">Date</th>
              <th className="px-3 py-1.5">Type</th>
              <th className="px-3 py-1.5">Amount</th>
              <th className="px-3 py-1.5">Description</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {line.billing_events.map((event) => (
              <tr key={event.id} className="bg-white dark:bg-zinc-950">
                <td className="px-3 py-1.5">{event.event_date}</td>
                <td className="px-3 py-1.5">{event.event_type}</td>
                <td
                  className={`px-3 py-1.5 ${event.amount < 0 ? "text-green-600 dark:text-green-400" : ""}`}
                >
                  {formatCurrency(event.amount)}
                </td>
                <td className="px-3 py-1.5">{event.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {line.status === "active" && (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <div>
            <label className="block text-xs text-zinc-500 dark:text-zinc-400">New Quantity</label>
            <input
              type="number"
              min={1}
              value={newQuantity}
              onChange={(e) => setNewQuantity(Number(e.target.value))}
              className="w-20 rounded border border-zinc-300 px-2 py-1 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-500 dark:text-zinc-400">Effective Date</label>
            <input
              type="date"
              value={changeDate}
              onChange={(e) => setChangeDate(e.target.value)}
              className="rounded border border-zinc-300 px-2 py-1 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
          </div>
          <button
            onClick={handleQuantityChange}
            disabled={busy}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            Change Quantity
          </button>
          <button
            onClick={handleCancel}
            disabled={busy}
            className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
          >
            Cancel Subscription
          </button>
          <button
            onClick={handleGenerateInvoice}
            disabled={busy}
            className="rounded bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            Generate Invoice
          </button>
        </div>
      )}
      {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
      {generatedInvoiceId !== null && (
        <p className="mt-2 text-sm text-green-700 dark:text-green-400">
          Invoice created.{" "}
          <Link href={`/workspace/invoices/${generatedInvoiceId}`} className="underline">
            View invoice
          </Link>
        </p>
      )}
    </div>
  );
}

export default function BillingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const quoteId = Number(id);
  const { reloadNonce } = useReload();

  const [summary, setSummary] = useState<BillingSummary | null>(null);
  const [products, setProducts] = useState<ProductRef[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastActionResult, setLastActionResult] = useState<ActionResult | null>(null);

  const productById = useMemo(() => {
    const map = new Map<number, ProductRef>();
    for (const product of products) map.set(product.id, product);
    return map;
  }, [products]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setError(null);
      try {
        const [billingSummary, productList] = await Promise.all([
          getBillingSummary(quoteId),
          listProducts(),
        ]);
        if (!cancelled) {
          setSummary(billingSummary);
          setProducts(productList);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load billing summary");
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [quoteId, reloadNonce]);

  async function refetchSummary() {
    try {
      setSummary(await getBillingSummary(quoteId));
    } catch {
      // Keep showing the last-known summary rather than blanking the page.
    }
  }

  function handleActionResult(result: ActionResult) {
    setLastActionResult(result);
    refetchSummary();
  }

  if (error) return <p className="text-red-600 dark:text-red-400">Error: {error}</p>;
  if (summary === null) return <p className="text-zinc-500 dark:text-zinc-400">Loading…</p>;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          href={`/workspace/quotations/${quoteId}`}
          className="text-sm text-blue-600 hover:underline dark:text-blue-400"
        >
          ← Back to Quote #{quoteId}
        </Link>
        <h1 className="mt-2 text-xl font-semibold text-zinc-900 dark:text-zinc-50">Billing</h1>
      </div>

      {lastActionResult && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950/40">
          <p className="font-semibold text-blue-900 dark:text-blue-200">
            {formatCurrency(lastActionResult.amount)}
          </p>
          <p className="text-sm text-blue-800 dark:text-blue-300">{lastActionResult.description}</p>
        </div>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          One-Time Lines
        </h2>
        {summary.one_time_lines.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">None.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
            <table className="w-full text-sm">
              <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500 dark:bg-zinc-900 dark:text-zinc-400">
                <tr>
                  <th className="px-4 py-2">Product</th>
                  <th className="px-4 py-2">Quantity</th>
                  <th className="px-4 py-2">Discount %</th>
                  <th className="px-4 py-2">Line Value</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {summary.one_time_lines.map((line) => (
                  <tr key={line.quote_line_id} className="bg-white dark:bg-zinc-950">
                    <td className="px-4 py-2">
                      {productById.get(line.product_id)?.name ?? `Product #${line.product_id}`}
                    </td>
                    <td className="px-4 py-2">{line.quantity}</td>
                    <td className="px-4 py-2">{line.discount_pct}%</td>
                    <td className="px-4 py-2">{formatCurrency(line.line_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          Recurring Lines
        </h2>
        {summary.recurring_lines.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">None.</p>
        ) : (
          <div className="flex flex-col gap-4">
            {summary.recurring_lines.map((line) => (
              <RecurringLineCard
                key={line.quote_line_id}
                line={line}
                productName={productById.get(line.product_id)?.name ?? `Product #${line.product_id}`}
                onChanged={handleActionResult}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
