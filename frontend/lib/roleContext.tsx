"use client";

import { createContext, ReactNode, useContext, useEffect, useState } from "react";

// Lightweight, demo-appropriate role scoping for the internal shell. This is
// NOT an auth boundary - there is no real login anywhere in this app
// (deliberately deferred since Phase 7). The selection just lives in
// localStorage as a UI convenience so it survives a page refresh mid-demo;
// it carries no server-side effect and grants no real access.
export type Role = "rep" | "sales_manager" | "finance_manager";

export const ROLE_LABELS: Record<Role, string> = {
  rep: "Sales Rep View",
  sales_manager: "Sales Manager View",
  finance_manager: "Finance Manager View",
};

const ROLE_STORAGE_KEY = "dealflow360.role";
const VALID_ROLES: Role[] = ["rep", "sales_manager", "finance_manager"];

interface RoleContextValue {
  role: Role;
  setRole: (role: Role) => void;
}

const RoleContext = createContext<RoleContextValue | null>(null);

export function RoleProvider({ children }: { children: ReactNode }) {
  const [role, setRoleState] = useState<Role>("rep");

  useEffect(() => {
    function hydrateFromStorage() {
      try {
        const stored = localStorage.getItem(ROLE_STORAGE_KEY);
        if (stored && (VALID_ROLES as string[]).includes(stored)) {
          setRoleState(stored as Role);
        }
      } catch {
        // localStorage unavailable (private mode, etc.) - default role stands.
      }
    }

    hydrateFromStorage();
  }, []);

  function setRole(next: Role) {
    setRoleState(next);
    try {
      localStorage.setItem(ROLE_STORAGE_KEY, next);
    } catch {
      // Best-effort persistence only - not a correctness requirement.
    }
  }

  return <RoleContext.Provider value={{ role, setRole }}>{children}</RoleContext.Provider>;
}

export function useRole(): RoleContextValue {
  const ctx = useContext(RoleContext);
  if (!ctx) {
    throw new Error("useRole must be used within a RoleProvider (the workspace layout)");
  }
  return ctx;
}
