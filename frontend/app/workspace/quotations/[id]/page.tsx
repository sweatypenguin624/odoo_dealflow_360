"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  getMarginSummary,
  getQuote,
  listProducts,
  submitQuote,
  updateQuoteLine,
} from "@/lib/api";
import type { MarginSummary, ProductRef, QuoteDetail, QuoteRiskResult } from "@/lib/api";
import { useReload } from "@/lib/reload-context";
import { StatusBadge } from "@/components/StatusBadge";

const DEBOUNCE_MS = 500;

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);
}

const APPROVAL_LEVEL_LABEL: Record<string, string> = {
  none: "Auto-approved — no manager sign-off required",
  manager: "Routed to Manager for approval",
  manager_then_finance: "Routed to Manager, then Finance for approval",
};

function RiskResultPanel({ result }: { result: QuoteRiskResult }) {
  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-900 dark:bg-blue-950/40">
      <p className="font-semibold text-blue-900 dark:text-blue-200">
        {APPROVAL_LEVEL_LABEL[result.required_approval_level] ?? result.required_approval_level}
      </p>
      <p className="mt-1 text-sm text-blue-800 dark:text-blue-300">
        Blended discount score: {result.blended_score.toFixed(2)}
      </p>
      {result.reasons.length > 0 && (
        <ul className="mt-2 list-inside list-disc text-sm text-blue-800 dark:text-blue-300">
          {result.reasons.map((reason, i) => (
            <li key={i}>{reason}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function QuotationBuilderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const quoteId = Number(id);
  const { reloadNonce } = useReload();

  const [quote, setQuote] = useState<QuoteDetail | null>(null);
  const [products, setProducts] = useState<ProductRef[]>([]);
  const [margin, setMargin] = useState<MarginSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savingLineIds, setSavingLineIds] = useState<Set<number>>(new Set());
  const [submitResult, setSubmitResult] = useState<QuoteRiskResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const timers = useRef<Record<number, ReturnType<typeof setTimeout>>>({});

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
        const [quoteDetail, productList, marginSummary] = await Promise.all([
          getQuote(quoteId),
          listProducts(),
          getMarginSummary(quoteId),
        ]);
        if (!cancelled) {
          setQuote(quoteDetail);
          setProducts(productList);
          setMargin(marginSummary);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load quote");
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [quoteId, reloadNonce]);

  const reloadQuoteAndMargin = useCallback(async () => {
    try {
      const [quoteDetail, marginSummary] = await Promise.all([
        getQuote(quoteId),
        getMarginSummary(quoteId),
      ]);
      setQuote(quoteDetail);
      setMargin(marginSummary);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to reload quote");
    }
  }, [quoteId]);

  const refetchMargin = useCallback(async () => {
    try {
      setMargin(await getMarginSummary(quoteId));
    } catch {
      // Margin refresh failing shouldn't block the rest of the page.
    }
  }, [quoteId]);

  const saveLine = useCallback(
    async (lineId: number, payload: { quantity?: number; discount_pct?: number }) => {
      setSavingLineIds((prev) => new Set(prev).add(lineId));
      try {
        await updateQuoteLine(quoteId, lineId, payload);
        await refetchMargin();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to save line");
      } finally {
        setSavingLineIds((prev) => {
          const next = new Set(prev);
          next.delete(lineId);
          return next;
        });
      }
    },
    [quoteId, refetchMargin],
  );

  const scheduleSave = useCallback(
    (lineId: number, payload: { quantity?: number; discount_pct?: number }) => {
      clearTimeout(timers.current[lineId]);
      timers.current[lineId] = setTimeout(() => saveLine(lineId, payload), DEBOUNCE_MS);
    },
    [saveLine],
  );

  const flushSave = useCallback(
    (lineId: number, payload: { quantity?: number; discount_pct?: number }) => {
      clearTimeout(timers.current[lineId]);
      saveLine(lineId, payload);
    },
    [saveLine],
  );

  function updateLocalLine(lineId: number, patch: { quantity?: number; discount_pct?: number }) {
    setQuote((prev) =>
      prev
        ? {
            ...prev,
            lines: prev.lines.map((line) => (line.id === lineId ? { ...line, ...patch } : line)),
          }
        : prev,
    );
  }

  async function handleSubmitForApproval() {
    setSubmitting(true);
    setSubmitError(null);
    setSubmitResult(null);
    try {
      const response = await submitQuote(quoteId);
      setSubmitResult(response.risk_result);
      await reloadQuoteAndMargin();
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Failed to submit quote");
    } finally {
      setSubmitting(false);
    }
  }

  if (error) {
    return <p className="text-red-600 dark:text-red-400">Error: {error}</p>;
  }

  if (quote === null) {
    return <p className="text-zinc-500 dark:text-zinc-400">Loading quote…</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          href="/workspace/quotations"
          className="text-sm text-blue-600 hover:underline dark:text-blue-400"
        >
          ← Back to Quotations
        </Link>
        <div className="mt-2 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
              Quote #{quote.id} — {quote.customer_name}
            </h1>
          </div>
          <StatusBadge status={quote.status} />
        </div>
      </div>

      {margin && (
        <div className="flex flex-wrap gap-6 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
          <div>
            <p className="text-xs text-zinc-500 dark:text-zinc-400">Total Price</p>
            <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
              {formatCurrency(margin.total_price)}
            </p>
          </div>
          <div>
            <p className="text-xs text-zinc-500 dark:text-zinc-400">Margin Amount</p>
            <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
              {formatCurrency(margin.total_margin_amount)}
            </p>
          </div>
          <div>
            <p className="text-xs text-zinc-500 dark:text-zinc-400">Overall Margin %</p>
            <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
              {margin.overall_margin_pct.toFixed(1)}%
            </p>
          </div>
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500 dark:bg-zinc-900 dark:text-zinc-400">
            <tr>
              <th className="px-4 py-2">Product</th>
              <th className="px-4 py-2">Quantity</th>
              <th className="px-4 py-2">Discount %</th>
              <th className="px-4 py-2">Line Total</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {quote.lines.map((line) => {
              const product = productById.get(line.product_id);
              const price = product?.price ?? 0;
              const lineTotal = price * line.quantity * (1 - line.discount_pct / 100);
              const isSaving = savingLineIds.has(line.id);

              return (
                <tr key={line.id} className="bg-white dark:bg-zinc-950">
                  <td className="px-4 py-2">
                    {line.product_name}
                    {line.is_recurring && (
                      <span className="ml-2 rounded bg-purple-100 px-1.5 py-0.5 text-xs text-purple-700 dark:bg-purple-900/40 dark:text-purple-300">
                        Recurring
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    <input
                      type="number"
                      min={1}
                      value={line.quantity}
                      onChange={(e) => {
                        const quantity = Number(e.target.value);
                        updateLocalLine(line.id, { quantity });
                        scheduleSave(line.id, { quantity });
                      }}
                      onBlur={(e) => flushSave(line.id, { quantity: Number(e.target.value) })}
                      className="w-20 rounded border border-zinc-300 px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
                    />
                  </td>
                  <td className="px-4 py-2">
                    <input
                      type="number"
                      min={0}
                      max={100}
                      step={0.5}
                      value={line.discount_pct}
                      onChange={(e) => {
                        const discount_pct = Number(e.target.value);
                        updateLocalLine(line.id, { discount_pct });
                        scheduleSave(line.id, { discount_pct });
                      }}
                      onBlur={(e) => flushSave(line.id, { discount_pct: Number(e.target.value) })}
                      className="w-20 rounded border border-zinc-300 px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
                    />
                  </td>
                  <td className="px-4 py-2 font-medium">{formatCurrency(lineTotal)}</td>
                  <td className="px-4 py-2 text-xs text-zinc-400">
                    {isSaving ? "Saving…" : ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-col gap-3">
        {quote.status === "draft" && (
          <button
            onClick={handleSubmitForApproval}
            disabled={submitting}
            className="w-fit rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {submitting ? "Submitting…" : "Submit for Approval"}
          </button>
        )}
        {submitError && <p className="text-sm text-red-600 dark:text-red-400">{submitError}</p>}
        {submitResult && <RiskResultPanel result={submitResult} />}
      </div>
    </div>
  );
}
