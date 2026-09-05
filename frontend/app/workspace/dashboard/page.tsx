"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  createQuote,
  getDealHealth,
  getPendingApproval,
  getRecentAuditLog,
  listCustomers,
  listInvoices,
  listProducts,
  listQuotes,
} from "@/lib/api";
import type {
  CustomerRef,
  InvoiceListItem,
  ProductRef,
  QuoteHealth,
  QuoteListItem,
  RecentAuditLogEntry,
} from "@/lib/api";
import { useReload } from "@/lib/reload-context";
import { useRole } from "@/lib/roleContext";

const OPEN_STATUSES = new Set(["draft", "pending_approval", "approved"]);
// Client-side keyword filter over the existing recent-activity feed - no
// new backend endpoint needed, per the "acceptable fallback" guidance for
// finance-relevant activity.
const FINANCE_ACTIVITY_KEYWORDS = ["approv", "payment", "invoice"];

function Tile({ label, value, href }: { label: string; value: number; href: string }) {
  return (
    <Link
      href={href}
      className="flex flex-col gap-1 rounded-lg border border-zinc-200 bg-white p-4 transition hover:border-blue-400 hover:shadow dark:border-zinc-800 dark:bg-zinc-900"
    >
      <p className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className="text-3xl font-semibold text-zinc-900 dark:text-zinc-50">{value}</p>
    </Link>
  );
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

function activityLine(entry: RecentAuditLogEntry): string {
  const base = `${entry.customer_name} (Quote #${entry.quote_id}) — ${entry.action.replaceAll("_", " ")}`;
  return entry.reason ? `${base}: ${entry.reason}` : base;
}

function NewQuotationForm({
  customers,
  products,
  onCreated,
}: {
  customers: CustomerRef[];
  products: ProductRef[];
  onCreated: (quoteId: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const [customerId, setCustomerId] = useState<number | "">("");
  const [repName, setRepName] = useState("");
  const [productId, setProductId] = useState<number | "">("");
  const [quantity, setQuantity] = useState(1);
  const [discountPct, setDiscountPct] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate() {
    if (customerId === "" || productId === "") return;
    setSubmitting(true);
    setError(null);
    try {
      const quote = await createQuote({
        customer_id: customerId,
        rep_name: repName || undefined,
        lines: [{ product_id: productId, quantity, discount_pct: discountPct }],
      });
      onCreated(quote.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create quotation");
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="w-fit rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
      >
        + New Quotation
      </button>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <p className="mb-3 text-sm font-semibold text-zinc-900 dark:text-zinc-50">New Quotation</p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <select
          value={customerId}
          onChange={(e) => setCustomerId(e.target.value ? Number(e.target.value) : "")}
          className="rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        >
          <option value="">Customer…</option>
          {customers.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <input
          value={repName}
          onChange={(e) => setRepName(e.target.value)}
          placeholder="Rep name"
          className="rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        />
        <select
          value={productId}
          onChange={(e) => setProductId(e.target.value ? Number(e.target.value) : "")}
          className="rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        >
          <option value="">Product…</option>
          {products.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <input
          type="number"
          min={1}
          value={quantity}
          onChange={(e) => setQuantity(Number(e.target.value))}
          placeholder="Qty"
          className="rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        />
        <input
          type="number"
          min={0}
          max={100}
          step={0.5}
          value={discountPct}
          onChange={(e) => setDiscountPct(Number(e.target.value))}
          placeholder="Discount %"
          className="rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        />
      </div>
      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={handleCreate}
          disabled={submitting || customerId === "" || productId === ""}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? "Creating…" : "Create Quotation"}
        </button>
        <button
          onClick={() => setOpen(false)}
          className="rounded border border-zinc-300 px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
        >
          Cancel
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}
    </div>
  );
}

export default function DashboardHomePage() {
  const { reloadNonce } = useReload();
  const { role } = useRole();

  const [pendingApprovals, setPendingApprovals] = useState<QuoteListItem[] | null>(null);
  const [managerQueue, setManagerQueue] = useState<QuoteListItem[] | null>(null);
  const [financeQueue, setFinanceQueue] = useState<QuoteListItem[] | null>(null);
  const [quotes, setQuotes] = useState<QuoteListItem[] | null>(null);
  const [dealHealth, setDealHealth] = useState<QuoteHealth[] | null>(null);
  const [invoices, setInvoices] = useState<InvoiceListItem[] | null>(null);
  const [activity, setActivity] = useState<RecentAuditLogEntry[] | null>(null);
  const [customers, setCustomers] = useState<CustomerRef[]>([]);
  const [products, setProducts] = useState<ProductRef[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [createdQuoteId, setCreatedQuoteId] = useState<number | null>(null);

  const fetchAll = useCallback(async () => {
    const [pending, managerPending, financePending, quoteList, health, invoiceList, recent, customerList, productList] =
      await Promise.all([
        getPendingApproval(),
        getPendingApproval("manager"),
        getPendingApproval("finance"),
        listQuotes(),
        getDealHealth(),
        listInvoices(),
        getRecentAuditLog(15),
        listCustomers(),
        listProducts(),
      ]);
    setPendingApprovals(pending);
    setManagerQueue(managerPending);
    setFinanceQueue(financePending);
    setQuotes(quoteList);
    setDealHealth(health);
    setInvoices(invoiceList);
    setActivity(recent);
    setCustomers(customerList);
    setProducts(productList);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setError(null);
      try {
        const [pending, managerPending, financePending, quoteList, health, invoiceList, recent, customerList, productList] =
          await Promise.all([
            getPendingApproval(),
            getPendingApproval("manager"),
            getPendingApproval("finance"),
            listQuotes(),
            getDealHealth(),
            listInvoices(),
            getRecentAuditLog(15),
            listCustomers(),
            listProducts(),
          ]);
        if (!cancelled) {
          setPendingApprovals(pending);
          setManagerQueue(managerPending);
          setFinanceQueue(financePending);
          setQuotes(quoteList);
          setDealHealth(health);
          setInvoices(invoiceList);
          setActivity(recent);
          setCustomers(customerList);
          setProducts(productList);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load dashboard");
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [reloadNonce]);

  const openQuotationsCount = useMemo(
    () => (quotes ?? []).filter((q) => OPEN_STATUSES.has(q.status)).length,
    [quotes],
  );
  const flaggedDealsCount = useMemo(
    () => (dealHealth ?? []).filter((q) => q.flags.length > 0).length,
    [dealHealth],
  );
  const anomalyCount = useMemo(
    () => (dealHealth ?? []).filter((q) => q.flags.some((f) => f.flag_type === "discount_anomaly")).length,
    [dealHealth],
  );
  const unpaidInvoicesCount = useMemo(
    () => (invoices ?? []).filter((i) => i.status === "unpaid").length,
    [invoices],
  );
  const highRiskFinanceCount = useMemo(
    () => (financeQueue ?? []).filter((q) => q.required_approval_level === "manager_then_finance").length,
    [financeQueue],
  );
  const displayedActivity = useMemo(() => {
    if (activity === null) return [];
    if (role !== "finance_manager") return activity;
    const filtered = activity.filter((entry) =>
      FINANCE_ACTIVITY_KEYWORDS.some((keyword) => entry.action.includes(keyword)),
    );
    // Fall back to the unfiltered feed rather than showing an empty list
    // when nothing finance-relevant has happened recently.
    return filtered.length > 0 ? filtered : activity;
  }, [activity, role]);

  if (error) return <p className="text-red-600 dark:text-red-400">Error: {error}</p>;
  if (
    pendingApprovals === null ||
    managerQueue === null ||
    financeQueue === null ||
    quotes === null ||
    dealHealth === null ||
    invoices === null ||
    activity === null
  ) {
    return <p className="text-zinc-500 dark:text-zinc-400">Loading…</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Dashboard</h1>

      {role === "rep" && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Tile label="Pending Approvals" value={pendingApprovals.length} href="/workspace/approvals" />
          <Tile label="Open Quotations" value={openQuotationsCount} href="/workspace/quotations" />
          <Tile label="At-Risk Deals" value={flaggedDealsCount} href="/workspace/deal-health" />
        </div>
      )}

      {role === "sales_manager" && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Tile
            label="My Approval Queue"
            value={managerQueue.length}
            href="/workspace/approvals?step=manager"
          />
          <Tile
            label="Flagged Deals"
            value={flaggedDealsCount}
            href="/workspace/deal-health?filter=flagged"
          />
          <Tile
            label="Team Discount Anomalies"
            value={anomalyCount}
            href="/workspace/deal-health?filter=discount_anomaly"
          />
        </div>
      )}

      {role === "finance_manager" && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Tile
            label="My Approval Queue"
            value={financeQueue.length}
            href="/workspace/approvals?step=finance"
          />
          <Tile
            label="Unpaid Invoices"
            value={unpaidInvoicesCount}
            href="/workspace/invoices?status=unpaid"
          />
          <Tile
            label="High-Risk Approvals"
            value={highRiskFinanceCount}
            href="/workspace/approvals?step=finance"
          />
        </div>
      )}

      {createdQuoteId !== null && (
        <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-300">
          Quotation #{createdQuoteId} created.{" "}
          <Link href={`/workspace/quotations/${createdQuoteId}`} className="underline">
            Open it
          </Link>
        </div>
      )}

      {role === "rep" && (
        <NewQuotationForm
          customers={customers}
          products={products}
          onCreated={(quoteId) => {
            setCreatedQuoteId(quoteId);
            fetchAll().catch(() => {
              // Quote creation already succeeded; a stale tile refresh isn't worth surfacing.
            });
          }}
        />
      )}

      <div>
        <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          Recent Activity
        </h2>
        {displayedActivity.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Nothing yet.</p>
        ) : (
          <ol className="flex flex-col gap-2">
            {displayedActivity.map((entry) => (
              <li
                key={entry.id}
                className="rounded-lg border border-zinc-200 bg-white p-3 text-sm dark:border-zinc-800 dark:bg-zinc-900"
              >
                <Link
                  href={`/workspace/quotations/${entry.quote_id}`}
                  className="font-medium text-zinc-900 hover:underline dark:text-zinc-50"
                >
                  {activityLine(entry)}
                </Link>
                <p className="mt-0.5 text-xs text-zinc-400">
                  {entry.user} · {formatTimestamp(entry.timestamp)}
                </p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
