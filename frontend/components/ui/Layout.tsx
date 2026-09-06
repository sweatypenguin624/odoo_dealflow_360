import Link from "next/link";
import { ReactNode } from "react";

export function PageHeader({ title, subtitle, actions, breadcrumb }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; breadcrumb?: { href: string; label: string } }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        {breadcrumb && (
          <Link href={breadcrumb.href} className="text-xs text-blue-600 hover:underline">
            ← {breadcrumb.label}
          </Link>
        )}
        <h1 className="text-xl font-semibold text-zinc-900">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-zinc-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ title, children, actions, className = "", padded = true }: { title?: ReactNode; children: ReactNode; actions?: ReactNode; className?: string; padded?: boolean }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="flex items-center justify-between border-b border-zinc-100 px-4 py-2.5">
          <h2 className="text-sm font-semibold text-zinc-800">{title}</h2>
          {actions}
        </div>
      )}
      <div className={padded ? "p-4" : ""}>{children}</div>
    </section>
  );
}

export function KpiTile({ label, value, hint, href, tone = "neutral" }: { label: string; value: ReactNode; hint?: ReactNode; href?: string; tone?: "neutral" | "warn" | "danger" | "good" }) {
  const accent = { neutral: "border-zinc-200", warn: "border-amber-300", danger: "border-red-300", good: "border-emerald-300" }[tone];
  const body = (
    <div className={`card flex h-full flex-col gap-1 border-l-4 p-4 ${accent} ${href ? "transition hover:shadow" : ""}`}>
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="text-2xl font-semibold tabular-nums text-zinc-900">{value}</p>
      {hint && <p className="text-xs text-zinc-500">{hint}</p>}
    </div>
  );
  return href ? <Link href={href} className="block">{body}</Link> : body;
}

export function DescriptionList({ items, columns = 2 }: { items: { label: string; value: ReactNode }[]; columns?: 1 | 2 | 3 }) {
  const cols = { 1: "sm:grid-cols-1", 2: "sm:grid-cols-2", 3: "sm:grid-cols-3" }[columns];
  return (
    <dl className={`grid grid-cols-1 gap-x-6 gap-y-3 ${cols}`}>
      {items.map((i) => (
        <div key={i.label}>
          <dt className="text-xs uppercase tracking-wide text-zinc-500">{i.label}</dt>
          <dd className="text-sm text-zinc-900">{i.value ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Tabs({ tabs, active, onChange }: { tabs: { key: string; label: ReactNode }[]; active: string; onChange: (key: string) => void }) {
  return (
    <div className="flex gap-1 border-b border-zinc-200" role="tablist">
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={active === t.key} onClick={() => onChange(t.key)} className={`-mb-px border-b-2 px-3 py-2 text-sm ${active === t.key ? "border-blue-600 font-medium text-blue-700" : "border-transparent text-zinc-500 hover:text-zinc-800"}`}>
          {t.label}
        </button>
      ))}
    </div>
  );
}
