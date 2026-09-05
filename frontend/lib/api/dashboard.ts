import { apiGet } from "./client";
import type { QuoteHealth, RecentAuditLogEntry } from "./types";

export const getDealHealth = () => apiGet<QuoteHealth[]>("/dashboard/deal-health");

export const getRecentAuditLog = (limit?: number) =>
  apiGet<RecentAuditLogEntry[]>("/audit-log/recent", limit ? { limit } : undefined);
