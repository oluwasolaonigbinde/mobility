import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { get, requireRole } = vi.hoisted(() => ({ get: vi.fn(), requireRole: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));

import AdminWorkQueuePage from "./page";

function item(name: string) {
  return screen.getByRole("link", { name: new RegExp(`^${name}`) });
}

describe("admin Waiting for you work queue (D38e)", () => {
  beforeEach(() => {
    requireRole.mockResolvedValue({ user: { role: "admin" } });
    get.mockReset().mockImplementation(async () => ({ data: { items: [], total: 0 } }));
  });

  it("groups the queue by department and links each item to its page", async () => {
    get.mockImplementation(async (path: string, options?: { params?: { query?: object } }) => {
      if (path === "/api/v1/admin/fraud-flags") return { data: { items: [], total: 3 } };
      if (path === "/api/v1/admin/installation-evidence/pending") {
        return { data: { items: [{ id: "a" }, { id: "b" }] } };
      }
      if (
        path === "/api/v1/admin/payout-batches/summaries" &&
        (options?.params?.query as { batch_status?: string }).batch_status === "failed"
      ) {
        return { data: { items: [], total: 1 } };
      }
      return { data: { items: [], total: 0 } };
    });

    render(await AdminWorkQueuePage());

    expect(screen.getByRole("heading", { level: 1, name: "Waiting for you" })).toBeInTheDocument();
    for (const section of ["Operations", "Compliance", "Finance", "Customer Service", "Admin"]) {
      expect(screen.getByRole("heading", { level: 2, name: section })).toBeInTheDocument();
    }
    expect(item("Trip reviews")).toHaveAttribute("href", "/admin/fraud");
    expect(within(item("Trip reviews")).getByText("3")).toBeInTheDocument();
    expect(item("Installation photos to review")).toHaveAttribute("href", "/admin/approvals");
    expect(within(item("Installation photos to review")).getByText("2")).toBeInTheDocument();
    expect(within(item("Payout batches with failed payments")).getByText("1")).toBeInTheDocument();
    expect(
      within(item("Payout batches to approve or send")).getByText("Nothing waiting"),
    ).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/api/v1/admin/campaign-assignments", {
      params: { query: { limit: 1, status: "accepted" } },
    });
  });

  it("shows Couldn't check for a failed read without hiding the other items", async () => {
    get.mockImplementation(async (path: string) => {
      if (path === "/api/v1/admin/fraud-flags") return { error: { code: "X" } };
      if (path === "/api/v1/admin/manual-driver-contact-tasks") throw new Error("offline");
      if (path === "/api/v1/admin/campaign-change-requests/pending") return {};
      return { data: { items: [], total: 0 } };
    });

    render(await AdminWorkQueuePage());

    for (const name of ["Trip reviews", "Driver contact tasks", "Campaign changes to review"]) {
      expect(within(item(name)).getByText("Couldn't check")).toBeInTheDocument();
    }
    expect(within(item("Campaigns to review")).getByText("Nothing waiting")).toBeInTheDocument();
  });
});
