import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const redirect = vi.hoisted(() =>
  vi.fn((path: string) => {
    throw new Error(`redirect:${path}`);
  }),
);
vi.mock("next/navigation", () => ({ redirect }));
import { loadAdvertiserPageData } from "./page-data";

describe("advertiser page data", () => {
  beforeEach(() => {
    redirect.mockClear();
  });
  it.each([undefined, null])(
    "does not treat missing response data %s as an empty success",
    async (data) => {
      expect(await loadAdvertiserPageData(async () => ({ data }))).toEqual({
        available: false,
        reason: "protocol",
      });
    },
  );
  it.each([{ data: [] }, { data: { items: [] } }, { data: 0 }, { data: false }])(
    "preserves actual successful data $data",
    async ({ data }) => {
      expect(await loadAdvertiserPageData(async () => ({ data }))).toEqual({
        available: true,
        data,
      });
    },
  );
  it.each([
    [503, "PRIVACY_LIVE_USE_BLOCKED", "gated"],
    [403, "PRIVACY_LIVE_USE_BLOCKED", "gated"],
    [403, "FORBIDDEN", "forbidden"],
    [404, "NOT_FOUND", "missing"],
    [429, "RATE_LIMITED", "operational"],
    [503, "PROVIDER_UNAVAILABLE", "operational"],
  ])("classifies HTTP%s %s without leaking internals", async (status, code, reason) => {
    expect(
      await loadAdvertiserPageData(async () => {
        throw new ApiError(status as number, { code: code as string, message: "Private detail" });
      }),
    ).toEqual({ available: false, reason });
  });
  it.each([
    [400, "BAD_REQUEST"],
    [409, "CONFLICT"],
    [422, "VALIDATION_ERROR"],
  ])("rethrows non-transient HTTP%s %s instead of offering a retry", async (status, code) => {
    const error = new ApiError(status as number, { code: code as string, message: "Private" });
    await expect(
      loadAdvertiserPageData(async () => {
        throw error;
      }),
    ).rejects.toBe(error);
  });
  it("redirects every 401 before classifying even a gate-shaped error", async () => {
    await expect(
      loadAdvertiserPageData(async () => {
        throw new ApiError(401, { code: "PRIVACY_LIVE_USE_BLOCKED", message: "Private" });
      }),
    ).rejects.toThrow("redirect:/login");
    expect(redirect).toHaveBeenCalledWith("/login");
  });
  it.each(["fetch failed", "Failed to fetch", "NetworkError when attempting to fetch resource."])(
    "handles the fetch network failure %s",
    async (message) => {
      expect(
        await loadAdvertiserPageData(async () => {
          throw new TypeError(message);
        }),
      ).toEqual({ available: false, reason: "operational" });
    },
  );
  it.each([
    new TypeError("Cannot read properties of undefined"),
    new Error("Unexpected implementation failure"),
    new Error("fetch failed"),
    new TypeError("fetch failed to map an invalid field"),
  ])("rethrows unexpected errors %s", async (error) => {
    await expect(
      loadAdvertiserPageData(async () => {
        throw error;
      }),
    ).rejects.toBe(error);
  });
});
