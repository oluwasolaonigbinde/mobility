import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./errors";
import { publicActionError } from "./public-action-error";
import { notFound, redirect } from "next/navigation";

afterEach(() => vi.restoreAllMocks());

describe("public action errors", () => {
  it.each<Readonly<Record<string, string>>>([{}, { OTHER: "Other message" }])(
    "uses shared busy copy with local allowlists",
    (messages) => {
      expect(
        publicActionError(
          new ApiError(503, { code: "TRY_AGAIN_SOON", message: "private" }),
          messages,
          "Custom fallback",
        ),
      ).toBe("This page is busy. Try again in a moment.");
    },
  );
  it.each([401, 403, 404, 422, 500])(
    "never forwards arbitrary %s backend text or details",
    (status) => {
      const log = vi.spyOn(console, "warn").mockImplementation(() => undefined);
      const error = new ApiError(status, {
        code: "UNKNOWN_PRIVATE_CODE",
        message: "secret bank 0123456789 https://private.test/?token=abc",
        details: { token: "private", latitude: 9.0765 },
      });
      expect(publicActionError(error, {}, "Please try again.")).toBe("Please try again.");
      expect(JSON.stringify(log.mock.calls)).not.toMatch(/secret|bank|token|latitude|private/);
    },
  );

  it("uses only approved own code-specific copy, including known server failures", () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const messages = { STALE: "Refresh this record before trying again." };
    expect(
      publicActionError(
        new ApiError(409, { code: "STALE", message: "private" }),
        messages,
        "Retry.",
      ),
    ).toBe(messages.STALE);
    expect(
      publicActionError(
        new ApiError(500, { code: "STALE", message: "private" }),
        messages,
        "Retry.",
      ),
    ).toBe(messages.STALE);
    expect(
      publicActionError(
        new ApiError(422, { code: "constructor", message: "private" }),
        messages,
        "Retry.",
      ),
    ).toBe("Retry.");
    expect(publicActionError(new TypeError("private transport URL"), messages, "Retry.")).toBe(
      "Retry.",
    );
  });

  it("preserves framework navigation signals", () => {
    for (const operation of [() => redirect("/login"), () => notFound()]) {
      let signal: unknown;
      try {
        operation();
      } catch (error) {
        signal = error;
      }
      expect(() => publicActionError(signal)).toThrow(signal as Error);
    }
  });
});

it("uses fixed invite copy for the disabled-email code", () => {
  expect(
    publicActionError(new ApiError(503, { code: "EMAIL_NOT_CONFIGURED", message: "untrusted" })),
  ).toBe("Emails aren't connected yet, so this invite can't be sent.");
});

it("gives staff plain vehicle approval guidance instead of raw server text", () => {
  expect(
    publicActionError(
      new ApiError(409, { code: "VEHICLE_APPROVAL_REQUIRED", message: "raw internal detail" }),
    ),
  ).toBe(
    "Use the car document review to approve this car. Expired or rejected documents need a fresh submission.",
  );
});
