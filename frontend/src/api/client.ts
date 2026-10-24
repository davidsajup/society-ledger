// One small fetch wrapper for the whole app.
//  - Same-origin requests: the browser sends the session cookie by itself.
//  - Session auth means writes need a CSRF token. We fetch it once, send it as X-CSRFToken, and
//    forget it after login/logout because Django rotates it then.

export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(status: number, data: unknown) {
    super(messageFrom(data) ?? `Request failed (${status})`);
    this.status = status;
    this.data = data;
  }

  /** Field-level messages from a 400, e.g. { amount: ["Exceeds the amount owed (70.00)."] }. */
  fieldError(field: string): string | undefined {
    return this.fieldErrors()[field];
  }

  /**
   * Every message in the response, keyed by field, whatever shape DRF used:
   *   { amount: ["too big"] } | { amount: "too big" } | ["not allowed"] | { detail: "..." }.
   * A bare list (no field) becomes `non_field_errors`, so nothing is ever dropped silently.
   */
  fieldErrors(): Record<string, string> {
    const data = this.data;
    if (Array.isArray(data)) return data.length ? { non_field_errors: String(data[0]) } : {};
    if (data && typeof data === "object") {
      const out: Record<string, string> = {};
      for (const [key, value] of Object.entries(data as Record<string, unknown>)) {
        const first = Array.isArray(value) ? value[0] : value;
        if (first !== undefined && first !== null) out[key] = String(first);
      }
      if (Object.keys(out).length) return out;
    }
    return { detail: this.message };
  }
}

/** Errors for a form: field-keyed from the API, or one general message for anything else. */
export function formErrors(error: unknown, fallback: string): Record<string, string> {
  return error instanceof ApiError ? error.fieldErrors() : { detail: fallback };
}

/** The message to show above a form: any error that does not belong to one of its inputs. */
export function generalError(
  errors: Record<string, string>,
  inputs: string[],
): string | undefined {
  const entry = Object.entries(errors).find(([key]) => !inputs.includes(key));
  return entry?.[1];
}

function messageFrom(data: unknown): string | undefined {
  if (!data || typeof data !== "object") return undefined;
  const record = data as Record<string, unknown>;
  if (typeof record.detail === "string") return record.detail;
  const first = Object.values(record)[0];
  if (Array.isArray(first) && first.length) return String(first[0]);
  return typeof first === "string" ? first : undefined;
}

let csrfToken: string | null = null;

export function forgetCsrfToken() {
  csrfToken = null;
}

async function getCsrfToken(): Promise<string> {
  if (!csrfToken) {
    const response = await fetch("/api/auth/csrf/", { credentials: "same-origin" });
    csrfToken = ((await response.json()) as { csrfToken: string }).csrfToken;
  }
  return csrfToken;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT";
  body?: unknown;
  headers?: Record<string, string>;
}

async function send(path: string, options: RequestOptions, retry: boolean): Promise<Response> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
  // A file upload is multipart: the browser must set Content-Type itself (it adds the boundary).
  const isUpload = options.body instanceof FormData;
  if (options.body !== undefined && !isUpload) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRFToken"] = await getCsrfToken();

  const response = await fetch(`/api${path}`, {
    method,
    headers,
    credentials: "same-origin",
    body:
      options.body === undefined
        ? undefined
        : isUpload
          ? (options.body as FormData)
          : JSON.stringify(options.body),
  });

  // A stale CSRF token (after a session change) is the one 403 worth retrying, exactly once.
  if (response.status === 403 && retry && method !== "GET") {
    const text = await response.clone().text();
    if (text.includes("CSRF")) {
      forgetCsrfToken();
      return send(path, options, false);
    }
  }
  return response;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await send(path, options, true);
  const text = await response.text();
  const data = text ? (JSON.parse(text) as unknown) : null;
  if (!response.ok) throw new ApiError(response.status, data);
  return data as T;
}
