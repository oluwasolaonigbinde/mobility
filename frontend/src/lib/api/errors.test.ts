import { describe, expect, it } from "vitest";
import { ApiError, toApiError } from "./errors";

describe("toApiError", () => {
  it("parses the backend error envelope", () => {
    const err = toApiError(403, {
      error: {
        code: "FORBIDDEN_ROLE",
        message: "Admin role required",
        details: { required: "admin" },
        request_id: "req-123",
      },
    });
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(403);
    expect(err.code).toBe("FORBIDDEN_ROLE");
    expect(err.message).toBe("Admin role required");
    expect(err.details).toEqual({ required: "admin" });
    expect(err.requestId).toBe("req-123");
    expect(err.isForbidden).toBe(true);
    expect(err.isAuthError).toBe(false);
  });

  it("normalizes FastAPI 422 validation bodies", () => {
    const err = toApiError(422, { detail: [{ loc: ["body", "email"], msg: "invalid" }] });
    expect(err.code).toBe("VALIDATION_ERROR");
    expect(err.status).toBe(422);
  });

  it("falls back safely on unknown bodies", () => {
    for (const body of [undefined, null, "oops", 42, { random: true }]) {
      const err = toApiError(500, body);
      expect(err.code).toBe("UNEXPECTED_ERROR");
      expect(err.status).toBe(500);
    }
  });

  it("flags 401 as auth errors", () => {
    expect(toApiError(401, undefined).isAuthError).toBe(true);
  });
});
