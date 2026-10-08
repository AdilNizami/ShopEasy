import type { ApiErrorBody } from "./types";

const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  code?: string;
  correlationId?: string;
  retryable?: boolean;
  constructor(message: string, status: number, body?: ApiErrorBody) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = body?.error?.code;
    this.correlationId = body?.error?.correlationId;
    this.retryable = body?.error?.retryable;
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = typeof window === "undefined" ? null : window.sessionStorage.getItem("shopeasy.accessToken");
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!headers.has("X-Correlation-ID")) headers.set("X-Correlation-ID", crypto.randomUUID());
  let response: Response;
  try {
    response = await fetch(`${apiBase}/v1${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    throw new ApiError("We couldn’t reach ShopEasy. Check your connection and try again.", 0);
  }
  if (!response.ok) {
    let body: ApiErrorBody | undefined;
    try { body = await response.json() as ApiErrorBody; } catch { /* response may not contain JSON */ }
    const messages: Record<number, string> = {
      400: "That request could not be understood. Please review the details and try again.",
      401: "Your session has expired. Please sign in again.",
      404: "We couldn’t find that item. It may have moved or been removed.",
      409: "This action conflicts with the latest order or stock status. Refresh and try again.",
      422: "Some details need attention. Check the form and try again.",
      429: "You’re moving a little quickly. Wait a moment and try again.",
      502: "A service returned an unexpected response. Please try again shortly.",
      503: "This service is temporarily unavailable. Please try again shortly.",
      504: "The request took too long. Check your order before trying checkout again.",
    };
    const message = body?.error?.message || messages[response.status] || "Something went wrong. Please try again.";
    if (response.status === 401 && token && typeof window !== "undefined") {
      window.sessionStorage.removeItem("shopeasy.accessToken");
      window.dispatchEvent(new Event("shopeasy:unauthorized"));
    }
    throw new ApiError(message, response.status, body);
  }
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

export function money(value: { amount: string | number; currency: string } | null | undefined): string {
  if (!value) return "—";
  const amount = Number(value.amount);
  if (!Number.isFinite(amount)) return `${value.currency} ${value.amount}`;
  try { return new Intl.NumberFormat(undefined, { style: "currency", currency: value.currency }).format(amount); }
  catch { return `${value.currency} ${amount.toFixed(2)}`; }
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
