// Dedicated API client for the customer-facing portal (frontend/app/portal/[token]).
//
// Deliberately separate from lib/api/* (the internal workspace client): the
// portal is a genuinely different, restricted surface authenticated by a
// per-quote X-Portal-Token header rather than being open like the internal
// endpoints. It reuses only the low-level fetch wrapper (apiFetch/ApiError)
// from lib/api/client, not any of the internal endpoint functions or types.
import { apiFetch, ApiError } from "./api/client";

export { ApiError };

// ---- GET /portal/quote ----
// Shapes below match backend/app/routers/portal.py exactly. `status` is
// already the customer-friendly label ("Sent" / "Under Negotiation" /
// "Confirmed" / "Rejected") - the backend does that mapping, not us.

export interface PortalLineComment {
  id: number;
  quote_line_id: number;
  author_type: "customer" | "rep" | string;
  author_name: string;
  comment: string;
  created_at: string;
}

export interface PortalQuoteLine {
  id: number;
  product_id: number;
  quantity: number;
  discount_pct: number;
  line_value: number;
  comments: PortalLineComment[];
}

export interface PortalQuote {
  quote_id: number;
  status: string;
  lines: PortalQuoteLine[];
}

const withToken = (token: string): HeadersInit => ({ "X-Portal-Token": token });

export const getPortalQuote = (token: string) =>
  apiFetch<PortalQuote>("/portal/quote", { method: "GET", headers: withToken(token) });
