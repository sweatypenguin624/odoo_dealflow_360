"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { search, type SearchResults } from "@/lib/api";
import { useDebounce } from "@/lib/hooks/useApi";
import { formatCurrency } from "@/lib/format";
import { StatusBadge } from "@/components/ui/Badge";

export function GlobalSearch() {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<SearchResults | null>(null);
  const debounced = useDebounce(q, 300);
  const router = useRouter();
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!debounced.trim()) return;
    let cancelled = false;
    search.global(debounced).then((r) => { if (!cancelled) setResults(r); }).catch(() => { if (!cancelled) setResults(null); });
    return () => { cancelled = true; };
  }, [debounced]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  // Cleared query derives to "no results" here rather than an effect reset,
  // so stale hits never linger after the box is emptied.
  const shown = debounced.trim() ? results : null;
  const groups: { title: string; items: { key: string; link: string; primary: string; secondary: string; badge?: string }[] }[] = shown
    ? [
        { title: "Quotations", items: shown.quotes.map((x) => ({ key: `q${x.id}`, link: x.link, primary: x.quote_number ?? `Quote ${x.id}`, secondary: `${x.customer_name} · ${formatCurrency(x.total)}`, badge: x.status })) },
        { title: "Orders", items: shown.orders.map((x) => ({ key: `o${x.id}`, link: x.link, primary: x.order_number, secondary: x.customer_name, badge: x.fulfillment_status })) },
        { title: "Customers", items: shown.customers.map((x) => ({ key: `c${x.id}`, link: x.link, primary: x.name, secondary: `${x.code ?? ""} · ${x.tier}` })) },
        { title: "Products", items: shown.products.map((x) => ({ key: `p${x.id}`, link: x.link, primary: x.name, secondary: `${x.sku ?? ""} · ${x.category} · ${formatCurrency(x.price)}` })) },
        { title: "Invoices", items: shown.invoices.map((x) => ({ key: `i${x.id}`, link: x.link, primary: x.invoice_number, secondary: `${x.customer_name} · ${formatCurrency(x.amount)}`, badge: x.status })) },
        { title: "Subscriptions", items: shown.subscriptions.map((x) => ({ key: `s${x.id}`, link: x.link, primary: x.plan_name, secondary: x.customer_name ?? "", badge: x.status })) },
      ].filter((g) => g.items.length)
    : [];

  return (
    <div ref={box} className="relative w-full max-w-md">
      <input
        type="search"
        value={q}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        placeholder="Search customers, quotes, SKUs, invoices…"
        aria-label="Global search"
        className="field py-1.5"
      />
      {open && q.trim() && (
        <div className="absolute left-0 right-0 top-full z-40 mt-1 max-h-96 overflow-y-auto rounded-md border border-zinc-200 bg-white shadow-lg">
          {groups.length === 0 ? (
            <p className="px-3 py-3 text-sm text-zinc-500">{shown ? "No matches." : "Searching…"}</p>
          ) : (
            groups.map((g) => (
              <div key={g.title}>
                <p className="bg-zinc-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{g.title}</p>
                {g.items.map((i) => (
                  <Link key={i.key} href={i.link} onClick={() => { setOpen(false); setQ(""); router.push(i.link); }} className="flex items-center justify-between gap-2 px-3 py-2 text-sm hover:bg-blue-50">
                    <span>
                      <span className="font-medium text-zinc-900">{i.primary}</span>
                      <span className="block text-xs text-zinc-500">{i.secondary}</span>
                    </span>
                    {i.badge && <StatusBadge status={i.badge} />}
                  </Link>
                ))}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
