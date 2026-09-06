"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useState } from "react";
import { useAuth } from "@/lib/auth/AuthContext";
import { ROLE_LABELS, visibleItems, type NavSection } from "@/lib/rbac";
import { GlobalSearch } from "./GlobalSearch";
import { NotificationBell } from "./NotificationBell";

export function AppShell({ children, sections, area }: { children: ReactNode; sections: NavSection[]; area: "workspace" | "admin" }) {
  const { user, permissions, logout, can } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const nav = visibleItems(sections, user?.role ?? null, permissions);
  const isAdmin = can("user:manage") || can("catalog:manage") || can("settings:manage");

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  const sidebar = (
    <nav className="flex flex-col gap-4 p-3" aria-label="Main">
      {nav.map((s, i) => (
        <div key={i}>
          {s.title && <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">{s.title}</p>}
          <ul className="flex flex-col gap-0.5">
            {s.items.map((item) => {
              const active = pathname === item.href || (item.href !== "/admin" && pathname.startsWith(`${item.href}/`)) || (item.href === "/admin" && pathname === "/admin");
              return (
                <li key={item.href}>
                  <Link href={item.href} onClick={() => setOpen(false)} className={`block rounded-md px-2.5 py-1.5 text-sm ${active ? "bg-blue-600 text-white" : "text-zinc-700 hover:bg-zinc-100"}`} aria-current={active ? "page" : undefined}>
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-56 shrink-0 border-r border-zinc-200 bg-white lg:block">
        <div className="flex h-14 items-center border-b border-zinc-200 px-4">
          <Link href="/workspace/dashboard" className="text-base font-bold tracking-tight text-zinc-900">DealFlow<span className="text-blue-600">360</span></Link>
        </div>
        {sidebar}
        {isAdmin && (
          <div className="border-t border-zinc-200 p-3">
            <Link href={area === "admin" ? "/workspace/dashboard" : "/admin"} className="block rounded-md px-2.5 py-1.5 text-sm text-zinc-700 hover:bg-zinc-100">
              {area === "admin" ? "← Back to workspace" : "Administration →"}
            </Link>
          </div>
        )}
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 bg-zinc-900/40 lg:hidden" onClick={() => setOpen(false)}>
          <aside className="h-full w-64 bg-white" onClick={(e) => e.stopPropagation()}>{sidebar}</aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-zinc-200 bg-white px-4">
          <button className="rounded-md p-2 text-zinc-600 hover:bg-zinc-100 lg:hidden" onClick={() => setOpen(true)} aria-label="Open navigation">☰</button>
          <GlobalSearch />
          <div className="ml-auto flex items-center gap-2">
            <NotificationBell />
            {user && (
              <div className="flex items-center gap-2 border-l border-zinc-200 pl-3">
                <div className="hidden text-right sm:block">
                  <p className="text-sm font-medium leading-tight text-zinc-900">{user.full_name}</p>
                  <p className="text-[11px] text-zinc-500">{ROLE_LABELS[user.role]}{user.team ? ` · ${user.team}` : ""}</p>
                </div>
                <button onClick={handleLogout} className="rounded-md border border-zinc-300 px-2.5 py-1 text-xs text-zinc-700 hover:bg-zinc-50">Sign out</button>
              </div>
            )}
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">{children}</main>
      </div>
    </div>
  );
}
