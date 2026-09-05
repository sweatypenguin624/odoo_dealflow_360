import { apiGet, apiPatch, apiPost } from "./client";
import type {
  ApprovalActionResponse,
  ApprovalHistoryResponse,
  ApprovalStep,
  QuoteDetail,
  QuoteListItem,
  QuoteLineDetail,
  QuoteRiskResult,
  SubmitQuoteResponse,
} from "./types";

export const listQuotes = () => apiGet<QuoteListItem[]>("/quotes");

export const getQuote = (quoteId: number) => apiGet<QuoteDetail>(`/quotes/${quoteId}`);

export const getPendingApproval = (step?: ApprovalStep) =>
  apiGet<QuoteListItem[]>("/quotes/pending-approval", step ? { step } : undefined);

export const evaluateQuote = (quoteId: number) =>
  apiPost<QuoteRiskResult>(`/quotes/${quoteId}/evaluate`);

export const submitQuote = (quoteId: number) =>
  apiPost<SubmitQuoteResponse>(`/quotes/${quoteId}/submit`);

export const submitApprovalAction = (
  quoteId: number,
  payload: { actor: string; action: "approved" | "rejected" | "returned_for_revision"; note?: string },
) => apiPost<ApprovalActionResponse>(`/quotes/${quoteId}/approval-action`, payload);

export const getApprovalHistory = (quoteId: number) =>
  apiGet<ApprovalHistoryResponse>(`/quotes/${quoteId}/approval-history`);

export const updateQuoteLine = (
  quoteId: number,
  lineId: number,
  payload: { quantity?: number; discount_pct?: number },
) => apiPatch<QuoteLineDetail>(`/quotes/${quoteId}/lines/${lineId}`, payload);

export const createQuote = (payload: {
  customer_id: number;
  rep_name?: string;
  lines: { product_id: number; quantity: number; discount_pct?: number }[];
}) => apiPost<QuoteDetail>("/quotes", payload);
