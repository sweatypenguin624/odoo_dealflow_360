"use client";

import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { apiGet, apiPost, setUnauthorizedHandler } from "@/lib/api/client";
import type { Role } from "@/lib/rbac";

export interface SessionUser {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  team: string | null;
  customer_id: number | null;
  is_active: boolean;
}

interface MeResponse {
  user: SessionUser;
  permissions: string[];
}

interface AuthContextValue {
  user: SessionUser | null;
  permissions: Set<string>;
  loading: boolean;
  can: (permission: string) => boolean;
  hasRole: (...roles: Role[]) => boolean;
  login: (email: string, password: string) => Promise<SessionUser>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [permissions, setPermissions] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const me = await apiGet<MeResponse>("/auth/me");
      setUser(me.user);
      setPermissions(new Set(me.permissions));
    } catch {
      setUser(null);
      setPermissions(new Set());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Bootstrapping the session is exactly what an effect is for: it reads an
    // external system (the cookie session) and subscribes to its 401 signal.
    // Every setState here lands in an async callback, never synchronously.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh();
    setUnauthorizedHandler(() => {
      setUser(null);
      setPermissions(new Set());
    });
    return () => setUnauthorizedHandler(null);
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const session = await apiPost<MeResponse>("/auth/login", { email, password });
    setUser(session.user);
    setPermissions(new Set(session.permissions));
    setLoading(false);
    return session.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiPost("/auth/logout");
    } finally {
      setUser(null);
      setPermissions(new Set());
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      permissions,
      loading,
      can: (p) => permissions.has(p),
      hasRole: (...roles) => !!user && roles.includes(user.role),
      login,
      logout,
      refresh,
    }),
    [user, permissions, loading, login, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
