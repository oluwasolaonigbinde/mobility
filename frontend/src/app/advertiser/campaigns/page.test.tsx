import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ get: vi.fn(), role: vi.fn() }));
vi.mock("@/lib/auth/current-user", () => ({
  requireRole: mocks.role,
  isAdvertiserViewer: (me: { advertiser_organization?: { membership_role?: string } }) =>
    me.advertiser_organization?.membership_role === "viewer",
}));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));

import CampaignsPage from "./page";

beforeEach(() => {
  mocks.get.mockResolvedValue({ data: { items: [], total: 0 } });
});

it("offers campaign creation to owners and managers", async () => {
  mocks.role.mockResolvedValue({ advertiser_organization: { membership_role: "manager" } });
  render(await CampaignsPage({ searchParams: Promise.resolve({}) }));
  expect(screen.getByRole("link", { name: "+ New campaign" })).toBeInTheDocument();
});

it("explains view-only access instead of a create button for viewers", async () => {
  mocks.role.mockResolvedValue({ advertiser_organization: { membership_role: "viewer" } });
  render(await CampaignsPage({ searchParams: Promise.resolve({}) }));
  expect(screen.queryByRole("link", { name: "+ New campaign" })).not.toBeInTheDocument();
  expect(screen.getByText(/View only/)).toBeInTheDocument();
});
