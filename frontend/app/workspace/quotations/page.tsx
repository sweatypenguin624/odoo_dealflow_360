"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { getMarginSummary, listQuotes } from "@/lib/api";
import type { QuoteListItem, QuoteStatus } from "@/lib/api";
import { useReload } from "@/lib/reload-context";
import { StatusBadge } from "@/components/StatusBadge";

const PIPELINE_COLUMNS: QuoteStatus[] = [
  "draft",
  "pending_approval",
  "approved",
  "confirmed",
  "rejected",
];

interface QuoteWithAmount extends QuoteListItem {
  amount: number | null;
}

function formatCurrency(amount: number | null): string {
  if (amount === null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);
}

function QuoteCard({ quote }: { quote: QuoteWithAmount }) {
  return (
    <Link
      href={`/workspace/quotations/${quote.id}`}
      className="block rounded-lg border border-zinc-200 bg-white p-4 shadow-sm transition hover:border-blue-400 hover:shadow dark:border-zinc-800 dark:bg-zinc-900"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-medium text-zinc-900 dark:text-zinc-50">{quote.customer_name}</p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">Quote #{quote.id}</p>
        </div>
        <StatusBadge status={quote.status} />
      </div>
      <p className="mt-3 text-lg font-semibold text-zinc-900 dark:text-zinc-50">
        {formatCurrency(quote.amount)}
      </p>
    </Link>
  );
}

export default function QuotationsPage() {
  return (
    <Suspense fallback={<p className="text-zinc-500 dark:text-zinc-400">Loading…</p>}>
      <QuotationsPageInner />
    </Suspense>
  );
}

function QuotationsPageInner() {
  const searchParams = useSearchParams();
  const isPipelineView = searchParams.get("view") === "pipeline";
  const { reloadNonce } = useReload();

  const [quotes, setQuotes] = useState<QuoteWithAmount[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setError(null);
      try {
        const list = await listQuotes();
        const withAmounts = await Promise.all(
          list.map(async (quote) => {
            try {
              const margin = await getMarginSummary(quote.id);
              return { ...quote, amount: margin.total_price };
            } catch {
              return { ...quote, amount: null };
            }
          }),
        );
        if (!cancelled) setQuotes(withAmounts);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load quotes");
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [reloadNonce]);

  if (error) {
    return <p className="text-red-600 dark:text-red-400">Error loading quotes: {error}</p>;
  }

  if (quotes === null) {
    return <p className="text-zinc-500 dark:text-zinc-400">Loading quotes…</p>;
  }

  if (!isPipelineView) {
    return (
      <div>
        <h1 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-zinc-50">Quotations</h1>
        {quotes.length === 0 ? (
          <p className="text-zinc-500 dark:text-zinc-400">No quotes yet.</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {quotes.map((quote) => (
              <QuoteCard key={quote.id} quote={quote} />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-zinc-50">Pipeline</h1>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {PIPELINE_COLUMNS.map((status) => {
          const columnQuotes = quotes.filter((q) => q.status === status);
          return (
            <div key={status} className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <StatusBadge status={status} />
                <span className="text-xs text-zinc-500 dark:text-zinc-400">
                  {columnQuotes.length}
                </span>
              </div>
              <div className="flex flex-col gap-3">
                {columnQuotes.map((quote) => (
                  <QuoteCard key={quote.id} quote={quote} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
