"use client";
import { useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";
import { useAuth } from "@/lib/auth/AuthContext";
import type { Role } from "@/lib/rbac";
import { Spinner } from "@/components/ui/States";

export function RequireAuth({ children, roles, permission }: { children: ReactNode; roles?: Role[]; permission?: string }) {
  const { user, loading, can } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!loading && !user) router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
  }, [loading, user, router]);
  if (loading) return <div className="p-8"><Spinner label="Checking your session…" /></div>;
  if (!user) return null;
  if ((roles && !roles.includes(user.role)) || (permission && !can(permission))) {
    return (
      <div className="card m-8 p-8 text-center">
        <p className="text-lg font-semibold text-zinc-900">You don&apos;t have access to this area</p>
        <p className="mt-1 text-sm text-zinc-500">Your account ({user.role.replaceAll("_", " ")}) isn&apos;t permitted to view this page.</p>
      </div>
    );
  }
  return <>{children}</>;
}
