"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, getFulfillment, listQuotes } from "@/lib/api";
import type { QuoteListItem } from "@/lib/api";
import { useReload } from "@/lib/reload-context";
import { StatusBadge } from "@/components/StatusBadge";

// Fulfillment only becomes relevant once a quote has cleared approval -
// draft/pending_approval/rejected quotes have nothing to ship yet.
const FULFILLABLE_STATUSES = new Set(["approved", "confirmed"]);

interface FulfillableQuote extends QuoteListItem {
  fulfillmentStatus: string | null; // null = no plan suggested/confirmed yet
}

export default function FulfillmentListPage() {
  const { reloadNonce } = useReload();
  const [quotes, setQuotes] = useState<FulfillableQuote[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setError(null);
      try {
        const list = await listQuotes();
        const candidates = list.filter((q) => FULFILLABLE_STATUSES.has(q.status));
        const withStatus = await Promise.all(
          candidates.map(async (quote) => {
            try {
              const plan = await getFulfillment(quote.id);
              return { ...quote, fulfillmentStatus: plan.status };
            } catch (err) {
              if (err instanceof ApiError && err.status === 404) {
                return { ...quote, fulfillmentStatus: null };
              }
              throw err;
            }
          }),
        );
        if (!cancelled) setQuotes(withStatus);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load fulfillment");
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [reloadNonce]);

  if (error) return <p className="text-red-600 dark:text-red-400">Error: {error}</p>;
  if (quotes === null) return <p className="text-zinc-500 dark:text-zinc-400">Loading…</p>;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Fulfillment</h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Approved and confirmed quotes ready for (or already through) shipment planning.
        </p>
      </div>

      {quotes.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">Nothing to fulfill right now.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {quotes.map((quote) => (
            <Link
              key={quote.id}
              href={`/workspace/quotations/${quote.id}/fulfillment`}
              className="flex items-center justify-between rounded-lg border border-zinc-200 bg-white p-4 transition hover:border-blue-400 hover:shadow dark:border-zinc-800 dark:bg-zinc-900"
            >
              <div>
                <p className="font-medium text-zinc-900 dark:text-zinc-50">
                  {quote.customer_name}
                </p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">Quote #{quote.id}</p>
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={quote.status} />
                {quote.fulfillmentStatus ? (
                  <StatusBadge status={quote.fulfillmentStatus} />
                ) : (
                  <span className="rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
                    Not started
                  </span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
