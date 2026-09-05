"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";
import { ReloadProvider, useReload } from "@/lib/reload-context";

function NavLink({ href, children }: { href: string; children: ReactNode }) {
  const pathname = usePathname();
  const isActive = pathname === href || pathname?.startsWith(`${href}/`);

  return (
    <Link
      href={href}
      className={
        isActive
          ? "font-semibold text-blue-600 dark:text-blue-400"
          : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
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
        <div className="flex items-center gap-6">
          <span className="text-base font-semibold text-zinc-900 dark:text-zinc-50">
            DealFlow360 Workspace
          </span>
          <nav className="flex items-center gap-4 text-sm">
            <NavLink href="/workspace/quotations">Quotations</NavLink>
            <NavLink href="/workspace/quotations?view=pipeline">Pipeline</NavLink>
            <NavLink href="/workspace/approvals">Approvals</NavLink>
            <NavLink href="/workspace/dashboard">Deal Health</NavLink>
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
