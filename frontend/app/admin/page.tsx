"use client";
import Link from "next/link";
import { useAuth } from "@/lib/auth/AuthContext";
import { ADMIN_NAV, visibleItems } from "@/lib/rbac";
import { Card, PageHeader } from "@/components/ui";

const BLURBS: Record<string, string> = {
  "/admin/users": "People, roles and team assignment.",
  "/admin/products": "Catalog products, pricing basis and variants.",
  "/admin/categories": "Product grouping and category discount ceilings.",
  "/admin/customer-tiers": "Tiers and the maximum discount each one allows.",
  "/admin/price-lists": "Negotiated price books by tier and validity window.",
  "/admin/discount-rules": "Discount ceilings by tier, category or product.",
  "/admin/approval-rules": "Thresholds that decide manager vs finance approval.",
  "/admin/warehouses": "Stock locations and shipping cost weighting.",
  "/admin/subscription-plans": "Recurring plans, intervals and proration.",
  "/admin/pairings": "Cross-sell pairings that drive upsell suggestions.",
  "/admin/settings": "System behaviour: expiry windows, thresholds, email.",
  "/admin/audit-logs": "Every state change, who made it and why.",
  "/admin/emails": "Outbound email log and delivery status.",
};

export default function AdminOverviewPage() {
  const { user, permissions } = useAuth();
  const sections = visibleItems(ADMIN_NAV, user?.role ?? null, permissions);
  const items = sections.flatMap((s) => s.items).filter((i) => i.href !== "/admin");

  return (
    <div className="space-y-5">
      <PageHeader
        title="Administration"
        subtitle="Reference data and policy. Changes here take effect immediately for new pricing and approval decisions."
      />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => (
          <Link key={item.href} href={item.href} className="card block p-4 transition hover:border-blue-400 hover:shadow">
            <p className="font-medium text-zinc-900">{item.label}</p>
            <p className="mt-0.5 text-sm text-zinc-500">{BLURBS[item.href] ?? ""}</p>
          </Link>
        ))}
      </div>
      <Card title="A note on policy changes">
        <p className="text-sm text-zinc-600">
          Discount rules, approval rules and price lists are read at evaluation time. Existing quotations keep the approval decision they
          already received; re-submitting a quotation re-evaluates it against the current policy.
        </p>
      </Card>
    </div>
  );
}
