import { apiGet, apiPatch, apiPost } from "./client";
import type { FulfillmentPlan, Warehouse } from "./types";

export const listWarehouses = () => apiGet<Warehouse[]>("/warehouses");

export const getFulfillment = (quoteId: number) =>
  apiGet<FulfillmentPlan>(`/quotes/${quoteId}/fulfillment`);

export const suggestFulfillment = (quoteId: number) =>
  apiPost<FulfillmentPlan>(`/quotes/${quoteId}/fulfillment/suggest`);

export const confirmFulfillment = (quoteId: number) =>
  apiPost<FulfillmentPlan>(`/quotes/${quoteId}/fulfillment/confirm`);

export const overrideFulfillment = (
  quoteId: number,
  allocations: { quote_line_id: number; warehouse_id: number; quantity_fulfilled: number }[],
) => apiPatch<FulfillmentPlan>(`/quotes/${quoteId}/fulfillment/override`, { allocations });
