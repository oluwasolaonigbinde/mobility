import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import Page from "./page";
const mocks = vi.hoisted(() => ({ get: vi.fn(), role: vi.fn() }));
vi.mock("@/lib/auth/current-user", () => ({
  requireRole: mocks.role,
}));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("not-found");
  },
  redirect: (to: string) => {
    throw new Error(`redirect:${to}`);
  },
}));
vi.mock("./wizard", () => ({
  CampaignWizard: ({
    currency,
    existingCampaign,
    areasEditable,
  }: {
    currency: string;
    areasEditable: boolean;
    existingCampaign?: { id: string };
  }) => (
    <p data-testid="wizard" data-areas-editable={String(areasEditable)}>
      {currency}:{existingCampaign?.id ?? "new"}
    </p>
  ),
}));
const id = "00000000-0000-4000-8000-000000000001";
beforeEach(() => {
  vi.resetAllMocks();
  mocks.role.mockResolvedValue({ advertiser_organization: { currency: "NGN" } });
  mocks.get.mockImplementation(async (path: string) => ({
    data: path.endsWith("/zones")
      ? { items: [], total: 0 }
      : path.endsWith("/commercial")
        ? { production_start: null }
        : { id, name: "Existing draft", status: "draft" },
  }));
});
it("keeps ordinary new campaign creation available", async () => {
  render(await Page({ searchParams: Promise.resolve({}) }));
  expect(screen.getByRole("heading", { name: "New campaign" })).toBeInTheDocument();
  expect(mocks.get).not.toHaveBeenCalled();
  expect(mocks.role).toHaveBeenCalledWith("advertiser");
});
it("loads the authorised saved campaign and areas for recovery", async () => {
  render(await Page({ searchParams: Promise.resolve({ campaignId: id }) }));
  expect(screen.getByRole("heading", { name: "Finish Existing draft" })).toBeInTheDocument();
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
    render(await Page({ searchParams: Promise.resolve({ campaignId: id }) }));
    expect(
      screen.getByRole("status", { name: "Your saved draft couldn't be confirmed" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("wizard")).toBeNull();
  },
);
it.each(["campaign", "areas"])(
  "sends an expired session on the %s read to sign in",
  async (failing) => {
    mocks.get.mockImplementation(async (path: string) => {
      if (path.endsWith("/zones") === (failing === "areas"))
        throw new ApiError(401, { code: "UNAUTHORIZED", message: "Expired" });
      return {
        data: path.endsWith("/commercial")
          ? { production_start: null }
          : { id, name: "Existing draft", status: "draft" },
      };
    });
    await expect(Page({ searchParams: Promise.resolve({ campaignId: id }) })).rejects.toThrow(
      "redirect:/login",
    );
  },
);
it("shows unavailable authority without presenting a create fallback", async () => {
  mocks.get.mockRejectedValue(new ApiError(503, { code: "UNAVAILABLE", message: "Unavailable" }));
  render(await Page({ searchParams: Promise.resolve({ requestId: id }) }));
  expect(
    screen.getByRole("status", { name: "Your saved draft couldn't be confirmed" }),
  ).toBeInTheDocument();
  expect(screen.queryByTestId("wizard")).toBeNull();
});
it.each(["approved", "paused"])(
  "offers the existing support path after production for %s",
  async (status) => {
    mocks.get.mockImplementation(async (path: string) => ({
      data: path.endsWith("/commercial")
        ? { production_start: { started_at: "2026-10-20T09:00Z" } }
        : { id, name: "Printed campaign", status },
    }));
    render(await Page({ searchParams: Promise.resolve({ campaignId: id }) }));
    expect(screen.queryByTestId("wizard")).toBeNull();
    expect(screen.getByRole("link", { name: /Ask Terrax to change it/ })).toHaveAttribute(
      "href",
      `/advertiser/campaigns/${id}#artwork-change`,
    );
  },
);
it("never opens the artwork wizard for a running campaign, even if commercial data is unavailable", async () => {
  mocks.get.mockResolvedValue({ data: { id, name: "Running campaign", status: "active" } });
  render(await Page({ searchParams: Promise.resolve({ campaignId: id }) }));
  expect(screen.queryByTestId("wizard")).toBeNull();
  expect(screen.getByRole("link", { name: /Ask Terrax to change it/ })).toBeInTheDocument();
  expect(mocks.get).toHaveBeenCalledTimes(1);
});

it.each(["draft", "rejected", "pending_review", "approved", "paused"])(
  "passes server-compatible area permission for %s",
  async (status) => {
    mocks.get.mockImplementation(async (path: string) => ({
      data: path.endsWith("/zones")
        ? { items: [], total: 0 }
        : path.endsWith("/commercial")
          ? { production_start: null }
          : { id, name: "Saved campaign", status },
    }));
    render(await Page({ searchParams: Promise.resolve({ campaignId: id }) }));
    expect(screen.getByTestId("wizard")).toHaveAttribute(
      "data-areas-editable",
      String(["draft", "rejected"].includes(status)),
    );
  },
);
