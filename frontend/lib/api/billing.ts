import { apiGet, apiPatch, apiPost } from "./client";
import type { BillingSummary, SubscriptionWithEvent } from "./types";

export const getBillingSummary = (quoteId: number) =>
  apiGet<BillingSummary>(`/quotes/${quoteId}/billing-summary`);

export const changeSubscriptionQuantity = (
  subscriptionId: number,
  payload: { new_quantity: number; change_date: string },
) => apiPatch<SubscriptionWithEvent>(`/subscriptions/${subscriptionId}/quantity`, payload);

export const cancelSubscription = (subscriptionId: number, payload: { cancellation_date: string }) =>
  apiPost<SubscriptionWithEvent>(`/subscriptions/${subscriptionId}/cancel`, payload);

export const advanceSubscriptionCycle = (subscriptionId: number) =>
  apiPost<SubscriptionWithEvent>(`/subscriptions/${subscriptionId}/advance-cycle`);
