import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  notFound: vi.fn(() => {
    throw new Error("NOT_FOUND");
  }),
}));
vi.mock("next/navigation", () => ({ notFound: mocks.notFound }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("./company/actions", () => ({ updateCompanyAction: vi.fn() }));
vi.mock("../../users/user-status-menu", () => ({
  UserStatusMenu: () => <button>Account actions</button>,
}));
import CompanyHub from "./page";
const run = () =>
  CompanyHub({
    params: Promise.resolve({ organizationId: "org" }),
    searchParams: Promise.resolve({}),
  });
it("does not display or edit a company returned for a different identity", async () => {
  mocks.get.mockResolvedValue({ data: { id: "other", name: "Another company", status: "active" } });
  render(await run());
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this section — try again");
  expect(screen.queryByRole("button", { name: "Save company profile" })).toBeNull();
  expect(mocks.get).toHaveBeenCalledTimes(1);
});
beforeEach(() => {
  mocks.get.mockReset();
  mocks.get.mockImplementation(async (path) => {
    if (path.endsWith("/company"))
      return { data: { id: "org", name: "PalmPay", status: "active", currency: "NGN" } };
    if (path.endsWith("/members"))
      return {
        data: {
          items: [
            {
              user: {
                id: "user",
                full_name: "Amina Yusuf",
                email: "amina@example.invalid",
                role: "advertiser",
                status: "active",
              },
              membership: { role: "owner", status: "active" },
            },
          ],
          total: 1,
        },
      };
    return { data: { items: [], total: 0 } };
  });
});
it("keeps company details, company-only account and exact scoped reads together", async () => {
  render(await run());
  expect(screen.getByRole("heading", { name: "PalmPay" })).toBeInTheDocument();
  expect(screen.getByText("Amina Yusuf")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save company profile" })).toBeInTheDocument();
  expect(screen.queryByText("Invite person")).not.toBeInTheDocument();
  expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/complaints", {
    params: { query: { organization_id: "org", limit: 25, offset: 0 } },
  });
  expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/audit-events", {
    params: { query: { entity_id: "org", limit: 25, offset: 0 } },
  });
});
it("limits company hub reads to four concurrent requests", async () => {
  const original = mocks.get.getMockImplementation()!;
  let active = 0,
    peak = 0;
  mocks.get.mockImplementation(async (path, options) => {
    active++;
    peak = Math.max(peak, active);
    await new Promise((resolve) => setTimeout(resolve, 5));
    active--;
    if (path.endsWith("/campaigns"))
      return {
        data: {
          items: Array.from({ length: 8 }, (_, i) => ({
            id: `campaign${i}`,
            organization_id: "org",
            name: `Campaign ${i}`,
            status: "active",
          })),
          total: 8,
        },
      };
    if (path.endsWith("/commercial")) return { data: { invoices: [], settlements: [] } };
    return original(path, options);
  });
  render(await run());
  expect(screen.queryByRole("alert")).toBeNull();
  expect(peak).toBe(4);
});
it("shows exact invoice funding and recorded refunds without inventing payment events", async () => {
  const original = mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation(async (path, options) => {
    if (path.endsWith("/campaigns"))
      return {
        data: {
          items: [
            { id: "campaign", organization_id: "org", name: "PalmPay Wuse", status: "active" },
          ],
          total: 1,
        },
      };
    if (path.endsWith("/commercial"))
      return {
        data: {
          invoices: [
            {
              id: "invoice",
              organization_id: "org",
              campaign_id: "campaign",
              invoice_number: "INV-001",
              status: "issued",
              payment_status: "part_paid",
              currency: "NGN",
              effective_obligation_amount: "9007199254740993.01",
              funded_amount: "100.00",
              issued_at: "2026-09-03T00:00:00Z",
            },
          ],
          settlements: [
            {
              id: "refund",
              disposition: "refund_recorded",
              currency: "NGN",
              amount: "25.00",
              recorded_at: "2026-09-04T00:00:00Z",
            },
          ],
        },
      };
    return original(path, options);
  });
  render(await run());
  expect(
    screen.getByText(/Amount: ₦9,007,199,254,740,993.01.*Recorded funding: ₦100.00/),
  ).toBeVisible();
  expect(screen.getByText(/Refund recorded.*₦25.00/)).toBeVisible();
  expect(screen.queryByText(/Payment recorded/)).toBeNull();
});
it("shows a single plain failure for a failed section", async () => {
  const original = mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation(async (path, options) => {
    if (path.endsWith("/members")) throw new Error("offline");
    return original(path, options);
  });
  render(await run());
  expect(screen.getAllByRole("alert")).toHaveLength(1);
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this section — try again");
});
it("distinguishes missing companies from a failed read", async () => {
  mocks.get.mockRejectedValue(new ApiError(404, { code: "NOT_FOUND", message: "missing" }));
  await expect(run()).rejects.toThrow("NOT_FOUND");
  mocks.get.mockRejectedValue(new Error("offline"));
  render(await run());
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this section — try again");
});
it("keeps each company section and its independent page position scoped to the company", async () => {
  const original = mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation(async (path, options) => {
    if (path.endsWith("/members")) {
      const response = await original(path, options);
      return { data: { ...response.data, total: 80 } };
    }
    if (path.endsWith("/complaints"))
      return {
        data: {
          total: 80,
          items: [
            {
              id: "complaint",
              raised_by_name: "Amina Yusuf",
              category: "billing_or_invoice",
              status: "open",
              created_at: "2026-09-03T00:00:00Z",
            },
          ],
        },
      };
    if (path.endsWith("/audit-events"))
      return {
        data: {
          total: 80,
          items: [
            {
              id: "event",
              actor_email: null,
              created_at: "2026-09-03T00:00:00Z",
              action: "company_profile_updated",
              metadata: { source: "company" },
            },
          ],
        },
      };
    return original(path, options);
  });
  render(
    await CompanyHub({
      params: Promise.resolve({ organizationId: "org" }),
      searchParams: Promise.resolve({
        people_offset: "25",
        complaint_offset: "25",
        activity_offset: "25",
      }),
    }),
  );
  expect(screen.getByRole("link", { name: /Amina Yusuf ·/ })).toHaveAttribute(
    "href",
    "/admin/support?tab=complaints&organization_id=org&complaint=complaint",
  );
  expect(screen.getByText(/System ·/)).toBeVisible();
  const nextLinks = screen.getAllByRole("link", { name: /Next/ });
  expect(nextLinks.map((link) => link.getAttribute("href"))).toEqual([
    "/admin/advertisers/org?people_offset=50&complaint_offset=25&activity_offset=25#people",
    "/admin/advertisers/org?people_offset=25&complaint_offset=50&activity_offset=25#complaints",
    "/admin/advertisers/org?people_offset=25&complaint_offset=25&activity_offset=50#activity",
  ]);
});
it("shows separate plain failures when company complaints and activity fail", async () => {
  const original = mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation(async (path, options) => {
    if (path.endsWith("/complaints") || path.endsWith("/audit-events")) throw new Error("offline");
    return original(path, options);
  });
  render(await run());
  expect(screen.getAllByRole("alert")).toHaveLength(2);
  for (const alert of screen.getAllByRole("alert"))
    expect(alert).toHaveTextContent("Couldn't load this section — try again");
  expect(screen.getByText("Amina Yusuf")).toBeVisible();
});
