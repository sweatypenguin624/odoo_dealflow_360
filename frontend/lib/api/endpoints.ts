import { apiDelete, apiDownload, apiGet, apiPatch, apiPost, apiPut, apiFetch, type Query } from "./client";
import type * as T from "./types";

export const quotes = {
  list: (q: Query) => apiGet<T.Page<T.QuoteListItem>>("/quotes", q),
  get: (id: number) => apiGet<T.QuoteDetail>(`/quotes/${id}`),
  create: (body: unknown) => apiPost<T.QuoteDetail>("/quotes", body),
  update: (id: number, body: unknown) => apiPatch<T.QuoteDetail>(`/quotes/${id}`, body),
  addLine: (id: number, body: unknown) => apiPost<T.QuoteDetail>(`/quotes/${id}/lines`, body),
  updateLine: (id: number, lineId: number, body: unknown) => apiPatch<T.QuoteLine>(`/quotes/${id}/lines/${lineId}`, body),
  deleteLine: (id: number, lineId: number) => apiDelete<T.QuoteDetail>(`/quotes/${id}/lines/${lineId}`),
  risk: (id: number) => apiGet<T.RiskResult>(`/quotes/${id}/risk`),
  submit: (id: number) => apiPost<{ quote: T.QuoteDetail; risk_result: T.RiskResult }>(`/quotes/${id}/submit`),
  approvalAction: (id: number, body: { action: string; note?: string }) => apiPost<{ quote: T.QuoteDetail; history: T.ApprovalAction[] }>(`/quotes/${id}/approval-action`, body),
  history: (id: number) => apiGet<{ approval_actions: T.ApprovalAction[]; audit_logs: T.AuditEntry[]; requests: T.ApprovalRequest[] }>(`/quotes/${id}/approval-history`),
  revisions: (id: number) => apiGet<{ id: number; version: number; reason: string | null; created_at: string; snapshot: unknown }[]>(`/quotes/${id}/revisions`),
  send: (id: number) => apiPost<{ quote: T.QuoteDetail; portal_url: string; token_expires_at: string; email_status: string; email_to: string | null }>(`/quotes/${id}/send`),
  confirm: (id: number, reason?: string) => apiPost<T.QuoteDetail>(`/quotes/${id}/confirm`, { reason }),
  revise: (id: number, reason?: string) => apiPost<T.QuoteDetail>(`/quotes/${id}/revise`, { reason }),
  cancel: (id: number, reason?: string) => apiPost<T.QuoteDetail>(`/quotes/${id}/cancel`, { reason }),
  negotiation: (id: number) => apiGet<{ comments: T.LineComment[]; counter_proposals: T.CounterProposal[] }>(`/quotes/${id}/negotiation`),
  comment: (id: number, lineId: number, body: { comment: string; is_internal?: boolean }) => apiPost<T.LineComment>(`/quotes/${id}/lines/${lineId}/comments`, body),
  suggestions: (id: number) => apiGet<T.Suggestion[]>(`/quotes/${id}/upsell-suggestions`),
  addSuggestion: (id: number, body: { product_id: number; quantity?: number }) => apiPost<{ quote: T.QuoteDetail }>(`/quotes/${id}/upsell/add`, body),
  billingSummary: (id: number) => apiGet<T.BillingSummary>(`/quotes/${id}/billing-summary`),
};

export const approvals = { queue: (q: Query) => apiGet<T.Page<T.ApprovalQueueItem>>("/approvals", q) };

export const customers = {
  list: (q: Query) => apiGet<T.Page<T.Customer>>("/customers", q),
  get: (id: number) => apiGet<T.CustomerDetail>(`/customers/${id}`),
  create: (body: unknown) => apiPost<T.CustomerDetail>("/customers", body),
  update: (id: number, body: unknown) => apiPatch<T.CustomerDetail>(`/customers/${id}`, body),
  archive: (id: number) => apiPost<T.CustomerDetail>(`/customers/${id}/archive`),
  restore: (id: number) => apiPost<T.CustomerDetail>(`/customers/${id}/restore`),
  history: (id: number) => apiGet<T.CustomerHistory>(`/customers/${id}/history`),
};

