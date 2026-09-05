import { apiGet } from "./client";
import type { CustomerRef, ProductRef } from "./types";

export const listProducts = () => apiGet<ProductRef[]>("/products");

export const listCustomers = () => apiGet<CustomerRef[]>("/customers");
