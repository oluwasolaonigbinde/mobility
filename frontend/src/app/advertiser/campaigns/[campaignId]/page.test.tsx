import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const { get, requireRole, redirect, notFound } = vi.hoisted(() => ({
  get: vi.fn(),
  requireRole: vi.fn(),
  redirect: vi.fn((path: string) => {
    throw new Error(`redirect:${path}`);
  }),
  notFound: vi.fn(() => {
    throw new Error("notFound");
  }),
}));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole }));
vi.mock("next/navigation", () => ({ redirect, notFound }));
vi.mock("./status-actions", () => ({ StatusActions: () => <button>Submit for review</button> }));
vi.mock("./commercial-panel", () => ({
  CommercialPanel: ({ error }: { error?: string }) => (
    <section>
      <h2>Commercial terms</h2>
      <button>Request quotation</button>
      {error && <p>{error}</p>}
    </section>
  ),
}));
vi.mock("./campaign-change-panel", () => ({
  CampaignChangePanel: () => <button>Request campaign change</button>,
}));
vi.mock("./campaign-cancellation-panel", () => ({
  CampaignCancellationPanel: () => <button>Cancel campaign</button>,
}));
vi.mock("./creative-status-actions", () => ({
  CreativeStatusActions: () => <button>Submit creative</button>,
}));

import CampaignDetailPage from "./page";

const campaign = {
  id: "campaign-1",
  organization_id: "org-1",
  name: "Healthy campaign",
  status: "active",
  currency: "NGN",
  budget_amount: "1000",
  daily_budget_amount: "100",
  description: "Healthy details",
  start_at: null,
  end_at: null,
  created_at: "2026-09-01T00:00:00Z",
  metadata: {},
};
const input = {
  params: Promise.resolve({ campaignId: campaign.id }),
  searchParams: Promise.resolve({}),
};
const failure = (status = 503, code = "PRIVACY_LIVE_USE_BLOCKED") =>
  new ApiError(status, { code, message: "Private backend detail" });
function healthy(path: string) {
  if (path.endsWith("/summary"))
    return {
      data: {
        impressions: {
          estimated_impressions: "100",
          estimated_trip_count: 2,
          average_confidence_score: "0.8",
        },
        route_analytics: {
          total_distance_m: "2000",
          target_zone_distance_m: "1000",
          average_quality_score: "0.9",
        },
        costs: { totals_by_currency: [] },
        fraud_flags: { open: 0 },
        zones: { total: 42 },
        assignments: { active: 3, total: 4 },
      },
    };
  if (path.endsWith("/commercial")) return { data: {} };
  if (path.endsWith("/creatives")) return { data: { items: [] } };
  if (path.endsWith("/review-history") || path.endsWith("/change-requests"))
    return { data: { items: [] } };
  return { data: campaign };
}

