import type { AuditEntry } from "@/lib/api";
import { formatDateTime, titleCase } from "@/lib/format";

export function Timeline({ entries, emptyText = "No activity yet." }: { entries: AuditEntry[]; emptyText?: string }) {
  if (entries.length === 0) return <p className="text-sm text-zinc-500">{emptyText}</p>;
  return (
    <ol className="relative space-y-3 border-l border-zinc-200 pl-4">
      {entries.map((e) => (
        <li key={e.id} className="text-sm">
          <span className="absolute -left-[5px] mt-1.5 h-2 w-2 rounded-full bg-blue-500" aria-hidden />
          <p className="text-zinc-900"><span className="font-medium">{titleCase(e.action)}</span> <span className="text-zinc-500">by {e.user}</span></p>
          {e.reason && <p className="text-zinc-600">{e.reason}</p>}
          <p className="text-xs text-zinc-400">{formatDateTime(e.timestamp)}</p>
        </li>
      ))}
    </ol>
  );
}
