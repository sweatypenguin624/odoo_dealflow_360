"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth/AuthContext";
import { homeFor } from "@/lib/rbac";
import { Spinner } from "@/components/ui/States";

/**
 * Entry point. It has to be role-aware: the proxy bounces an already-signed-in
 * visitor from /login to here, and sending everyone to the workspace dashboard
 * lands customers on a page their role cannot open.
 */
export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (loading) return;
    router.replace(user ? homeFor(user.role) : "/login");
  }, [loading, user, router]);
  return <div className="p-8"><Spinner label="Loading…" /></div>;
}
