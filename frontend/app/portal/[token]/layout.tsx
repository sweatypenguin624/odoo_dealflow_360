import { ReactNode } from "react";

// Deliberately minimal and self-contained: no internal workspace nav, no
// "Go to Back-end" link, nothing that lets a customer reach an internal
// screen from here. This is the customer's own view of one quotation.
export default function PortalLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-1 flex-col bg-white dark:bg-zinc-950">
      <header className="border-b border-zinc-200 bg-zinc-50 px-6 py-4 dark:border-zinc-800 dark:bg-zinc-900">
        <span className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          Your Quotation
        </span>
      </header>
      <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-8">{children}</main>
      <footer className="border-t border-zinc-200 px-6 py-4 text-center text-xs text-zinc-400 dark:border-zinc-800">
        Questions about this quote? Reply to the email that sent you this link.
      </footer>
    </div>
  );
}
