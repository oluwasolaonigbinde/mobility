/**
 * The backend returns expected errors in a standard envelope:
 *   { "error": { "code": "...", "message": "...", "details": {...}, "request_id": "..." } }
 * This module gives the rest of the app one typed way to consume it.
 */

export interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    request_id?: string;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: Record<string, unknown>;
  readonly requestId?: string;

  constructor(status: number, envelope: ApiErrorEnvelope["error"]) {
    super(envelope.message);
    this.name = "ApiError";
    this.status = status;
    this.code = envelope.code;
    this.details = envelope.details;
    this.requestId = envelope.request_id;
  }

  get isAuthError(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }
}

function isEnvelope(body: unknown): body is ApiErrorEnvelope {
  return (
    typeof body === "object" &&
    body !== null &&
    "error" in body &&
    typeof (body as ApiErrorEnvelope).error === "object" &&
    (body as ApiErrorEnvelope).error !== null &&
    typeof (body as ApiErrorEnvelope).error.message === "string"
  );
}

/** Normalize any failed response body into an ApiError. */
export function toApiError(status: number, body: unknown): ApiError {
  if (isEnvelope(body)) {
    return new ApiError(status, body.error);
  }
  // FastAPI validation errors (422) arrive as {detail: [...]} — normalize them too.
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    return new ApiError(status, {
      code: "VALIDATION_ERROR",
      message: typeof detail === "string" ? detail : "Request validation failed",
      details: typeof detail === "object" && detail !== null ? { detail } : undefined,
    });
  }
  return new ApiError(status, {
    code: "UNEXPECTED_ERROR",
    message: `Request failed with status ${status}`,
  });
}
