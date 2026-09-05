import { apiGet, apiPost } from "./client";
import type { Invoice, InvoiceDetail, InvoiceListItem, InvoiceStatusValue } from "./types";

export const listInvoices = (status?: InvoiceStatusValue) =>
  apiGet<InvoiceListItem[]>("/invoices", status ? { status } : undefined);

export const getInvoice = (invoiceId: number) => apiGet<InvoiceDetail>(`/invoices/${invoiceId}`);

export const generateQuoteInvoice = (quoteId: number) =>
  apiPost<Invoice>(`/quotes/${quoteId}/invoices/generate`);

export const generateRecurringInvoice = (subscriptionId: number) =>
  apiPost<Invoice>(`/subscriptions/${subscriptionId}/invoices/generate`);

export const recordPayment = (
  invoiceId: number,
  payload: { amount: number; method: string; recorded_by: string },
) => apiPost<InvoiceDetail>(`/invoices/${invoiceId}/payments`, payload);
