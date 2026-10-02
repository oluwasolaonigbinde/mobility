import { beforeEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ patch: vi.fn(), guard: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ PATCH: mocks.patch }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.guard }));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("next/navigation", () => ({ redirect: vi.fn() }));
import { updateDriverDetailsAction } from "../fleet-actions";
import { ApiError } from "@/lib/api/errors";
const id = "00000000-0000-4000-8000-000000000001";
function form() {
  const data = new FormData();
  data.set("driver_profile_id", id);
  data.set("service_city", " Abuja ");
  data.set("country_code", "ng");
  return data;
}
beforeEach(() => vi.clearAllMocks());
it("edits profile details through the existing PATCH without status or account changes", async () => {
  expect(await updateDriverDetailsAction({}, form())).toEqual({ saved: true });
  expect(mocks.guard).toHaveBeenCalledWith("admin");
  expect(mocks.patch).toHaveBeenCalledExactlyOnceWith("/api/v1/admin/drivers/{driver_profile_id}", {
    params: { path: { driver_profile_id: id } },
    body: { service_city: "Abuja", country_code: "NG", license_number: null },
  });
  expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/drivers/[driverId]", "page");
});
it("rejects invalid selection before attempting a write", async () => {
  const data = form();
  data.set("driver_profile_id", "wrong");
  expect(await updateDriverDetailsAction({}, data)).toHaveProperty("error");
  expect(mocks.patch).not.toHaveBeenCalled();
});
it("allows existing 128-character profile values without truncation", async () => {
  const data = form();
  data.set("license_number", "L".repeat(128));
  data.set("service_city", "C".repeat(128));
  expect(await updateDriverDetailsAction({}, data)).toEqual({ saved: true });
  expect(mocks.patch).toHaveBeenCalledWith(
    expect.any(String),
    expect.objectContaining({
      body: expect.objectContaining({
        license_number: "L".repeat(128),
        service_city: "C".repeat(128),
      }),
    }),
  );
});
it("does not write if staff authorization is denied", async () => {
  mocks.guard.mockRejectedValueOnce(new Error("denied"));
  await expect(updateDriverDetailsAction({}, form())).rejects.toThrow("denied");
  expect(mocks.patch).not.toHaveBeenCalled();
});
it.each([new ApiError(409, { code: "CONFLICT", message: "Please reload." }), new Error("offline")])(
  "reports refused or failed writes without claiming success",
  async (error) => {
    mocks.patch.mockRejectedValueOnce(error);
    expect(await updateDriverDetailsAction({}, form())).toEqual({
      error: error instanceof ApiError ? "Please reload." : "Could not reach the server.",
    });
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
  },
);
