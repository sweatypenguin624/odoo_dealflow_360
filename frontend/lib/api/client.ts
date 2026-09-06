// Single HTTP client for the internal workspace and the portal.
//
// - Sends the httpOnly session cookies (credentials: "include").
// - Adds the double-submit CSRF header on every mutating request.
// - On a 401 it tries one silent refresh (POST /auth/refresh) and replays.
// - Normalises every backend error into ApiError with a human message.

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const CSRF_COOKIE = "df_csrf";
const CSRF_HEADER = "X-CSRF-Token";

export class ApiError extends Error {
  status: number;
  code: string;
  body: unknown;
  errors?: { field: string; message: string }[];

  constructor(message: string, status: number, code = "error", body: unknown = null, errors?: { field: string; message: string }[]) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.body = body;
    this.errors = errors;
  }
}

type ErrorBody = { detail?: string | { loc?: (string | number)[]; msg: string }[]; code?: string; errors?: { field: string; message: string }[] };

const FRIENDLY: Record<number, string> = {
  401: "Your session has expired. Please sign in again.",
  403: "You don't have permission to do that.",
  404: "We couldn't find what you were looking for.",
  409: "This action conflicts with the current state. Refresh and try again.",
  429: "Too many attempts. Please wait a moment and try again.",
  500: "Something went wrong on our side. Please try again.",
};

function messageFrom(body: unknown, status: number): string {
  const detail = (body as ErrorBody | null)?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) return detail.map((e) => `${(e.loc ?? []).filter((p) => p !== "body").join(".")}: ${e.msg}`).join("; ");
  return FRIENDLY[status] ?? `Request failed (${status}).`;
}

export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

export type Query = Record<string, string | number | boolean | undefined | null>;

export function buildUrl(path: string, query?: Query): string {
  const url = new URL(path, API_BASE_URL);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

export type FetchOptions = Omit<RequestInit, "body"> & { body?: unknown; query?: Query; skipRefresh?: boolean; raw?: boolean };

let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (!refreshing) {
    refreshing = fetch(buildUrl("/auth/refresh"), { method: "POST", credentials: "include" })
      .then((r) => r.ok)
      .catch(() => false)
      .finally(() => {
        setTimeout(() => (refreshing = null), 0);
      });
  }
  return refreshing;
}

export let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

export async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { body, query, headers, skipRefresh, raw, ...rest } = options;
  const method = (rest.method ?? "GET").toUpperCase();
  const init: RequestInit = {
    ...rest,
    method,
    credentials: "include",
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(method !== "GET" && method !== "HEAD" ? { [CSRF_HEADER]: readCookie(CSRF_COOKIE) ?? "" } : {}),
      ...(headers as Record<string, string>),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  };

  let response = await fetch(buildUrl(path, query), init);
  if (response.status === 401 && !skipRefresh && !path.startsWith("/auth/") && !path.startsWith("/portal")) {
    const ok = await tryRefresh();
    if (ok) {
      (init.headers as Record<string, string>)[CSRF_HEADER] = readCookie(CSRF_COOKIE) ?? "";
      response = await fetch(buildUrl(path, query), init);
    } else {
      onUnauthorized?.();
    }
  }

  if (raw) {
    if (!response.ok) throw new ApiError(FRIENDLY[response.status] ?? "Download failed", response.status);
    return (await response.blob()) as unknown as T;
  }

  const text = await response.text();
  let parsed: unknown = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = null;
  }
  if (!response.ok) {
    const err = parsed as ErrorBody | null;
    throw new ApiError(messageFrom(parsed, response.status), response.status, err?.code ?? "error", parsed, err?.errors);
  }
  return parsed as T;
}

export const apiGet = <T>(path: string, query?: Query) => apiFetch<T>(path, { method: "GET", query });
export const apiPost = <T>(path: string, body?: unknown, query?: Query) => apiFetch<T>(path, { method: "POST", body, query });
export const apiPatch = <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: "PATCH", body });
export const apiPut = <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: "PUT", body });
export const apiDelete = <T>(path: string) => apiFetch<T>(path, { method: "DELETE" });
export const apiDownload = (path: string, query?: Query) => apiFetch<Blob>(path, { method: "GET", query, raw: true });

export function errorMessage(err: unknown, fallback = "Something went wrong."): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error && err.message === "Failed to fetch") return "Can't reach the server. Check that the API is running.";
  return fallback;
}
