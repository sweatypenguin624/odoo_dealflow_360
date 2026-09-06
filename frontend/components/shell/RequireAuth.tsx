"use client";
import { useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";
import { useAuth } from "@/lib/auth/AuthContext";
import { homeFor, type Role } from "@/lib/rbac";
import { Spinner } from "@/components/ui/States";

export function RequireAuth({ children, roles, permission }: { children: ReactNode; roles?: Role[]; permission?: string }) {
  const { user, loading, can, signedOut } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (loading || user) return;
    // Only an interrupted visit is worth resuming. After an explicit sign-out
    // the path belongs to the person who left, and stamping it on the login URL
    // hands the next person to sign in a page they may not be allowed to open.
    router.replace(signedOut ? "/login" : `/login?next=${encodeURIComponent(window.location.pathname)}`);
  }, [loading, user, signedOut, router]);
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

/**
 * Portal chrome is customer-only, but it has no navigation to escape from, and
 * its API calls just fail for anyone else. Send staff back to their own home
 * rather than leaving them on a page that can only error.
 */
export function RequireCustomer({ children, staffHref }: { children: ReactNode; staffHref?: string }) {
  const { user, loading, signedOut } = useAuth();
  const router = useRouter();
  const denied = !!user && user.role !== "customer";
  useEffect(() => {
    if (loading) return;
    if (!user) router.replace(signedOut ? "/login" : `/login?next=${encodeURIComponent(window.location.pathname)}`);
    else if (denied) router.replace(staffHref ?? homeFor(user.role));
  }, [loading, user, denied, signedOut, staffHref, router]);
  if (loading) return <div className="p-8"><Spinner label="Checking your session…" /></div>;
  if (!user || denied) return null;
  return <>{children}</>;
}
