"use client";
import { useRef, useState } from "react";
import type { QuoteDetail, QuoteLine } from "@/lib/api";
import { formatCurrency, formatPct } from "@/lib/format";
import { Badge, Button, Input } from "@/components/ui";

/** Editable lines. Values are saved server-side (debounced); totals/risk are always the backend's. */
export function QuoteLinesTable({ quote, onUpdate, onRemove, saving }: { quote: QuoteDetail; onUpdate: (lineId: number, patch: { quantity?: number; discount_pct?: number }) => Promise<void>; onRemove: (lineId: number) => Promise<void>; saving: Set<number> }) {
  const [drafts, setDrafts] = useState<Record<number, { quantity?: number; discount_pct?: number }>>({});
  const timers = useRef<Record<number, ReturnType<typeof setTimeout>>>({});
  const editable = quote.can_edit;

  function schedule(line: QuoteLine, patch: { quantity?: number; discount_pct?: number }) {
    setDrafts((d) => ({ ...d, [line.id]: { ...d[line.id], ...patch } }));
    clearTimeout(timers.current[line.id]);
    timers.current[line.id] = setTimeout(async () => {
      await onUpdate(line.id, patch);
      setDrafts((d) => { const n = { ...d }; delete n[line.id]; return n; });
    }, 500);
  }

  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm" data-testid="quote-lines">
        <thead className="bg-zinc-50 text-left text-xs font-semibold uppercase tracking-wide text-zinc-500">
          <tr>
            <th className="px-4 py-2">Product</th>
            <th className="px-2 py-2 text-right">Unit price</th>
            <th className="px-2 py-2 text-right">Qty</th>
            <th className="px-2 py-2 text-right">Discount</th>
            <th className="px-2 py-2">Policy</th>
            <th className="px-2 py-2 text-right">Line total</th>
            <th className="px-2 py-2 text-right">Margin</th>
            <th className="px-2 py-2" />
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100">
          {quote.lines.map((line) => {
            const d = drafts[line.id] ?? {};
            const over = line.line_status === "over_limit";
            return (
              <tr key={line.id} className={over ? "bg-red-50/40" : ""}>
                <td className="px-4 py-2">
                  <p className="font-medium text-zinc-900">{line.description ?? line.product_name}</p>
                  <p className="text-xs text-zinc-500">
                    {line.sku}
                    {line.is_recurring && <Badge tone="purple" className="ml-1">{line.billing_interval ?? "recurring"}</Badge>}
                    {line.stock_available !== null && line.stock_available < line.quantity && <Badge tone="amber" className="ml-1">only {line.stock_available} in stock</Badge>}
                    {line.comment_count > 0 && <span className="ml-1">💬 {line.comment_count}</span>}
                  </p>
                </td>
                <td className="px-2 py-2 text-right tabular-nums">{formatCurrency(line.unit_price)}</td>
                <td className="px-2 py-2 text-right">
                  {editable ? <Input type="number" min={1} className="w-20 text-right" value={d.quantity ?? line.quantity} onChange={(e) => schedule(line, { quantity: Math.max(1, Number(e.target.value)) })} aria-label="Quantity" /> : line.quantity}
                </td>
                <td className="px-2 py-2 text-right">
                  {editable ? <Input type="number" min={0} max={100} step={0.5} className="w-20 text-right" value={d.discount_pct ?? line.discount_pct} onChange={(e) => schedule(line, { discount_pct: Number(e.target.value) })} invalid={over} aria-label="Discount percent" /> : formatPct(line.discount_pct)}
                </td>
                <td className="px-2 py-2 text-xs">
                  <span className={over ? "text-red-700" : "text-emerald-700"}>{over ? `${Number(line.points_over).toFixed(1)} pts over` : "Within limit"}</span>
                  <span className="block text-zinc-500">max {formatPct(line.allowed_discount_pct, 0)} · {line.limit_source}</span>
                </td>
                <td className="px-2 py-2 text-right tabular-nums">{formatCurrency(line.line_total)}{saving.has(line.id) && <span className="block text-[10px] text-zinc-400">saving…</span>}</td>
                <td className="px-2 py-2 text-right tabular-nums text-zinc-600">{formatPct(line.margin_pct)}</td>
                <td className="px-2 py-2 text-right">{editable && <Button variant="ghost" size="sm" onClick={() => onRemove(line.id)} aria-label="Remove line">✕</Button>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
