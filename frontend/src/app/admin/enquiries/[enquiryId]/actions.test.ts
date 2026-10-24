import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({
  convert: vi.fn(),
  role: vi.fn(),
  redirect: vi.fn(),
  revalidate: vi.fn(),
}));
vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidate }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({}) }));
vi.mock("@/lib/api/audit-batch2", () => ({ createAdvertiserFromEnquiry: mocks.convert }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.role }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));
import { convertEnquiry } from "./actions";
const enquiryId = "00000000-0000-4000-8000-000000000001";
const organizationId = "00000000-0000-4000-8000-000000000002";
beforeEach(() => {
  vi.resetAllMocks();
  mocks.convert.mockResolvedValue({
    data: { status: "converted", organization_id: organizationId },
  });
  mocks.redirect.mockImplementation((path: string) => {
    throw new Error(`redirect:${path}`);
  });
});
it("uses the authorised enquiry conversion without browser-supplied owner/login credentials", async () => {
  await expect(convertEnquiry(enquiryId, {})).rejects.toThrow(
    `redirect:/admin/advertisers/${organizationId}#people`,
  );
  expect(mocks.role).toHaveBeenCalledWith("admin");
  expect(mocks.convert).toHaveBeenCalledWith(expect.anything(), enquiryId);
  expect(mocks.revalidate).toHaveBeenCalledWith("/admin/enquiries");
});
it("does not create for a malformed enquiry route", async () => {
  expect(await convertEnquiry("bad", {})).toHaveProperty("error");
  expect(mocks.convert).not.toHaveBeenCalled();
});
it.each([
  undefined,
  { status: "new", organization_id: organizationId },
  { status: "converted", organization_id: "bad" },
])("does not redirect to an unconfirmed organisation", async (data) => {
  mocks.convert.mockResolvedValue({ data });
  expect(await convertEnquiry(enquiryId, {})).toHaveProperty("error");
  expect(mocks.redirect).not.toHaveBeenCalled();
});
it("keeps an unexpected refusal neutral without echoing private server copy", async () => {
  mocks.convert.mockRejectedValue(
    new ApiError(503, { code: "UNAVAILABLE", message: "private note" }),
  );
  const state = await convertEnquiry(enquiryId, {});
  expect(state.error).toContain("couldn’t confirm");
  expect(state.error).not.toContain("private note");
  expect(mocks.redirect).not.toHaveBeenCalled();
});
it("supports the backend's convergent repeated conversion result", async () => {
  for (let n = 0; n < 2; n++)
    await expect(convertEnquiry(enquiryId, {})).rejects.toThrow(
      `redirect:/admin/advertisers/${organizationId}#people`,
    );
  expect(mocks.convert).toHaveBeenCalledTimes(2);
});
