"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";
import { ApiError, getInvoice, listProducts, recordPayment } from "@/lib/api";
import type { InvoiceDetail, ProductRef } from "@/lib/api";
import { useReload } from "@/lib/reload-context";

const PIPELINE_STEPS = ["Order Confirmed", "Shipped", "Invoiced", "Paid"] as const;

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);
}

function PipelineIndicator({ stage }: { stage: string }) {
  const currentIndex = PIPELINE_STEPS.indexOf(stage as (typeof PIPELINE_STEPS)[number]);

  return (
    <div className="flex items-center">
      {PIPELINE_STEPS.map((step, i) => {
        const done = currentIndex >= 0 && i <= currentIndex;
        return (
          <div key={step} className="flex items-center">
            <div className="flex flex-col items-center gap-1">
              <div
                className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${
                  done
                    ? "bg-green-600 text-white"
                    : "bg-zinc-200 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
                }`}
              >
                {i + 1}
              </div>
              <span
                className={`text-xs ${done ? "font-medium text-zinc-900 dark:text-zinc-50" : "text-zinc-400"}`}
              >
                {step}
              </span>
            </div>
            {i < PIPELINE_STEPS.length - 1 && (
              <div
                className={`mx-2 h-0.5 w-10 sm:w-16 ${done && currentIndex > i ? "bg-green-600" : "bg-zinc-200 dark:bg-zinc-800"}`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function RecordPaymentForm({
  invoice,
  onRecorded,
}: {
  invoice: InvoiceDetail;
  onRecorded: (updated: InvoiceDetail) => void;
}) {
  const totalPaid = invoice.payments.reduce((sum, p) => sum + p.amount, 0);
  const remaining = Math.max(0, invoice.amount - totalPaid);

  const [amount, setAmount] = useState(remaining);
  const [method, setMethod] = useState("Bank Transfer");
  const [recordedBy, setRecordedBy] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      const updated = await recordPayment(invoice.id, {
        amount,
        method,
        recorded_by: recordedBy || "Unknown",
      });
      onRecorded(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to record payment");
    } finally {
      setSubmitting(false);
    }
  }

  if (invoice.status === "paid") {
    return (
      <p className="text-sm text-green-700 dark:text-green-400">
        This invoice is fully paid.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        Remaining balance: <span className="font-medium">{formatCurrency(remaining)}</span>
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div>
          <label className="block text-xs text-zinc-500 dark:text-zinc-400">Amount</label>
          <input
            type="number"
            min={0}
            step={0.01}
            value={amount}
            onChange={(e) => setAmount(Number(e.target.value))}
            className="w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          />
        </div>
        <div>
          <label className="block text-xs text-zinc-500 dark:text-zinc-400">Method</label>
          <input
            value={method}
            onChange={(e) => setMethod(e.target.value)}
            placeholder="e.g. Bank Transfer"
            className="w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          />
        </div>
        <div>
          <label className="block text-xs text-zinc-500 dark:text-zinc-400">Recorded By</label>
          <input
            value={recordedBy}
            onChange={(e) => setRecordedBy(e.target.value)}
            placeholder="Your name"
            className="w-full rounded border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          />
        </div>
      </div>
      <button
        onClick={handleSubmit}
        disabled={submitting || amount <= 0}
        className="w-fit rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {submitting ? "Recording…" : "Record Payment"}
      </button>
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
    </div>
  );
}

export default function InvoiceDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const invoiceId = Number(id);
  const { reloadNonce } = useReload();

  const [invoice, setInvoice] = useState<InvoiceDetail | null>(null);
  const [products, setProducts] = useState<ProductRef[]>([]);
  const [error, setError] = useState<string | null>(null);

  const productById = useMemo(() => {
    const map = new Map<number, ProductRef>();
    for (const product of products) map.set(product.id, product);
    return map;
  }, [products]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setError(null);
      try {
        const [data, productList] = await Promise.all([getInvoice(invoiceId), listProducts()]);
        if (!cancelled) {
          setInvoice(data);
          setProducts(productList);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load invoice");
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [invoiceId, reloadNonce]);

  if (error) return <p className="text-red-600 dark:text-red-400">Error: {error}</p>;
  if (invoice === null) return <p className="text-zinc-500 dark:text-zinc-400">Loading…</p>;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          href="/workspace/invoices"
          className="text-sm text-blue-600 hover:underline dark:text-blue-400"
        >
          ← Back to Invoices
        </Link>
        <div className="mt-2 flex items-center justify-between">
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
            {invoice.invoice_number} — {invoice.customer_name}
          </h1>
          <Link
            href={`/workspace/quotations/${invoice.quote_id}`}
            className="text-sm text-blue-600 hover:underline dark:text-blue-400"
          >
            Quote #{invoice.quote_id}
          </Link>
        </div>
      </div>

      <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <PipelineIndicator stage={invoice.pipeline_stage} />
      </div>

      <div className="flex flex-wrap gap-6 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <div>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">Amount</p>
          <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
            {formatCurrency(invoice.amount)}
          </p>
        </div>
        <div>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">Type</p>
          <p className="text-lg font-semibold capitalize text-zinc-900 dark:text-zinc-50">
            {invoice.invoice_type.replace("_", " ")}
          </p>
        </div>
        <div>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">Due Date</p>
          <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">{invoice.due_date}</p>
        </div>
        <div>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">Status</p>
          <p className="text-lg font-semibold capitalize text-zinc-900 dark:text-zinc-50">
            {invoice.status}
          </p>
        </div>
      </div>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          One-Time Lines
        </h2>
        {invoice.one_time_lines.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">None.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
            <table className="w-full text-sm">
              <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500 dark:bg-zinc-900 dark:text-zinc-400">
                <tr>
                  <th className="px-4 py-2">Product</th>
                  <th className="px-4 py-2">Quantity</th>
                  <th className="px-4 py-2">Discount %</th>
                  <th className="px-4 py-2">Line Value</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {invoice.one_time_lines.map((line) => (
                  <tr key={line.quote_line_id} className="bg-white dark:bg-zinc-950">
                    <td className="px-4 py-2">
                      {productById.get(line.product_id)?.name ?? `Product #${line.product_id}`}
                    </td>
                    <td className="px-4 py-2">{line.quantity}</td>
                    <td className="px-4 py-2">{line.discount_pct}%</td>
                    <td className="px-4 py-2">{formatCurrency(line.line_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {invoice.recurring_lines.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-50">
            Recurring Lines
          </h2>
          <div className="flex flex-col gap-2">
            {invoice.recurring_lines.map((line) => (
              <div
                key={line.quote_line_id}
                className="rounded-lg border border-purple-200 bg-purple-50 p-3 text-sm dark:border-purple-900 dark:bg-purple-950/30"
              >
                {productById.get(line.product_id)?.name ?? `Product #${line.product_id}`} · Qty{" "}
                {line.quantity} · Cycle {line.current_cycle_start} → {line.current_cycle_end} ·{" "}
                {line.status}
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          Payment History
        </h2>
        {invoice.payments.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">No payments recorded yet.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {invoice.payments.map((payment) => (
              <li
                key={payment.id}
                className="rounded-lg border border-zinc-200 bg-white p-3 text-sm dark:border-zinc-800 dark:bg-zinc-900"
              >
                {formatCurrency(payment.amount)} via {payment.method} — recorded by{" "}
                {payment.recorded_by}
                <p className="text-xs text-zinc-400">{new Date(payment.paid_at).toLocaleString()}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          Record Payment
        </h2>
        <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
          <RecordPaymentForm invoice={invoice} onRecorded={setInvoice} />
        </div>
      </section>
    </div>
  );
}
