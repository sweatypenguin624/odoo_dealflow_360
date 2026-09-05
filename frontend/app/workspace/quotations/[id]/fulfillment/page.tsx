"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  confirmFulfillment,
  generateQuoteInvoice,
  getFulfillment,
  getQuote,
  listWarehouses,
  overrideFulfillment,
  suggestFulfillment,
} from "@/lib/api";
import type { FulfillmentPlan, QuoteDetail, Warehouse } from "@/lib/api";
import { useReload } from "@/lib/reload-context";
import { StatusBadge } from "@/components/StatusBadge";

export default function FulfillmentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const quoteId = Number(id);
  const { reloadNonce } = useReload();

  const [quote, setQuote] = useState<QuoteDetail | null>(null);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [plan, setPlan] = useState<FulfillmentPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [overrideQuantities, setOverrideQuantities] = useState<Record<number, Record<number, number>>>(
    {},
  );
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [generatingInvoice, setGeneratingInvoice] = useState(false);
  const [invoiceError, setInvoiceError] = useState<string | null>(null);
  const [generatedInvoiceId, setGeneratedInvoiceId] = useState<number | null>(null);
  const [overrideError, setOverrideError] = useState<string | null>(null);
  const [savingOverride, setSavingOverride] = useState(false);

  const warehouseById = useMemo(() => {
    const map = new Map<number, Warehouse>();
    for (const w of warehouses) map.set(w.id, w);
    return map;
  }, [warehouses]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [quoteDetail, warehouseList] = await Promise.all([getQuote(quoteId), listWarehouses()]);
        if (cancelled) return;
        setQuote(quoteDetail);
        setWarehouses(warehouseList);

        if (quoteDetail.status !== "approved") {
          setPlan(null);
          return;
        }

        let fulfillmentPlan: FulfillmentPlan;
        try {
          fulfillmentPlan = await getFulfillment(quoteId);
        } catch (err) {
          if (err instanceof ApiError && err.status === 404) {
            fulfillmentPlan = await suggestFulfillment(quoteId);
          } else {
            throw err;
          }
        }
        if (!cancelled) {
          setPlan(fulfillmentPlan);
          setOverrideQuantities(initializeOverrides(fulfillmentPlan));
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load fulfillment");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [quoteId, reloadNonce]);

  function initializeOverrides(fulfillmentPlan: FulfillmentPlan): Record<number, Record<number, number>> {
    const result: Record<number, Record<number, number>> = {};
    for (const split of fulfillmentPlan.splits) {
      if (split.is_backorder || split.warehouse_id === null) continue;
      result[split.quote_line_id] ??= {};
      result[split.quote_line_id][split.warehouse_id] =
        (result[split.quote_line_id][split.warehouse_id] ?? 0) + split.quantity_fulfilled;
    }
    return result;
  }

  async function handleAcceptSuggested() {
    setConfirming(true);
    setConfirmError(null);
    try {
      const confirmed = await confirmFulfillment(quoteId);
      setPlan(confirmed);
    } catch (err) {
      setConfirmError(err instanceof ApiError ? err.message : "Failed to confirm fulfillment");
    } finally {
      setConfirming(false);
    }
  }

  async function handleGenerateInvoice() {
    setGeneratingInvoice(true);
    setInvoiceError(null);
    try {
      const invoice = await generateQuoteInvoice(quoteId);
      setGeneratedInvoiceId(invoice.id);
    } catch (err) {
      setInvoiceError(err instanceof ApiError ? err.message : "Failed to generate invoice");
    } finally {
      setGeneratingInvoice(false);
    }
  }

  function setOverrideValue(lineId: number, warehouseId: number, value: number) {
    setOverrideQuantities((prev) => ({
      ...prev,
      [lineId]: { ...prev[lineId], [warehouseId]: value },
    }));
  }

  function lineOverrideTotal(lineId: number): number {
    const perWarehouse = overrideQuantities[lineId] ?? {};
    return Object.values(perWarehouse).reduce((sum, v) => sum + (Number.isFinite(v) ? v : 0), 0);
  }

  const overrideIsValid =
    quote !== null &&
    quote.lines.every((line) => lineOverrideTotal(line.id) === line.quantity);

  async function handleSaveOverride() {
    if (!quote || !overrideIsValid) return;
    setSavingOverride(true);
    setOverrideError(null);
    try {
      const allocations = quote.lines.flatMap((line) =>
        Object.entries(overrideQuantities[line.id] ?? {})
          .filter(([, qty]) => qty > 0)
          .map(([warehouseId, qty]) => ({
            quote_line_id: line.id,
            warehouse_id: Number(warehouseId),
            quantity_fulfilled: qty,
          })),
      );
      const updated = await overrideFulfillment(quoteId, allocations);
      setPlan(updated);
      setOverrideQuantities(initializeOverrides(updated));
    } catch (err) {
      setOverrideError(err instanceof ApiError ? err.message : "Failed to save override");
    } finally {
      setSavingOverride(false);
    }
  }

  if (error) return <p className="text-red-600 dark:text-red-400">Error: {error}</p>;
  if (loading || quote === null) return <p className="text-zinc-500 dark:text-zinc-400">Loading…</p>;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          href={`/workspace/quotations/${quoteId}`}
          className="text-sm text-blue-600 hover:underline dark:text-blue-400"
        >
          ← Back to Quote #{quoteId}
        </Link>
        <div className="mt-2 flex items-center justify-between">
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
            Fulfillment — {quote.customer_name}
          </h1>
          <StatusBadge status={quote.status} />
        </div>
      </div>

      {quote.status !== "approved" ? (
        <p className="rounded-lg border border-zinc-200 bg-white p-4 text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
          This quote isn&apos;t approved yet — fulfillment planning becomes available once it is.
        </p>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500 dark:bg-zinc-900 dark:text-zinc-400">
                <tr>
                  <th className="px-4 py-2">Line</th>
                  <th className="px-4 py-2">Warehouse</th>
                  <th className="px-4 py-2">Quantity</th>
                  <th className="px-4 py-2">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {plan?.splits.map((split) => {
                  const line = quote.lines.find((l) => l.id === split.quote_line_id);
                  const warehouse = split.warehouse_id ? warehouseById.get(split.warehouse_id) : null;
                  return (
                    <tr key={split.id} className="bg-white dark:bg-zinc-950">
                      <td className="px-4 py-2">{line?.product_name ?? `Line ${split.quote_line_id}`}</td>
                      <td className="px-4 py-2">{warehouse?.name ?? "—"}</td>
                      <td className="px-4 py-2">{split.quantity_fulfilled}</td>
                      <td className="px-4 py-2">
                        {split.is_backorder ? (
                          <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-800 dark:bg-red-900/40 dark:text-red-300">
                            Backorder
                          </span>
                        ) : (
                          <span className="rounded bg-green-100 px-2 py-0.5 text-xs text-green-800 dark:bg-green-900/40 dark:text-green-300">
                            Fulfilled
                          </span>
                        )}
                        {split.warning && (
                          <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">{split.warning}</p>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {plan && plan.backorder_summary.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
              {plan.backorder_summary.map((line, i) => (
                <p key={i}>{line}</p>
              ))}
            </div>
          )}

          <div className="flex items-center gap-3">
            {plan?.status === "suggested" && (
              <button
                onClick={handleAcceptSuggested}
                disabled={confirming}
                className="w-fit rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {confirming ? "Confirming…" : "Accept Suggested Split"}
              </button>
            )}
            {plan?.status === "confirmed" && (
              <button
                onClick={handleGenerateInvoice}
                disabled={generatingInvoice}
                className="w-fit rounded bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
              >
                {generatingInvoice ? "Generating…" : "Generate Invoice"}
              </button>
            )}
            {plan && <StatusBadge status={plan.status} />}
          </div>
          {confirmError && <p className="text-sm text-red-600 dark:text-red-400">{confirmError}</p>}
          {invoiceError && <p className="text-sm text-red-600 dark:text-red-400">{invoiceError}</p>}
          {generatedInvoiceId !== null && (
            <div className="rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-300">
              Invoice created.{" "}
              <Link href={`/workspace/invoices/${generatedInvoiceId}`} className="underline">
                View invoice
              </Link>
            </div>
          )}

          <div>
            <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-50">
              Manual Override
            </h2>
            <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
              <table className="w-full min-w-[560px] text-sm">
                <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500 dark:bg-zinc-900 dark:text-zinc-400">
                  <tr>
                    <th className="px-4 py-2">Line (needed)</th>
                    {warehouses.map((w) => (
                      <th key={w.id} className="px-4 py-2">
                        {w.name}
                      </th>
                    ))}
                    <th className="px-4 py-2">Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                  {quote.lines.map((line) => {
                    const total = lineOverrideTotal(line.id);
                    const valid = total === line.quantity;
                    return (
                      <tr key={line.id} className="bg-white dark:bg-zinc-950">
                        <td className="px-4 py-2">
                          {line.product_name} ({line.quantity})
                        </td>
                        {warehouses.map((w) => (
                          <td key={w.id} className="px-4 py-2">
                            <input
                              type="number"
                              min={0}
                              value={overrideQuantities[line.id]?.[w.id] ?? 0}
                              onChange={(e) => setOverrideValue(line.id, w.id, Number(e.target.value))}
                              className="w-16 rounded border border-zinc-300 px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
                            />
                          </td>
                        ))}
                        <td className={`px-4 py-2 font-medium ${valid ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
                          {total} / {line.quantity}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <button
              onClick={handleSaveOverride}
              disabled={!overrideIsValid || savingOverride}
              className="mt-3 w-fit rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {savingOverride ? "Saving…" : "Save Override"}
            </button>
            {!overrideIsValid && (
              <p className="mt-2 text-sm text-amber-600 dark:text-amber-400">
                Each line&apos;s warehouse quantities must sum to exactly the quantity needed before
                saving.
              </p>
            )}
            {overrideError && (
              <p className="mt-2 text-sm text-red-600 dark:text-red-400">{overrideError}</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
