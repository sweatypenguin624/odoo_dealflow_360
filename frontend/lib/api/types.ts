// Shared API types. Shapes mirror backend/app/schemas/*.py.

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export type QuoteStatus =
  | "draft" | "pending_approval" | "approved" | "rejected" | "revision_required" | "sent" | "under_negotiation" | "confirmed" | "expired" | "cancelled";

export interface LineRisk {
  line_id: number;
  applicable_limit: number;
  points_over: number;
  is_violating: boolean;
  reason: string | null;
  requested_pct: number;
  limit_source: string;
  excess_amount: number;
  status: "within_limit" | "over_limit";
  approval_hint: string;
  explanation: string;
}

export interface RiskResult {
  line_results: LineRisk[];
  blended_score: number;
  required_approval_level: "none" | "manager" | "manager_then_finance";
  reasons: string[];
  weighted_excess_pct: number;
  excess_discount_amount: number;
  worst_points_over: number;
  summary: string;
  level_label: string;
}

export interface QuoteLine {
  id: number;
  product_id: number;
  product_name: string;
  sku: string | null;
  variant_id: number | null;
  variant_name: string | null;
  description: string | null;
  quantity: number;
  unit_price: number;
  unit_cost: number;
  discount_pct: number;
  tax_rate_pct: number;
  line_value: number;
  line_total: number;
  tax_amount: number;
  margin_amount: number;
  margin_pct: number;
  is_recurring: boolean;
  subscription_plan_id: number | null;
  subscription_plan_name: string | null;
  billing_interval: string | null;
  allowed_discount_pct: number;
  limit_source: string;
  points_over: number;
  line_status: "within_limit" | "over_limit";
  explanation: string;
  comment_count: number;
  stock_available: number | null;
}

export interface ApprovalRequest {
  id: number;
  quote_id: number;
  quote_version: number;
  required_level: string;
  status: string;
  current_step: string | null;
  risk_summary: string | null;
  created_at: string;
  resolved_at: string | null;
  expires_at: string | null;
  is_stale: boolean;
}

export interface CounterProposal {
  id: number;
  quote_id: number;
  submitted_by: string;
  proposed_lines: { quote_line_id: number; proposed_discount_pct: number; previous_discount_pct: number; proposed_quantity?: number | null; previous_quantity?: number }[];
  message: string | null;
  status: string;
  approval_request_id: number | null;
  created_at: string;
  resolved_at: string | null;
}

export interface QuoteListItem {
  id: number;
  quote_number: string | null;
  customer_id: number;
  customer_name: string;
  owner_user_id: number | null;
  owner_name: string | null;
  status: QuoteStatus;
  version: number;
  total: number;
  margin_pct: number;
  risk_score: number | null;
  required_approval_level: string | null;
  current_approval_step: string | null;
  fulfillment_status: string;
  billing_status: string;
  order_number: string | null;
  valid_until: string | null;
  promised_delivery_date: string | null;
  created_at: string | null;
  last_activity_at: string | null;
  line_count: number;
  has_recurring: boolean;
}

export interface QuoteDetail extends QuoteListItem {
  approved_version: number | null;
  approval_valid: boolean;
  currency: string;
  order_discount_pct: number;
  subtotal: number;
  discount_total: number;
  tax_total: number;
  margin_amount: number;
  expected_delivery_date: string | null;
  actual_delivery_date: string | null;
  notes: string | null;
  sent_at: string | null;
  confirmed_at: string | null;
  risk_reasons: string[] | null;
  lines: QuoteLine[];
  risk: RiskResult;
  approval_request: ApprovalRequest | null;
  counter_proposals: CounterProposal[];
  portal_link_active: boolean;
  can_edit: boolean;
  available_actions: string[];
  customer_email: string | null;
  customer_tier: string | null;
}

export interface ApprovalAction {
  id: number;
  quote_id: number;
  approval_request_id: number | null;
  step: string;
  action: string;
  actor: string;
  actor_user_id: number | null;
  reason: string | null;
  timestamp: string;
}

