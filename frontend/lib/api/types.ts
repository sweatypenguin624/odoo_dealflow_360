// Every shape below was confirmed against the live backend (Phase 2-7
// routers plus the Phase 8 gap-fill endpoints), not guessed from the
// Python source alone - see the router files under backend/app/routers/
// for the source of truth if these ever drift.

export type QuoteStatus = "draft" | "pending_approval" | "approved" | "rejected" | "confirmed";
export type ApprovalLevel = "none" | "manager" | "manager_then_finance";
export type ApprovalStep = "manager" | "finance";

// ---- GET /quotes, GET /quotes/{id} (Phase 8 gap-fill) ----

export interface QuoteListItem {
  id: number;
  customer_id: number;
  customer_name: string;
  status: QuoteStatus;
  required_approval_level: ApprovalLevel | null;
  current_approval_step: ApprovalStep | null;
  created_at: string | null;
}

export interface QuoteLineDetail {
  id: number;
  product_id: number;
  product_name: string;
  quantity: number;
  discount_pct: number;
  line_value: number;
  is_recurring: boolean;
}

export interface QuoteDetail {
  id: number;
  customer_id: number;
  customer_name: string;
  status: QuoteStatus;
  required_approval_level: ApprovalLevel | null;
  current_approval_step: ApprovalStep | null;
  risk_reasons: string[] | null;
  created_at: string | null;
  lines: QuoteLineDetail[];
}

// ---- Risk engine (Phase 2) ----

export interface LineResult {
  line_id: number;
  applicable_limit: number;
  points_over: number;
  is_violating: boolean;
  reason: string | null;
}

export interface QuoteRiskResult {
  line_results: LineResult[];
  blended_score: number;
  required_approval_level: ApprovalLevel;
  reasons: string[];
}

// ---- POST /quotes/{id}/submit - returns raw ORM columns only, no
// relationships (confirmed live: no `lines`/`customer` nested object) ----

export interface SubmittedQuote {
  id: number;
  created_at: string;
  current_approval_step: ApprovalStep | null;
  rep_name: string | null;
  customer_id: number;
  status: QuoteStatus;
  required_approval_level: ApprovalLevel | null;
  risk_reasons: string[] | null;
}

export interface SubmitQuoteResponse {
  quote: SubmittedQuote;
  risk_result: QuoteRiskResult;
}

// ---- Approval workflow (Phase 3) ----

export interface ApprovalAction {
  id: number;
  action: "approved" | "rejected" | "returned_for_revision";
  reason: string | null;
  quote_id: number;
  step: ApprovalStep;
  actor: string;
  timestamp: string;
}

export interface AuditLogEntry {
  id: number;
  action: string;
  timestamp: string;
  quote_id: number;
  user: string;
  reason: string | null;
}

export interface ApprovalActionResponse {
  quote: SubmittedQuote;
  history: ApprovalAction[];
}

export interface ApprovalHistoryResponse {
  approval_actions: ApprovalAction[];
  audit_logs: AuditLogEntry[];
}

// ---- Upsell / margin engine (Phase 6) ----

export interface MarginSummary {
  total_price: number;
  total_margin_amount: number;
  overall_margin_pct: number;
}

export interface RankedSuggestion {
  product_id: number;
  name: string;
  price: number;
  margin_delta_if_added: number;
  is_promoted: boolean;
  reason: string;
}

export interface AddSuggestionLine {
  id: number;
  quote_id: number;
  product_id: number;
  quantity: number;
  discount_pct: number;
  line_value: number;
}

export interface AddSuggestionResponse {
  lines: AddSuggestionLine[];
  margin_summary: MarginSummary;
}

// ---- Fulfillment (Phase 4) ----

export interface FulfillmentSplit {
  id: number;
  quote_line_id: number;
  warehouse_id: number | null;
  quantity_fulfilled: number;
  is_backorder: boolean;
  warning: string | null;
}

export type FulfillmentPlanStatus = "suggested" | "confirmed" | "manually_overridden";

export interface FulfillmentPlan {
  id: number;
  quote_id: number;
  status: FulfillmentPlanStatus;
  splits: FulfillmentSplit[];
  backorder_summary: string[];
}

export interface Warehouse {
  id: number;
  name: string;
  shipping_cost_weight: number;
}

// ---- Billing / subscriptions (Phase 5) ----

export type SubscriptionStatus = "active" | "cancelled";
export type BillingEventType =
  | "invoice"
  | "proration_charge"
  | "proration_credit"
  | "refund"
  | "cancellation_credit";

export interface BillingEvent {
  id: number;
  subscription_id: number;
  event_type: BillingEventType;
  amount: number;
  description: string;
  event_date: string;
}

export interface Subscription {
  id: number;
  quote_line_id: number;
  subscription_plan_id: number;
  quantity: number;
  status: SubscriptionStatus;
  current_cycle_start: string;
  current_cycle_end: string;
}

export interface SubscriptionWithEvent {
  subscription: Subscription;
  billing_event: BillingEvent;
}

export interface OneTimeLine {
  quote_line_id: number;
  product_id: number;
  quantity: number;
  discount_pct: number;
  line_value: number;
}

export interface RecurringLine {
  quote_line_id: number;
  product_id: number;
  subscription_id: number;
  subscription_plan_id: number;
  quantity: number;
  status: SubscriptionStatus;
  current_cycle_start: string;
  current_cycle_end: string;
  billing_events: BillingEvent[];
}

export interface BillingSummary {
  one_time_lines: OneTimeLine[];
  recurring_lines: RecurringLine[];
}

// ---- Catalog (Phase 8 gap-fill) ----

export interface ProductRef {
  id: number;
  name: string;
  category_id: number;
  category_name: string;
  price: number;
  unit_margin_pct: number;
}

export interface CustomerRef {
  id: number;
  name: string;
  tier_id: number;
  tier_name: string;
  max_discount_pct: number;
}

// ---- Deal health (Phase 7, dashboard screen added in Phase 9) ----

export interface DealHealthFlag {
  flag_type: "stalled" | "discount_anomaly";
  severity: "warning" | "critical";
  message: string;
}

export interface QuoteHealth {
  quote_id: number;
  customer_name: string;
  status: string;
  last_updated_at: string;
  rep_name: string;
  applied_discount_pct: number;
  flags: DealHealthFlag[];
}
