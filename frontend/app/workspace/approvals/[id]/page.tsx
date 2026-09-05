"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { ApiError, getApprovalHistory, getQuote, submitApprovalAction } from "@/lib/api";
import type { ApprovalHistoryResponse, ApprovalStep, QuoteDetail } from "@/lib/api";
import { useReload } from "@/lib/reload-context";
import { StatusBadge } from "@/components/StatusBadge";

type StepState = "done" | "current" | "pending";

function stepState(step: ApprovalStep, quote: QuoteDetail): StepState {
  if (quote.status === "approved" || quote.status === "confirmed") return "done";
  if (quote.current_approval_step === step) return "current";
  if (step === "manager" && quote.current_approval_step === "finance") return "done";
  return "pending";
}

function StepBadge({ label, state }: { label: string; state: StepState }) {
  const style =
    state === "done"
      ? "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300"
      : state === "current"
        ? "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
        : "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400";

  return (
    <span className={`rounded-full px-3 py-1 text-xs font-medium ${style}`}>
      {label} {state === "done" ? "✓" : state === "current" ? "(in progress)" : ""}
    </span>
  );
}

export default function ApprovalDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const quoteId = Number(id);
  const { reloadNonce } = useReload();

  const [quote, setQuote] = useState<QuoteDetail | null>(null);
  const [history, setHistory] = useState<ApprovalHistoryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actor, setActor] = useState("");
  const [note, setNote] = useState("");
  const [actionInFlight, setActionInFlight] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setError(null);
      try {
        const [quoteDetail, approvalHistory] = await Promise.all([
          getQuote(quoteId),
          getApprovalHistory(quoteId),
        ]);
        if (!cancelled) {
          setQuote(quoteDetail);
          setHistory(approvalHistory);
          setActor((prev) => prev || (quoteDetail.current_approval_step === "finance" ? "Finance" : "Manager"));
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

  async function handleAction(action: "approved" | "rejected" | "returned_for_revision") {
    setActionInFlight(action);
    setActionError(null);
    try {
      await submitApprovalAction(quoteId, { actor: actor || "Unknown", action, note: note || undefined });
      const [quoteDetail, approvalHistory] = await Promise.all([
        getQuote(quoteId),
        getApprovalHistory(quoteId),
      ]);
      setQuote(quoteDetail);
      setHistory(approvalHistory);
      setNote("");
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Action failed");
    } finally {
      setActionInFlight(null);
    }
  }

  if (error) return <p className="text-red-600 dark:text-red-400">Error: {error}</p>;
  if (quote === null) return <p className="text-zinc-500 dark:text-zinc-400">Loading…</p>;

  const showFinanceStep = quote.required_approval_level === "manager_then_finance";

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          href="/workspace/approvals"
          className="text-sm text-blue-600 hover:underline dark:text-blue-400"
        >
          ← Back to Approvals
        </Link>
        <div className="mt-2 flex items-center justify-between">
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
            Quote #{quote.id} — {quote.customer_name}
          </h1>
          <StatusBadge status={quote.status} />
        </div>
      </div>

      <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <p className="text-sm text-zinc-500 dark:text-zinc-400">Required Approval Level</p>
        <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          {quote.required_approval_level ?? "—"}
        </p>

        {quote.risk_reasons && quote.risk_reasons.length > 0 && (
          <ul className="mt-3 list-inside list-disc text-sm text-zinc-700 dark:text-zinc-300">
            {quote.risk_reasons.map((reason, i) => (
              <li key={i}>{reason}</li>
            ))}
          </ul>
        )}

        <div className="mt-4 flex items-center gap-3">
          <StepBadge label="Sales Manager" state={stepState("manager", quote)} />
          {showFinanceStep && <StepBadge label="Finance" state={stepState("finance", quote)} />}
        </div>
      </div>

      {quote.status === "pending_approval" && (
        <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
          <p className="mb-3 text-sm font-medium text-zinc-700 dark:text-zinc-300">
            Acting as {quote.current_approval_step ?? "approver"}
          </p>
          <div className="mb-3 flex flex-col gap-2 sm:flex-row">
            <input
              value={actor}
              onChange={(e) => setActor(e.target.value)}
              placeholder="Your name"
              className="rounded border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Note (optional)"
              className="flex-1 rounded border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => handleAction("approved")}
              disabled={actionInFlight !== null}
              className="rounded bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
            >
              {actionInFlight === "approved" ? "Approving…" : "Approve"}
            </button>
            <button
              onClick={() => handleAction("rejected")}
              disabled={actionInFlight !== null}
              className="rounded bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              {actionInFlight === "rejected" ? "Rejecting…" : "Reject"}
            </button>
            <button
              onClick={() => handleAction("returned_for_revision")}
              disabled={actionInFlight !== null}
              className="rounded border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
            >
              {actionInFlight === "returned_for_revision" ? "Returning…" : "Return for Revision"}
            </button>
          </div>
          {actionError && (
            <p className="mt-2 text-sm text-red-600 dark:text-red-400">{actionError}</p>
          )}
        </div>
      )}

      <div>
        <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-50">History</h2>
        <ol className="flex flex-col gap-2">
          {history?.audit_logs.map((entry) => (
            <li
              key={`audit-${entry.id}`}
              className="rounded border border-zinc-200 bg-white p-3 text-sm dark:border-zinc-800 dark:bg-zinc-900"
            >
              <p className="font-medium text-zinc-900 dark:text-zinc-50">
                {entry.action.replaceAll("_", " ")} — {entry.user}
              </p>
              {entry.reason && (
                <p className="text-zinc-600 dark:text-zinc-400">{entry.reason}</p>
              )}
              <p className="text-xs text-zinc-400">{new Date(entry.timestamp).toLocaleString()}</p>
            </li>
          ))}
          {history?.audit_logs.length === 0 && (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">No history yet.</p>
          )}
        </ol>
      </div>
    </div>
  );
}
