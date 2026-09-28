import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  redirect: vi.fn((url: string) => {
    throw new Error(`REDIRECT:${url}`);
  }),
}));

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));
vi.mock("@/lib/complaints/actions", () => ({
  raiseDriverComplaintAction: vi.fn(),
  raiseAdvertiserComplaintAction: vi.fn(),
  followUpDriverComplaintAction: vi.fn(),
  followUpAdvertiserComplaintAction: vi.fn(),
}));

import { ComplaintConversationPage, ComplaintHelpPage } from "./complainant-pages";

const ID = "00000000-0000-4000-8000-0000000000aa";
const TRIP = "00000000-0000-4000-8000-0000000000bb";

const summary = {
  id: ID,
  category: "trip_or_tracking",
  status: "answered",
  reference_type: "trip",
  reference_label: "Trip on 3 Sep 2026, 08:15 (Nigeria time, WAT)",
  created_at: "2026-09-03T07:15:00Z",
  last_message_at: "2026-09-03T09:00:00Z",
  waiting_on_you: true,
};

const options = {
  campaigns: [{ id: "00000000-0000-4000-8000-0000000000cc", label: "Lagos Launch" }],
  trips: [{ id: TRIP, label: "Trip on 3 Sep 2026, 08:15 (Nigeria time, WAT)" }],
  payouts: [],
};

describe("complainant Help page", () => {
  beforeEach(() => {
    mocks.get.mockReset();
    mocks.redirect.mockClear();
  });

  it("lists complaints in plain words with links and a raise form", async () => {
    mocks.get.mockImplementation(async (path: string) =>
      path.endsWith("reference-options") ? { data: options } : { data: { items: [summary] } },
    );

    render(await ComplaintHelpPage({ party: "driver" }));

    expect(screen.getByRole("heading", { level: 1, name: "Help" })).toBeInTheDocument();
    const row = screen.getByRole("link", { name: /Trips and tracking/ });
    expect(row).toHaveAttribute("href", `/driver/help/${ID}`);
    expect(within(row).getByText("Terrax Media replied")).toBeInTheDocument();
    expect(within(row).getByText(/3 Sep 2026, 10:00 WAT/)).toBeInTheDocument();
    expect(screen.getByText("Terrax Media replied to one of your complaints.")).toBeVisible();
    // Record identifiers are option values only, never visible text.
    expect(screen.queryByText(new RegExp(TRIP))).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Lagos Launch" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Jobs" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Payouts" })).not.toBeInTheDocument();
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/driver/complaints");
  });

  it("shows the empty state and a form that explains missing records", async () => {
    mocks.get.mockImplementation(async (path: string) => {
      if (path.endsWith("reference-options")) throw new Error("offline");
      return { data: { items: [] } };
    });

    render(await ComplaintHelpPage({ party: "advertiser" }));

    expect(screen.getByText("You haven't raised any complaints.")).toBeInTheDocument();
    expect(screen.getByText(/Your campaigns couldn't be loaded/)).toBeInTheDocument();
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/advertiser/complaints/reference-options");
  });

  it("offers a retry when the list fails, and hides the form without an account", async () => {
    mocks.get.mockImplementation(async () => ({}));
    const { unmount } = render(await ComplaintHelpPage({ party: "driver" }));
    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute("href", "/driver/help");
    unmount();

    mocks.get.mockImplementation(async () => {
      throw new ApiError(404, { code: "DRIVER_PROFILE_NOT_FOUND", message: "" });
    });
    render(await ComplaintHelpPage({ party: "driver" }));
    expect(screen.getByText(/once your driver profile is set up/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send complaint" })).not.toBeInTheDocument();
  });

  it("sends a signed-out user to sign in", async () => {
    mocks.get.mockImplementation(async () => {
      throw new ApiError(401, { code: "INVALID_TOKEN", message: "" });
    });
    await expect(ComplaintHelpPage({ party: "driver" })).rejects.toThrow("REDIRECT:/login");
  });
});

describe("complainant conversation page", () => {
  beforeEach(() => {
    mocks.get.mockReset();
  });

  it("shows who said what without staff names or identifiers", async () => {
    mocks.get.mockResolvedValue({
      data: {
        ...summary,
        status: "resolved",
        messages: [
          { sender: "your_team", body: "Invoice is wrong", sent_at: "2026-09-03T07:15:00Z" },
          { sender: "you", body: "Still wrong", sent_at: "2026-09-03T08:00:00Z" },
          { sender: "terrax_media", body: "Corrected", sent_at: "2026-09-03T09:00:00Z" },
        ],
      },
    });

    render(await ComplaintConversationPage({ party: "advertiser", complaintId: ID }));

    const thread = screen.getByRole("list", { name: "Conversation" });
    expect(within(thread).getByText(/Someone in your team/)).toBeInTheDocument();
    expect(within(thread).getByText(/^You ·/)).toBeInTheDocument();
    expect(within(thread).getByText(/Terrax Media · 3 Sep 2026, 10:00 WAT/)).toBeInTheDocument();
    expect(screen.getByText(/^Trip on 3 Sep 2026/)).toBeInTheDocument();
    expect(screen.getByText(/reply below and it will reopen/)).toBeInTheDocument();
    expect(screen.queryByText(ID)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← All complaints" })).toHaveAttribute(
      "href",
      "/advertiser/help",
    );
  });

  it("handles a missing complaint and a failed read", async () => {
    mocks.get.mockRejectedValueOnce(
      new ApiError(404, { code: "COMPLAINT_NOT_FOUND", message: "" }),
    );
    const { unmount } = render(
      await ComplaintConversationPage({ party: "driver", complaintId: ID }),
    );
    expect(screen.getByText("Complaint not found")).toBeInTheDocument();
    unmount();

    mocks.get.mockRejectedValueOnce(new Error("offline"));
    render(await ComplaintConversationPage({ party: "driver", complaintId: ID }));
    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute(
      "href",
      `/driver/help/${ID}`,
    );
  });

  it("sends a signed-out user to sign in", async () => {
    mocks.get.mockImplementation(async () => {
      throw new ApiError(403, { code: "FORBIDDEN_ROLE", message: "" });
    });
    await expect(ComplaintConversationPage({ party: "driver", complaintId: ID })).rejects.toThrow(
      "REDIRECT:/login",
    );
  });
});
