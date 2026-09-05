"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ApiError, listInvoices } from "@/lib/api";
import type { InvoiceListItem, InvoiceStatusValue } from "@/lib/api";
import { useReload } from "@/lib/reload-context";

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);
}

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

function StatusPill({ status }: { status: InvoiceStatusValue }) {
  const style =
    status === "paid"
      ? "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300"
      : "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300";
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>
      {status === "paid" ? "Paid" : "Unpaid"}
    </span>
  );
}

export default function InvoicesPage() {
  return (
    <Suspense fallback={<p className="text-zinc-500 dark:text-zinc-400">Loading…</p>}>
      <InvoicesPageInner />
    </Suspense>
  );
}

function InvoicesPageInner() {
  const searchParams = useSearchParams();
  const statusFilter = (searchParams.get("status") as InvoiceStatusValue | null) ?? undefined;
  const { reloadNonce } = useReload();

  const [allInvoices, setAllInvoices] = useState<InvoiceListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setError(null);
      try {
        const all = await listInvoices();
        if (!cancelled) setAllInvoices(all);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load invoices");
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [reloadNonce]);

  if (error) return <p className="text-red-600 dark:text-red-400">Error: {error}</p>;
  if (allInvoices === null) {
    return <p className="text-zinc-500 dark:text-zinc-400">Loading…</p>;
  }

  const unpaidCount = allInvoices.filter((i) => i.status === "unpaid").length;
  const paidCount = allInvoices.filter((i) => i.status === "paid").length;
  const invoices = statusFilter
    ? allInvoices.filter((i) => i.status === statusFilter)
    : allInvoices;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Invoices</h1>
        <div className="flex gap-3 text-sm">
          <FilterLink href="/workspace/invoices" active={!statusFilter}>
            All
          </FilterLink>
          <FilterLink href="/workspace/invoices?status=unpaid" active={statusFilter === "unpaid"}>
            Unpaid
          </FilterLink>
          <FilterLink href="/workspace/invoices?status=paid" active={statusFilter === "paid"}>
            Paid
          </FilterLink>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
          <p className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">Unpaid</p>
          <p className="text-3xl font-semibold text-amber-600 dark:text-amber-400">{unpaidCount}</p>
        </div>
        <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
          <p className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">Paid</p>
          <p className="text-3xl font-semibold text-green-600 dark:text-green-400">{paidCount}</p>
        </div>
      </div>

      {invoices.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">No invoices here.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="bg-zinc-50 text-left text-xs uppercase text-zinc-500 dark:bg-zinc-900 dark:text-zinc-400">
              <tr>
                <th className="px-4 py-2">Invoice #</th>
                <th className="px-4 py-2">Customer</th>
                <th className="px-4 py-2">Type</th>
                <th className="px-4 py-2">Amount</th>
                <th className="px-4 py-2">Due Date</th>
                <th className="px-4 py-2">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {invoices.map((invoice) => (
                <tr key={invoice.id} className="bg-white dark:bg-zinc-950">
                  <td className="px-4 py-2">
                    <Link
                      href={`/workspace/invoices/${invoice.id}`}
                      className="font-medium text-blue-600 hover:underline dark:text-blue-400"
                    >
                      {invoice.invoice_number}
                    </Link>
                  </td>
                  <td className="px-4 py-2">{invoice.customer_name}</td>
                  <td className="px-4 py-2 capitalize">{invoice.invoice_type.replace("_", " ")}</td>
                  <td className="px-4 py-2 font-medium">{formatCurrency(invoice.amount)}</td>
                  <td className="px-4 py-2">{invoice.due_date}</td>
                  <td className="px-4 py-2">
                    <StatusPill status={invoice.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
