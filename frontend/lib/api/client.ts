const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// FastAPI's default error body is `{ detail: string }`, but the built-in
// Pydantic validation error path (422s) instead sends
// `{ detail: [{ type, loc, msg, input }, ...] }`. Both are handled here so
// every caller gets a single readable message either way.
type FastApiValidationError = {
  type: string;
  loc: (string | number)[];
  msg: string;
  input?: unknown;
};

type FastApiErrorBody = {
  detail?: string | FastApiValidationError[];
};

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

function extractErrorMessage(body: unknown, fallback: string): string {
  const detail = (body as FastApiErrorBody | null)?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail.map((error) => `${error.loc?.join(".")}: ${error.msg}`).join("; ");
  }

  return fallback;
}

export type ApiFetchOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
};

function buildUrl(path: string, query?: ApiFetchOptions["query"]): string {
  const url = new URL(path, API_BASE_URL);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { body, query, headers, ...rest } = options;

  const response = await fetch(buildUrl(path, query), {
    ...rest,
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  // 204/empty responses (none currently in this API, but guard anyway).
  const text = await response.text();
  const parsed: unknown = text ? JSON.parse(text) : null;

  if (!response.ok) {
    throw new ApiError(
      extractErrorMessage(parsed, `Request to ${path} failed with status ${response.status}`),
      response.status,
      parsed,
    );
  }

  return parsed as T;
}

export const apiGet = <T>(path: string, query?: ApiFetchOptions["query"]) =>
  apiFetch<T>(path, { method: "GET", query });

export const apiPost = <T>(path: string, body?: unknown) =>
  apiFetch<T>(path, { method: "POST", body });

export const apiPatch = <T>(path: string, body?: unknown) =>
  apiFetch<T>(path, { method: "PATCH", body });
