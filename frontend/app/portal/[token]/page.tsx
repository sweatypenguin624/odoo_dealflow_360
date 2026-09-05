"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  confirmPortalQuote,
  getPortalQuote,
  listPortalProducts,
  submitCounterProposal,
  submitPortalComment,
} from "@/lib/portalApi";
import type { PortalProductRef, PortalQuote, PortalQuoteLine } from "@/lib/portalApi";

// GET /portal/quote fails with 401 for a bad/expired token and 403 for a
// quote that isn't visible yet (still in draft). Neither case should ever
// mention tokens, status codes, or internal terms to a customer.
function loadErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) {
      return "This link has expired or is no longer valid. Please contact your sales representative for a new one.";
    }
    if (err.status === 403) {
      return "This quotation isn't ready to view yet. Please check back soon, or contact your sales representative.";
    }
  }
  return "We couldn't load your quotation. Please try again shortly.";
}

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

type ProposalBanner = { kind: "applied" | "pending"; text: string };

export default function CustomerPortalPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);

  const [quote, setQuote] = useState<PortalQuote | null>(null);
  const [products, setProducts] = useState<PortalProductRef[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [draftDiscounts, setDraftDiscounts] = useState<Record<number, string>>({});
  const [proposalSubmitting, setProposalSubmitting] = useState(false);
  const [proposalError, setProposalError] = useState<string | null>(null);
  const [proposalBanner, setProposalBanner] = useState<ProposalBanner | null>(null);

  const productById = useMemo(() => {
    const map = new Map<number, PortalProductRef>();
    for (const product of products) map.set(product.id, product);
    return map;
  }, [products]);

  const refetch = useCallback(async () => {
    const [quoteData, productList] = await Promise.all([
      getPortalQuote(token),
      listPortalProducts(),
    ]);
    setQuote(quoteData);
    setProducts(productList);
  }, [token]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setError(null);
      try {
        const [quoteData, productList] = await Promise.all([
          getPortalQuote(token),
          listPortalProducts(),
        ]);
        if (!cancelled) {
          setQuote(quoteData);
          setProducts(productList);
        }
      } catch (err) {
        if (!cancelled) {
          setError(loadErrorMessage(err));
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const [confirmSubmitting, setConfirmSubmitting] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  async function handleConfirm() {
    setConfirmSubmitting(true);
    setConfirmError(null);
    try {
      await confirmPortalQuote(token);
      await refetch();
    } catch {
      setConfirmError(
        "We couldn't confirm this quotation right now — please try again or contact your sales representative.",
      );
    } finally {
      setConfirmSubmitting(false);
    }
  }

  const proposedEntries = Object.entries(draftDiscounts).filter(([, value]) => value.trim() !== "");

  async function handleSubmitProposal() {
    if (proposedEntries.length === 0) return;
    setProposalSubmitting(true);
    setProposalError(null);
    setProposalBanner(null);
    try {
      const proposedLines = proposedEntries.map(([lineId, value]) => ({
        quote_line_id: Number(lineId),
        proposed_discount_pct: Number(value),
      }));
      const result = await submitCounterProposal(token, proposedLines);

      setProposalBanner(
        result.counter_proposal.status === "accepted"
          ? {
              kind: "applied",
              text: "Your requested change has been applied — the quote below is up to date.",
            }
          : {
              kind: "pending",
              text: "Your request has been sent for internal review — we'll follow up shortly.",
            },
      );
      setDraftDiscounts({});
      await refetch();
    } catch (err) {
      setProposalError(
        err instanceof ApiError ? err.message : "We couldn't submit your request — please try again.",
      );
    } finally {
      setProposalSubmitting(false);
    }
  }

  if (error) {
    return (
      <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-6 text-center dark:border-zinc-800 dark:bg-zinc-900">
        <p className="text-zinc-700 dark:text-zinc-300">{error}</p>
      </div>
    );
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

      <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        {quote.status === "Sent" && (
          <>
            <p className="mb-3 text-sm text-zinc-600 dark:text-zinc-400">
              This quotation is ready for you to confirm.
            </p>
            <button
              onClick={handleConfirm}
              disabled={confirmSubmitting}
              className="rounded bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
            >
              {confirmSubmitting ? "Confirming…" : "Confirm Quotation"}
            </button>
            {confirmError && (
              <p className="mt-2 text-sm text-red-600 dark:text-red-400">{confirmError}</p>
            )}
          </>
        )}
        {quote.status === "Under Negotiation" && (
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Awaiting internal approval — you&apos;ll be able to confirm this quotation once
            that&apos;s complete.
          </p>
        )}
        {quote.status === "Confirmed" && (
          <p className="text-sm text-green-700 dark:text-green-400">
            You&apos;ve confirmed this quotation. Thank you!
          </p>
        )}
        {quote.status === "Rejected" && (
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            This quotation is no longer available for confirmation. Please contact your sales
            representative.
          </p>
        )}
      </div>

      {proposalBanner && (
        <div
          className={`rounded-lg border p-4 text-sm ${
            proposalBanner.kind === "applied"
              ? "border-green-200 bg-green-50 text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-300"
              : "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300"
          }`}
        >
          {proposalBanner.text}
        </div>
      )}

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

              <div className="mt-3 flex items-center gap-2 text-sm">
                <label className="text-zinc-500 dark:text-zinc-400" htmlFor={`discount-${line.id}`}>
                  Propose a different discount %:
                </label>
                <input
                  id={`discount-${line.id}`}
                  type="number"
                  min={0}
                  max={100}
                  step={0.5}
                  placeholder={`${line.discount_pct}`}
                  value={draftDiscounts[line.id] ?? ""}
                  onChange={(e) =>
                    setDraftDiscounts((prev) => ({ ...prev, [line.id]: e.target.value }))
                  }
                  className="w-24 rounded border border-zinc-300 px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
                />
              </div>

              <CommentThread
                line={line}
                onSubmit={async (comment) => {
                  await submitPortalComment(token, line.id, comment);
                  await refetch();
                }}
              />
            </div>
          );
        })}
      </div>

      <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <p className="mb-3 text-sm text-zinc-600 dark:text-zinc-400">
          Enter a proposed discount above for any line you&apos;d like changed, then submit — you
          don&apos;t need to change every line.
        </p>
        <button
          onClick={handleSubmitProposal}
          disabled={proposalSubmitting || proposedEntries.length === 0}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {proposalSubmitting ? "Submitting…" : "Submit Request"}
        </button>
        {proposalError && (
          <p className="mt-2 text-sm text-red-600 dark:text-red-400">{proposalError}</p>
        )}
      </div>
    </div>
  );
}
