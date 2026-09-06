"use client";
import { ReactNode } from "react";
import { AppShell } from "@/components/shell/AppShell";
import { RequireAuth } from "@/components/shell/RequireAuth";
import { WORKSPACE_NAV } from "@/lib/rbac";

export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  return (
    <RequireAuth roles={["admin", "sales_manager", "sales_rep", "finance"]}>
      <AppShell sections={WORKSPACE_NAV} area="workspace">{children}</AppShell>
    </RequireAuth>
  );
}