describe("resilient campaign detail", () => {
  beforeEach(() => {
    get.mockReset().mockImplementation(async (path: string) => healthy(path));
    requireRole.mockResolvedValue({
      user: { role: "advertiser", email: "real@example.com" },
      advertiser_organization: { id: "org-1" },
    });
    redirect.mockClear();
    notFound.mockClear();
  });

  it("preserves campaign-only controls and healthy sections when summary is gated", async () => {
    get.mockImplementation(async (path: string) => {
      if (path.endsWith("/summary")) throw failure();
      return healthy(path);
    });
    render(await CampaignDetailPage(input));
    expect(screen.getByRole("heading", { name: campaign.name })).toBeInTheDocument();
    expect(screen.getByText("Healthy details")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit for review" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel campaign" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Commercial terms" })).toBeInTheDocument();
    expect(
      screen.getByText("No creatives yet. Add a private creative file to this campaign."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Estimated ad exposure")).not.toBeInTheDocument();
    expect(screen.queryByText("Fleet")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Zones/ })).not.toHaveTextContent("42");
    expect(document.body).not.toHaveTextContent("Private backend detail");
  });

  it("does not mistake an optional 404 for a missing campaign", async () => {
    get.mockImplementation(async (path: string) => {
      if (path.endsWith("/creatives")) throw failure(404, "NOT_FOUND");
      return healthy(path);
    });
    render(await CampaignDetailPage(input));
    expect(screen.getByRole("heading", { name: campaign.name })).toBeInTheDocument();
    expect(notFound).not.toHaveBeenCalled();
    expect(screen.queryByRole("link", { name: "Add missing creatives" })).not.toBeInTheDocument();
  });

  it.each([
    ["/summary", "Campaign results unavailable", "Estimated ad exposure"],
    [
      "/creatives",
      "Creatives unavailable",
      "No creatives yet. Add a private creative file to this campaign.",
    ],
    ["/commercial", "Commercial terms unavailable", "Commercial terms"],
    [
      "/review-history",
      "Submission and review history unavailable",
      "This campaign has not been submitted for review.",
    ],
    ["/change-requests", "Campaign changes unavailable", "Request campaign change"],
  ])(
    "isolates a failed %s read without false empty data or dependent controls",
    async (suffix, title, absent) => {
      get.mockImplementation(async (path: string) => {
        if (path.endsWith(suffix)) throw failure(503, "UNAVAILABLE");
        return healthy(path);
      });
      render(await CampaignDetailPage(input));
      expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
      expect(screen.queryByText(absent, { exact: true })).not.toBeInTheDocument();
      expect(screen.getByText("Healthy details")).toBeInTheDocument();
      if (suffix === "/creatives")
        expect(
          screen.queryByRole("link", { name: "Add missing creatives" }),
        ).not.toBeInTheDocument();
      if (suffix === "/commercial")
        expect(screen.queryByRole("button", { name: "Request quotation" })).not.toBeInTheDocument();
    },
  );

  it.each(["/summary", "/creatives", "/commercial", "/review-history", "/change-requests"])(
    "redirects expiry during optional %s after successful user/campaign reads",
    async (suffix) => {
      get.mockImplementation(async (path: string) => {
        if (path.endsWith(suffix)) throw failure(401, "SESSION_EXPIRED");
        return healthy(path);
      });
      await expect(CampaignDetailPage(input)).rejects.toThrow("redirect:/login");
      expect(requireRole).toHaveBeenCalledWith("advertiser");
      expect(notFound).not.toHaveBeenCalled();
    },
  );

  it.each([
    [failure(404, "NOT_FOUND"), "notFound"],
    [failure(401, "SESSION_EXPIRED"), "redirect:/login"],
  ])("stops before optional requests for required authority failure %s", async (error, message) => {
    get.mockRejectedValue(error);
    await expect(CampaignDetailPage(input)).rejects.toThrow(message);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it.each([
    undefined,
    failure(403, "FORBIDDEN"),
    failure(503, "DOWN"),
    new TypeError("fetch failed"),
  ])("shows required unavailable without404 or auxiliary reads for %s", async (error) => {
    get.mockImplementation(async () => {
      if (error) throw error;
      return {};
    });
    render(await CampaignDetailPage(input));
    expect(screen.getByRole("heading", { name: "Campaign unavailable" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: campaign.name })).not.toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(1);
    expect(notFound).not.toHaveBeenCalled();
  });

  it("rethrows programmer errors before optional reads", async () => {
    const error = new TypeError("Cannot read properties of undefined");
    get.mockRejectedValue(error);
    await expect(CampaignDetailPage(input)).rejects.toBe(error);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it("keeps successful metrics, counts, empty histories and section controls unchanged", async () => {
    render(await CampaignDetailPage(input));
    expect(screen.getByText("Estimated ad exposure")).toBeInTheDocument();
    expect(screen.getByText("Fleet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Zones/ })).toHaveTextContent("42");
    expect(
      screen.getByText("This campaign has not been submitted for review."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Request campaign change" })).toBeInTheDocument();
  });

  it("renders a successful history and creative list", async () => {
    get.mockImplementation(async (path: string) => {
      if (path.endsWith("/review-history"))
        return {
          data: {
            items: [
              {
                id: "review-1",
                prior_status: "draft",
                new_status: "pending_review",
                created_at: "2026-09-01T00:00:00Z",
                rejection_reason: null,
                reviewed_snapshot_sha256: null,
              },
            ],
          },
        };
      if (path.endsWith("/creatives"))
        return {
          data: {
            items: [
              {
                id: "creative-1",
                name: "Private creative",
                creative_type: "image",
                placement: "vehicle_exterior",
                status: "draft",
                asset_source: "managed_file",
                scan_status: "clean",
              },
            ],
          },
        };
      return healthy(path);
    });
    render(await CampaignDetailPage(input));
    expect(screen.getByText("Draft → Pending review")).toBeInTheDocument();
    expect(screen.getByText("Private creative")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit creative" })).toBeInTheDocument();
  });

  it("preserves successful creative variants, cost and rejection provenance", async () => {
    get.mockImplementation(async (path: string) => {
      if (path.endsWith("/summary"))
        return {
          data: {
            ...healthy(path).data,
            costs: { totals_by_currency: [{ final_payout_total: "500", currency: "NGN" }] },
            fraud_flags: { open: 2 },
          },
        };
      if (path.endsWith("/review-history"))
        return {
          data: {
            items: [
              {
                id: "review-1",
                prior_status: "rejected",
                new_status: "pending_review",
                created_at: "2026-09-01T00:00:00Z",
                rejection_reason: "Revise artwork",
                reviewed_snapshot_sha256: "review-proof",
              },
            ],
          },
        };
      if (path.endsWith("/creatives"))
        return {
          data: {
            items: ["approved", "rejected", "archived", "ready"].map((status, index) => ({
              id: `creative-${index}`,
              name: `${status} creative`,
              creative_type: "unknown-format",
              placement: "unknown-placement",
              status,
              asset_source: "legacy_url",
              width_px: 400,
              height_px: 300,
            })),
          },
        };
      return {
        ...healthy(path),
        ...(path.endsWith("}")
          ? { data: { ...campaign, description: null, status: "draft" } }
          : {}),
      };
    });
    render(await CampaignDetailPage(input));
    expect(screen.getByText("Resubmitted for review")).toBeInTheDocument();
    expect(screen.getByText("Reason: Revise artwork")).toBeInTheDocument();
    expect(screen.getByText(/review-proof/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel campaign" })).not.toBeInTheDocument();
    expect(screen.getByText("₦500.00")).toBeInTheDocument();
  });

  it("sanitizes a sensitive commercial error query at the page boundary", async () => {
    render(
      await CampaignDetailPage({
        ...input,
        searchParams: Promise.resolve({
          commercial_error: "PRIVATE bank account 1234567890 stack trace",
        }),
      }),
    );
    expect(
      screen.getByText("That request didn't go through. Check the current terms and try again."),
    ).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("1234567890");
  });

  it.each([true, "true", false])(
    "presents a campaign with demo metadata %s as an ordinary campaign",
    async (demo) => {
      requireRole.mockResolvedValue({
        user: { role: "advertiser", email: "demo@example.com" },
        advertiser_organization: { id: "org-1" },
      });
      get.mockImplementation(async (path: string) =>
        path.endsWith("}") ? { data: { ...campaign, metadata: { demo } } } : healthy(path),
      );
      render(await CampaignDetailPage(input));
      expect(screen.getByRole("heading", { name: campaign.name })).toBeInTheDocument();
      expect(document.body).not.toHaveTextContent(/demo|synthetic/i);
    },
  );

  it("labels campaign results by what they measure", async () => {
    render(await CampaignDetailPage(input));
    expect(
      screen.getByText(
        "Estimated opportunities to see the ad, based on routes and traffic. This is not a count of people or measured views.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("GPS evidence quality")).toBeInTheDocument();
    expect(screen.queryByText("Quality score")).not.toBeInTheDocument();
    expect(screen.getByText("Driver pay to date")).toBeInTheDocument();
    expect(
      screen.getByText("Calculated driver pay; your invoice is shown in Billing."),
    ).toBeInTheDocument();
    expect(screen.getByText("Trip integrity checks awaiting Cardvert review")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Submission and review history" }),
    ).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(
      /potential contacts|confidence|diagnostic|immutable server-recorded/i,
    );
  });
});
