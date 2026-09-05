"use client";

import { use, useEffect, useState } from "react";
import { ApiError, getPortalQuote } from "@/lib/portalApi";
import type { PortalQuote } from "@/lib/portalApi";

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);
}

export default function CustomerPortalPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);

  const [quote, setQuote] = useState<PortalQuote | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setError(null);
      try {
        const data = await getPortalQuote(token);
        if (!cancelled) setQuote(data);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "We couldn't load your quotation.");
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [token]);

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

      <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
        <table className="w-full min-w-[480px] text-sm">
          <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500 dark:bg-zinc-900 dark:text-zinc-400">
            <tr>
              <th className="px-4 py-2">Product</th>
              <th className="px-4 py-2">Quantity</th>
              <th className="px-4 py-2">Discount</th>
              <th className="px-4 py-2">Line Total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {quote.lines.map((line) => (
              <tr key={line.id} className="bg-white dark:bg-zinc-950">
                <td className="px-4 py-2">Product #{line.product_id}</td>
                <td className="px-4 py-2">{line.quantity}</td>
                <td className="px-4 py-2">{line.discount_pct}%</td>
                <td className="px-4 py-2 font-medium">{formatCurrency(line.line_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
