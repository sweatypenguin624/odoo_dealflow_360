"use client";
import { Button } from "./Button";

export function Pagination({ page, totalPages, total, pageSize, onChange }: { page: number; totalPages: number; total: number; pageSize: number; onChange: (page: number) => void }) {
  if (total === 0) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <nav className="flex flex-wrap items-center justify-between gap-2 text-sm text-zinc-600" aria-label="Pagination">
      <span>
        Showing <strong>{from}–{to}</strong> of <strong>{total.toLocaleString()}</strong>
      </span>
      <div className="flex items-center gap-1">
        <Button variant="secondary" size="sm" onClick={() => onChange(1)} disabled={page <= 1} aria-label="First page">«</Button>
        <Button variant="secondary" size="sm" onClick={() => onChange(page - 1)} disabled={page <= 1}>Previous</Button>
        <span className="px-2">
          Page {page} of {Math.max(1, totalPages)}
        </span>
        <Button variant="secondary" size="sm" onClick={() => onChange(page + 1)} disabled={page >= totalPages}>Next</Button>
        <Button variant="secondary" size="sm" onClick={() => onChange(totalPages)} disabled={page >= totalPages} aria-label="Last page">»</Button>
      </div>
    </nav>
  );
}
