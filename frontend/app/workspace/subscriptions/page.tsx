"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, getQuote, listQuotes } from "@/lib/api";
import type { QuoteDetail } from "@/lib/api";
import { useReload } from "@/lib/reload-context";
import { StatusBadge } from "@/components/StatusBadge";

export default function SubscriptionsListPage() {
  const { reloadNonce } = useReload();
  const [quotes, setQuotes] = useState<QuoteDetail[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setError(null);
      try {
        const list = await listQuotes();
        const details = await Promise.all(list.map((q) => getQuote(q.id)));
        const withRecurring = details.filter((quote) =>
          quote.lines.some((line) => line.is_recurring),
        );
        if (!cancelled) setQuotes(withRecurring);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load subscriptions");
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
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Subscriptions</h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Quotes with at least one recurring line.
        </p>
      </div>

      {quotes.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">No recurring lines yet.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {quotes.map((quote) => {
            const recurringLines = quote.lines.filter((line) => line.is_recurring);
            return (
              <Link
                key={quote.id}
                href={`/workspace/quotations/${quote.id}/billing`}
                className="flex items-center justify-between rounded-lg border border-zinc-200 bg-white p-4 transition hover:border-blue-400 hover:shadow dark:border-zinc-800 dark:bg-zinc-900"
              >
                <div>
                  <p className="font-medium text-zinc-900 dark:text-zinc-50">
                    {quote.customer_name}
                  </p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    Quote #{quote.id} · {recurringLines.length} recurring line
                    {recurringLines.length === 1 ? "" : "s"}: {" "}
                    {recurringLines.map((l) => l.product_name).join(", ")}
                  </p>
                </div>
                <StatusBadge status={quote.status} />
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
