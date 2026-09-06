"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";
import { useAuth } from "@/lib/auth/AuthContext";
import { errorMessage } from "@/lib/api/client";
import { homeFor } from "@/lib/rbac";
import { Button, Field, FormError, Input } from "@/components/ui";

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const user = await login(email, password);
      const next = params.get("next");
      router.replace(next && user.role !== "customer" ? next : homeFor(user.role));
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
