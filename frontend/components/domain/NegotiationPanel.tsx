"use client";
import { useState } from "react";
import { quotes, type CounterProposal, type LineComment, type QuoteDetail } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { Button, Card, Checkbox, FormError, Select, StatusBadge, Textarea } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";

export function NegotiationPanel({ quote, comments, proposals, onChanged }: { quote: QuoteDetail; comments: LineComment[]; proposals: CounterProposal[]; onChanged: () => void }) {
  const [lineId, setLineId] = useState(quote.lines[0]?.id ?? 0);
  const [text, setText] = useState("");
  const [internal, setInternal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const lineName = (id: number) => quote.lines.find((l) => l.id === id)?.description ?? `Line ${id}`;

  async function send() {
    setBusy(true); setError(null);
    try {
      await quotes.comment(quote.id, lineId, { comment: text, is_internal: internal });
      setText(""); toast.success(internal ? "Internal note saved." : "Reply posted to the customer portal."); onChanged();
    } catch (err) { setError(errorMessage(err)); } finally { setBusy(false); }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Counter proposals">
        {proposals.length === 0 ? <p className="text-sm text-zinc-500">The customer hasn&apos;t proposed changes.</p> : (
          <ul className="space-y-3">
            {proposals.map((p) => (
              <li key={p.id} className="rounded-md border border-zinc-200 p-3 text-sm">
                <div className="flex items-center justify-between"><StatusBadge status={p.status} /><span className="text-xs text-zinc-500">{formatDateTime(p.created_at)}</span></div>
                {p.message && <p className="mt-1 italic text-zinc-700">“{p.message}”</p>}
                <ul className="mt-1 text-xs text-zinc-600">
                  {p.proposed_lines.map((l) => <li key={l.quote_line_id}>{lineName(l.quote_line_id)}: {l.previous_discount_pct}% → <strong>{l.proposed_discount_pct}%</strong>{l.proposed_quantity ? `, qty ${l.previous_quantity} → ${l.proposed_quantity}` : ""}</li>)}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Line comments">
        <ul className="mb-3 max-h-72 space-y-2 overflow-y-auto">
          {comments.length === 0 && <li className="text-sm text-zinc-500">No comments yet.</li>}
          {comments.map((c) => (
            <li key={c.id} className={`rounded-md px-3 py-2 text-sm ${c.author_type === "customer" ? "bg-blue-50" : c.is_internal ? "bg-amber-50" : "bg-zinc-100"}`}>
              <p className="text-xs text-zinc-500">{c.author_name} · {lineName(c.quote_line_id)} · {formatDateTime(c.created_at)}{c.is_internal && " · internal"}</p>
              <p>{c.comment}</p>
            </li>
          ))}
        </ul>
        <FormError message={error} />
        <div className="space-y-2">
          <Select value={lineId} onChange={(e) => setLineId(Number(e.target.value))} aria-label="Line">{quote.lines.map((l) => <option key={l.id} value={l.id}>{l.description ?? l.product_name}</option>)}</Select>
          <Textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Reply to the customer or leave an internal note…" />
          <div className="flex items-center justify-between">
            <Checkbox label="Internal note (hidden from customer)" checked={internal} onChange={(e) => setInternal(e.target.checked)} />
            <Button size="sm" onClick={send} loading={busy} disabled={!text.trim() || !lineId}>Post</Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
