// Portal client. Token links send X-Portal-Token; signed-in customers use their session.
import { apiFetch } from "./client";
import type { PortalComment, PortalQuote, PortalQuoteSummary, Page } from "./types";

const withToken = (token: string | null): Record<string, string> => (token ? { "X-Portal-Token": token } : {});

export interface PortalCounterResult {
  quote: { quote_id: number; status: string };
  counter_proposal: { id: number; status: string };
  risk_result: { required_approval_level: string } | null;
  customer_status: string;
}

export const portalApi = {
  quote: (token: string | null, quoteId?: number) =>
    apiFetch<PortalQuote>(token ? "/portal/quote" : `/portal/quotes/${quoteId}`, { method: "GET", headers: withToken(token), skipRefresh: !!token }),
  myQuotes: (page = 1) => apiFetch<Page<PortalQuoteSummary>>("/portal/quotes", { method: "GET", query: { page, page_size: 20 } }),
  comment: (token: string | null, quoteId: number | undefined, lineId: number, comment: string) =>
    apiFetch<PortalComment>(token ? `/portal/lines/${lineId}/comment` : `/portal/quotes/${quoteId}/lines/${lineId}/comment`, { method: "POST", body: { comment }, headers: withToken(token) }),
  counter: (token: string | null, quoteId: number | undefined, proposed_lines: { quote_line_id: number; proposed_discount_pct?: number; proposed_quantity?: number }[], message?: string) =>
    apiFetch<PortalCounterResult>(token ? "/portal/counter-proposal" : `/portal/quotes/${quoteId}/counter-proposal`, { method: "POST", body: { proposed_lines, message }, headers: withToken(token) }),
  confirm: (token: string | null, quoteId?: number) =>
    apiFetch<{ quote_id: number; status: string; order_number: string | null }>(token ? "/portal/confirm" : `/portal/quotes/${quoteId}/confirm`, { method: "POST", headers: withToken(token) }),
};
