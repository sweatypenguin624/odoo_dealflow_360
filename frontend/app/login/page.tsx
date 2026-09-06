"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth/AuthContext";
import { errorMessage } from "@/lib/api/client";
import { homeFor, landingFor } from "@/lib/rbac";
import { Button, Field, FormError, Input } from "@/components/ui";

function LoginForm() {
  const { login, user, loading: sessionLoading } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const submitted = useRef(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Someone who is already signed in has no business on this form. This lives
  // here rather than in the proxy because only a live /auth/me can tell a real
  // session from a leftover cookie - and it knows the role, so a customer goes
  // to the portal instead of a workspace they cannot open.
  useEffect(() => {
    if (sessionLoading || !user || submitted.current) return;
    router.replace(homeFor(user.role));
  }, [sessionLoading, user, router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    submitted.current = true;
    setLoading(true);
    setError(null);
    try {
      const user = await login(email, password);
      router.replace(landingFor(user.role, params.get("next")));
    } catch (err) {
      setError(errorMessage(err, "Sign-in failed."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="card w-full max-w-sm space-y-4 p-6" aria-label="Sign in">
      <div>
        <h1 className="text-lg font-semibold text-zinc-900">Sign in to DealFlow360</h1>
        <p className="text-sm text-zinc-500">Use your work email and password.</p>
      </div>
      <FormError message={error} />
      <Field label="Email" required>
        <Input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
      </Field>
      <Field label="Password" required>
        <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
      </Field>
      <Button type="submit" loading={loading} className="w-full">Sign in</Button>
      <p className="text-center text-xs text-zinc-500">
        <Link href="/forgot-password" className="link">Forgot your password?</Link>
      </p>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-zinc-50 px-4">
      <p className="text-2xl font-bold tracking-tight text-zinc-900">DealFlow<span className="text-blue-600">360</span></p>
      <Suspense>
        <LoginForm />
      </Suspense>
    </div>
  );
}
