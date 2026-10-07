import { beforeEach, expect, it, vi } from "vitest";
import { recordPhoneVerificationAction } from "./phone-verification-actions";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.post }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "driver-token" }));
const code = "485921";
function form() {
  const f = new FormData();
  for (const [k, v] of Object.entries({
    driver_profile_id: "11111111-1111-4111-8111-111111111111",
    challenge_id: "22222222-2222-4222-8222-222222222222",
    code,
    sender_phone: "+447700900101",
  }))
    f.set(k, v);
  return f;
}
beforeEach(() => {
  vi.clearAllMocks();
  mocks.post.mockResolvedValue({ data: { verified: true } });
});
it("forwards staff received input but never returns it", async () => {
  const result = await recordPhoneVerificationAction({}, form());
  expect(result.done).toMatch(/Phone verified/);
  expect(JSON.stringify(result)).not.toContain(code);
  expect(JSON.stringify(result)).not.toContain("+447700900101");
  expect(mocks.post).toHaveBeenCalledWith(
    "/api/v1/admin/drivers/{driver_profile_id}/phone-verification",
    expect.objectContaining({
      body: expect.objectContaining({ code, sender_phone: "+447700900101" }),
    }),
  );
});
it.each(["code", "sender_phone", "challenge_id", "driver_profile_id"])(
  "rejects malformed %s without echoing inputs",
  async (field) => {
    const f = form();
    f.set(field, "x");
    const result = await recordPhoneVerificationAction({}, f);
    expect(result.error).toBeTruthy();
    expect(JSON.stringify(result)).not.toContain(code);
    expect(mocks.post).not.toHaveBeenCalled();
  },
);
it("returns safe server mismatch and unavailable errors without input", async () => {
  mocks.post.mockRejectedValue(
    new ApiError(400, {
      code: "PHONE_VERIFICATION_MISMATCH",
      message: "The code and sender do not match",
    }),
  );
  expect(JSON.stringify(await recordPhoneVerificationAction({}, form()))).not.toContain(code);
  mocks.post.mockRejectedValue(new Error("offline"));
  expect((await recordPhoneVerificationAction({}, form())).error).toMatch(/Couldn't record/);
});
