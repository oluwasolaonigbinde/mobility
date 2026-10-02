import { render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ get: vi.fn(), notFound: vi.fn(), photo: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("next/navigation", () => ({ notFound: mocks.notFound }));
vi.mock("../../approvals/review-actions", () => ({
  ReviewActions: () => <button>Review campaign</button>,
}));
vi.mock("../../approvals/creative-review-actions", () => ({
  CreativeReviewActions: () => <button>Review artwork</button>,
}));
vi.mock("../../approvals/campaign-change-review-actions", () => ({
  CampaignChangeReviewActions: () => <button>Review change</button>,
}));
vi.mock("../../approvals/installation-review-actions", () => ({
  InstallationReviewActions: (props: Record<string, unknown>) => {
    mocks.photo(props);
    return <p>Audited installation photos</p>;
  },
}));
vi.mock("../../assignments/activate-button", () => ({
  ActivateAssignmentButton: () => <button>Start job</button>,
}));
vi.mock("../../assignments/cancel-button", () => ({
  CancelAssignmentButton: () => <button>Cancel job</button>,
}));
vi.mock("../../assignments/new/assignment-form", () => ({
  AssignmentForm: () => <p>Offer form</p>,
}));
vi.mock("../pay-terms-section", () => ({ default: () => <p>Pay terms form</p> }));
vi.mock("../../billing/[campaignId]/content", () => ({ default: () => <p>Campaign money</p> }));
vi.mock("../../billing/[campaignId]/invoices/[invoiceId]/content", () => ({
  default: () => <p>Invoice details</p>,
}));
vi.mock("../../billing/[campaignId]/closeout/content", () => ({
  default: () => <p>Close-out details</p>,
}));
vi.mock("../../measurement/[runId]/content", () => ({ default: () => <p>Results details</p> }));
vi.mock("../../measurement/issue-form", () => ({
  IssueMeasurementForm: () => <p>Results form</p>,
}));
vi.mock("../resume-form", () => ({ ResumeForm: () => <button>Resume</button> }));
vi.mock("../artwork-preview", () => ({ ArtworkPreview: () => <button>View artwork</button> }));
vi.mock("../../hub-drawer", () => ({
  HubDrawer: ({
    title,
    closeHref,
    children,
  }: {
    title: string;
    closeHref: string;
    children: React.ReactNode;
  }) => (
    <section role="dialog" aria-label={title}>
      <a href={closeHref}>Close</a>
      {children}
    </section>
  ),
}));
import CampaignHub from "./page";
import { ApiError } from "@/lib/api/errors";
const id = "00000000-0000-4000-8000-000000000001";
const jobId = "00000000-0000-4000-8000-000000000002";
const runId = "00000000-0000-4000-8000-000000000003";
const campaign = {
  id,
  name: "PalmPay Wuse",
  description: "Exterior campaign",
  organization: { id: "company", name: "PalmPay" },
  status: "approved",
  start_at: null,
  end_at: null,
  budget_amount: "500000.00",
  currency: "NGN",
};
const job = {
  id: jobId,
  campaign_id: id,
  driver_profile_id: "driver",
  status: "accepted",
  driver_profile: { full_name: "Ada Okafor" },
  vehicle: { plate_number: "ABC-123-XY" },
};
function reads({
  ready = false,
  status = "approved",
  resume = false,
  parent = id,
  photoStatus = "approved",
}: {
  ready?: boolean;
  status?: string;
  resume?: boolean;
  parent?: string;
  photoStatus?: string;
} = {}) {
  mocks.get.mockImplementation(async (path: string) => {
    if (path === "/api/v1/admin/campaigns/{campaign_id}") return { data: { ...campaign, status } };
    if (path.endsWith("/commercial"))
      return {
        data: {
          terms: null,
          financial_authority: { authority_type: "corporate_credit" },
          budget_evaluations: [{ resume_allowed: resume, billing_spend_amount: "100000.00" }],
          invoices: [{ id: "invoice" }],
        },
      };
    if (path.endsWith("/campaign-assignments")) return { data: { items: [job], total: 1 } };
    if (path.endsWith("/campaign-assignments/{assignment_id}"))
      return { data: { ...job, campaign_id: parent } };
    if (path.endsWith("/readiness")) return { data: { ready, message: "Check installation" } };
    if (path.endsWith("/installation-evidence"))
      return { data: { items: [{ id: "photo", revision: 1, status: photoStatus, photos: [] }] } };
    if (path.endsWith("/measurement-runs")) return { data: { items: [], total: 0 } };
    if (path.endsWith("/measurement-runs/{run_id}"))
      return { data: { id: runId, campaign_id: parent } };
    return { data: { items: [], total: 0 } };
  });
}
const page = (query = {}) =>
  CampaignHub({
    params: Promise.resolve({ campaignId: id }),
    searchParams: Promise.resolve(query),
  });
beforeEach(() => {
  vi.clearAllMocks();
  mocks.notFound.mockImplementation(() => {
    throw new Error("not found");
  });
  reads();
});
it.each([true, false])("offers Start only when readiness allows it (%s)", async (ready) => {
  reads({ ready });
  render(await page({ job: jobId }));
  expect(screen.queryByRole("button", { name: "Start job" }) !== null).toBe(ready);
  expect(screen.getByText("Payment or approved credit")).toBeTruthy();
  expect(screen.queryByText("Payment confirmed")).toBeNull();
});
it.each([
  { status: "paused", resume: true, expected: true },
  { status: "paused", resume: false, expected: false },
  { status: "active", resume: true, expected: false },
])("shows only the supported budget resume action: $status/$resume", async (input) => {
  reads(input);
  render(await page());
  expect(screen.queryByRole("button", { name: "Resume" }) !== null).toBe(input.expected);
});
it.each(["approved", "pending_review"])(
  "keeps installation decisions tied to current photo status (%s)",
  async (photoStatus) => {
    reads({ photoStatus });
    render(await page({ job: jobId }));
    expect(mocks.photo).toHaveBeenCalledWith({
      submissionId: "photo",
      photos: [],
      canReview: photoStatus === "pending_review",
    });
  },
);
it("shows one drawer even when a URL includes several selections, and keeps pagination on close", async () => {
  render(
    await page({
      drawer: "invoice",
      invoice: "invoice",
      job: jobId,
      run: runId,
      jobs_offset: "25",
    }),
  );
  expect(screen.getAllByRole("dialog")).toHaveLength(1);
  expect(screen.getByRole("dialog", { name: "Invoice" })).toHaveTextContent("Invoice details");
  expect(screen.getByRole("link", { name: "Close" })).toHaveAttribute(
    "href",
    "/admin/campaigns/" + id + "?jobs_offset=25#money",
  );
  expect(mocks.photo).not.toHaveBeenCalled();
});
it.each([
  { drawer: "invoice", invoice: "elsewhere" },
  { job: "00000000-0000-4000-8000-000000000004" },
  { run: runId },
])("refuses a detail selected from another campaign", async (query) => {
  reads({ parent: "other-campaign" });
  render(await page(query));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.getByRole("alert")).toBeTruthy();
  expect(mocks.photo).not.toHaveBeenCalled();
});
it("does not render or fan out for a denied campaign", async () => {
  mocks.get.mockRejectedValue(new ApiError(403, { code: "DENIED", message: "Unavailable" }));
  await expect(page()).rejects.toThrow("not found");
  expect(mocks.get).toHaveBeenCalledOnce();
});
it("retains result reproducibility, replacement and report download state in the hub", async () => {
  const original = mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation(async (path: string) => {
    if (path.endsWith("/measurement-runs"))
      return {
        data: {
          items: [
            {
              id: runId,
              period_start_at: "2026-09-01T00:00:00Z",
              period_end_at: "2026-10-01T00:00:00Z",
              test_only: true,
              superseded: true,
              reproducible: false,
              report_status: "published",
              report_issuance_id: "report-1",
            },
          ],
          total: 1,
        },
      };
    return original(path);
  });
  render(await page());
  const result = screen.getByRole("link", { name: /Synthetic test/ });
  expect(result).toHaveTextContent("Replaced results");
  expect(result).toHaveTextContent("cannot be reproduced — do not issue a report");
  expect(result).toHaveTextContent("Report: Published");
  expect(result).toHaveAttribute(
    "href",
    `/admin/campaigns/${id}?run=${runId}&report=report-1#results`,
  );
});
it("preserves job activity problems alongside readiness", async () => {
  const original = mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation(async (path: string) => {
    if (path.endsWith("/campaign-assignments"))
      return {
        data: {
          items: [
            {
              ...job,
              activity_flags: [
                {
                  id: "flag",
                  flag_type: "inactivity",
                  status: "open",
                  window_start: "2026-09-20T00:00:00Z",
                  window_end: "2026-09-27T00:00:00Z",
                },
              ],
            },
          ],
          total: 1,
        },
      };
    return original(path);
  });
  render(await page());
  expect(screen.getByText(/No recent verified activity/)).toHaveTextContent("Needs attention");
});
it("shows unavailable sections without inventing empty records or completed prerequisites", async () => {
  mocks.get.mockImplementation(async (path) => {
    if (path.endsWith("/campaigns/{campaign_id}")) return { data: campaign };
    throw new Error("offline");
  });
  render(await page());
  expect(screen.getAllByRole("alert").length).toBeGreaterThan(5);
  expect(screen.queryByText("No driver jobs recorded.")).toBeNull();
  expect(screen.queryByText("No results calculations recorded.")).toBeNull();
  expect(screen.queryByText("Artwork status unavailable")).toBeNull();
  expect(screen.queryByRole("region", { name: "Launch checklist" })).toBeNull();
});
it("keeps named artwork, history, reviews and activity within their campaign", async () => {
  const normal = mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation(async (path) => {
    if (path.endsWith("/creatives"))
      return {
        data: {
          items: [
            {
              id: "creative",
              name: "Door wrap",
              status: "pending_review",
              stored_file_id: "file",
              scan_status: "clean",
            },
          ],
          total: 60,
        },
      };
    if (path.endsWith("/review-history"))
      return {
        data: {
          items: [
            {
              id: "history",
              new_status: "rejected",
              rejection_reason: "Fix artwork",
              created_at: "2026-09-29T10:00:00Z",
            },
          ],
          total: 60,
        },
      };
    if (path.endsWith("/campaign-change-requests/pending"))
      return { data: { items: [{ id: "change", campaign_id: id, status: "pending_review" }] } };
    if (path.endsWith("/fraud-flags"))
      return {
        data: {
          items: [{ id: "review", status: "open", description: "Trip needs checking" }],
          total: 60,
        },
      };
    if (path.endsWith("/audit-events"))
      return {
        data: {
          items: [
            { id: "event", action: "admin.campaign.approved", created_at: "2026-09-29T10:00:00Z" },
          ],
          total: 60,
        },
      };
    return normal(path);
  });
  render(
    await page({
      history_offset: "25",
      artwork_offset: "25",
      reviews_offset: "25",
      activity_offset: "25",
    }),
  );
  expect(screen.getByRole("button", { name: "View artwork" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Review artwork" })).toBeTruthy();
  expect(screen.getByText(/Fix artwork/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Review change" })).toBeTruthy();
  expect(screen.getByRole("link", { name: /Trip needs checking/ })).toHaveAttribute(
    "href",
    `/admin/trip-checks?tab=suspicious&campaign_id=${id}&flag=review`,
  );
  expect(screen.getByText(/Campaign approved/)).toBeTruthy();
  expect(screen.getAllByRole("link", { name: "Next →" }).length).toBeGreaterThanOrEqual(4);
});
it("retains close-out as one drawer on the campaign hub", async () => {
  render(await page({ drawer: "closeout", page: "2" }));
  expect(screen.getByRole("dialog", { name: "Close-out" })).toHaveTextContent("Close-out details");
  expect(screen.getAllByRole("dialog")).toHaveLength(1);
});

it("never marks incomplete artwork and job pages as launch-ready", async () => {
  reads({ ready: true });
  const normal = mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation(async (path, options) => {
    if (path.endsWith("/creatives"))
      return {
        data: { items: [{ id: "art", status: "approved", name: "Approved wrap" }], total: 26 },
      };
    if (path.endsWith("/campaign-assignments")) return { data: { items: [job], total: 26 } };
    return normal(path, options);
  });
  render(
    await CampaignHub({
      params: Promise.resolve({ campaignId: id }),
      searchParams: Promise.resolve({}),
    }),
  );
  for (const name of ["Artwork approved", "Drivers on board", "Installation photos approved"])
    expect(screen.getByRole("link", { name: new RegExp(name) })).toHaveTextContent("○");
});

it("opens readiness only for the selected job drawer", async () => {
  reads({ ready: true });
  render(await page());
  expect(screen.queryByRole("button", { name: "Start job" })).toBeNull();
  expect(mocks.get.mock.calls.some(([path]) => path.endsWith("/readiness"))).toBe(false);
});
it("does not open job reads behind a higher-priority invoice drawer", async () => {
  render(await page({ drawer: "invoice", invoice: "invoice", job: jobId }));
  expect(
    mocks.get.mock.calls.some(
      ([path]) => path.endsWith("/readiness") || path.endsWith("/installation-evidence"),
    ),
  ).toBe(false);
});
it.each(["readiness", "installation-evidence"])(
  "fails closed with one drawer failure when %s cannot be read",
  async (endpoint) => {
    reads({ ready: true });
    const normal = mocks.get.getMockImplementation()!;
    mocks.get.mockImplementation(async (path, options) =>
      path.endsWith("/" + endpoint) ? { data: undefined } : normal(path, options),
    );
    render(await page({ job: jobId }));
    const drawer = screen.getByRole("dialog");
    expect(within(drawer).getAllByRole("alert")).toHaveLength(1);
    expect(within(drawer).getByRole("alert")).toHaveTextContent(
      "Couldn't load this section — try again",
    );
    expect(screen.queryByRole("button", { name: "Start job" })).toBeNull();
    expect(mocks.photo).not.toHaveBeenCalled();
  },
);
