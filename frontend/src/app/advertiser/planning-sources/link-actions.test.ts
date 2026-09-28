import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ post: vi.fn(), revalidatePath: vi.fn() }));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));

import {
  createSourceAction,
  createSourceLinkAction,
  deactivateSourceAction,
  removeSourceLinkAction,
} from "./actions";

const OPERATION_KEY = "00000000-0000-4000-8000-000000000044";

function linkData(operationKey = OPERATION_KEY) {
  const data = new FormData();
  data.set("operation_key", operationKey);
  data.set("source_id", "00000000-0000-4000-8000-000000000001");
  data.set("campaign_id", "00000000-0000-4000-8000-000000000002");
  data.set("zone_id", "00000000-0000-4000-8000-000000000003");
  data.set("start_at", "2026-09-01T10:00");
  data.set("end_at", "2026-09-02T10:00");
  return data;
}

describe("createSourceLinkAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: { id: "link-1" } });
  });

  it("sends only the selected owned resource references and normalized window", async () => {
    const data = linkData();

    await expect(createSourceLinkAction({}, data)).resolves.toEqual({
      success: "Audience connected to the campaign area.",
      operationKey: OPERATION_KEY,
    });
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/advertiser/retargeting-source-links",
      expect.objectContaining({
        params: { header: { "Idempotency-Key": OPERATION_KEY } },
        body: {
          source_id: "00000000-0000-4000-8000-000000000001",
          campaign_id: "00000000-0000-4000-8000-000000000002",
          zone_id: "00000000-0000-4000-8000-000000000003",
          // Entered as Nigeria time (WAT, UTC+1), whatever zone the server runs in.
          start_at: "2026-09-01T09:00:00.000Z",
          end_at: "2026-09-02T09:00:00.000Z",
        },
      }),
    );
  });

  it("reuses one browser operation key after a lost response", async () => {
    mocks.post
      .mockRejectedValueOnce(new Error("response lost"))
      .mockResolvedValueOnce({ data: { id: "link-1" } });
    const data = linkData();

    await expect(createSourceLinkAction({}, data)).resolves.toEqual({
      error: "Could not reach the server.",
      operationKey: OPERATION_KEY,
    });
    await expect(createSourceLinkAction({}, data)).resolves.toEqual({
      success: "Audience connected to the campaign area.",
      operationKey: OPERATION_KEY,
    });

    expect(mocks.post).toHaveBeenCalledTimes(2);
    expect(mocks.post.mock.calls.map((call) => call[1].params.header)).toEqual([
      { "Idempotency-Key": OPERATION_KEY },
      { "Idempotency-Key": OPERATION_KEY },
    ]);
  });

  it("reuses one browser key for a source-create response-loss retry", async () => {
    mocks.post
      .mockRejectedValueOnce(new Error("response lost"))
      .mockResolvedValueOnce({ data: { id: "source-1" } });
    const data = new FormData();
    data.set("operation_key", OPERATION_KEY);
    data.set("source_type", "manual-insight");
    data.set("category", "area-demand");
    data.set("confidence", "high");
    data.set("expires_at", "2027-09-01T10:00");

    await expect(createSourceAction({}, data)).resolves.toEqual({
      error: "Could not reach the server.",
      operationKey: OPERATION_KEY,
    });
    await expect(createSourceAction({}, data)).resolves.toEqual({
      success: "Audience saved.",
      operationKey: OPERATION_KEY,
    });
    expect(mocks.post.mock.calls.map((call) => call[1].params.header)).toEqual([
      { "Idempotency-Key": OPERATION_KEY },
      { "Idempotency-Key": OPERATION_KEY },
    ]);
  });

  it("keeps terminal source and link retries on their supplied operation keys", async () => {
    const sourceData = new FormData();
    sourceData.set("operation_key", "00000000-0000-4000-8000-000000000045");
    const linkData = new FormData();
    linkData.set("operation_key", "00000000-0000-4000-8000-000000000046");

    await deactivateSourceAction("source-1", {}, sourceData);
    await removeSourceLinkAction("link-1", {}, linkData);

    expect(mocks.post.mock.calls.map((call) => call[1].params.header)).toEqual([
      { "Idempotency-Key": "00000000-0000-4000-8000-000000000045" },
      { "Idempotency-Key": "00000000-0000-4000-8000-000000000046" },
    ]);
  });

  it("retains terminal mutation keys when the first response is lost", async () => {
    mocks.post
      .mockRejectedValueOnce(new Error("source response lost"))
      .mockResolvedValueOnce({ data: { id: "source-1" } })
      .mockRejectedValueOnce(new Error("link response lost"))
      .mockResolvedValueOnce({ data: { id: "link-1" } });
    const sourceData = new FormData();
    sourceData.set("operation_key", "00000000-0000-4000-8000-000000000045");
    const linkData = new FormData();
    linkData.set("operation_key", "00000000-0000-4000-8000-000000000046");

    await expect(deactivateSourceAction("source-1", {}, sourceData)).resolves.toEqual({
      error: "Could not reach the server.",
      operationKey: "00000000-0000-4000-8000-000000000045",
    });
    await expect(deactivateSourceAction("source-1", {}, sourceData)).resolves.toEqual({
      success: "Audience no longer used.",
      operationKey: "00000000-0000-4000-8000-000000000045",
    });
    await expect(removeSourceLinkAction("link-1", {}, linkData)).resolves.toEqual({
      error: "Could not reach the server.",
      operationKey: "00000000-0000-4000-8000-000000000046",
    });
    await expect(removeSourceLinkAction("link-1", {}, linkData)).resolves.toEqual({
      success: "Audience disconnected from the campaign area.",
      operationKey: "00000000-0000-4000-8000-000000000046",
    });
    expect(mocks.post.mock.calls.map((call) => call[1].params.header)).toEqual([
      { "Idempotency-Key": "00000000-0000-4000-8000-000000000045" },
      { "Idempotency-Key": "00000000-0000-4000-8000-000000000045" },
      { "Idempotency-Key": "00000000-0000-4000-8000-000000000046" },
      { "Idempotency-Key": "00000000-0000-4000-8000-000000000046" },
    ]);
  });

  it("rejects an unordered window before the API call", async () => {
    const data = new FormData();
    data.set("operation_key", OPERATION_KEY);
    data.set("start_at", "2026-09-02T10:00");
    data.set("end_at", "2026-09-01T10:00");

    expect(await createSourceLinkAction({}, data)).toEqual({
      error: "Choose a start date and time before the end.",
      operationKey: OPERATION_KEY,
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it.each([
    ["", "2026-09-02T10:00"],
    ["2026-09-01", "2026-09-02T10:00"],
    ["2026-13-01T10:00", "2026-09-02T10:00"],
    ["2026-09-01T10:00Z", "2026-09-02T10:00"],
  ])("rejects a start of %j that isn't a date and time", async (start, end) => {
    const data = linkData();
    data.set("start_at", start);
    data.set("end_at", end);

    expect(await createSourceLinkAction({}, data)).toEqual({
      error: "Choose a start date and time before the end.",
      operationKey: OPERATION_KEY,
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });
});

describe("createSourceAction expiry", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
    mocks.post.mockResolvedValue({ data: { id: "source-1" } });
  });

  function sourceData(expiresAt: string) {
    const data = new FormData();
    data.set("operation_key", OPERATION_KEY);
    data.set("source_type", "manual-insight");
    data.set("category", "area-demand");
    data.set("confidence", "high");
    data.set("expires_at", expiresAt);
    return data;
  }

  it("sends the expiry as the Nigeria-time instant", async () => {
    await createSourceAction({}, sourceData("2027-09-01T10:00"));
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/advertiser/retargeting-sources",
      expect.objectContaining({
        body: expect.objectContaining({ expires_at: "2027-09-01T09:00:00.000Z" }),
      }),
    );
  });

  it("refuses an expiry that has already passed in Nigeria time", async () => {
    vi.useFakeTimers();
    // 09:30 UTC is 10:30 in Nigeria, so 10:00 Nigeria time has already passed.
    vi.setSystemTime(new Date("2026-09-01T09:30:00Z"));
    try {
      expect(await createSourceAction({}, sourceData("2026-09-01T10:00"))).toEqual({
        error: "Choose a future date and time to stop using it.",
        operationKey: OPERATION_KEY,
      });
      await createSourceAction({}, sourceData("2026-09-01T11:00"));
    } finally {
      vi.useRealTimers();
    }
    expect(mocks.post).toHaveBeenCalledTimes(1);
  });

  it("refuses an expiry that isn't a date and time", async () => {
    expect(await createSourceAction({}, sourceData("next week"))).toEqual({
      error: "Choose a future date and time to stop using it.",
      operationKey: OPERATION_KEY,
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });
});
