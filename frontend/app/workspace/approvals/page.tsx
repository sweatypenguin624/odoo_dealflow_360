"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ApiError, getPendingApproval } from "@/lib/api";
import type { ApprovalStep, QuoteListItem } from "@/lib/api";
import { useReload } from "@/lib/reload-context";
import { useRole } from "@/lib/roleContext";
import { StatusBadge } from "@/components/StatusBadge";

function FilterLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={
        active
          ? "font-semibold text-blue-600 dark:text-blue-400"
          : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
      }
    >
      {children}
    </Link>
  );
}

export default function ApprovalsPage() {
  return (
    <Suspense fallback={<p className="text-zinc-500 dark:text-zinc-400">Loading…</p>}>
      <ApprovalsPageInner />
    </Suspense>
  );
}

function ApprovalsPageInner() {
  const searchParams = useSearchParams();
  const { role } = useRole();
  const { reloadNonce } = useReload();

  // No explicit ?step= in the URL: default per role (manager -> manager,
  // finance -> finance, rep -> the full queue, since reps track their own
  // submissions across both steps). "All" is its own explicit sentinel
  // (?step=all) rather than "no param", so a manager/finance user can still
  // deliberately choose the full view and have it stick on this URL.
  const rawStep = searchParams.get("step");
  const roleDefaultStep: ApprovalStep | undefined =
    role === "sales_manager" ? "manager" : role === "finance_manager" ? "finance" : undefined;
  const stepFilter: ApprovalStep | undefined =
    rawStep === "manager" || rawStep === "finance"
      ? rawStep
      : rawStep === "all"
        ? undefined
        : roleDefaultStep;

  const [quotes, setQuotes] = useState<QuoteListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setError(null);
      try {
        const list = await getPendingApproval(stepFilter);
        if (!cancelled) setQuotes(list);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load approvals");
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [stepFilter, reloadNonce]);

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Pending Approvals</h1>
        <div className="flex gap-3 text-sm">
          <FilterLink href="/workspace/approvals?step=all" active={!stepFilter}>
            All
          </FilterLink>
          <FilterLink href="/workspace/approvals?step=manager" active={stepFilter === "manager"}>
            Manager
          </FilterLink>
          <FilterLink href="/workspace/approvals?step=finance" active={stepFilter === "finance"}>
            Finance
          </FilterLink>
        </div>
      </div>

      {error && <p className="text-red-600 dark:text-red-400">Error: {error}</p>}
      {quotes === null && !error && <p className="text-zinc-500 dark:text-zinc-400">Loading…</p>}
      {quotes !== null && quotes.length === 0 && (
        <p className="text-zinc-500 dark:text-zinc-400">Nothing pending.</p>
      )}

      <div className="flex flex-col gap-3">
        {quotes?.map((quote) => (
          <Link
            key={quote.id}
            href={`/workspace/approvals/${quote.id}`}
            className="flex items-center justify-between rounded-lg border border-zinc-200 bg-white p-4 transition hover:border-blue-400 hover:shadow dark:border-zinc-800 dark:bg-zinc-900"
          >
            <div>
              <p className="font-medium text-zinc-900 dark:text-zinc-50">{quote.customer_name}</p>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                Quote #{quote.id} · step: {quote.current_approval_step ?? "—"} · level:{" "}
                {quote.required_approval_level ?? "—"}
              </p>
            </div>
            <StatusBadge status={quote.status} />
          </Link>
        ))}
      </div>
    </div>
  );
}
