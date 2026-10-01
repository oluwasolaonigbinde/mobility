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

const ORG_ID = "00000000-0000-4000-8000-000000000001";
const PATH = `/admin/advertisers/${ORG_ID}/company`;

function form(): FormData {
  const data = new FormData();
  data.set("name", " Demo Advertiser Ltd ");
  data.set("industry", "");
  return data;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.patch.mockResolvedValue({ data: {} });
});

it("saves through the admin endpoint and returns to the page", async () => {
  await expect(updateCompanyAction(ORG_ID, undefined, form())).rejects.toThrow(
    `REDIRECT ${PATH}?saved=1`,
  );
  expect(mocks.patch).toHaveBeenCalledWith(
    "/api/v1/admin/advertiser-organizations/{organization_id}/company",
    expect.objectContaining({
      params: { path: { organization_id: ORG_ID } },
      body: expect.objectContaining({ name: "Demo Advertiser Ltd", industry: null }),
    }),
  );
  expect(mocks.revalidatePath).toHaveBeenCalledWith(PATH);
  expect(mocks.revalidatePath).toHaveBeenCalledTimes(1);
});

it("keeps the campaign context and revalidates its billing page", async () => {
  await expect(updateCompanyAction(ORG_ID, "campaign-1", form())).rejects.toThrow(
    `REDIRECT ${PATH}?campaign=campaign-1&saved=1`,
  );
  expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/billing/campaign-1");
});

it("returns the API message on failure, with and without campaign context", async () => {
  mocks.patch.mockRejectedValue(
    new ApiError(422, { code: "INVALID", message: "Name is required" }),
  );
  await expect(updateCompanyAction(ORG_ID, undefined, form())).rejects.toThrow(
    `REDIRECT ${PATH}?error=Name%20is%20required`,
  );
  await expect(updateCompanyAction(ORG_ID, "campaign-1", form())).rejects.toThrow(
    `REDIRECT ${PATH}?campaign=campaign-1&error=Name%20is%20required`,
  );
  mocks.patch.mockRejectedValue(new Error("network"));
  await expect(updateCompanyAction(ORG_ID, undefined, form())).rejects.toThrow(
    `REDIRECT ${PATH}?error=Could%20not%20update%20company%20profile`,
  );
  expect(mocks.revalidatePath).not.toHaveBeenCalled();
});
