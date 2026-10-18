import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({ get: vi.fn(), role: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/auth/current-user", () => ({
  requireRole: mocks.role,
  isAdvertiserViewer: (me: { viewer?: boolean }) => Boolean(me.viewer),
}));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("notFound");
  },
  redirect: (path: string) => {
    throw new Error(`redirect:${path}`);
  },
}));
vi.mock("./commercial-panel", () => ({
  CommercialPanel: () => (
    <section>
      <h2>Quotation</h2>
    </section>
  ),
}));
vi.mock("./campaign-change-panel", () => ({
  CampaignChangePanel: () => <button>Request campaign change</button>,
}));
vi.mock("./status-actions", () => ({ StatusActions: () => <button>Submit for review</button> }));
vi.mock("./creative-status-actions", () => ({
  CreativeStatusActions: () => <button>Submit artwork</button>,
}));
import Page from "./page";
const campaign = {
  id: "one",
  name: "Wuse lunch rush",
  status: "active",
  currency: "NGN",
  budget_amount: "1000",
  start_at: null,
  end_at: null,
  description: "Lunch for the city",
};
const input = { params: Promise.resolve({ campaignId: "one" }), searchParams: Promise.resolve({}) };
function ready(path: string) {
  if (path.endsWith("/commercial"))
    return { data: { invoices: [], terms: {}, budget_evaluations: [] } };
  if (path.endsWith("/summary")) return { data: { assignments: { active: 8 } } };
  if (
    ["/creatives", "/zones", "/review-history", "/change-requests"].some((suffix) =>
      path.endsWith(suffix),
    )
  )
    return { data: { items: [], total: 0 } };
  return { data: campaign };
}
beforeEach(() => {
  mocks.get.mockReset().mockImplementation(async (path: string) => ready(path));
  mocks.role.mockResolvedValue({ viewer: false });
});
it("leads with status and one next action, keeping quotation and changes closed", async () => {
  const { container } = render(await Page(input));
  expect(screen.getByRole("heading", { name: campaign.name })).toBeInTheDocument();
  expect(
    screen.getByText("Your campaign is running. Your brand is out on the road."),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /See results/ })).toHaveAttribute(
    "href",
    "/advertiser/campaigns/one/report",
  );
  expect(container.querySelector("#details")).not.toHaveAttribute("open");
  expect(container.querySelector("#manage")).not.toHaveAttribute("open");
  expect(document.body).not.toHaveTextContent(
    /driver pay|GPS signal quality|fraud flags|cancel permanently/i,
  );
});
it("keeps campaign visuals and safe controls when the summary is gated", async () => {
  mocks.get.mockImplementation(async (path: string) => {
    if (path.endsWith("/summary"))
      throw new ApiError(409, { code: "DISCLOSURE_SUPPRESSED", message: "Sensitive detail" });
    return ready(path);
  });
  render(await Page(input));
  expect(screen.getByRole("heading", { name: "Your advert" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Where your advert goes" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /See results/ })).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent("Sensitive detail");
});
it("opens Manage to a prepared request, never permanent cancellation", async () => {
  const user = userEvent.setup();
  render(await Page(input));
  await user.click(screen.getByText("Manage"));
  expect(screen.getByRole("button", { name: "Ask Terrax to cancel" })).toBeDisabled();
  expect(screen.getByRole("textbox", { name: "Why would you like to cancel?" })).toBeVisible();
});
it("withholds write controls for a company viewer", async () => {
  mocks.role.mockResolvedValue({ viewer: true });
  render(await Page(input));
  expect(screen.queryByText("Manage")).toBeNull();
  expect(screen.queryByRole("link", { name: "Edit artwork" })).toBeNull();
});
it("uses an available invoice as the next step before launch", async () => {
  mocks.get.mockImplementation(async (path: string) =>
    path.endsWith("/commercial")
      ? {
          data: {
            terms: {},
            invoices: [{ id: "invoice", status: "issued", payment_status: "unpaid" }],
            budget_evaluations: [],
          },
        }
      : path.endsWith("/creatives")
        ? {
            data: { items: [{ id: "art", status: "approved", name: "Art", stored_file_id: null }] },
          }
        : path.endsWith("/campaigns/{campaign_id}")
          ? { data: { ...campaign, status: "scheduled" } }
          : ready(path),
  );
  render(await Page(input));
  expect(screen.getByRole("link", { name: /Pay invoice/ })).toHaveAttribute(
    "href",
    "/advertiser/campaigns/one/invoices/invoice",
  );
});
it("keeps quotation errors visible by opening Details", async () => {
  const { container } = render(
    await Page({ ...input, searchParams: Promise.resolve({ commercial_error: "failed" }) }),
  );
  expect(container.querySelector("#details")).toHaveAttribute("open");
});
it("returns not found for an unowned campaign", async () => {
  mocks.get.mockRejectedValue(new ApiError(404, { code: "MISSING", message: "Missing" }));
  await expect(Page(input)).rejects.toThrow("notFound");
});
it.each(["prepared", "incomplete"])(
  "gives a viewer a reachable read-only next step for a %s draft",
  async (state) => {
    mocks.role.mockResolvedValue({ viewer: true });
    mocks.get.mockImplementation(async (path: string) => {
      if (path.endsWith("/campaigns/{campaign_id}"))
        return {
          data: {
            ...campaign,
            status: "draft",
            start_at: state === "prepared" ? "2026-10-01T00:00:00Z" : null,
            end_at: state === "prepared" ? "2026-11-01T00:00:00Z" : null,
          },
        };
      if (path.endsWith("/zones"))
        return {
          data: {
            items: state === "prepared" ? [{ id: "area", name: "Wuse II" }] : [],
            total: state === "prepared" ? 1 : 0,
          },
        };
      if (path.endsWith("/creatives"))
        return {
          data: {
            items:
              state === "prepared"
                ? [{ id: "art", name: "Art", status: "approved", stored_file_id: null }]
                : [],
          },
        };
      return ready(path);
    });
    render(await Page(input));
    expect(
      within(screen.getByRole("region", { name: "Next step" })).getByRole("link", {
        name: "View campaign details",
      }),
    ).toHaveAttribute("href", "/advertiser/campaigns/one?details=campaign#details");
    expect(screen.queryByText("Manage")).toBeNull();
    expect(
      screen.queryByRole("link", {
        name: /Review and submit|Add campaign details|Choose your area|Add or update artwork/,
      }),
    ).toBeNull();
  },
);
it.each(["draft", "rejected"])(
  "never implies %s readiness when the area read failed",
  async (status) => {
    mocks.get.mockImplementation(async (path: string) => {
      if (path.endsWith("/campaigns/{campaign_id}"))
        return {
          data: {
            ...campaign,
            status,
            start_at: "2026-10-01T00:00:00Z",
            end_at: "2026-11-01T00:00:00Z",
          },
        };
      if (path.endsWith("/zones"))
        throw new ApiError(503, { code: "DOWN", message: "Private area failure" });
      if (path.endsWith("/creatives"))
        return {
          data: { items: [{ id: "art", name: "Art", status: "approved", stored_file_id: null }] },
        };
      return ready(path);
    });
    render(await Page(input));
    expect(
      within(screen.getByRole("region", { name: "Next step" })).getByRole("link", {
        name: "Try again",
      }),
    ).toHaveAttribute("href", "/advertiser/campaigns/one");
    expect(screen.queryByRole("link", { name: "Review and submit" })).toBeNull();
    expect(document.body).not.toHaveTextContent("Private area failure");
  },
);
it("lets a viewer read an outstanding invoice without offering payment as the next step", async () => {
  mocks.role.mockResolvedValue({ viewer: true });
  mocks.get.mockImplementation(async (path: string) =>
    path.endsWith("/campaigns/{campaign_id}")
      ? { data: { ...campaign, status: "scheduled" } }
      : path.endsWith("/commercial")
        ? {
            data: {
              terms: {},
              invoices: [{ id: "invoice", status: "issued", payment_status: "unpaid" }],
              budget_evaluations: [],
            },
          }
        : ready(path),
  );
  render(await Page(input));
  expect(
    within(screen.getByRole("region", { name: "Next step" })).getByRole("link", {
      name: "View invoice",
    }),
  ).toHaveAttribute("href", "/advertiser/campaigns/one/invoices/invoice");
  expect(screen.queryByRole("link", { name: "Pay invoice" })).toBeNull();
});
