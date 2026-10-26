import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({ put: vi.fn(), role: vi.fn(), refresh: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ PUT: mocks.put }) }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.role }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));
vi.mock("next/cache", () => ({ revalidatePath: mocks.refresh }));
import { saveArtworkWebsite } from "./website-actions";
const campaignId = "00000000-0000-4000-8000-000000000001",
  creativeId = "00000000-0000-4000-8000-000000000002";
function form(destination = "https://example.com/menu") {
  const data = new FormData();
  data.set("campaign_id", campaignId);
  data.set("creative_id", creativeId);
  data.set("destination", destination);
  return data;
}
beforeEach(() => {
  vi.clearAllMocks();
  mocks.put.mockResolvedValue({
    data: { creative_id: creativeId, short_path: "/q/" + "a".repeat(32) },
  });
});
it("requires advertiser access, saves just the artwork link and revalidates its campaign", async () => {
  expect(await saveArtworkWebsite({}, form())).toEqual({ done: "Website link saved." });
  expect(mocks.role).toHaveBeenCalledWith("advertiser");
  expect(mocks.put).toHaveBeenCalledWith(
    "/api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}/website",
    {
      params: { path: { campaign_id: campaignId, creative_id: creativeId } },
      body: { destination: "https://example.com/menu" },
    },
  );
  expect(mocks.refresh).toHaveBeenCalledWith(`/advertiser/campaigns/${campaignId}`);
});
it("keeps a failed or unconfirmed write distinct from success without exposing raw errors", async () => {
  mocks.put.mockRejectedValue(
    new ApiError(422, { code: "VALIDATION_ERROR", message: "private data" }),
  );
  expect(await saveArtworkWebsite({}, form("http://example.com"))).toEqual({
    error: "Enter a public https website link without a sign-in or custom port.",
  });
  expect(mocks.refresh).not.toHaveBeenCalled();
  mocks.put.mockResolvedValue({ data: { creative_id: "other", short_path: "/q/other" } });
  expect(await saveArtworkWebsite({}, form())).toHaveProperty("error");
});
