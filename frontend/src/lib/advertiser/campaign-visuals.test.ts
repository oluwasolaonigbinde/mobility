import { expect, it, vi } from "vitest";
import type { ApiClient } from "@/lib/api/client";
import { loadCampaignAreas, previewFile } from "./campaign-visuals";
it("loads every area before drawing a campaign boundary", async () => {
  const get = vi
    .fn()
    .mockResolvedValueOnce({ data: { items: [{ id: "one" }], total: 2 } })
    .mockResolvedValueOnce({ data: { items: [{ id: "two" }], total: 2 } });
  const result = await loadCampaignAreas({ GET: get } as unknown as ApiClient, "campaign");
  expect(result.available && result.data.items.map((item) => item.id)).toEqual(["one", "two"]);
  expect(get).toHaveBeenLastCalledWith("/api/v1/advertiser/campaigns/{campaign_id}/zones", {
    params: {
      path: { campaign_id: "campaign" },
      query: { zone_type: "target", limit: 100, offset: 1 },
    },
  });
});
it("withholds a partial map if pagination changes or repeats", async () => {
  const get = vi.fn().mockResolvedValue({ data: { items: [{ id: "one" }], total: 2 } });
  expect(await loadCampaignAreas({ GET: get } as unknown as ApiClient, "campaign")).toEqual({
    available: false,
    reason: "protocol",
  });
});
it("prefers approved clean managed artwork to a newer draft or unsafe file", () => {
  const image = {
    creative_type: "image",
    asset_source: "managed_file",
    scan_status: "clean",
    status: "draft",
    stored_file_id: "draft",
  };
  expect(
    previewFile([
      image,
      { ...image, status: "approved", stored_file_id: "approved" },
      { ...image, status: "approved", scan_status: "pending", stored_file_id: "unsafe" },
    ]),
  ).toBe("approved");
});
