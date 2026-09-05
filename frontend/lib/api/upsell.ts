import { apiGet, apiPost } from "./client";
import type { AddSuggestionResponse, MarginSummary, RankedSuggestion } from "./types";

export const getMarginSummary = (quoteId: number) =>
  apiGet<MarginSummary>(`/quotes/${quoteId}/margin-summary`);

export const getUpsellSuggestions = (
  quoteId: number,
  options?: { limit?: number; minMarginPctThreshold?: number },
) =>
  apiGet<RankedSuggestion[]>(`/quotes/${quoteId}/upsell-suggestions`, {
    limit: options?.limit,
    min_margin_pct_threshold: options?.minMarginPctThreshold,
  });

export const addSuggestion = (
  quoteId: number,
  lineId: number,
  payload: { product_id: number; quantity?: number },
) => apiPost<AddSuggestionResponse>(`/quotes/${quoteId}/lines/${lineId}/add-suggestion`, payload);
