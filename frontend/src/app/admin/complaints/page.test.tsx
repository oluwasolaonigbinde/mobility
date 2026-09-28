import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/complaints/actions", () => ({
  replyToComplaintAction: vi.fn(),
  updateComplaintAction: vi.fn(),
}));

import CustomerServiceInbox from "./page";
import StaffComplaintPage from "./[complaintId]/page";

const ID = "00000000-0000-4000-8000-0000000000aa";

const item = {
  id: ID,
  party: "driver",
  category: "pay_or_payout",
  status: "open",
  raised_by_user_id: "u1",
  raised_by_name: "Dayo Driver",
  driver_profile_id: "d1",
  advertiser_organization_id: null,
  party_name: "Dayo Driver",
  reference_type: "payout",
  reference_id: "e1",
  reference_label: "Trip pay ₦2,678.94 · 3 Sep 2026",
  assigned_to_user_id: null,
  assigned_to_name: null,
  revision: 1,
  created_at: "2026-09-03T07:15:00Z",
  last_message_at: "2026-09-03T07:15:00Z",
  resolved_at: null,
};

describe("Customer Service inbox", () => {
  beforeEach(() => {
    mocks.get.mockReset();
  });

  it("defaults to complaints needing a reply and links each one", async () => {
    mocks.get.mockResolvedValue({ data: { items: [item], total: 1, limit: 25, offset: 0 } });

    render(await CustomerServiceInbox({ searchParams: Promise.resolve({}) }));

    expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/complaints", {
      params: { query: { limit: 25, offset: 0, assigned_to_me: false, status: "open" } },
    });
    const row = screen.getByRole("link", { name: /Dayo Driver/ });
    expect(row).toHaveAttribute("href", `/admin/complaints/${ID}`);
    expect(within(row).getByText("Needs a reply")).toBeInTheDocument();
    expect(within(row).getByText(/Unassigned/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Needs a reply" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("filters to mine and all, with empty and error states", async () => {
    mocks.get.mockResolvedValue({ data: { items: [], total: 0, limit: 25, offset: 0 } });
    const { unmount } = render(
      await CustomerServiceInbox({ searchParams: Promise.resolve({ status: "", mine: "true" }) }),
    );
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/complaints", {
      params: { query: { limit: 25, offset: 0, assigned_to_me: true } },
    });
    expect(screen.getByText("No complaints match this view.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Show everyone's" })).toBeInTheDocument();
    unmount();

    mocks.get.mockResolvedValueOnce({ data: { items: [], total: 0, limit: 25, offset: 0 } });
    const second = render(await CustomerServiceInbox({ searchParams: Promise.resolve({}) }));
    expect(screen.getByText("No complaint is waiting for a reply.")).toBeInTheDocument();
    second.unmount();

    mocks.get.mockRejectedValueOnce(new Error("offline"));
    render(await CustomerServiceInbox({ searchParams: Promise.resolve({ status: "resolved" }) }));
    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute(
      "href",
      "/admin/complaints?status=resolved&mine=false&offset=0",
    );
  });
});

describe("staff complaint page", () => {
  beforeEach(() => {
    mocks.get.mockReset();
  });

  it("shows the party, record, thread with names and the staff forms", async () => {
    mocks.get.mockImplementation(async (path: string) =>
      path === "/api/v1/admin/users"
        ? { data: { items: [{ id: "s1", full_name: "Bola Staff" }], total: 1 } }
        : {
            data: {
              ...item,
              assigned_to_user_id: "s1",
              assigned_to_name: "Bola Staff",
              messages: [
                {
                  id: "m1",
                  author_side: "complainant",
                  author_user_id: "u1",
                  author_name: "Dayo Driver",
                  body: "Paid short",
                  status_after: "open",
                  sent_at: "2026-09-03T07:15:00Z",
                },
                {
                  id: "m2",
                  author_side: "staff",
                  author_user_id: "s1",
                  author_name: "Bola Staff",
                  body: "Checking",
                  status_after: "answered",
                  sent_at: "2026-09-03T08:15:00Z",
                },
              ],
            },
          },
    );

    render(await StaffComplaintPage({ params: Promise.resolve({ complaintId: ID }) }));

    expect(screen.getByRole("heading", { level: 1, name: "Dayo Driver" })).toBeInTheDocument();
    expect(screen.getByText("Payout: Trip pay ₦2,678.94 · 3 Sep 2026")).toBeInTheDocument();
    expect(screen.getByText(/Bola Staff \(Terrax Media\) · 3 Sep 2026, 09:15 WAT/)).toBeVisible();
    expect(screen.getByRole("option", { name: "Bola Staff" })).toBeInTheDocument();
    expect(screen.getByLabelText("Reply as Terrax Media")).toBeInTheDocument();
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/users", {
      params: { query: { role: "admin", status: "active", limit: 100 } },
    });
  });

  it("says when a complaint is not found", async () => {
    mocks.get.mockImplementation(async (path: string) => {
      if (path === "/api/v1/admin/users") throw new Error("offline");
      throw new ApiError(404, { code: "COMPLAINT_NOT_FOUND", message: "" });
    });
    render(await StaffComplaintPage({ params: Promise.resolve({ complaintId: ID }) }));
    expect(screen.getByText("Complaint not found")).toBeInTheDocument();
  });

  it("offers a retry when the complaint can't be loaded", async () => {
    mocks.get.mockImplementation(async () => {
      throw new Error("offline");
    });
    render(await StaffComplaintPage({ params: Promise.resolve({ complaintId: ID }) }));
    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute(
      "href",
      `/admin/complaints/${ID}`,
    );
  });
});
