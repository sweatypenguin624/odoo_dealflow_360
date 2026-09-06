"use client";
import { useState } from "react";
import { quotes, type QuoteDetail } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { formatDateTime, titleCase } from "@/lib/format";
import { Button, Card, Field, FormError, StatusBadge, Textarea } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";

export function ApprovalPanel({ quote, onChanged }: { quote: QuoteDetail; onChanged: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const req = quote.approval_request;
  const canAct = quote.available_actions.includes("approve");

  async function act(action: string) {
    setBusy(action);
    setError(null);
    try {
      await quotes.approvalAction(quote.id, { action, note: note || undefined });
      toast.success(`Quotation ${titleCase(action).toLowerCase()}.`);
      setNote("");
      onChanged();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card title="Approval">
      {req ? (
        <dl className="grid grid-cols-2 gap-2 text-sm">
          <div><dt className="text-xs text-zinc-500">Request status</dt><dd><StatusBadge status={req.status} /> {req.is_stale && <StatusBadge status="superseded" label="Stale version" />}</dd></div>
          <div><dt className="text-xs text-zinc-500">Required level</dt><dd><StatusBadge status={req.required_level} /></dd></div>
          <div><dt className="text-xs text-zinc-500">Current step</dt><dd>{req.current_step ? titleCase(req.current_step) : "—"}</dd></div>
          <div><dt className="text-xs text-zinc-500">Raised</dt><dd>{formatDateTime(req.created_at)}{req.expires_at ? ` · expires ${formatDateTime(req.expires_at)}` : ""}</dd></div>
          {req.risk_summary && <div className="col-span-2"><dt className="text-xs text-zinc-500">Risk summary</dt><dd className="text-zinc-700">{req.risk_summary}</dd></div>}
        </dl>
      ) : (
        <p className="text-sm text-zinc-500">{quote.status === "approved" || quote.approval_valid ? "Approved automatically — all lines within policy." : "Not submitted for approval yet."}</p>
      )}
      {canAct && (
        <div className="mt-4 space-y-2 border-t border-zinc-100 pt-3">
          <FormError message={error} />
          <Field label="Decision note"><Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional reason shown to the rep and recorded in the audit trail" /></Field>
          <div className="flex flex-wrap gap-2">
            <Button variant="success" onClick={() => act("approved")} loading={busy === "approved"} data-testid="approve-btn">Approve</Button>
            <Button variant="secondary" onClick={() => act("returned_for_revision")} loading={busy === "returned_for_revision"}>Return for revision</Button>
            <Button variant="danger" onClick={() => act("rejected")} loading={busy === "rejected"}>Reject</Button>
          </div>
        </div>
      )}
    </Card>
  );
}
