export type Role = "admin" | "sales_manager" | "sales_rep" | "finance" | "customer";

export const ROLE_LABELS: Record<Role, string> = {
  admin: "Administrator",
  sales_manager: "Sales Manager",
  sales_rep: "Sales Rep",
  finance: "Finance & Operations",
  customer: "Customer",
};

export interface NavItem {
  href: string;
  label: string;
  permission?: string; // any of the permissions returned by /auth/me
  roles?: Role[];
}

export interface NavSection {
  title?: string;
  items: NavItem[];
}

// Navigation is derived from the server-issued permission list. Hiding an
// entry is a convenience only: every API route enforces authorization.
export const WORKSPACE_NAV: NavSection[] = [
  {
    items: [
      { href: "/workspace/dashboard", label: "Dashboard" },
      { href: "/workspace/quotations", label: "Quotations", permission: "quote:read" },
      { href: "/workspace/pipeline", label: "Pipeline", permission: "quote:read" },
      { href: "/workspace/approvals", label: "Approvals", permission: "approval:read", roles: ["sales_manager", "finance", "admin", "sales_rep"] },
      { href: "/workspace/customers", label: "Customers", permission: "customer:read" },
    ],
  },
  {
    title: "Operations",
    items: [
      { href: "/workspace/fulfillment", label: "Fulfillment", permission: "fulfillment:read" },
      { href: "/workspace/inventory", label: "Inventory", permission: "inventory:read", roles: ["finance", "admin"] },
      { href: "/workspace/subscriptions", label: "Subscriptions", permission: "subscription:read" },
      { href: "/workspace/invoices", label: "Invoices", permission: "invoice:read" },
      { href: "/workspace/payments", label: "Payments", permission: "invoice:read", roles: ["finance", "admin"] },
    ],
  },
  {
    title: "Insight",
    items: [
      { href: "/workspace/deal-health", label: "Deal Health", permission: "deal_health:read" },
      { href: "/workspace/reports", label: "Reporting", permission: "report:read" },
      { href: "/workspace/notifications", label: "Notifications" },
    ],
  },
];

export const ADMIN_NAV: NavSection[] = [
  {
    items: [
      { href: "/admin", label: "Overview" },
      { href: "/admin/users", label: "Users", permission: "user:manage" },
      { href: "/admin/products", label: "Products", permission: "catalog:manage" },
      { href: "/admin/categories", label: "Categories", permission: "catalog:manage" },
      { href: "/admin/customer-tiers", label: "Customer Tiers", permission: "discount_rules:manage" },
      { href: "/admin/price-lists", label: "Price Lists", permission: "pricing:manage" },
      { href: "/admin/discount-rules", label: "Discount Rules", permission: "discount_rules:manage" },
      { href: "/admin/approval-rules", label: "Approval Rules", permission: "approval_rules:manage" },
      { href: "/admin/warehouses", label: "Warehouses", permission: "inventory:manage" },
      { href: "/admin/subscription-plans", label: "Subscription Plans", permission: "catalog:manage" },
      { href: "/admin/pairings", label: "Upsell Rules", permission: "catalog:manage" },
      { href: "/admin/settings", label: "System Settings", permission: "settings:manage" },
      { href: "/admin/audit-logs", label: "Audit Logs", permission: "audit:read" },
      { href: "/admin/emails", label: "Email Log", permission: "settings:manage" },
    ],
  },
];

export function visibleItems(sections: NavSection[], role: Role | null, permissions: Set<string>): NavSection[] {
  if (!role) return [];
  return sections
    .map((s) => ({
      ...s,
      items: s.items.filter((i) => (!i.permission || permissions.has(i.permission)) && (!i.roles || i.roles.includes(role))),
    }))
    .filter((s) => s.items.length > 0);
}

export function homeFor(role: Role | null): string {
  if (role === "customer") return "/portal";
  return "/workspace/dashboard";
}
