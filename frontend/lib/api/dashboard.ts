import { apiGet } from "./client";
import type { QuoteHealth } from "./types";

export const getDealHealth = () => apiGet<QuoteHealth[]>("/dashboard/deal-health");
