import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn(), token: vi.fn() }));
vi.mock("@/lib/api/client", () => ({
  createApiClient: (token: string) => {
    mocks.token(token);
    return { GET: mocks.GET, POST: mocks.POST };
  },
}));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "operator-token" }));

import { previewOperatorArtwork, searchOperatorOptions } from "./queue-options";

const CAMPAIGN = "11111111-1111-4111-8111-111111111111";
const DRIVER = "22222222-2222-4222-8222-222222222222";
const FILE = "33333333-3333-4333-8333-333333333333";
const UNAVAILABLE = { items: [], total: 0, error: "Selection list is unavailable. Try again." };

describe("searchOperatorOptions", () => {
  beforeEach(() => vi.resetAllMocks());

  it("rejects malformed searches before reading any list", async () => {
    expect(await searchOperatorOptions({ kind: "driver", q: "x".repeat(121), offset: 0 })).toEqual({
      items: [],
      total: 0,
      error: "Select a valid search.",
    });
    expect(
      await searchOperatorOptions({ kind: "vehicle", q: "", offset: 0, parentId: "not-a-uuid" }),
    ).toEqual({ items: [], total: 0, error: "Select a valid search." });
    expect(await searchOperatorOptions({ kind: "campaign", q: "", offset: -25 })).toEqual({
      items: [],
      total: 0,
      error: "Select a valid search.",
    });
    expect(mocks.GET).not.toHaveBeenCalled();
  });

  it("lists campaigns and marks only approved, scheduled or active campaigns selectable", async () => {
    mocks.GET.mockResolvedValue({
      data: {
        total: 60,
        items: [
          { id: "aaaaaaaa-0000-4000-8000-000000000001", name: "Approved", status: "approved" },
          { id: "bbbbbbbb-0000-4000-8000-000000000002", name: "Scheduled", status: "scheduled" },
          { id: "cccccccc-0000-4000-8000-000000000003", name: "Live", status: "active" },
          { id: "dddddddd-0000-4000-8000-000000000004", name: "Draft", status: "draft" },
        ],
      },
    });
    const result = await searchOperatorOptions({ kind: "campaign", q: "rain", offset: 25 });
    expect(mocks.token).toHaveBeenCalledWith("operator-token");
    expect(mocks.GET).toHaveBeenCalledExactlyOnceWith("/api/v1/admin/campaigns", {
      params: { query: { q: "rain", limit: 25, offset: 25 } },
    });
    expect(result.total).toBe(60);
    expect(result.items.map((i) => [i.label, i.detail, i.unavailable])).toEqual([
      ["Approved", "approved · aaaaaaaa", undefined],
      ["Scheduled", "scheduled · bbbbbbbb", undefined],
      ["Live", "active · cccccccc", undefined],
      ["Draft", "draft · dddddddd", "Campaign approval required"],
    ]);
  });

  it("lists drivers with their city and blocks drivers that are not active", async () => {
    mocks.GET.mockResolvedValue({
      data: {
        total: 2,
        items: [
          {
            id: DRIVER,
            full_name: "Ada Active",
            email: "ada@example.test",
            service_city: "Lagos",
            onboarding_status: "active",
          },
          {
            id: "44444444-4444-4444-8444-444444444444",
            full_name: "Pending Pat",
            email: "pat@example.test",
            service_city: null,
            onboarding_status: "pending",
          },
        ],
      },
    });
    const result = await searchOperatorOptions({ kind: "driver", q: "a", offset: 0 });
    expect(mocks.GET).toHaveBeenCalledWith("/api/v1/admin/drivers", {
      params: { query: { q: "a", limit: 25, offset: 0 } },
    });
    expect(result.items).toEqual([
      {
        id: DRIVER,
        label: "Ada Active",
        detail: "ada@example.test · Lagos",
        unavailable: undefined,
      },
      {
        id: "44444444-4444-4444-8444-444444444444",
        label: "Pending Pat",
        detail: "pat@example.test · No city",
        unavailable: "Driver pending",
      },
    ]);
  });

  it("requires a driver before listing vehicles and allows only active cars", async () => {
    expect(await searchOperatorOptions({ kind: "vehicle", q: "", offset: 0 })).toEqual({
      items: [],
      total: 0,
      error: "Select a driver first.",
    });
    expect(mocks.GET).not.toHaveBeenCalled();
    mocks.GET.mockResolvedValue({
      data: {
        total: 3,
        items: [
          {
            id: "v1",
            plate_number: "CAR-001",
            make: "Toyota",
            model: "Corolla",
            status: "active",
            vehicle_type: "car",
          },
          {
            id: "v2",
            plate_number: "BIKE-002",
            make: null,
            model: "Okada",
            status: "active",
            vehicle_type: "motorcycle",
          },
          {
            id: "v3",
            plate_number: "CAR-003",
            make: "Honda",
            model: null,
            status: "suspended",
            vehicle_type: "car",
          },
        ],
      },
    });
    const result = await searchOperatorOptions({
      kind: "vehicle",
      q: "CAR",
      offset: 0,
      parentId: DRIVER,
    });
    expect(mocks.GET).toHaveBeenCalledWith("/api/v1/admin/vehicles", {
      params: { query: { q: "CAR", limit: 25, offset: 0, driver_profile_id: DRIVER } },
    });
    expect(result.items.map((i) => [i.label, i.detail, i.unavailable])).toEqual([
      ["CAR-001", "Toyota · Corolla · active", undefined],
      ["BIKE-002", "Okada · active", "An active approved car is required"],
      ["CAR-003", "Honda · suspended", "An active approved car is required"],
    ]);
  });

  it("requires a campaign before listing creatives and allows only approved scan-clean artwork", async () => {
    expect(await searchOperatorOptions({ kind: "creative", q: "", offset: 0 })).toEqual({
      items: [],
      total: 0,
      error: "Select a campaign first.",
    });
    expect(mocks.GET).not.toHaveBeenCalled();
    mocks.GET.mockResolvedValue({
      data: {
        total: 3,
        items: [
          {
            id: "eeeeeeee-0000-4000-8000-000000000001",
            name: "Clean art",
            placement: "rear_window",
            status: "approved",
            scan_status: "clean",
            stored_file_id: FILE,
          },
          {
            id: "ffffffff-0000-4000-8000-000000000002",
            name: "Scanning art",
            placement: "side_panel",
            status: "approved",
            scan_status: "pending",
            stored_file_id: null,
          },
          {
            id: "99999999-0000-4000-8000-000000000003",
            name: "Rejected art",
            placement: "side_panel",
            status: "rejected",
            scan_status: "clean",
            stored_file_id: null,
          },
        ],
      },
    });
    const result = await searchOperatorOptions({
      kind: "creative",
      q: "ignored",
      offset: 50,
      parentId: CAMPAIGN,
    });
    expect(mocks.GET).toHaveBeenCalledWith("/api/v1/admin/campaigns/{campaign_id}/creatives", {
      params: { path: { campaign_id: CAMPAIGN }, query: { limit: 25, offset: 50 } },
    });
    expect(result).toEqual({
      total: 3,
      items: [
        {
          id: "eeeeeeee-0000-4000-8000-000000000001",
          label: "Clean art",
          detail: "rear_window · approved · eeeeeeee",
          fileId: FILE,
          unavailable: undefined,
        },
        {
          id: "ffffffff-0000-4000-8000-000000000002",
          label: "Scanning art",
          detail: "side_panel · approved · ffffffff",
          fileId: undefined,
          unavailable: "Approved, scan-clean artwork is required",
        },
        {
          id: "99999999-0000-4000-8000-000000000003",
          label: "Rejected art",
          detail: "side_panel · rejected · 99999999",
          fileId: undefined,
          unavailable: "Approved, scan-clean artwork is required",
        },
      ],
    });
  });

  it.each([
    ["campaign", undefined],
    ["driver", undefined],
    ["vehicle", DRIVER],
    ["creative", CAMPAIGN],
  ] as const)("reports %s lists without a response body as unavailable", async (kind, parentId) => {
    mocks.GET.mockResolvedValue({ data: undefined });
    expect(await searchOperatorOptions({ kind, q: "", offset: 0, parentId })).toEqual(UNAVAILABLE);
  });

  it("does not expose upstream failure details", async () => {
    mocks.GET.mockRejectedValue(new Error("internal host db-01 refused"));
    const result = await searchOperatorOptions({ kind: "driver", q: "", offset: 0 });
    expect(result).toEqual(UNAVAILABLE);
    expect(JSON.stringify(result)).not.toMatch(/db-01/);
  });
});

