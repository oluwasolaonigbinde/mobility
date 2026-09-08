import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import Page from "./page";
const mocks = vi.hoisted(() => ({ get: vi.fn(), role: vi.fn() }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.role }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("not-found");
  },
}));
vi.mock("./wizard", () => ({
  CampaignWizard: ({
    currency,
    existingCampaign,
  }: {
    currency: string;
    existingCampaign?: { id: string };
  }) => (
    <p data-testid="wizard">
      {currency}:{existingCampaign?.id ?? "new"}
    </p>
  ),
}));
const id = "00000000-0000-4000-8000-000000000001";
beforeEach(() => {
  vi.resetAllMocks();
  mocks.role.mockResolvedValue({ advertiser_organization: { currency: "NGN" } });
  mocks.get.mockResolvedValue({ data: { id, name: "Existing draft" } });
});
it("keeps ordinary new campaign creation available", async () => {
  render(await Page({ searchParams: Promise.resolve({}) }));
  expect(screen.getByRole("heading", { name: "New campaign" })).toBeInTheDocument();
  expect(mocks.get).not.toHaveBeenCalled();
  expect(mocks.role).toHaveBeenCalledWith("advertiser");
});
it("loads the authorized existing campaign for creative-only recovery", async () => {
  render(await Page({ searchParams: Promise.resolve({ campaignId: id }) }));
  expect(
    screen.getByRole("heading", { name: "Add creatives to Existing draft" }),
  ).toBeInTheDocument();
  expect(screen.getByTestId("wizard")).toHaveTextContent(`NGN:${id}`);
  expect(mocks.get).toHaveBeenCalledWith("/api/v1/advertiser/campaigns/{campaign_id}", {
    params: { path: { campaign_id: id } },
  });
});
it("rejects malformed recovery references before querying", async () => {
  await expect(Page({ searchParams: Promise.resolve({ campaignId: "invalid" }) })).rejects.toThrow(
    "not-found",
  );
  expect(mocks.get).not.toHaveBeenCalled();
});
it.each(["absent", "cross-tenant"])(
  "does not turn %s recovery into a new campaign",
  async (kind) => {
    if (kind === "absent") mocks.get.mockResolvedValue({ data: undefined });
    else
      mocks.get.mockRejectedValue(
        new ApiError(404, { code: "CAMPAIGN_NOT_FOUND", message: "Unavailable" }),
      );
    await expect(Page({ searchParams: Promise.resolve({ campaignId: id }) })).rejects.toThrow(
      "not-found",
    );
  },
);
it("propagates unavailable authority instead of presenting a create fallback", async () => {
  mocks.get.mockRejectedValue(new ApiError(503, { code: "UNAVAILABLE", message: "Unavailable" }));
  await expect(Page({ searchParams: Promise.resolve({ campaignId: id }) })).rejects.toThrow(
    "Unavailable",
  );
});
