"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { notifications } from "@/lib/api";

export function NotificationBell() {
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    let active = true;
    const load = () => notifications.unreadCount().then((r) => active && setUnread(r.unread)).catch(() => undefined);
    load();
    const t = setInterval(load, 60000);
    return () => { active = false; clearInterval(t); };
  }, []);
  return (
    <Link href="/workspace/notifications" className="relative rounded-md p-2 text-zinc-600 hover:bg-zinc-100" aria-label={`Notifications, ${unread} unread`}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></svg>
      {unread > 0 && <span className="absolute -right-0.5 -top-0.5 rounded-full bg-red-600 px-1.5 text-[10px] font-semibold text-white">{unread > 99 ? "99+" : unread}</span>}
    </Link>
  );
}
