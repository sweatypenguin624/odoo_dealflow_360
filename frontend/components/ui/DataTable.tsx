"use client";
import { ReactNode } from "react";
import { EmptyState, TableSkeleton } from "./States";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  className?: string;
  align?: "left" | "right" | "center";
}

export function DataTable<T>({ columns, rows, keyOf, loading, emptyTitle = "Nothing here yet", emptyDescription, onRowClick, dense }: {
  columns: Column<T>[];
  rows: T[] | null | undefined;
  keyOf: (row: T) => string | number;
  loading?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  onRowClick?: (row: T) => void;
  dense?: boolean;
}) {
  if (loading && !rows) return <TableSkeleton cols={columns.length} />;
  if (!rows || rows.length === 0) return <EmptyState title={emptyTitle} description={emptyDescription} />;
  const pad = dense ? "px-3 py-1.5" : "px-4 py-2.5";
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-zinc-50 text-left text-xs font-semibold uppercase tracking-wide text-zinc-500">
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={`${pad} ${c.align === "right" ? "text-right" : c.align === "center" ? "text-center" : ""} ${c.className ?? ""}`}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100">
          {rows.map((row) => (
            <tr key={keyOf(row)} className={onRowClick ? "cursor-pointer hover:bg-blue-50/40" : "hover:bg-zinc-50"} onClick={onRowClick ? () => onRowClick(row) : undefined}>
              {columns.map((c) => (
                <td key={c.key} className={`${pad} align-middle ${c.align === "right" ? "text-right tabular-nums" : c.align === "center" ? "text-center" : ""} ${c.className ?? ""}`}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
