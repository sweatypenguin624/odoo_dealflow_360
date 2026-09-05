"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  getPortalQuote,
  listPortalProducts,
  submitPortalComment,
} from "@/lib/portalApi";
import type { PortalProductRef, PortalQuote, PortalQuoteLine } from "@/lib/portalApi";

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);
}

function CommentThread({
  line,
  onSubmit,
}: {
  line: PortalQuoteLine;
  onSubmit: (comment: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    if (!draft.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(draft.trim());
      setDraft("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't send that — please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mt-3 flex flex-col gap-2">
      {line.comments.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {line.comments.map((comment) => {
            const isCustomer = comment.author_type === "customer";
            return (
              <li
                key={comment.id}
                className={`max-w-[85%] rounded-lg px-3 py-1.5 text-sm ${
                  isCustomer
                    ? "self-end bg-blue-100 text-blue-900 dark:bg-blue-900/40 dark:text-blue-200"
                    : "self-start bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200"
                }`}
              >
                <p className="text-xs font-medium opacity-70">
                  {isCustomer ? "You" : comment.author_name}
                </p>
                <p>{comment.comment}</p>
              </li>
            );
          })}
        </ul>
      )}
      <div className="flex gap-2">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask a question or request a change to this line…"
          rows={2}
          className="flex-1 rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        />
        <button
          onClick={handleSubmit}
          disabled={submitting || !draft.trim()}
          className="h-fit rounded bg-zinc-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-600 dark:hover:bg-zinc-500"
        >
          {submitting ? "Sending…" : "Submit Request"}
        </button>
      </div>
      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  );
}

export default function CustomerPortalPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);

  const [quote, setQuote] = useState<PortalQuote | null>(null);
  const [products, setProducts] = useState<PortalProductRef[]>([]);
  const [error, setError] = useState<string | null>(null);

  const productById = useMemo(() => {
    const map = new Map<number, PortalProductRef>();
    for (const product of products) map.set(product.id, product);
    return map;
  }, [products]);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [quoteData, productList] = await Promise.all([
        getPortalQuote(token),
        listPortalProducts(),
      ]);
      setQuote(quoteData);
      setProducts(productList);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "We couldn't load your quotation.");
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    return <p className="text-red-600 dark:text-red-400">{error}</p>;
  }

  if (quote === null) {
    return <p className="text-zinc-500 dark:text-zinc-400">Loading your quotation…</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
          Quotation #{quote.quote_id}
        </h1>
        <span className="inline-block rounded-full bg-blue-100 px-3 py-1 text-sm font-medium text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
          {quote.status}
        </span>
      </div>

      <div className="flex flex-col gap-4">
        {quote.lines.map((line) => {
          const product = productById.get(line.product_id);
          return (
            <div
              key={line.id}
              className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium text-zinc-900 dark:text-zinc-50">
                  {product?.name ?? `Product #${line.product_id}`}
                </p>
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  Qty {line.quantity} · {line.discount_pct}% off
                </p>
                <p className="font-medium text-zinc-900 dark:text-zinc-50">
                  {formatCurrency(line.line_value)}
                </p>
              </div>

              <CommentThread
                line={line}
                onSubmit={async (comment) => {
                  await submitPortalComment(token, line.id, comment);
                  await load();
                }}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
