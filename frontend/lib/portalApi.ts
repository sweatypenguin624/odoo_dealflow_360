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

// ---- GET /products ----
// Public, unauthenticated lookup (backend/app/routers/catalog.py) - used
// here only to resolve product_id -> a display name for the portal's line
// table. Kept minimal and local rather than importing lib/api/catalog.ts,
// so this file has no dependency on the internal client's endpoint layer.

export interface PortalProductRef {
  id: number;
  name: string;
}

export const listPortalProducts = () => apiFetch<PortalProductRef[]>("/products", { method: "GET" });

// ---- POST /portal/lines/{line_id}/comment ----

export const submitPortalComment = (token: string, lineId: number, comment: string) =>
  apiFetch<PortalLineComment>(`/portal/lines/${lineId}/comment`, {
    method: "POST",
    body: { comment },
    headers: withToken(token),
  });

// ---- POST /portal/counter-proposal ----
// Mirrors backend/app/routers/portal.py's CounterProposalResult exactly.
// `risk_result` is only present when the proposal wasn't a pure discount
// downgrade (i.e. it needed re-evaluation by the risk engine) - the UI
// must never surface its raw contents (reasons, approval-level names) to
// the customer, only whether re-approval is now pending.

export interface ProposedLine {
  quote_line_id: number;
  proposed_discount_pct: number;
}

export interface PortalCounterProposal {
  id: number;
  quote_id: number;
  submitted_by: string;
  proposed_lines: ProposedLine[];
  status: string;
  created_at: string;
}

export interface PortalQuoteState {
  quote_id: number;
  status: string;
  required_approval_level: string | null;
  current_approval_step: string | null;
}

export interface CounterProposalResult {
  quote: PortalQuoteState;
  counter_proposal: PortalCounterProposal;
  risk_result: { required_approval_level: string } | null;
}

export const submitCounterProposal = (token: string, proposedLines: ProposedLine[]) =>
  apiFetch<CounterProposalResult>("/portal/counter-proposal", {
    method: "POST",
    body: { proposed_lines: proposedLines },
    headers: withToken(token),
  });

// ---- POST /portal/confirm ----

export interface PortalConfirmResult {
  quote_id: number;
  status: string;
}

export const confirmPortalQuote = (token: string) =>
  apiFetch<PortalConfirmResult>("/portal/confirm", { method: "POST", headers: withToken(token) });
