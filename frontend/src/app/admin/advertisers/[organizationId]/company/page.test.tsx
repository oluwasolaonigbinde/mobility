import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  action: vi.fn(),
  bind: vi.fn(),
  notFound: vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
}));
vi.mock("next/navigation", () => ({ notFound: mocks.notFound }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("./actions", () => ({
  updateCompanyAction: Object.assign(mocks.action, { bind: mocks.bind }),
}));

import AdminCompanyPage from "./page";

const ORG_ID = "00000000-0000-4000-8000-000000000001";

function renderPage(query: { campaign?: string; saved?: string; error?: string } = {}) {
  return AdminCompanyPage({
    params: Promise.resolve({ organizationId: ORG_ID }),
    searchParams: Promise.resolve(query),
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.bind.mockReturnValue(vi.fn());
  mocks.get.mockResolvedValue({ data: { name: "Demo Advertiser Ltd" } });
});

it("shows the company with an editable form bound to the organization", async () => {
  render(await renderPage({ saved: "1" }));
  expect(mocks.get).toHaveBeenCalledWith(
    "/api/v1/admin/advertiser-organizations/{organization_id}/company",
    { params: { path: { organization_id: ORG_ID } } },
  );
  expect(mocks.bind).toHaveBeenCalledWith(null, ORG_ID, undefined);
  expect(screen.getByRole("heading", { name: "Demo Advertiser Ltd" })).toBeInTheDocument();
  expect(screen.getByText("Company profile saved.")).toBeInTheDocument();
  expect(screen.getByLabelText("Legal or trading name")).toBeEnabled();
  expect(screen.getByRole("button", { name: "Save company profile" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Campaign billing" })).not.toBeInTheDocument();
});

it("keeps the campaign billing breadcrumb and passes the campaign to the action", async () => {
  render(await renderPage({ campaign: "campaign-1", error: "Name is required" }));
  expect(mocks.bind).toHaveBeenCalledWith(null, ORG_ID, "campaign-1");
  expect(screen.getByRole("link", { name: "Campaign billing" })).toHaveAttribute(
    "href",
    "/admin/billing/campaign-1",
  );
  expect(screen.getByText("Name is required")).toBeInTheDocument();
});

it("treats a missing organization as not found", async () => {
  mocks.get.mockRejectedValue(new ApiError(404, { code: "NOT_FOUND", message: "missing" }));
  await expect(renderPage()).rejects.toThrow("NEXT_NOT_FOUND");
  mocks.get.mockResolvedValue({ data: undefined });
  await expect(renderPage()).rejects.toThrow("NEXT_NOT_FOUND");
  expect(mocks.notFound).toHaveBeenCalledTimes(2);
});

it("rethrows other API failures", async () => {
  const failure = new ApiError(500, { code: "INTERNAL", message: "boom" });
  mocks.get.mockRejectedValue(failure);
  await expect(renderPage()).rejects.toBe(failure);
  expect(mocks.notFound).not.toHaveBeenCalled();
});
