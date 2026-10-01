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
vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));
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
  await expect(updateCompanyAction(form())).rejects.toThrow("REDIRECT /advertiser/company?saved=1");
  expect(mocks.patch).toHaveBeenCalledWith("/api/v1/advertiser/company", {
    body: expect.objectContaining({ name: "Demo Advertiser Ltd", billing_email: null }),
  });
  expect(mocks.revalidatePath).toHaveBeenCalledWith("/advertiser/company");
});

it("returns the API message, or a generic one, on failure", async () => {
  mocks.patch.mockRejectedValue(new ApiError(403, { code: "FORBIDDEN", message: "Not allowed" }));
  await expect(updateCompanyAction(form())).rejects.toThrow(
    "REDIRECT /advertiser/company?error=Not%20allowed",
  );
  mocks.patch.mockRejectedValue(new Error("network"));
  await expect(updateCompanyAction(form())).rejects.toThrow(
    "REDIRECT /advertiser/company?error=Could%20not%20update%20company%20profile",
  );
  expect(mocks.revalidatePath).not.toHaveBeenCalled();
});
