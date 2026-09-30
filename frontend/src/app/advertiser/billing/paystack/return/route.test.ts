import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  session: vi.fn(async () => "session-token"),
}));

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: mocks.session }));

import { GET } from "./route";

const REFERENCE = "cv-synthetic-checkout-0001";

function request(query: string): NextRequest {
  return new NextRequest(`https://cardvert.example/advertiser/billing/paystack/return?${query}`);
}

describe("Paystack return route", () => {
  beforeEach(() => vi.clearAllMocks());

  it.each(["reference=bad%20reference", `reference=${REFERENCE}&trxref=cv-other-reference`])(
    "rejects an invalid provider reference without verification: %s",
    async (query) => {
      const response = await GET(request(query));
      const destination = new URL(response.headers.get("location")!);

      expect(destination.pathname).toBe("/advertiser/billing");
      expect(destination.searchParams.get("payment")).toBe("error");
      expect(destination.searchParams.get("message")).toBe(
        "Paystack returned an invalid payment reference.",
      );
      expect(mocks.post).not.toHaveBeenCalled();
    },
  );

  it.each([
    ["confirmed", "confirmed"],
    ["failed", "failed"],
    ["initialized", "pending"],
  ])("maps verified status %s to %s", async (status, expected) => {
    mocks.post.mockResolvedValueOnce({ data: { status } });

    const response = await GET(request(`reference=${REFERENCE}&trxref=${REFERENCE}`));
    const destination = new URL(response.headers.get("location")!);

    expect(destination.searchParams.get("payment")).toBe(expected);
    expect(destination.searchParams.has("message")).toBe(false);
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/advertiser/payment-checkouts/{reference}/verify",
      { params: { path: { reference: REFERENCE } } },
    );
  });

  it("treats a not-final provider response as pending", async () => {
    mocks.post.mockRejectedValueOnce(
      new ApiError(409, { code: "PAYMENT_NOT_FINAL", message: "private provider detail" }),
    );

    const response = await GET(request(`reference=${REFERENCE}`));
    const destination = new URL(response.headers.get("location")!);

    expect(destination.searchParams.get("payment")).toBe("pending");
    expect(destination.searchParams.has("message")).toBe(false);
  });

  it("reports a safe retry message when verification is unavailable", async () => {
    mocks.post.mockRejectedValueOnce(new Error("private upstream detail"));

    const response = await GET(request(`reference=${REFERENCE}`));
    const destination = new URL(response.headers.get("location")!);

    expect(destination.searchParams.get("payment")).toBe("error");
    expect(destination.searchParams.get("message")).toBe(
      "Cardvert could not verify this payment yet. No unverified payment was applied.",
    );
  });
});
