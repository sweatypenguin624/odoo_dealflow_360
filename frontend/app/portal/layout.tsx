import Link from "next/link";
import { ReactNode } from "react";

/**
 * Portal chrome. Deliberately free of workspace navigation: this shell is
 * shared by tokenised links (no session at all) and signed-in customers.
 */
export default function PortalLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-zinc-50">
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between px-4">
          <Link href="/portal" className="text-base font-bold tracking-tight text-zinc-900">
            DealFlow<span className="text-blue-600">360</span>
          </Link>
          <span className="text-xs text-zinc-500">Customer portal</span>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">{children}</main>
      <footer className="border-t border-zinc-200 bg-white py-4">
        <p className="mx-auto max-w-5xl px-4 text-xs text-zinc-500">
          Questions about this quotation? Reply to the email it came from and your sales contact will pick it up.
        </p>
      </footer>
    </div>
  );
}
