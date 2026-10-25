import { afterEach, describe, expect, it, vi } from "vitest";
import { notFound, redirect } from "next/navigation";
import { ApiError } from "./errors";
import { adminReadFailure, adminValueFailure } from "./admin-read";

afterEach(() => vi.restoreAllMocks());

describe("scoped admin reads", () => {
  it.each([403, 404, 422, 500])(
    "marks %s unavailable without raw text, zero balances or an empty result",
    (status) => {
      const log = vi.spyOn(console, "warn").mockImplementation(() => undefined);
      expect(
        adminReadFailure(new ApiError(status, { code: "PRIVATE", message: "secret NIN bank" })),
      ).toEqual({ data: undefined });
      expect(JSON.stringify(log.mock.calls)).not.toMatch(/secret|NIN|bank|PRIVATE/);
    },
  );

  it("preserves framework redirect/notFound signals and redirects expired authority", () => {
    for (const operation of [() => redirect("/login"), () => notFound()]) {
      let signal: unknown;
      try {
        operation();
      } catch (error) {
        signal = error;
      }
      expect(() => adminValueFailure(signal)).toThrow(signal as Error);
    }
    expect(() =>
      adminValueFailure(new ApiError(401, { code: "SESSION_ENDED", message: "private" })),
    ).toThrow(/NEXT_REDIRECT/);
  });

  it("retains successful concurrent panels while transport failure stays unavailable", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const reads = await Promise.all([
      Promise.resolve({ data: { balance: "17.25" } }).catch(adminReadFailure),
      Promise.reject(new TypeError("private transport URL")).catch(adminReadFailure),
      Promise.resolve({ data: { items: [], total: 0 } }).catch(adminReadFailure),
    ]);
    expect(reads).toEqual([
      { data: { balance: "17.25" } },
      { data: undefined },
      { data: { items: [], total: 0 } },
    ]);
  });
});
