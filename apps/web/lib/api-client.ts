// Every call to the API goes through here. The session is a cookie the browser
// sends by itself; nothing about it is kept in script-readable storage.

export const API_BASE = "/api";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    // The machine-readable reason, when the API gives one ("duplicate_paper", "invalid_key").
    readonly code: string | null = null,
    readonly body: unknown = null,
  ) {
    super(message);
  }
}

/** Reads the reason out of an error body. The API uses three shapes for `detail`. */
export function errorFrom(status: number, body: unknown): ApiError {
  const record = (body ?? {}) as Record<string, unknown>;
  const detail = record.detail;
  let message = `The request failed (${status}).`;
  let code = typeof record.code === "string" ? record.code : null;
  if (typeof detail === "string") {
    message = detail;
  } else if (Array.isArray(detail)) {
    // Validation: one entry per field that was refused.
    const first = detail[0] as { loc?: unknown[]; msg?: string } | undefined;
    if (first?.msg) {
      const field = first.loc?.at(-1);
      message = typeof field === "string" ? `${field}: ${first.msg}` : first.msg;
    }
  } else if (detail && typeof detail === "object") {
    const inner = detail as { code?: string; message?: string };
    message = inner.message ?? message;
    code = inner.code ?? code;
  }
  return new ApiError(status, message, code, body);
}

function leaveForLogin() {
  const path = window.location.pathname;
  if (path !== "/login" && path !== "/register") {
    window.location.assign("/login");
  }
}

type Options = Omit<RequestInit, "body"> & { json?: unknown };

export async function api<T>(path: string, { json, ...init }: Options = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      credentials: "include",
      headers: json === undefined ? init.headers : { "Content-Type": "application/json", ...init.headers },
      body: json === undefined ? undefined : JSON.stringify(json),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "Couldn't reach the server. Check your connection and try again.", "network");
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    // Signing in with a wrong password is also a 401; that one stays on the page.
    if (response.status === 401 && !path.startsWith("/auth/")) leaveForLogin();
    throw errorFrom(response.status, body);
  }
  return body as T;
}

export function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong.";
}
