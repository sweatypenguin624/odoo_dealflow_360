"use client";
import { use } from "react";
import { portalApi } from "@/lib/api/portal";
import { useApi } from "@/lib/hooks/useApi";
import { ErrorState, Skeleton } from "@/components/ui";
import { PortalQuoteView } from "@/components/domain/PortalQuoteView";

/**
 * Tokenised entry point from the "your quotation is ready" email. The token in
 * the URL is the only credential; no sign-in is required or used here.
 */
export default function PortalTokenPage({ params }: { params: Promise<{ token: string }> }) {
  const token = use(params).token;
  const { data, error, loading, reload } = useApi(() => portalApi.quote(token), [token]);

  if (loading && !data) return <Skeleton className="h-64" />;

  if (error) {
    return (
      <div className="space-y-3">
        <ErrorState message={error} onRetry={reload} />
        <p className="text-sm text-zinc-600">
          Links expire for security. If this one has, ask your sales contact to send a fresh link.
        </p>
      </div>
    );
  }

  if (!data) return null;
  return <PortalQuoteView quote={data} token={token} onChanged={reload} />;
}
