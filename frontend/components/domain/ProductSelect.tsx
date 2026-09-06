"use client";
import { useEffect, useState } from "react";
import { catalog, type Product } from "@/lib/api";
import { useDebounce } from "@/lib/hooks/useApi";
import { Input } from "@/components/ui";

/** Small searchable product picker for forms (returns a product id). */
export function ProductSelect({ value, onChange, stockedOnly }: { value: number; onChange: (id: number, product?: Product) => void; stockedOnly?: boolean }) {
  const [q, setQ] = useState("");
  const [label, setLabel] = useState("");
  const [options, setOptions] = useState<Product[]>([]);
  const debounced = useDebounce(q, 250);
  useEffect(() => {
    if (!debounced.trim()) return;
    catalog.products({ q: debounced, page_size: 8 }).then((p) => setOptions(p.items.filter((x) => !stockedOnly || x.is_stocked))).catch(() => undefined);
  }, [debounced, stockedOnly]);
  // An emptied box shows nothing without an effect having to clear state.
  const visible = debounced.trim() ? options : [];
  useEffect(() => { if (value && !label) catalog.product(value).then((p) => setLabel(`${p.name} (${p.sku})`)).catch(() => undefined); }, [value, label]);
  return (
    <div className="relative">
      <Input value={value && label && !q ? label : q} onChange={(e) => { setQ(e.target.value); setLabel(""); onChange(0); }} placeholder="Search product…" />
      {q && visible.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-md border border-zinc-200 bg-white shadow">
          {visible.map((p) => <li key={p.id}><button type="button" className="w-full px-3 py-1.5 text-left text-sm hover:bg-blue-50" onClick={() => { onChange(p.id, p); setLabel(`${p.name} (${p.sku})`); setQ(""); }}>{p.name} <span className="text-xs text-zinc-500">{p.sku}</span></button></li>)}
        </ul>
      )}
    </div>
  );
}
