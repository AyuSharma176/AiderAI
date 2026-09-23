import type { ApiErrorBody } from "./types";
import { clearSession, getAccessToken } from "../auth/storage";

export const API_URL = import.meta.env.VITE_API_URL ?? "/api/v1";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly requestId?: string,
  ) {
    super(message);
  }
}

export async function authenticatedFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (response.status === 401 && token) {
    clearSession();
    window.dispatchEvent(new Event("supportai:unauthorized"));
  }
  return response;
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await authenticatedFetch(path, { ...init, headers });
  if (!response.ok) {
    let body: ApiErrorBody = { code: "request_failed", message: "Request failed" };
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // Use the stable fallback without exposing response content.
    }
    throw new ApiError(response.status, body.code, body.message, body.request_id);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
