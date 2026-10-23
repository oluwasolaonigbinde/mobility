import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({ get: vi.fn(), token: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: mocks.token }));
import { GET } from "./route";
const campaignId = "00000000-0000-4000-8000-000000000001";
const creativeId = "00000000-0000-4000-8000-000000000002";
const context = { params: Promise.resolve({ campaignId, creativeId }) };
beforeEach(() => {
  vi.clearAllMocks();
  mocks.token.mockResolvedValue("session");
  mocks.get.mockResolvedValue({ data: new TextEncoder().encode("<svg/>").buffer });
});
it("authorizes each download and serves the bounded code privately", async () => {
  const response = await GET(new Request("http://localhost/qr?download=1"), context);
  expect(response.status).toBe(200);
  expect(response.headers.get("content-type")).toBe("image/svg+xml");
  expect(response.headers.get("content-disposition")).toContain("attachment");
  expect(response.headers.get("cache-control")).toBe("private, no-store");
  expect(response.headers.get("content-security-policy")).toContain("sandbox");
  expect(mocks.get).toHaveBeenCalledWith(
    "/api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}/qr.svg",
    {
      params: { path: { campaign_id: campaignId, creative_id: creativeId } },
      parseAs: "arrayBuffer",
    },
  );
  expect(await response.text()).toBe("<svg/>");
});
it("does not call the API for a signed-out or malformed request", async () => {
  mocks.token.mockResolvedValue(undefined);
  expect((await GET(new Request("http://localhost/qr"), context)).status).toBe(401);
  expect(
    (
      await GET(new Request("http://localhost/qr"), {
        params: Promise.resolve({ campaignId: "bad", creativeId }),
      })
    ).status,
  ).toBe(404);
  expect(mocks.get).not.toHaveBeenCalled();
});
it.each([401, 403, 404, 409])(
  "preserves safe authorization and unavailable-link status %s",
  async (status) => {
    mocks.get.mockRejectedValue(
      new ApiError(status, { code: "DENIED", message: "Private detail" }),
    );
    const response = await GET(new Request("http://localhost/qr"), context);
    expect(response.status).toBe(status);
    expect(await response.text()).toBe("");
    expect(response.headers.get("cache-control")).toBe("private, no-store");
  },
);
it("rejects an unexpectedly large QR response", async () => {
  mocks.get.mockResolvedValue({ data: new ArrayBuffer(200_001) });
  expect((await GET(new Request("http://localhost/qr"), context)).status).toBe(503);
});
