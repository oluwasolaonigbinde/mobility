import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));

import { cancelAssignmentAction } from "./actions";

const ASSIGNMENT_ID = "00000000-0000-4000-8000-00000000000a";

describe("cancelAssignmentAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: {} });
  });

  it("requires and trims the permanent removal reason", async () => {
    await expect(cancelAssignmentAction(ASSIGNMENT_ID, "   ")).resolves.toEqual({
      error: "A cancellation reason is required",
    });
    expect(mocks.post).not.toHaveBeenCalled();

    await expect(
      cancelAssignmentAction(ASSIGNMENT_ID, "  Vehicle removed from campaign scope  "),
    ).resolves.toEqual({});
    expect(mocks.post).toHaveBeenCalledWith(
      "/api/v1/admin/campaign-assignments/{assignment_id}/cancel",
      {
        params: { path: { assignment_id: ASSIGNMENT_ID } },
        body: { reason: "Vehicle removed from campaign scope" },
      },
    );
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/assignments");
  });
});
