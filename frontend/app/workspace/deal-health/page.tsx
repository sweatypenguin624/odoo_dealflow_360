"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { ApiError, getDealHealth } from "@/lib/api";
import type { DealHealthFlag, QuoteHealth } from "@/lib/api";
import { useReload } from "@/lib/reload-context";
import { useRole } from "@/lib/roleContext";
import { StatusBadge } from "@/components/StatusBadge";

// The backend's deal-health engine (backend/app/services/deal_health_engine.py)
// only emits "stalled" and "discount_anomaly" flags - a delivery-promise
// slippage flag was in the original plan but was never implemented there,
// so no such indicator is built here (would be fabricated data otherwise).

type FlagFilter = "flagged" | "discount_anomaly" | null;

function detailHref(quote: QuoteHealth): string {
  return quote.status === "pending_approval"
    ? `/workspace/approvals/${quote.quote_id}`
    : `/workspace/quotations/${quote.quote_id}`;
}

function hasAnomaly(quote: QuoteHealth): boolean {
  return quote.flags.some((f) => f.flag_type === "discount_anomaly");
}

function FlagBadge({ flag }: { flag: DealHealthFlag }) {
  if (flag.flag_type === "stalled") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
        Stalled
      </span>
    );
  }

  const style =
    flag.severity === "critical"
      ? "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300"
      : "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300";

  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>
      Discount Anomaly {flag.severity === "critical" ? "(critical)" : ""}
    </span>
  );
}

// No backend endpoint exists to actually escalate or nudge on an alert
// (no such action was built in Phase 7). Rather than invent real side
// effects, this stays a clearly-labeled demo-only affordance.
function NudgeButton({ quote }: { quote: QuoteHealth }) {
  const [message, setMessage] = useState<string | null>(null);

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={() => setMessage(`(Demo only) Nudge queued for ${quote.rep_name} — no backend action is wired up.`)}
        className="rounded border border-zinc-300 px-2 py-1 text-xs font-medium text-zinc-600 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
      >
        Nudge (Demo)
      </button>
      {message && <p className="text-right text-xs text-zinc-400">{message}</p>}
    </div>
  );
}

export default function DealHealthDashboardPage() {
  return (
    <Suspense fallback={<p className="text-zinc-500 dark:text-zinc-400">Loading…</p>}>
      <DealHealthPageInner />
    </Suspense>
  );
}

function DealHealthPageInner() {
  const searchParams = useSearchParams();
  const filter = searchParams.get("filter") as FlagFilter;
  const { role } = useRole();
  const { reloadNonce } = useReload();

  const [quotes, setQuotes] = useState<QuoteHealth[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setError(null);
      try {
        const data = await getDealHealth();
        if (!cancelled) setQuotes(data);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load deal health");
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [reloadNonce]);

  const displayedQuotes = useMemo(() => {
    if (quotes === null) return [];

    let list = quotes;
    if (filter === "flagged") list = list.filter((q) => q.flags.length > 0);
    if (filter === "discount_anomaly") list = list.filter(hasAnomaly);

    // Finance's specific lens: discount anomalies are financially relevant,
    // staleness is more of an operational/rep concern - surface anomalies
    // first rather than hiding stalled ones entirely.
    if (role === "finance_manager") {
      list = [...list].sort((a, b) => Number(hasAnomaly(b)) - Number(hasAnomaly(a)));
    }

    return list;
  }, [quotes, filter, role]);

  if (error) return <p className="text-red-600 dark:text-red-400">Error: {error}</p>;
  if (quotes === null) return <p className="text-zinc-500 dark:text-zinc-400">Loading…</p>;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Deal Health</h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Non-terminal quotes flagged for stalled activity or unusual discounting.
        </p>
        {filter && (
          <p className="mt-2 text-sm text-blue-600 dark:text-blue-400">
            Showing: {filter === "flagged" ? "flagged deals only" : "discount anomalies only"} ·{" "}
            <Link href="/workspace/deal-health" className="underline">
              Clear filter
            </Link>
          </p>
        )}
      </div>

      <div className="flex flex-col gap-3">
        {displayedQuotes.map((quote) => (
          <Link
            key={quote.quote_id}
            href={detailHref(quote)}
            className="flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-4 hover:border-blue-300 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-blue-800 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2">
                <p className="font-medium text-zinc-900 dark:text-zinc-50">
                  Quote #{quote.quote_id} — {quote.customer_name}
                </p>
                <StatusBadge status={quote.status} />
              </div>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                Rep: {quote.rep_name} · Discount: {quote.applied_discount_pct.toFixed(1)}% · Last
                activity: {quote.last_updated_at}
              </p>
              {quote.flags.length > 0 && (
                <div className="mt-1 flex flex-col gap-1">
                  <div className="flex flex-wrap gap-2">
                    {quote.flags.map((flag, i) => (
                      <FlagBadge key={i} flag={flag} />
                    ))}
                  </div>
                  {quote.flags.map((flag, i) => (
                    <p key={i} className="text-xs text-zinc-500 dark:text-zinc-400">
                      {flag.message}
                    </p>
                  ))}
                </div>
              )}
            </div>

            {quote.flags.length > 0 && (
              <div onClick={(e) => e.preventDefault()}>
                <NudgeButton quote={quote} />
              </div>
            )}
          </Link>
        ))}
        {displayedQuotes.length === 0 && (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {filter ? "No quotes match this filter." : "No active quotes to show."}
          </p>
        )}
      </div>
    </div>
  );
}
