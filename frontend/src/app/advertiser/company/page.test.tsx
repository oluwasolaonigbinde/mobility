import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ get: vi.fn(), role: vi.fn() }));
vi.mock("@/lib/auth/current-user", () => ({
  requireRole: mocks.role,
}));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("./actions", () => ({ updateCompanyAction: vi.fn() }));

import CompanyPage from "./page";

beforeEach(() => {
  mocks.get.mockResolvedValue({ data: { name: "Demo Advertiser Ltd" } });
});

it("lets advertisers edit company details", async () => {
  mocks.role.mockResolvedValue({ advertiser_organization: { membership_role: "advertiser" } });
  render(await CompanyPage({ searchParams: Promise.resolve({}) }));
  expect(screen.getByLabelText("Legal or trading name")).toBeEnabled();
  expect(screen.getByRole("button", { name: "Save company profile" })).toBeInTheDocument();
  expect(screen.getByText(/contact details only/)).toBeInTheDocument();
});