export const catalog = {
  products: (q: Query) => apiGet<T.Page<T.Product>>("/products", q),
  product: (id: number) => apiGet<T.ProductDetail>(`/products/${id}`),
  pricing: (id: number, q: Query) => apiGet<T.ProductPricing>(`/products/${id}/pricing`, q),
  createProduct: (body: unknown) => apiPost<T.Product>("/products", body),
  updateProduct: (id: number, body: unknown) => apiPatch<T.Product>(`/products/${id}`, body),
  archiveProduct: (id: number) => apiPost<T.Product>(`/products/${id}/archive`),
  restoreProduct: (id: number) => apiPost<T.Product>(`/products/${id}/restore`),
  createVariant: (productId: number, body: unknown) => apiPost<T.Variant>(`/products/${productId}/variants`, body),
  updateVariant: (id: number, body: unknown) => apiPatch<T.Variant>(`/variants/${id}`, body),
  categories: (q: Query = {}) => apiGet<T.Page<T.Category>>("/categories", q),
  createCategory: (body: unknown) => apiPost<T.Category>("/categories", body),
  updateCategory: (id: number, body: unknown) => apiPatch<T.Category>(`/categories/${id}`, body),
  tiers: (includeInactive = false) => apiGet<T.Tier[]>("/customer-tiers", { include_inactive: includeInactive }),
  createTier: (body: unknown) => apiPost<T.Tier>("/customer-tiers", body),
  updateTier: (id: number, body: unknown) => apiPatch<T.Tier>(`/customer-tiers/${id}`, body),
  plans: (q: Query = {}) => apiGet<T.Page<T.SubscriptionPlan>>("/subscription-plans", q),
  createPlan: (body: unknown) => apiPost<T.SubscriptionPlan>("/subscription-plans", body),
  updatePlan: (id: number, body: unknown) => apiPatch<T.SubscriptionPlan>(`/subscription-plans/${id}`, body),
  pairings: (q: Query = {}) => apiGet<T.Page<T.Pairing>>("/product-pairings", q),
  createPairing: (body: unknown) => apiPost<T.Pairing>("/product-pairings", body),
  updatePairing: (id: number, body: unknown) => apiPatch<T.Pairing>(`/product-pairings/${id}`, body),
  deletePairing: (id: number) => apiDelete<void>(`/product-pairings/${id}`),
};

export const pricing = {
  priceLists: (q: Query = {}) => apiGet<T.Page<T.PriceList>>("/price-lists", q),
  priceList: (id: number) => apiGet<T.PriceList & { items: T.PriceListItem[] }>(`/price-lists/${id}`),
  createPriceList: (body: unknown) => apiPost<T.PriceList>("/price-lists", body),
  updatePriceList: (id: number, body: unknown) => apiPatch<T.PriceList>(`/price-lists/${id}`, body),
  addItem: (id: number, body: unknown) => apiPost<T.PriceListItem>(`/price-lists/${id}/items`, body),
  deleteItem: (id: number, itemId: number) => apiDelete<void>(`/price-lists/${id}/items/${itemId}`),
  discountRules: (q: Query = {}) => apiGet<T.Page<T.DiscountRule>>("/discount-rules", q),
  createDiscountRule: (body: unknown) => apiPost<T.DiscountRule>("/discount-rules", body),
  updateDiscountRule: (id: number, body: unknown) => apiPatch<T.DiscountRule>(`/discount-rules/${id}`, body),
  deleteDiscountRule: (id: number) => apiDelete<void>(`/discount-rules/${id}`),
  approvalRules: () => apiGet<T.ApprovalRule[]>("/approval-rules"),
  policy: () => apiGet<{ manager_threshold: number; finance_threshold: number; manager_excess_amount: number | null; finance_excess_amount: number | null }>("/approval-rules/policy"),
  createApprovalRule: (body: unknown) => apiPost<T.ApprovalRule>("/approval-rules", body),
  updateApprovalRule: (id: number, body: unknown) => apiPatch<T.ApprovalRule>(`/approval-rules/${id}`, body),
  deleteApprovalRule: (id: number) => apiDelete<void>(`/approval-rules/${id}`),
};

export const users = {
  list: (q: Query) => apiGet<T.Page<T.User>>("/users", q),
  reps: () => apiGet<T.User[]>("/users/reps"),
  create: (body: unknown) => apiPost<T.User>("/users", body),
  update: (id: number, body: unknown) => apiPatch<T.User>(`/users/${id}`, body),
};

export const settings = {
  list: () => apiGet<T.Setting[]>("/settings"),
  update: (key: string, value: unknown) => apiPut<T.Setting>(`/settings/${key}`, { value }),
};

export const audit = {
  list: (q: Query) => apiGet<T.Page<T.AuditEntry>>("/audit-logs", q),
  emails: (q: Query) => apiGet<T.Page<T.EmailMessage>>("/emails", q),
};

export const inventory = {
  warehouses: (q: Query = {}) => apiGet<T.Page<T.Warehouse>>("/warehouses", q),
  createWarehouse: (body: unknown) => apiPost<T.Warehouse>("/warehouses", body),
  updateWarehouse: (id: number, body: unknown) => apiPatch<T.Warehouse>(`/warehouses/${id}`, body),
  stock: (q: Query) => apiGet<T.Page<T.Stock>>("/inventory", q),
  receive: (warehouseId: number, body: unknown) => apiPost<T.Stock>(`/warehouses/${warehouseId}/receipts`, body),
  adjust: (warehouseId: number, body: unknown) => apiPost<T.Stock>(`/warehouses/${warehouseId}/adjustments`, body),
  movements: (q: Query) => apiGet<T.Page<T.Movement>>("/inventory/movements", q),
};

