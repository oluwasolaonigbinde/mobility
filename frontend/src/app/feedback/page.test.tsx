import { render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ get: vi.fn(), client: vi.fn() }));
vi.mock("@/lib/api/client", () => ({
  createApiClient: (...args: unknown[]) => {
    mocks.client(...args);
    return { GET: mocks.get };
  },
}));
vi.mock("./actions", () => ({ setFeedbackStatusAction: vi.fn() }));

import FeedbackPage, { metadata } from "./page";

const item = {
  id: "10000000-0000-4000-8000-000000000001",
  name: "Ada",
  page_path: "/advertiser/campaigns",
  portal: "advertiser",
  message: "The total looks wrong. It shows zero.",
  status: "opened",
  created_at: "2026-11-19T10:00:00Z",
  resolved_at: null,
  signed_in: true,
  has_screenshot: true,
  screenshot_width: 1200,
  screenshot_height: 750,
  pin_x: 0.25,
  pin_y: 0.5,
};
const open = async (query: Record<string, string> = {}) =>
  render(await FeedbackPage({ searchParams: Promise.resolve(query) }));

beforeEach(() => {
  mocks.get.mockReset();
  mocks.client.mockReset();
});

it("is kept out of search engines", () => {
  expect(metadata.robots).toEqual({ index: false, follow: false });
});

it("says when feedback is switched off, without asking for a password", async () => {
  mocks.get.mockRejectedValue(new ApiError(404, { code: "FEEDBACK_NOT_ENABLED", message: "x" }));
  await open();
  expect(screen.getByRole("heading", { name: "Feedback" })).toBeInTheDocument();
  expect(screen.getByText("Feedback isn't switched on for this site.")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.queryByLabelText(/password/i)).toBeNull();
});

it("lists a page of notes with counts, portal link, screenshot and pin", async () => {
  mocks.get.mockResolvedValue({
    data: { items: [item], total: 12, counts: { opened: 12, resolved: 3 }, limit: 10, offset: 10 },
  });
  await open({ page: "2" });
  // The list opens straight away: a plain API client, no session or review token.
  expect(mocks.client).toHaveBeenCalledWith();
  expect(screen.queryByLabelText(/password/i)).toBeNull();
  expect(mocks.get).toHaveBeenCalledWith("/api/v1/feedback/review", {
    params: { query: { status: "opened", limit: 10, offset: 10 } },
  });
  const tabs = screen.getByRole("navigation", { name: "Feedback status" });
  expect(within(tabs).getByRole("link", { name: /Opened\s*12/ })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(within(tabs).getByRole("link", { name: /Resolved\s*3/ })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "The total looks wrong." })).toBeInTheDocument();
  expect(
    screen.getByText(
      (_, el) =>
        el?.tagName === "P" &&
        /^Ada · \d+ Nov 2026, \d\d:\d\d · Advertiser \/advertiser/.test(el.textContent ?? ""),
    ),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "/advertiser/campaigns" })).toHaveAttribute(
    "href",
    "/advertiser/campaigns",
  );
  expect(screen.getByRole("link", { name: "Open page" })).toHaveAttribute(
    "href",
    "/advertiser/campaigns",
  );
  expect(screen.getByRole("img")).toHaveAttribute("src", `/api/feedback/${item.id}/screenshot`);
  expect(screen.getByRole("button", { name: "Mark resolved" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Export CSV" })).toHaveAttribute(
    "href",
    "/api/feedback/export",
  );
  expect(screen.getByText(/Page 2 of 2/)).toBeInTheDocument();
});

it("shows Reopen on resolved notes, an empty state, and an error state", async () => {
  mocks.get.mockResolvedValue({
    data: {
      items: [{ ...item, status: "resolved", page_path: "//evil" }],
      total: 1,
      counts: { opened: 0, resolved: 1 },
      limit: 10,
      offset: 0,
    },
  });
  await open({ status: "resolved" });
  expect(screen.getByRole("button", { name: "Reopen" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Open page" })).toBeNull();

  mocks.get.mockResolvedValue({
    data: { items: [], total: 0, counts: { opened: 0, resolved: 0 }, limit: 10, offset: 0 },
  });
  await open();
  expect(screen.getByText("No open feedback.")).toBeInTheDocument();

  mocks.get.mockRejectedValue(new Error("down"));
  await open();
  expect(screen.getByRole("alert")).toHaveTextContent("Feedback can't be loaded right now.");
});
