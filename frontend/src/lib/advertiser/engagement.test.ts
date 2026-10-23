import { expect, it, vi } from "vitest";
import type { ApiClient } from "@/lib/api/client";
import { loadLivePositions } from "./engagement";

it("accepts only the owning campaign's delayed coordinates at the client boundary", async () => {
  const data = {
    campaign_id: "one",
    delay_minutes: 15,
    positions: [{ longitude: 7.4, latitude: 9.1, vehicle_id: "private" }],
  };
  const api = { GET: vi.fn().mockResolvedValue({ data }) } as unknown as ApiClient;
  expect(await loadLivePositions(api, "one")).toEqual({
    available: true,
    data: {
      campaign_id: "one",
      delay_minutes: 15,
      positions: [{ longitude: 7.4, latitude: 9.1 }],
    },
  });
});
it.each([
  { campaign_id: "other", delay_minutes: 15, positions: [] },
  { campaign_id: "one", delay_minutes: 0, positions: [] },
  { campaign_id: "one", delay_minutes: 15 },
  { campaign_id: "one", delay_minutes: 15, positions: [null] },
  { campaign_id: "one", delay_minutes: 15, positions: [{ longitude: 200, latitude: 9 }] },
  { campaign_id: "one", delay_minutes: 15, positions: [{ longitude: 7, latitude: NaN }] },
])("does not render malformed or another campaign's positions", async (data) => {
  const api = { GET: vi.fn().mockResolvedValue({ data }) } as unknown as ApiClient;
  expect(await loadLivePositions(api, "one")).toEqual({ available: false, reason: "protocol" });
});
