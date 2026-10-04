import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const get = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({ redirect: vi.fn(), notFound: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));

import PlanningSourcesPage from "./page";

const SOURCE_ID = "00000000-0000-4000-8000-000000000001";
const LINK_ID = "00000000-0000-4000-8000-000000000002";
const CAMPAIGN_ID = "00000000-0000-4000-8000-000000000003";
const ZONE_ID = "00000000-0000-4000-8000-000000000004";
const SEGMENT_ID = "00000000-0000-4000-8000-000000000005";

function mockReadyRecommendation() {
  get.mockImplementation(async (path: string) => {
    if (path === "/api/v1/advertiser/retargeting-sources") {
      return {
        data: {
          items: [
            {
              id: SOURCE_ID,
              source_type: "manual-insight",
              status: "active",
              expires_at: "2026-10-01T00:00:00Z",
              snapshot_sha256: "a".repeat(64),
            },
          ],
        },
      };
    }
    if (path === "/api/v1/advertiser/retargeting-source-links") {
      return {
        data: {
          items: [
            {
              id: LINK_ID,
              campaign_id: CAMPAIGN_ID,
              zone_id: ZONE_ID,
              status: "active",
              stale: false,
              start_at: "2026-09-01T00:00:00Z",
              end_at: "2026-09-02T00:00:00Z",
            },
          ],
        },
      };
    }
    if (path === "/api/v1/advertiser/campaigns") {
      return { data: { items: [{ id: CAMPAIGN_ID, name: "Campaign" }] } };
    }
    if (path === "/api/v1/advertiser/campaigns/{campaign_id}/zones") {
      return { data: { items: [{ id: ZONE_ID, name: "Wuse II core" }] } };
    }
    return {
      data: {
        state: "ready",
        segment_id: SEGMENT_ID,
        campaign_id: CAMPAIGN_ID,
        recommendations: [],
        provenance: { segment_version: 3, segment_snapshot_sha256: "c".repeat(64) },
        disclaimer: "Aggregate disclaimer",
        uncertainty: "Model uncertainty",
      },
    };
  });
}

describe("PlanningSourcesPage", () => {
  beforeEach(() => {
    get.mockReset();
  });

  it("shows a temporary service error instead of crashing and offers no forms", async () => {
    get.mockImplementation(async (path: string) => {
      if (path === "/api/v1/advertiser/campaigns") return { data: { items: [] } };
      throw new ApiError(503, {
        code: "PROVIDER_UNAVAILABLE",
        message: "The service is temporarily unavailable",
        details: {},
      });
    });

    render(await PlanningSourcesPage());

    expect(
      screen.getByRole("heading", { name: "Couldn't load your audiences — try again" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/This couldn't be loaded right now./)).toBeInTheDocument();
    expect(screen.queryByTestId("planning-source-form")).not.toBeInTheDocument();
    expect(screen.queryByTestId("planning-source-link-form")).not.toBeInTheDocument();
  });

  it("describes a declared audience in plain words without showing its fingerprint", async () => {
    mockReadyRecommendation();

    const { container } = render(await PlanningSourcesPage());

    expect(screen.getByRole("heading", { name: "Other insight you describe" })).toBeInTheDocument();
    expect(screen.getByText("In use")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/a{64}|c{64}|fingerprint|Technical reference/i);
  });

  it("does not render stale targeting cells or governed provenance", async () => {
    get.mockImplementation(async (path: string) => {
      if (path === "/api/v1/advertiser/retargeting-sources") {
        return {
          data: {
            items: [
              {
                id: SOURCE_ID,
                source_type: "manual-insight",
                status: "active",
                expires_at: "2026-10-01T00:00:00Z",
                snapshot_sha256: "a".repeat(64),
              },
            ],
          },
        };
      }
      if (path === "/api/v1/advertiser/retargeting-source-links") {
        return {
          data: {
            items: [
              {
                id: LINK_ID,
                campaign_id: CAMPAIGN_ID,
                zone_id: ZONE_ID,
                status: "active",
                stale: true,
                start_at: "2026-09-01T00:00:00Z",
                end_at: "2026-09-02T00:00:00Z",
              },
            ],
          },
        };
      }
      if (path === "/api/v1/advertiser/campaigns") {
        return { data: { items: [{ id: CAMPAIGN_ID, name: "Campaign" }] } };
      }
      if (path === "/api/v1/advertiser/campaigns/{campaign_id}/zones") {
        return { data: { items: [] } };
      }
      return {
        data: {
          state: "stale",
          segment_id: "00000000-0000-4000-8000-000000000005",
          campaign_id: CAMPAIGN_ID,
          recommendations: [
            {
              rank: 1,
              coverage_cell: "grid-500m:10:20",
              window_start_at: "2026-09-01T00:00:00Z",
              window_end_at: "2026-09-01T01:00:00Z",
              campaign_context: "vehicle_transit",
              rationale: "stale",
            },
          ],
          provenance: { segment_version: 7, segment_snapshot_sha256: "b".repeat(64) },
          disclaimer: "Aggregate disclaimer",
          uncertainty: "Stale uncertainty must stay hidden",
        },
      };
    });

    render(await PlanningSourcesPage());

    expect(
      screen.getByText("These suggestions are out of date, so they can't be downloaded."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/grid-500m:10:20/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Segment v7/)).not.toBeInTheDocument();
    expect(screen.queryByText("Stale uncertainty must stay hidden")).not.toBeInTheDocument();
  });

  it("offers aggregate export without an approval form", async () => {
    mockReadyRecommendation();

    const { container } = render(await PlanningSourcesPage());

    expect(screen.getByRole("button", { name: "Download suggestions (CSV)" })).toBeInTheDocument();
    expect(container.querySelector('input[name="approval_id"]')).toBeNull();
  });

  it("names linked campaigns and zones without exposing their internal identifiers", async () => {
    mockReadyRecommendation();

    render(await PlanningSourcesPage());

    expect(screen.getByText("Campaign: Campaign")).toBeInTheDocument();
    expect(screen.getByText("Area: Wuse II core")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(CAMPAIGN_ID);
    expect(document.body).not.toHaveTextContent(ZONE_ID);
  });
});
