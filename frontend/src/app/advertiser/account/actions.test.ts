import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({
  patch: vi.fn(),
  revalidatePath: vi.fn(),
  redirect: vi.fn((url: string) => {
    throw new Error(`REDIRECT ${url}`);
  }),
}));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  redirect: mocks.redirect,
}));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ PATCH: mocks.patch }) }));

import { updateCompanyAction } from "./actions";

function form(): FormData {
  const data = new FormData();
  data.set("name", " Demo Advertiser Ltd ");
  data.set("billing_email", "");
  return data;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.patch.mockResolvedValue({ data: {} });
});

it("saves the advertiser's own company and returns to the page", async () => {
  await expect(updateCompanyAction(form())).rejects.toThrow("REDIRECT /advertiser/account?saved=1");
  expect(mocks.patch).toHaveBeenCalledWith("/api/v1/advertiser/company", {
    body: expect.objectContaining({ name: "Demo Advertiser Ltd", billing_email: null }),
  });
  expect(mocks.revalidatePath).toHaveBeenCalledWith("/advertiser/account");
});

it("redirects with safe copy for an unmapped refusal or transport failure", async () => {
  mocks.patch.mockRejectedValue(
    new ApiError(403, {
      code: "FORBIDDEN",
      message: "private company contact private@example.com",
    }),
  );
  await expect(updateCompanyAction(form())).rejects.toThrow(
    `REDIRECT /advertiser/account?error=${encodeURIComponent("The request could not be completed. Check the details and try again.")}`,
  );
  mocks.patch.mockRejectedValue(new Error("network"));
  await expect(updateCompanyAction(form())).rejects.toThrow(
    "REDIRECT /advertiser/account?error=Could%20not%20update%20company%20profile",
  );
  expect(mocks.revalidatePath).not.toHaveBeenCalled();
});
