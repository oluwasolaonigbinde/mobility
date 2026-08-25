import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ post: vi.fn(), revalidatePath: vi.fn() }));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));

import { createSourceLinkAction } from "./actions";

describe("createSourceLinkAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: { id: "link-1" } });
  });

  it("sends only the selected owned resource references and normalized window", async () => {
    const data = new FormData();
    data.set("source_id", "00000000-0000-4000-8000-000000000001");
    data.set("campaign_id", "00000000-0000-4000-8000-000000000002");
    data.set("zone_id", "00000000-0000-4000-8000-000000000003");
    data.set("start_at", "2026-09-01T10:00");
    data.set("end_at", "2026-09-02T10:00");

    await expect(createSourceLinkAction({}, data)).resolves.toEqual({
      success: "Planning source linked to the target zone.",
    });
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/advertiser/retargeting-source-links",
      expect.objectContaining({
        params: { header: { "Idempotency-Key": expect.any(String) } },
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

  it("rejects an unordered window before the API call", async () => {
    const data = new FormData();
    data.set("start_at", "2026-09-02T10:00");
    data.set("end_at", "2026-09-01T10:00");

    expect(await createSourceLinkAction({}, data)).toEqual({
      error: "Choose a valid linkage window with the start before the end.",
    });
    expect(mocks.post).not.toHaveBeenCalled();
  });
});