export const fulfillment = {
  list: (q: Query) => apiGet<T.Page<T.FulfillmentListItem>>("/fulfillment", q),
  backorders: (q: Query) => apiGet<T.Page<T.Backorder>>("/fulfillment/backorders", q),
  plan: (quoteId: number) => apiGet<T.FulfillmentPlan>(`/quotes/${quoteId}/fulfillment`),
  suggest: (quoteId: number) => apiPost<T.FulfillmentPlan>(`/quotes/${quoteId}/fulfillment/suggest`),
  confirm: (quoteId: number) => apiPost<T.FulfillmentPlan>(`/quotes/${quoteId}/fulfillment/confirm`),
  override: (quoteId: number, body: unknown) => apiPatch<T.FulfillmentPlan>(`/quotes/${quoteId}/fulfillment/override`, body),
  ship: (quoteId: number, body: unknown = {}) => apiPost<T.FulfillmentPlan>(`/quotes/${quoteId}/fulfillment/ship`, body),
  deliver: (quoteId: number, shipmentId: number) => apiPost<T.FulfillmentPlan>(`/quotes/${quoteId}/fulfillment/shipments/${shipmentId}/deliver`, {}),
  consolidate: (quoteId: number) => apiPost<{ plan: T.FulfillmentPlan; units_reserved: number; units_still_backordered: number }>(`/quotes/${quoteId}/fulfillment/consolidate-backorders`),
  release: (quoteId: number, reason?: string) => apiPost<T.FulfillmentPlan>(`/quotes/${quoteId}/fulfillment/release`, undefined, { reason }),
};

export const subscriptions = {
  list: (q: Query) => apiGet<T.Page<T.Subscription>>("/subscriptions", q),
  get: (id: number) => apiGet<T.SubscriptionDetail>(`/subscriptions/${id}`),
  changeQuantity: (id: number, body: { new_quantity: number; change_date: string }) => apiPatch<{ subscription: T.Subscription; billing_event: T.BillingEvent }>(`/subscriptions/${id}/quantity`, body),
  cancel: (id: number, body: { cancellation_date: string; reason?: string }) => apiPost<{ subscription: T.Subscription; billing_event: T.BillingEvent }>(`/subscriptions/${id}/cancel`, body),
  pause: (id: number) => apiPost<T.SubscriptionDetail>(`/subscriptions/${id}/pause`),
  resume: (id: number) => apiPost<T.SubscriptionDetail>(`/subscriptions/${id}/resume`),
  advance: (id: number) => apiPost<{ subscription: T.Subscription; billing_event: T.BillingEvent; invoice: T.InvoiceBrief | null }>(`/subscriptions/${id}/advance-cycle`),
  runBilling: (as_of?: string) => apiPost<{ as_of: string; invoices_created: number; invoice_numbers: string[]; already_billed: number; overdue_marked: number }>("/billing/run", { as_of }),
};

export const invoices = {
  list: (q: Query) => apiGet<T.Page<T.Invoice>>("/invoices", q),
  get: (id: number) => apiGet<T.InvoiceDetail>(`/invoices/${id}`),
  generate: (quoteId: number) => apiPost<T.Invoice>(`/quotes/${quoteId}/invoices/generate`),
  generateRecurring: (subscriptionId: number) => apiPost<T.Invoice>(`/subscriptions/${subscriptionId}/invoices/generate`),
  pay: (id: number, body: unknown, idempotencyKey: string) => apiFetch<T.InvoiceDetail>(`/invoices/${id}/payments`, { method: "POST", body, headers: { "Idempotency-Key": idempotencyKey } }),
  refund: (id: number, body: unknown) => apiPost<T.InvoiceDetail>(`/invoices/${id}/refunds`, body),
  void: (id: number, reason: string) => apiPost<T.InvoiceDetail>(`/invoices/${id}/void`, { reason }),
  payments: (q: Query) => apiGet<T.Page<T.Payment>>("/payments", q),
};

export const dealHealth = {
  alerts: (q: Query) => apiGet<T.Page<T.Alert>>("/deal-health/alerts", q),
  alert: (id: number) => apiGet<T.AlertDetail>(`/deal-health/alerts/${id}`),
  act: (id: number, body: { action_type: string; note?: string }) => apiPost<T.AlertDetail>(`/deal-health/alerts/${id}/actions`, body),
  summary: () => apiGet<{ open: number; by_type: Record<string, number>; by_severity: Record<string, number> }>("/deal-health/summary"),
  run: () => apiPost<{ created: number; updated: number; resolved: number; open: number }>("/deal-health/run", {}),
};

export const dashboard = { summary: (period_days = 30) => apiGet<T.DashboardSummary>("/dashboard/summary", { period_days }) };

export const notifications = {
  list: (q: Query) => apiGet<T.Page<T.Notification>>("/notifications", q),
  unreadCount: () => apiGet<{ unread: number }>("/notifications/unread-count"),
  markRead: (ids?: number[]) => apiPost<{ marked: number }>("/notifications/mark-read", { ids }),
};

export const reports = {
  list: () => apiGet<{ name: string; title: string }[]>("/reports"),
  run: (name: string, q: Query) => apiGet<T.ReportResult>(`/reports/${name}`, q),
  exportFile: (name: string, format: string, q: Query) => apiDownload(`/reports/${name}/export`, { ...q, format }),
};

export const search = { global: (q: string) => apiGet<T.SearchResults>("/search", { q }) };
