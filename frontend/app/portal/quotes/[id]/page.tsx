"use client";
import Link from "next/link";
import { use } from "react";
import { portalApi } from "@/lib/api/portal";
import { useApi } from "@/lib/hooks/useApi";
import { ErrorState, Skeleton } from "@/components/ui";
import { PortalQuoteView } from "@/components/domain/PortalQuoteView";

/** Signed-in customer view. Authorisation is by session, not a link token. */
export default function PortalQuotePage({ params }: { params: Promise<{ id: string }> }) {
  const quoteId = Number(use(params).id);
  const { data, error, loading, reload } = useApi(() => portalApi.quote(null, quoteId), [quoteId]);

  if (loading && !data) return <Skeleton className="h-64" />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <Link href="/portal" className="text-xs text-blue-600 hover:underline">← All quotations</Link>
      <PortalQuoteView quote={data} token={null} quoteId={quoteId} onChanged={reload} />
    </div>
  );
}
