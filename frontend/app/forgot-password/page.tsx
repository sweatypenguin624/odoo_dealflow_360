"use client";
import Link from "next/link";
import { FormEvent, useState } from "react";
import { apiPost, errorMessage } from "@/lib/api/client";
import { Button, Field, FormError, Input } from "@/components/ui";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await apiPost("/auth/forgot-password", { email });
      setDone(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 px-4">
      <form onSubmit={onSubmit} className="card w-full max-w-sm space-y-4 p-6">
        <h1 className="text-lg font-semibold">Reset your password</h1>
        {done ? (
          <p className="text-sm text-zinc-600">If an account exists for <strong>{email}</strong>, a reset link is on its way. In development the link is printed by the API server (console email provider).</p>
        ) : (
          <>
            <FormError message={error} />
            <Field label="Email" required>
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </Field>
            <Button type="submit" loading={loading} className="w-full">Send reset link</Button>
          </>
        )}
        <p className="text-center text-xs"><Link href="/login" className="link">Back to sign in</Link></p>
      </form>
    </div>
  );
}
