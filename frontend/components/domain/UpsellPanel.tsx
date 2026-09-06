"use client";
import { useState } from "react";
import { quotes, type Suggestion } from "@/lib/api";
import { useApi } from "@/lib/hooks/useApi";
import { formatCurrency, formatPct } from "@/lib/format";
import { Badge, Button, Card, Spinner } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { errorMessage } from "@/lib/api/client";

export function UpsellPanel({ quoteId, canEdit, onAdded, version }: { quoteId: number; canEdit: boolean; onAdded: () => void; version: number }) {
  const { data, loading, reload } = useApi(() => quotes.suggestions(quoteId), [quoteId, version]);
  const [dismissed, setDismissed] = useState<Set<number>>(new Set());
  const [adding, setAdding] = useState<number | null>(null);
  const toast = useToast();
  const visible = (data ?? []).filter((s) => !dismissed.has(s.product_id));

  async function add(s: Suggestion) {
    setAdding(s.product_id);
    try {
      await quotes.addSuggestion(quoteId, { product_id: s.product_id, quantity: 1 });
      toast.success(`${s.name} added — totals and risk recalculated.`);
      onAdded();
      reload();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setAdding(null);
    }
  }

  return (
    <Card title="Upsell & cross-sell">
      {loading && !data && <Spinner />}
      {data && visible.length === 0 && <p className="text-sm text-zinc-500">No suggestions for the current lines.</p>}
      <ul className="space-y-3">
        {visible.map((s) => (
          <li key={s.product_id} className="rounded-md border border-zinc-200 p-3" data-testid="upsell-suggestion">
            <div className="flex items-start justify-between gap-2">
              <p className="font-medium text-zinc-900">{s.name} <span className="text-xs text-zinc-500">{s.sku}</span></p>
              {s.is_promoted && <Badge tone="amber">Promotion</Badge>}
            </div>
            <p className="mt-0.5 text-xs text-zinc-600">{s.reason}</p>
            <div className="mt-1 flex flex-wrap gap-x-3 text-xs text-zinc-600">
              <span>+{formatCurrency(s.price_impact)}</span>
              <span>margin {formatPct(s.unit_margin_pct, 0)}</span>
              <span className={Number(s.margin_delta_if_added) >= 0 ? "text-emerald-700" : "text-red-700"}>{Number(s.margin_delta_if_added) >= 0 ? "+" : ""}{Number(s.margin_delta_if_added).toFixed(2)} pp overall</span>
              <span>{s.stock_available === null ? "not stocked" : s.in_stock ? `${s.stock_available} in stock` : "out of stock"}</span>
            </div>
            <div className="mt-2 flex gap-2">
              <Button size="sm" onClick={() => add(s)} loading={adding === s.product_id} disabled={!canEdit}>Add to quote</Button>
              <Button size="sm" variant="ghost" onClick={() => setDismissed((d) => new Set(d).add(s.product_id))}>Dismiss</Button>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
