import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));

import PlanningSourcesPage from "./page";

const SOURCE_ID = "00000000-0000-4000-8000-000000000001";
const LINK_ID = "00000000-0000-4000-8000-000000000002";
const CAMPAIGN_ID = "00000000-0000-4000-8000-000000000003";
const ZONE_ID = "00000000-0000-4000-8000-000000000004";
const SEGMENT_ID = "00000000-0000-4000-8000-000000000005";
const APPROVAL_ID = "00000000-0000-4000-8000-000000000006";

function mockReadyRecommendation(exportApprovalId: string | null) {
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
      return { data: { items: [] } };
    }
    return {
      data: {
        state: "ready",
        segment_id: SEGMENT_ID,
        campaign_id: CAMPAIGN_ID,
        recommendations: [],
        provenance: null,
        disclaimer: "Aggregate disclaimer",
        uncertainty: "Model uncertainty",
        export_approval_id: exportApprovalId,
      },
    };
  });
}

describe("PlanningSourcesPage", () => {
  beforeEach(() => get.mockReset());

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
      screen.getByText("The issued aggregate is stale and cannot be exported."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/grid-500m:10:20/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Segment v7/)).not.toBeInTheDocument();
    expect(screen.queryByText("Stale uncertainty must stay hidden")).not.toBeInTheDocument();
  });

  it("withholds controlled export until a current approval is returned", async () => {
    mockReadyRecommendation(null);

    render(await PlanningSourcesPage());

    expect(
      screen.getByText("Awaiting current privacy approval for controlled export."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Download controlled CSV" }),
    ).not.toBeInTheDocument();
  });

  it("submits the server-issued approval with the controlled export", async () => {
    mockReadyRecommendation(APPROVAL_ID);

    const { container } = render(await PlanningSourcesPage());

    expect(screen.getByRole("button", { name: "Download controlled CSV" })).toBeInTheDocument();
    expect(container.querySelector('input[name="approval_id"]')).toHaveValue(APPROVAL_ID);
  });
});
