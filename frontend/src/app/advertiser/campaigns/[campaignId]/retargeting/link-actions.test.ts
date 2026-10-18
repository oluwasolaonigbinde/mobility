import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({ GET: mocks.get, POST: mocks.post }),
}));
import { createSourceAction, createSourceLinkAction, removeSourceLinkAction } from "./actions";
const CAMPAIGN = "00000000-0000-4000-8000-000000000002",
  ZONE = "00000000-0000-4000-8000-000000000003",
  LINK = "00000000-0000-4000-8000-000000000004",
  KEY = "00000000-0000-4000-8000-000000000044";
function data() {
  const form = new FormData();
  for (const [key, value] of Object.entries({
    operation_key: KEY,
    campaign_id: CAMPAIGN,
    zone_id: ZONE,
    source_id: "00000000-0000-4000-8000-000000000001",
    start_at: "2026-09-01T10:00",
    end_at: "2026-09-02T10:00",
    source_type: "manual-insight",
    category: "area-demand",
    confidence: "high",
    expires_at: "2027-09-01T10:00",
  }))
    form.set(key, value);
  return form;
}
beforeEach(() => {
  vi.clearAllMocks();
  mocks.post.mockResolvedValue({ data: { id: LINK } });
  mocks.get.mockImplementation(async (path: string) =>
    path.endsWith("/zones/{zone_id}")
      ? { data: { id: ZONE, campaign_id: CAMPAIGN, zone_type: "target" } }
      : path.endsWith("/retargeting-source-links/{link_id}")
        ? { data: { id: LINK, campaign_id: CAMPAIGN } }
        : { data: { id: CAMPAIGN } },
  );
});
it("creates only a link in the bound owned campaign and normalises Nigeria time", async () => {
  expect(await createSourceLinkAction(CAMPAIGN, {}, data())).toMatchObject({
    success: "Audience linked to the campaign area.",
    operationKey: KEY,
  });
  expect(mocks.post).toHaveBeenCalledWith(
    "/api/v1/advertiser/retargeting-source-links",
    expect.objectContaining({
      params: { header: { "Idempotency-Key": KEY } },
      body: expect.objectContaining({
        campaign_id: CAMPAIGN,
        zone_id: ZONE,
        start_at: "2026-09-01T09:00:00.000Z",
        end_at: "2026-09-02T09:00:00.000Z",
      }),
    }),
  );
  expect(mocks.revalidatePath).toHaveBeenCalledWith(
    `/advertiser/campaigns/${CAMPAIGN}/retargeting`,
  );
});
it("rejects a second same-company campaign forged into the form", async () => {
  const form = data();
  form.set("campaign_id", "00000000-0000-4000-8000-000000000099");
  expect(await createSourceLinkAction(CAMPAIGN, {}, form)).toHaveProperty("error");
  expect(mocks.post).not.toHaveBeenCalled();
});
it("rejects a zone from another campaign", async () => {
  mocks.get.mockImplementation(async (path: string) =>
    path.endsWith("/zones/{zone_id}")
      ? { data: { id: ZONE, campaign_id: "other", zone_type: "target" } }
      : { data: { id: CAMPAIGN } },
  );
  expect(await createSourceLinkAction(CAMPAIGN, {}, data())).toHaveProperty("error");
  expect(mocks.post).not.toHaveBeenCalled();
});
it("does not remove a link belonging to a different campaign", async () => {
  mocks.get.mockImplementation(async (path: string) =>
    path.endsWith("/retargeting-source-links/{link_id}")
      ? { data: { id: LINK, campaign_id: "other" } }
      : { data: { id: CAMPAIGN } },
  );
  expect(await removeSourceLinkAction(CAMPAIGN, LINK, {}, data())).toHaveProperty("error");
  expect(mocks.post).not.toHaveBeenCalled();
});
it("does not write when the campaign is outside this tenant", async () => {
  mocks.get.mockRejectedValue(
    new ApiError(404, { code: "NOT_FOUND", message: "Campaign not found" }),
  );
  expect(await createSourceLinkAction(CAMPAIGN, {}, data())).toHaveProperty("error");
  expect(await createSourceAction(CAMPAIGN, {}, data())).toHaveProperty("error");
  expect(await removeSourceLinkAction(CAMPAIGN, LINK, {}, data())).toHaveProperty("error");
  expect(mocks.post).not.toHaveBeenCalled();
});
it("keeps retry identity after a response loss", async () => {
  mocks.post
    .mockRejectedValueOnce(new Error("Lost response"))
    .mockResolvedValueOnce({ data: { id: LINK } });
  await createSourceLinkAction(CAMPAIGN, {}, data());
  await createSourceLinkAction(CAMPAIGN, {}, data());
  expect(mocks.post.mock.calls.map((call) => call[1].params.header)).toEqual([
    { "Idempotency-Key": KEY },
    { "Idempotency-Key": KEY },
  ]);
});
it.each(["", "2026-09-01", "2026-13-01T10:00", "2026-09-01T10:00Z"])(
  "rejects invalid dates before writing: %s",
  async (value) => {
    const form = data();
    form.set("start_at", value);
    expect(await createSourceLinkAction(CAMPAIGN, {}, form)).toHaveProperty("error");
    expect(mocks.post).not.toHaveBeenCalled();
  },
);
it("creates an audience in current campaign context without a company-wide stop action", async () => {
  await createSourceAction(CAMPAIGN, {}, data());
  expect(mocks.post).toHaveBeenCalledWith(
    "/api/v1/advertiser/retargeting-sources",
    expect.objectContaining({
      body: expect.objectContaining({ expires_at: "2027-09-01T09:00:00.000Z" }),
    }),
  );
});
