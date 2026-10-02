import { beforeEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ post: vi.fn(), guard: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.guard }));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
import { resumeCampaign } from "./actions";
import { ApiError } from "@/lib/api/errors";
const id = "00000000-0000-4000-8000-000000000001";
function form(reason = " Funding reviewed ") {
  const data = new FormData();
  data.set("campaign_id", id);
  data.set("reason", reason);
  return data;
}
beforeEach(() => {
  vi.clearAllMocks();
});
it("uses the existing guarded resume operation with a required reason", async () => {
  expect(await resumeCampaign({}, form())).toEqual({ done: "Campaign resumed" });
  expect(mocks.guard).toHaveBeenCalledWith("admin");
  expect(mocks.post).toHaveBeenCalledExactlyOnceWith(
    "/api/v1/admin/campaigns/{campaign_id}/budget-policy-resume",
    { params: { path: { campaign_id: id } }, body: { reason: "Funding reviewed" } },
  );
  expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/campaigns/" + id);
});
it("sends the recorded pause ID to the staff Resume operation and never changes its reason category", async () => {
  const input = form(" Inspection complete ");
  input.set("pause_id", id);
  expect(await resumeCampaign({}, input)).toEqual({ done: "Campaign resumed" });
  expect(mocks.post).toHaveBeenCalledExactlyOnceWith(
    "/api/v1/admin/campaigns/{campaign_id}/resume",
    {
      params: { path: { campaign_id: id } },
      body: { pause_id: id, reason: "Inspection complete" },
    },
  );
});
it.each(["", " ".repeat(3), "x".repeat(1001)])(
  "does not resume without a valid reason",
  async (reason) => {
    expect(await resumeCampaign({}, form(reason))).toHaveProperty("error");
    expect(mocks.post).not.toHaveBeenCalled();
  },
);
it("does not contact the backend after a denied staff session", async () => {
  mocks.guard.mockRejectedValueOnce(new Error("denied"));
  await expect(resumeCampaign({}, form())).rejects.toThrow("denied");
  expect(mocks.post).not.toHaveBeenCalled();
});
it.each([
  new ApiError(409, { code: "BLOCKED", message: "Funding is still missing." }),
  new Error("offline"),
])("reports refusal without claiming resume succeeded", async (error) => {
  mocks.post.mockRejectedValueOnce(error);
  expect(await resumeCampaign({}, form())).toEqual({
    error: error instanceof ApiError ? "Funding is still missing." : "Could not reach the server.",
  });
  expect(mocks.revalidatePath).not.toHaveBeenCalled();
});
