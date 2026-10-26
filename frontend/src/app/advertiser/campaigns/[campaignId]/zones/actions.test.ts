import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import type { ZoneGeometry } from "@/lib/zones/geometry";
const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  patch: vi.fn(),
  remove: vi.fn(),
  revalidate: vi.fn(),
}));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidate }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));
vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({ POST: mocks.post, PATCH: mocks.patch, DELETE: mocks.remove }),
}));
import { createZoneAction, updateZoneAction, deleteZoneAction } from "./actions";
const campaignId = "00000000-0000-4000-8000-000000000001";
const zoneId = "00000000-0000-4000-8000-000000000002";
const zone = { id: zoneId, campaign_id: campaignId };
const geometry: ZoneGeometry = {
  type: "Polygon",
  coordinates: [
    [
      [7.4, 9],
      [7.5, 9],
      [7.5, 9.1],
      [7.4, 9],
    ],
  ],
};
beforeEach(() => {
  vi.resetAllMocks();
  mocks.post.mockResolvedValue({ data: zone });
  mocks.patch.mockResolvedValue({ data: zone });
  mocks.remove.mockResolvedValue({});
});
it("returns a confirmed own-campaign area and refreshes wizard and campaign areas", async () => {
  expect(
    await createZoneAction({ campaignId, name: " Wuse ", zoneType: "target", geometry }),
  ).toEqual({ zone });
  expect(mocks.post).toHaveBeenCalledWith("/api/v1/advertiser/campaigns/{campaign_id}/zones", {
    params: { path: { campaign_id: campaignId } },
    body: { name: "Wuse", zone_type: "target", geometry },
  });
  expect(mocks.revalidate).toHaveBeenCalledWith("/advertiser/campaigns/new");
});
it.each([undefined, { id: zoneId, campaign_id: zoneId }, { id: "bad", campaign_id: campaignId }])(
  "does not claim an incomplete or foreign create result",
  async (data) => {
    mocks.post.mockResolvedValue({ data });
    expect(
      await createZoneAction({ campaignId, name: "Wuse", zoneType: "target", geometry }),
    ).toMatchObject({ unknownOutcome: true });
    expect(mocks.revalidate).not.toHaveBeenCalled();
  },
);
it("marks a lost creation response unknown without automatic redispatch", async () => {
  mocks.post.mockRejectedValue(new Error("lost"));
  expect(
    await createZoneAction({ campaignId, name: "Wuse", zoneType: "target", geometry }),
  ).toHaveProperty("unknownOutcome", true);
  expect(mocks.post).toHaveBeenCalledTimes(1);
});
it("does not turn a definite backend refusal into a successful area", async () => {
  mocks.post.mockRejectedValue(new ApiError(403, { code: "FORBIDDEN", message: "Not permitted" }));
  const state = await createZoneAction({ campaignId, name: "Wuse", zoneType: "target", geometry });
  expect(state.error).toBeTruthy();
  expect(state.zone).toBeUndefined();
});
it("checks updated zone identity and campaign membership", async () => {
  mocks.patch.mockResolvedValue({ data: { ...zone, id: campaignId } });
  expect(
    await updateZoneAction({ campaignId, zoneId, name: "New name", zoneType: "target" }),
  ).toHaveProperty("unknownOutcome", true);
});
it("keeps the authorised route in a confirmed delete", async () => {
  expect(await deleteZoneAction({ campaignId, zoneId })).toEqual({});
  expect(mocks.remove).toHaveBeenCalledWith(
    "/api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}",
    { params: { path: { campaign_id: campaignId, zone_id: zoneId } } },
  );
});