export interface AuditEntry {
  id: number;
  quote_id: number | null;
  actor_user_id: number | null;
  user: string;
  action: string;
  entity_type: string | null;
  entity_id: number | null;
  reason: string | null;
  before_data?: unknown;
  after_data?: unknown;
  timestamp: string;
  quote_number?: string | null;
  customer_name?: string | null;
}

export interface ApprovalQueueItem {
  request_id: number;
  quote_id: number;
  quote_number: string | null;
  quote_version: number;
  customer_name: string;
  owner_name: string | null;
  required_level: string;
  current_step: string | null;
  risk_summary: string | null;
  total: number;
  margin_pct: number;
  risk_score: number | null;
  created_at: string;
  expires_at: string | null;
  waiting_days: number;
}

export interface LineComment {
  id: number;
  quote_line_id: number;
  author_type: string;
  author_name: string;
  comment: string;
  is_internal: boolean;
  created_at: string;
}

export interface Product {
  id: number;
  sku: string | null;
  name: string;
  description: string | null;
  category_id: number;
  category_name: string;
  cost: number;
  price: number;
  unit: string;
  tax_rate_pct: number;
  product_type: "one_time" | "recurring" | "both";
  is_stocked: boolean;
  unit_margin_pct: number;
  is_active: boolean;
  is_archived: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Variant {
  id: number;
  product_id: number;
  sku: string;
  name: string;
  attributes: Record<string, unknown>;
  price: number | null;
  cost: number | null;
  is_active: boolean;
}

export interface ProductDetail extends Product {
  variants: Variant[];
  stock_available: number;
  subscription_plans: { id: number; name: string; interval: string; price_per_interval: number; is_active: boolean }[];
}

export interface ProductPricing {
  product_id: number;
  variant_id: number | null;
  unit_price: number;
  unit_cost: number;
  currency: string;
  price_source: string;
  allowed_discount_pct: number;
  discount_limit_source: string;
  stock_available: number;
}

export interface Category {
  id: number;
  name: string;
  description: string | null;
  max_discount_pct: number | null;
  is_active: boolean;
  product_count: number;
}

export interface Tier {
  id: number;
  name: string;
  max_discount_pct: number;
  description: string | null;
  sort_order: number;
  is_active: boolean;
  customer_count: number;
}

export interface SubscriptionPlan {
  id: number;
  name: string;
  product_id: number;
  product_name: string;
  interval: string;
  price_per_interval: number;
  proration_enabled: boolean;
  is_active: boolean;
}

export interface Pairing {
  id: number;
  base_product_id: number;
  base_product_name: string;
  suggested_product_id: number;
  suggested_product_name: string;
  co_purchase_score: number;
  is_promoted: boolean;
  promotion_label: string | null;
  promotion_start: string | null;
  promotion_end: string | null;
  is_active: boolean;
}

export interface PriceListItem {
  id: number;
  product_id: number;
  product_name: string;
  product_sku: string | null;
  variant_id: number | null;
  min_quantity: number;
  unit_price: number;
}

export interface PriceList {
  id: number;
  name: string;
  currency: string;
  tier_id: number | null;
  tier_name: string | null;
  valid_from: string | null;
  valid_to: string | null;
  priority: number;
  is_active: boolean;
  item_count: number;
  items?: PriceListItem[];
}

export interface DiscountRule {
  id: number;
  name: string;
  scope: "tier" | "category" | "tier_category" | "product";
  tier_id: number | null;
  tier_name: string | null;
  category_id: number | null;
  category_name: string | null;
  product_id: number | null;
  product_name: string | null;
  max_discount_pct: number;
  valid_from: string | null;
  valid_to: string | null;
  priority: number;
  is_active: boolean;
}

export interface ApprovalRule {
  id: number;
  name: string;
  approval_level: "manager" | "manager_then_finance";
  min_points_over: number;
  min_excess_amount: number | null;
  valid_from: string | null;
  valid_to: string | null;
  is_active: boolean;
  expires_after_days: number | null;
}

export interface Customer {
  id: number;
  code: string | null;
  name: string;
  tier_id: number;
  tier_name: string;
  max_discount_pct: number;
  owner_user_id: number | null;
  owner_name: string | null;
  industry: string | null;
  email: string | null;
  phone: string | null;
  contact_name: string | null;
  currency: string;
  payment_terms_days: number;
  is_active: boolean;
  created_at: string | null;
  open_quote_count: number;
  outstanding_balance: number;
}

export interface CustomerDetail extends Customer {
  website: string | null;
  notes: string | null;
  billing_address_line1: string | null;
  billing_city: string | null;
  billing_state: string | null;
  billing_postal_code: string | null;
  billing_country: string | null;
  shipping_address_line1: string | null;
  shipping_city: string | null;
  shipping_state: string | null;
  shipping_postal_code: string | null;
  shipping_country: string | null;
  updated_at: string | null;
}

export interface CustomerHistory {
  quotes: { id: number; quote_number: string | null; status: string; total: number; owner_name: string | null; created_at: string; order_number: string | null; fulfillment_status: string; billing_status: string }[];
  orders: { id: number; order_number: string; quote_number: string | null; total: number; confirmed_at: string | null; fulfillment_status: string; billing_status: string }[];
  invoices: { id: number; invoice_number: string; status: string; amount: number; amount_paid: number; due_date: string; invoice_type: string; quote_id: number }[];
  payments: { id: number; invoice_id: number; invoice_number: string; amount: number; direction: string; method: string; paid_at: string; status: string }[];
  subscriptions: { id: number; plan_name: string | null; quantity: number; status: string; next_billing_date: string | null; quote_id: number | null }[];
  alerts: { id: number; quote_id: number; alert_type: string; severity: string; status: string; message: string; created_at: string }[];
  activity: { id: number; action: string; user: string; reason: string | null; quote_id: number | null; timestamp: string }[];
  totals: Record<string, number>;
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: string;
  team: string | null;
  customer_id: number | null;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string | null;
}

export interface Warehouse {
  id: number;
  code: string | null;
  name: string;
  shipping_cost_weight: number;
  city: string | null;
  country: string | null;
  is_active: boolean;
  sku_count: number;
  units_on_hand: number;
}

export interface Stock {
  id: number;
  warehouse_id: number;
  warehouse_name: string;
  product_id: number;
  product_name: string;
  sku: string | null;
  quantity_on_hand: number;
  quantity_reserved: number;
  quantity_available: number;
  reorder_point: number;
  needs_replenishment: boolean;
  updated_at: string | null;
}

export interface Movement {
  id: number;
  warehouse_id: number;
  warehouse_name: string;
  product_id: number;
  product_name: string;
  movement_type: string;
  quantity: number;
  on_hand_after: number;
  reserved_after: number;
  reference_type: string | null;
  reference_id: number | null;
  note: string | null;
  created_at: string;
}

export interface Split {
  id: number;
  quote_line_id: number;
  product_id: number;
  product_name: string;
  warehouse_id: number | null;
  warehouse_name: string | null;
  quantity_fulfilled: number;
  is_backorder: boolean;
  status: string;
  shipment_id: number | null;
  expected_date: string | null;
  warning: string | null;
}

export interface Shipment {
  id: number;
  shipment_number: string;
  warehouse_id: number;
  warehouse_name: string;
  status: string;
  promised_date: string | null;
  expected_date: string | null;
  shipped_at: string | null;
  delivered_at: string | null;
  tracking_reference: string | null;
  units: number;
}

export interface FulfillmentPlan {
  id: number;
  quote_id: number;
  status: string;
  splits: Split[];
  shipments: Shipment[];
  backorder_summary: string[];
  total_shipments: number;
  units_reserved: number;
  units_shipped: number;
  units_backordered: number;
  expected_delivery_date: string | null;
  available_actions: string[];
}

export interface FulfillmentListItem {
  quote_id: number;
  quote_number: string | null;
  order_number: string | null;
  customer_name: string;
  owner_name: string | null;
  quote_status: string;
  fulfillment_status: string;
  plan_status: string | null;
  total: number;
  promised_delivery_date: string | null;
  expected_delivery_date: string | null;
  confirmed_at: string | null;
  units_backordered: number;
  shipment_count: number;
}

export interface Backorder {
  split_id: number;
  quote_id: number;
  quote_number: string | null;
  order_number: string | null;
  customer_name: string;
  product_id: number;
  product_name: string;
  sku: string | null;
  quantity: number;
  expected_date: string | null;
  available_now: number;
  can_consolidate: boolean;
  promised_delivery_date: string | null;
}

export interface BillingEvent {
  id: number;
  subscription_id: number;
  event_type: string;
  amount: number;
  description: string;
  event_date: string;
  invoice_id: number | null;
  applied_to_invoice_id: number | null;
}

export interface Subscription {
  id: number;
  quote_line_id: number;
  quote_id: number | null;
  quote_number: string | null;
  customer_id: number | null;
  customer_name: string | null;
  subscription_plan_id: number;
  plan_name: string;
  product_name: string;
  interval: string;
  quantity: number;
  unit_price: number;
  cycle_amount: number;
  status: string;
  start_date: string | null;
  current_cycle_start: string;
  current_cycle_end: string;
  next_billing_date: string | null;
  cancelled_at: string | null;
  paused_at: string | null;
}

export interface SubscriptionDetail extends Subscription {
  billing_events: BillingEvent[];
  invoices: InvoiceBrief[];
  available_actions: string[];
}

export interface InvoiceBrief {
  id: number;
  invoice_number: string;
  status: string;
  amount: number;
  amount_paid: number;
  due_date: string;
  issued_at?: string;
  billing_period_start?: string | null;
  billing_period_end?: string | null;
}

export interface BillingSummary {
  quote_id: number;
  billing_status: string;
  one_time_lines: { quote_line_id: number; product_id: number; product_name: string; quantity: number; discount_pct: number; line_value: number; line_total: number }[];
  recurring_lines: { quote_line_id: number; product_id: number; product_name: string; subscription_id: number; subscription_plan_id: number; plan_name: string; quantity: number; status: string; current_cycle_start: string; current_cycle_end: string; next_billing_date: string | null; billing_events: BillingEvent[] }[];
  invoices: InvoiceBrief[];
}

export interface Invoice {
  id: number;
  invoice_number: string;
  quote_id: number;
  quote_number: string | null;
  order_number: string | null;
  customer_id: number | null;
  customer_name: string;
  subscription_id: number | null;
  invoice_type: string;
  status: string;
  currency: string;
  subtotal: number;
  discount_total: number;
  tax_total: number;
  amount: number;
  amount_paid: number;
  outstanding: number;
  due_date: string;
  issued_at: string;
  paid_at: string | null;
  is_overdue: boolean;
  days_overdue: number;
  billing_period_start: string | null;
  billing_period_end: string | null;
}

export interface Payment {
  id: number;
  payment_number: string | null;
  invoice_id: number;
  invoice_number?: string | null;
  customer_name?: string | null;
  direction: string;
  amount: number;
  method: string;
  reference: string | null;
  status: string;
  provider: string;
  provider_reference: string | null;
  paid_at: string;
  recorded_by: string;
  notes: string | null;
}

export interface InvoiceDetail extends Invoice {
  voided_at: string | null;
  void_reason: string | null;
  notes: string | null;
  pipeline_stage: string;
  lines: { id: number; quote_line_id: number | null; description: string; quantity: number; unit_price: number; discount_pct: number; tax_rate_pct: number; line_total: number; tax_amount: number }[];
  payments: Payment[];
  one_time_lines: BillingSummary["one_time_lines"];
  recurring_lines: BillingSummary["recurring_lines"];
  available_actions: string[];
}

export interface Alert {
  id: number;
  quote_id: number;
  quote_number: string | null;
  customer_name: string;
  owner_name: string | null;
  quote_status: string;
  alert_type: string;
  severity: "info" | "warning" | "critical";
  message: string;
  status: "open" | "acknowledged" | "resolved";
  details: Record<string, unknown> | null;
  created_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
  link: string;
  available_actions: string[];
}

export interface AlertDetail extends Alert {
  actions: { id: number; action_type: string; actor_label: string; note: string | null; recipients: string[] | null; created_at: string }[];
}

export interface Notification {
  id: number;
  type: string;
  title: string;
  body: string | null;
  entity_type: string | null;
  entity_id: number | null;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

export interface DashboardSummary {
  period_days: number;
  role: string;
  kpis: Record<string, number>;
  recent_activity: { id: number; quote_id: number | null; quote_number: string | null; customer_name: string | null; user: string; action: string; reason: string | null; timestamp: string }[];
}

export interface Suggestion {
  product_id: number;
  name: string;
  sku: string | null;
  price: number;
  price_impact: number;
  unit_margin_pct: number;
  margin_delta_if_added: number;
  is_promoted: boolean;
  promotion_label: string | null;
  reason: string;
  stock_available: number | null;
  in_stock: boolean;
  co_purchase_score: number;
}

export interface SearchResults {
  customers: { id: number; name: string; code: string | null; tier: string; link: string }[];
  quotes: { id: number; quote_number: string | null; customer_name: string; status: string; total: number; link: string }[];
  orders: { id: number; order_number: string; customer_name: string; fulfillment_status: string; total: number; link: string }[];
  products: { id: number; name: string; sku: string | null; category: string; price: number; link: string }[];
  invoices: { id: number; invoice_number: string; customer_name: string; status: string; amount: number; link: string }[];
  subscriptions: { id: number; plan_name: string; customer_name: string | null; status: string; link: string }[];
}

export interface ReportResult {
  summary: Record<string, number>;
  rows: Record<string, unknown>[];
  columns: string[];
  filters: string;
  by_status?: { status: string; count: number; value?: number; paid?: number }[];
  by_month?: { month: string; quotes: number; value: number; won_value: number }[];
  by_rep?: Record<string, unknown>[];
  by_customer?: Record<string, unknown>[];
  by_category?: Record<string, unknown>[];
  by_type?: Record<string, unknown>[];
}

export interface Setting {
  key: string;
  value: string | number | boolean;
  value_type: string;
  default: string | number | boolean;
  description: string;
  updated_at: string | null;
}

export interface EmailMessage {
  id: number;
  to_address: string;
  subject: string;
  body_text: string;
  template: string;
  status: string;
  provider: string;
  error: string | null;
  entity_type: string | null;
  entity_id: number | null;
  created_at: string;
}

// ---- portal ----

export interface PortalComment {
  id: number;
  quote_line_id: number;
  author_type: string;
  author_name: string;
  comment: string;
  created_at: string;
}

export interface PortalLine {
  id: number;
  product_id: number;
  product_name: string;
  description: string | null;
  sku: string | null;
  quantity: number;
  unit_price: number;
  discount_pct: number;
  line_value: number;
  line_total: number;
  tax_rate_pct: number;
  is_recurring: boolean;
  billing_interval: string | null;
  comments: PortalComment[];
}

export interface PortalQuote {
  quote_id: number;
  quote_number: string | null;
  status: string;
  customer_name: string;
  rep_name: string | null;
  currency: string;
  subtotal: number;
  discount_total: number;
  tax_total: number;
  total: number;
  order_discount_pct: number;
  valid_until: string | null;
  promised_delivery_date: string | null;
  order_number: string | null;
  can_confirm: boolean;
  can_negotiate: boolean;
  pending_review: boolean;
  lines: PortalLine[];
  history: { id: number; status: string; message: string | null; proposed_lines: unknown; created_at: string; resolved_at: string | null }[];
}

export interface PortalQuoteSummary {
  quote_id: number;
  quote_number: string | null;
  status: string;
  total: number;
  currency: string;
  valid_until: string | null;
  created_at: string | null;
  order_number: string | null;
}
