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
      success: "Planning source linked to the target zone.",
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
          start_at: expect.stringMatching(/^2026-09-01T/),
          end_at: expect.stringMatching(/^2026-09-02T/),
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
      success: "Planning source linked to the target zone.",
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
      success: "Planning source recorded.",
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
      success: "Planning source deactivated.",
      operationKey: "00000000-0000-4000-8000-000000000045",
    });
    await expect(removeSourceLinkAction("link-1", {}, linkData)).resolves.toEqual({
      error: "Could not reach the server.",
      operationKey: "00000000-0000-4000-8000-000000000046",
    });
    await expect(removeSourceLinkAction("link-1", {}, linkData)).resolves.toEqual({
      success: "Planning source link removed.",
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
      error: "Choose a valid linkage window with the start before the end.",
      operationKey: OPERATION_KEY,
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });
});
