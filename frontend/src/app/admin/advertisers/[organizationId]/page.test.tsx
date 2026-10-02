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
vi.mock("./company/actions", () => ({
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
  mocks.get.mockResolvedValue({ data: { id: ORG_ID, name: "Demo Advertiser Ltd" } });
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
  expect(screen.queryByRole("link", { name: "Campaign money" })).not.toBeInTheDocument();
});

it("keeps the canonical campaign money breadcrumb and passes the campaign to the action", async () => {
  render(await renderPage({ campaign: "campaign-1", error: "Name is required" }));
  expect(mocks.bind).toHaveBeenCalledWith(null, ORG_ID, "campaign-1");
  expect(screen.getByRole("link", { name: "Campaign money" })).toHaveAttribute(
    "href",
    "/admin/campaigns/campaign-1#money",
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

it("shows one section failure without exposing failed company fields", async () => {
  mocks.get.mockRejectedValue(new ApiError(500, { code: "INTERNAL", message: "boom" }));
  render(await renderPage());
  expect(screen.getAllByRole("alert")).toHaveLength(1);
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this section — try again");
  expect(screen.queryByLabelText("Legal or trading name")).toBeNull();
  expect(mocks.bind).not.toHaveBeenCalled();
});
it("refuses a different company identity and denied access before exposing the form", async () => {
  mocks.get.mockResolvedValue({ data: { id: "another-company", name: "Other company" } });
  await expect(renderPage()).rejects.toThrow("NEXT_NOT_FOUND");
  mocks.get.mockRejectedValue(new ApiError(403, { code: "DENIED", message: "denied" }));
  await expect(renderPage()).rejects.toThrow("NEXT_NOT_FOUND");
  expect(mocks.bind).not.toHaveBeenCalled();
});
