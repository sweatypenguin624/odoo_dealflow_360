"use client";

import { useEffect, useState } from "react";
import { addSuggestion, ApiError, getUpsellSuggestions } from "@/lib/api";
import type { RankedSuggestion } from "@/lib/api";

interface UpsellPanelProps {
  quoteId: number;
  /** Any existing QuoteLine id on this quote - add-suggestion's path
   * requires one to confirm the quote/line pairing, but doesn't attach
   * the new line to it in any other way. */
  anchorLineId: number | null;
  /** Called after a successful add so the parent can refetch the cart
   * and margin summary. */
  onAdded: () => void;
}

export function UpsellPanel({ quoteId, anchorLineId, onAdded }: UpsellPanelProps) {
  const [suggestions, setSuggestions] = useState<RankedSuggestion[] | null>(null);
  const [dismissedIds, setDismissedIds] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [addingProductId, setAddingProductId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setError(null);
      try {
        const result = await getUpsellSuggestions(quoteId);
        if (!cancelled) setSuggestions(result);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load suggestions");
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [quoteId]);

  async function handleAdd(productId: number) {
    if (anchorLineId === null) return;
    setAddingProductId(productId);
    setError(null);
    try {
      await addSuggestion(quoteId, anchorLineId, { product_id: productId, quantity: 1 });
      setDismissedIds((prev) => new Set(prev).add(productId));
      onAdded();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to add suggestion");
    } finally {
      setAddingProductId(null);
    }
  }

  function handleDismiss(productId: number) {
    setDismissedIds((prev) => new Set(prev).add(productId));
  }

  const visible = (suggestions ?? []).filter((s) => !dismissedIds.has(s.product_id));

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
        Upsell &amp; Cross-Sell Suggestions
      </h2>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      {suggestions === null && <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>}
      {suggestions !== null && visible.length === 0 && (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">No suggestions right now.</p>
      )}

      <ul className="flex flex-col gap-3">
        {visible.map((suggestion) => (
          <li
            key={suggestion.product_id}
            className="rounded border border-zinc-200 p-3 dark:border-zinc-700"
          >
            <div className="flex items-center justify-between gap-2">
              <p className="font-medium text-zinc-900 dark:text-zinc-50">{suggestion.name}</p>
              {suggestion.is_promoted && (
                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
                  Promoted
                </span>
              )}
            </div>
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
              ${suggestion.price.toFixed(2)} · margin{" "}
              {suggestion.margin_delta_if_added >= 0 ? "+" : ""}
              {suggestion.margin_delta_if_added.toFixed(2)}pp if added
            </p>
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{suggestion.reason}</p>
            <div className="mt-2 flex gap-2">
              <button
                onClick={() => handleAdd(suggestion.product_id)}
                disabled={addingProductId === suggestion.product_id || anchorLineId === null}
                className="rounded bg-blue-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {addingProductId === suggestion.product_id ? "Adding…" : "Add to Quote"}
              </button>
              <button
                onClick={() => handleDismiss(suggestion.product_id)}
                className="rounded border border-zinc-300 px-2.5 py-1 text-xs text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
              >
                Dismiss
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
