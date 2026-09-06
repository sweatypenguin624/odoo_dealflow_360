"use client";
import { ReactNode } from "react";
import { AppShell } from "@/components/shell/AppShell";
import { RequireAuth } from "@/components/shell/RequireAuth";
import { ADMIN_NAV } from "@/lib/rbac";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <RequireAuth roles={["admin", "sales_manager", "finance"]}>
      <AppShell sections={ADMIN_NAV} area="admin">{children}</AppShell>
    </RequireAuth>
  );
}
