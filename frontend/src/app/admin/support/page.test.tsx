import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { ApiError } from "@/lib/api/errors";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("../hub-drawer", () => ({
  HubDrawer: ({ children, closeHref }: { children: ReactNode; closeHref: string }) => (
    <section aria-label="Drawer">
      <a href={closeHref}>Close</a>
      {children}
    </section>
  ),
}));
vi.mock("../operation-form", () => ({
  OperationForm: ({ id }: { id: string }) => <button>Record outcome {id}</button>,
}));
vi.mock("@/components/complaints/forms", () => ({
  ComplaintMessageForm: () => <button>Send reply</button>,
  ComplaintUpdateForm: () => <button>Save assignment</button>,
}));
vi.mock("@/lib/complaints/actions", () => ({
  replyToComplaintAction: vi.fn(),
  updateComplaintAction: vi.fn(),
}));
import Support from "./page";

const complaint = {
  id: "complaint",
  category: "pay_or_payout",
  status: "open",
  party_name: "Dayo Driver",
  raised_by_user_id: "user",
  advertiser_organization_id: null,
  last_message_at: "2026-09-03T07:15:00Z",
  messages: [
    {
      id: "message",
      author_name: "Dayo Driver",
      sent_at: "2026-09-03T07:15:00Z",
      body: "Paid short",
    },
  ],
};
const task = {
  id: "task",
  driver_profile_id: "driver",
  driver_name: "Ada Driver",
  masked_phone: "+234 *** *** 1234",
  purpose: "activity_follow_up",
  status: "open",
  created_at: "2026-09-14T10:00:00Z",
  completed_at: null,
  completion_outcome: null,
};
const page = (query: Record<string, string> = {}) =>
  Support({ searchParams: Promise.resolve(query) });

describe("Support work lists", () => {
  beforeEach(() => {
    get.mockReset();
  });
  it("shows named current phone work with masked numbers and an empty received-code form", async () => {
    get.mockImplementation(async (path) => ({
      data: {
        items: path.endsWith("phone-verification-challenges")
          ? [
              {
                id: "challenge",
                driver_profile_id: "driver",
                driver_name: "Damilola Akinwale",
                masked_phone: "+44••••0114",
              },
            ]
          : [],
        total: path.endsWith("phone-verification-challenges") ? 1 : 0,
      },
    }));
    render(await page({ tab: "contact" }));
    expect(screen.getByRole("link", { name: "Damilola Akinwale" })).toHaveAttribute(
      "href",
      "/admin/drivers/driver#phone",
    );
    expect(screen.getByText("+44••••0114")).toBeVisible();
    expect(screen.getByRole("button", { name: "Record phone verification" })).toBeVisible();
    expect(screen.queryByLabelText("Code received")).toBeNull();
  });
  it("keeps the driver and list filters in row, page and close links", async () => {
    get.mockResolvedValue({ data: { items: [complaint], total: 30 } });
    render(await page({ user_id: "user", offset: "25" }));
    expect(get).toHaveBeenCalledWith("/api/v1/admin/complaints", {
      params: { query: expect.objectContaining({ user_id: "user", offset: 25, status: "open" }) },
    });
    expect(screen.getByRole("link", { name: /Dayo Driver/ })).toHaveAttribute(
      "href",
      "/admin/support?user_id=user&offset=25&tab=complaints&complaint=complaint",
    );
    expect(screen.getByRole("link", { name: /Prev/ })).toHaveAttribute(
      "href",
      "/admin/support?user_id=user&offset=0&tab=complaints",
    );
  });
  it("loads an off-page complaint independently and keeps its conversation", async () => {
    get.mockImplementation(async (path) => ({
      data: path.endsWith("{complaint_id}") ? complaint : { items: [], total: 0 },
    }));
    render(await page({ complaint: "complaint", user_id: "user", offset: "25" }));
    expect(screen.getByText("Paid short")).toBeVisible();
    expect(screen.getByRole("button", { name: "Send reply" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Close" })).toHaveAttribute(
      "href",
      "/admin/support?user_id=user&offset=25&tab=complaints",
    );
  });
  it("does not expose another company's selected complaint", async () => {
    get.mockImplementation(async (path) => ({
      data: path.endsWith("{complaint_id}")
        ? { ...complaint, advertiser_organization_id: "other" }
        : { items: [], total: 0 },
    }));
    render(await page({ complaint: "complaint", organization_id: "company" }));
    expect(screen.getByText("Complaint not found for these filters.")).toBeVisible();
    expect(screen.queryByText("Paid short")).toBeNull();
  });
  it.each([404, 503])("separates a selected complaint %s from an empty list", async (status) => {
    get.mockImplementation(async (path) => {
      if (path.endsWith("{complaint_id}"))
        throw new ApiError(status, { code: "FAILED", message: "" });
      return { data: { items: [], total: 0 } };
    });
    render(await page({ complaint: "missing" }));
    expect(
      status === 404
        ? screen.getByText("Complaint not found for these filters.")
        : screen.getByRole("alert"),
    ).toBeVisible();
  });
  it("locates a scoped contact on a later page and permits current work", async () => {
    get.mockImplementation(async (_path, options) => ({
      data: {
        items:
          options.params.query.limit === 25
            ? []
            : options.params.query.offset === 0
              ? [{ ...task, id: "first" }]
              : [task],
        total: 2,
      },
    }));
    render(await page({ tab: "contact", driver_profile_id: "driver", task: "task" }));
    expect(get).toHaveBeenCalledWith("/api/v1/admin/manual-driver-contact-tasks", {
      params: { query: { limit: 100, offset: 1, driver_profile_id: "driver", history: false } },
    });
    expect(screen.getByRole("button", { name: "Record outcome task" })).toBeVisible();
  });
  it("keeps contact history read-only and never labels a missing name as empty", async () => {
    get.mockResolvedValue({ data: { items: [task], total: 1 } });
    const first = render(await page({ tab: "contact", task: "task", history: "true" }));
    expect(screen.queryByRole("button", { name: /Record outcome/ })).toBeNull();
    expect(screen.getByText("Recorded history.")).toBeVisible();
    first.unmount();
    get.mockResolvedValue({ data: { items: [{ ...task, driver_name: null }], total: 1 } });
    render(await page({ tab: "contact" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this section — try again");
    expect(screen.queryByText("No contact tasks match these filters.")).toBeNull();
  });
});
