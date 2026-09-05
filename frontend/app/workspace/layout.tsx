"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";
import { ReloadProvider, useReload } from "@/lib/reload-context";

// The unified internal shell (Phase 10): one persistent nav bar across
// every internal screen, with the current module shown as a highlighted
// tab (matching the mockup's "white tab shows which module you're in").
// Products and Reports are intentionally omitted - out of scope this
// phase, so no dead links.
const NAV_ITEMS = [
  { href: "/workspace/dashboard", label: "Dashboard" },
  { href: "/workspace/quotations", label: "Quotations" },
  { href: "/workspace/approvals", label: "Approvals" },
  { href: "/workspace/fulfillment", label: "Fulfillment" },
  { href: "/workspace/subscriptions", label: "Subscriptions" },
  { href: "/workspace/invoices", label: "Invoices" },
  { href: "/workspace/deal-health", label: "Deal Health" },
] as const;

function NavTab({ href, children }: { href: string; children: ReactNode }) {
  const pathname = usePathname();
  const isActive = pathname === href || pathname?.startsWith(`${href}/`);

  return (
    <Link
      href={href}
      className={
        isActive
          ? "rounded-md bg-white px-3 py-1.5 text-sm font-medium text-zinc-900 shadow-sm dark:bg-zinc-950 dark:text-zinc-50"
          : "rounded-md px-3 py-1.5 text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
      }
    >
      {children}
    </Link>
  );
}

function WorkspaceHeader() {
  const { reload } = useReload();

  return (
    <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-3">
        <div className="flex flex-wrap items-center gap-4">
          <Link
            href="/workspace/dashboard"
            className="text-base font-semibold text-zinc-900 dark:text-zinc-50"
          >
            DealFlow360 Workspace
          </Link>
          <nav className="flex flex-wrap items-center gap-1 rounded-lg bg-zinc-100 p-1 dark:bg-zinc-800">
            {NAV_ITEMS.map((item) => (
              <NavTab key={item.href} href={item.href}>
                {item.label}
              </NavTab>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <button
            onClick={reload}
            className="rounded border border-zinc-300 px-3 py-1.5 text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            Reload Data
          </button>
          <Link
            href="/admin"
            className="rounded border border-zinc-300 px-3 py-1.5 text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            Go to Back-end
          </Link>
          <Link
            href="/"
            className="rounded border border-zinc-300 px-3 py-1.5 text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            Close Workspace
          </Link>
        </div>
      </div>
    </header>
  );
}

export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  return (
    <ReloadProvider>
      <div className="flex min-h-screen flex-1 flex-col bg-zinc-50 dark:bg-zinc-950">
        <WorkspaceHeader />
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">{children}</main>
      </div>
    </ReloadProvider>
  );
}
