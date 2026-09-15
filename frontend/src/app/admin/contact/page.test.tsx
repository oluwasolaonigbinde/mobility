import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("../operation-form", () => ({
  OperationForm: ({ id, contact }: { id: string; contact?: boolean }) => (
    <div>
      Record outcome {id} {contact ? "contact" : ""}
    </div>
  ),
}));

import ContactQueue from "./page";

const task = {
  id: "task-1",
  driver_name: "Ada Driver",
  masked_phone: "+234 *** *** 1234",
  purpose: "activity_follow_up",
  status: "open",
  created_at: "2026-09-14T10:00:00Z",
  completed_at: null,
  completion_outcome: null,
};

const props = (params: { offset?: string; history?: string } = {}) => ({
  searchParams: Promise.resolve(params),
});

describe("manual driver contact queue", () => {
  beforeEach(() => mocks.get.mockReset());

  it("offers outcome recording only for current unfinished work", async () => {
    mocks.get.mockResolvedValue({
      data: {
        items: [
          task,
          {
            ...task,
            id: "task-2",
            driver_name: null,
            completed_at: "2026-09-14T12:00:00Z",
            completion_outcome: "reached",
          },
        ],
        total: 2,
      },
    });
    render(await ContactQueue(props({ offset: "-1" })));
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/manual-driver-contact-tasks", {
      params: { query: { limit: 25, offset: 0, history: false } },
    });
    expect(screen.getByText("Current authorized work and completed outcomes")).toBeTruthy();
    expect(screen.getByText("Ada Driver · +234 *** *** 1234")).toBeTruthy();
    expect(screen.getAllByText(/activity follow up · open/)).toHaveLength(2);
    expect(screen.getByText("Record outcome task-1 contact")).toBeTruthy();
    expect(screen.getByText("Driver name unavailable · +234 *** *** 1234")).toBeTruthy();
    expect(screen.getByText(/Outcome: reached/)).toBeTruthy();
    expect(screen.queryByText("Record outcome task-2 contact")).toBeNull();
    expect(screen.getByRole("checkbox")).not.toBeChecked();
  });

  it("keeps blocked history read only", async () => {
    mocks.get.mockResolvedValue({ data: { items: [task], total: 30 } });
    render(await ContactQueue(props({ history: "true", offset: "25" })));
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/manual-driver-contact-tasks", {
      params: { query: { limit: 25, offset: 25, history: true } },
    });
    expect(screen.getByText("Recorded task history")).toBeTruthy();
    expect(screen.getByText(/Historical record. Return to current work/)).toBeTruthy();
    expect(screen.queryByText(/Record outcome/)).toBeNull();
    expect(screen.getByRole("checkbox")).toBeChecked();
    const pageLinks = screen
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"))
      .filter((href): href is string => Boolean(href) && href !== "#");
    expect(pageLinks).toContain("/admin/contact?history=true&offset=0");
    expect(pageLinks.every((href) => href.startsWith("/admin/contact?history=true"))).toBe(true);
  });

  it("separates an empty view from an unavailable queue", async () => {
    mocks.get.mockResolvedValue({ data: { items: [], total: 0 } });
    const { unmount } = render(await ContactQueue(props()));
    expect(screen.getByText("No contact tasks match this view.")).toBeTruthy();
    unmount();

    mocks.get.mockResolvedValue({ data: undefined });
    render(await ContactQueue(props()));
    expect(screen.getByRole("alert")).toHaveTextContent("No empty or complete result");
    expect(screen.queryByText("No contact tasks match this view.")).toBeNull();
  });
});