describe("previewOperatorArtwork", () => {
  beforeEach(() => vi.resetAllMocks());

  it("refuses a malformed file reference without requesting a download", async () => {
    expect(await previewOperatorArtwork("../etc/passwd")).toEqual({
      error: "Select current artwork.",
    });
    expect(mocks.POST).not.toHaveBeenCalled();
  });

  it("requests an audited creative-review download for the exact file", async () => {
    mocks.POST.mockResolvedValue({ data: { url: "https://files.example.test/art.png" } });
    expect(await previewOperatorArtwork(FILE)).toEqual({
      url: "https://files.example.test/art.png",
    });
    expect(mocks.POST).toHaveBeenCalledExactlyOnceWith("/api/v1/admin/files/{file_id}/download", {
      params: { path: { file_id: FILE } },
      body: { purpose: "creative_review", reason: "Assignment artwork selection" },
    });
  });

  it("returns no URL when the download is not authorized", async () => {
    mocks.POST.mockResolvedValue({ data: undefined });
    expect(await previewOperatorArtwork(FILE)).toEqual({ url: undefined });
  });

  it("explains that eligibility is rechecked when the preview fails", async () => {
    mocks.POST.mockRejectedValue(new Error("scanner offline"));
    expect(await previewOperatorArtwork(FILE)).toEqual({
      error:
        "Artwork preview is unavailable. Approval and file safety are rechecked when offering.",
    });
  });
});
