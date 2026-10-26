import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ get: vi.fn(), role: vi.fn() }));
vi.mock("@/lib/auth/current-user", () => ({
  requireRole: mocks.role,
}));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("./actions", () => ({ updateCompanyAction: vi.fn() }));
vi.mock("@/components/auth/change-password-form", () => ({
  ChangePasswordForm: () => <div>Change password form</div>,
}));
vi.mock("@/components/driver/logout-button", () => ({
  SessionLogoutButton: () => <button>Sign out</button>,
}));

import CompanyPage from "./page";

beforeEach(() => {
  mocks.get.mockResolvedValue({ data: { name: "Demo Advertiser Ltd" } });
});

it("lets advertisers edit company details", async () => {
  mocks.role.mockResolvedValue({
    user: { full_name: "Ada", email: "ada@example.test" },
    advertiser_organization: { membership_role: "advertiser" },
  });
  render(await CompanyPage({ searchParams: Promise.resolve({}) }));
  expect(screen.getByLabelText("Legal or trading name")).toBeEnabled();
  expect(screen.getByRole("button", { name: "Save company profile" })).toBeInTheDocument();
  expect(screen.getByText(/contact details only/)).toBeInTheDocument();
});

it("keeps sign-in and password controls when company details fail, with a retry", async () => {
  mocks.role.mockResolvedValue({ user: { full_name: "Ada", email: "ada@example.test" } });
  mocks.get.mockRejectedValue(
    new ApiError(503, { code: "UNAVAILABLE", message: "Private failure" }),
  );
  render(await CompanyPage({}));
  expect(screen.getByRole("heading", { name: "Company details unavailable" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Try again/ })).toHaveAttribute(
    "href",
    "/advertiser/account",
  );
  expect(screen.getByText("ada@example.test")).toBeInTheDocument();
  expect(screen.getByText("Change password form")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent("Private failure");
});
