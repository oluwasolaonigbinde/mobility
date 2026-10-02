import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const get = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({ redirect: vi.fn(), notFound: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "admin-token") }));

vi.mock("@/components/analytics/high-exposure-zone-insights", () => ({
  HighExposureZoneInsights: ({ insight }: { insight: { campaign_id: string } }) => (
    <div>Area detail {insight.campaign_id}</div>
  ),
}));

import AdminPlanningSourcesPage from "./page";

const SOURCE_ID = "00000000-0000-4000-8000-000000000011";
const LINK_ID = "00000000-0000-4000-8000-000000000012";
const CAMPAIGN_ID = "00000000-0000-4000-8000-000000000013";
const ZONE_ID = "00000000-0000-4000-8000-000000000014";

describe("AdminPlanningSourcesPage", () => {
  beforeEach(() => {
    get.mockReset();
  });

  it("does not render targeting cells from a stale recommendation", async () => {
    get.mockImplementation(async (path: string) => {
      if (path === "/api/v1/admin/retargeting-sources") {
        return {
          data: {
            items: [
              {
                id: SOURCE_ID,
                organization_id: "00000000-0000-4000-8000-000000000015",
                source_type: "manual-insight",
                status: "active",
                expires_at: "2026-10-01T00:00:00Z",
                snapshot_sha256: "a".repeat(64),
              },
            ],
            total: 1,
          },
        };
      }
      if (path === "/api/v1/admin/retargeting-source-links") {
        return {
          data: {
            items: [
              {
                id: LINK_ID,
                organization_id: "00000000-0000-4000-8000-000000000015",
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
      if (path === "/api/v1/admin/advertiser-organizations/{organization_id}/company")
        return { data: { id: "00000000-0000-4000-8000-000000000015", name: "Named company" } };
      if (path === "/api/v1/admin/campaigns/{campaign_id}")
        return { data: { id: CAMPAIGN_ID, name: "Named campaign" } };
      if (path === "/api/v1/admin/campaigns/{campaign_id}/zone-insights") {
        return { data: undefined };
      }
      return {
        data: {
          state: "stale",
          recommendations: [
            {
              rank: 1,
              coverage_cell: "grid-500m:10:20",
              window_start_at: "2026-09-01T00:00:00Z",
              window_end_at: "2026-09-01T01:00:00Z",
            },
          ],
        },
      };
    });

    render(await AdminPlanningSourcesPage());

    expect(screen.getAllByText("Needs refresh", { selector: "span" })).not.toHaveLength(0);
    expect(screen.queryByText("grid-500m:10:20")).not.toBeInTheDocument();
  });

  it("shows the privacy gate instead of crashing", async () => {
    get.mockRejectedValue(
      new ApiError(503, {
        code: "PROVIDER_UNAVAILABLE",
        message: "Advertiser analytics are unavailable until privacy approval",
        details: {},
      }),
    );

    render(await AdminPlanningSourcesPage());

    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this section — try again");
  });
  it("refuses mismatched company names rather than attributing an audience to another company", async () => {
    get.mockImplementation(async (path: string) => {
      if (path === "/api/v1/admin/retargeting-sources")
        return { data: { items: [{ id: SOURCE_ID, organization_id: "company" }], total: 1 } };
      if (path === "/api/v1/admin/retargeting-source-links") return { data: { items: [] } };
      if (path === "/api/v1/admin/advertiser-organizations/{organization_id}/company")
        return { data: { id: "wrong", name: "Wrong company" } };
      return {};
    });
    render(await AdminPlanningSourcesPage());
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.queryByText("Wrong company")).not.toBeInTheDocument();
  });
  it("keeps every delayed detail read globally bounded at four while preserving every result", async () => {
    const sources = Array.from({ length: 7 }, (_, i) => ({
      id: "source-" + i,
      organization_id: "company-" + i,
      source_type: "manual_insight",
      status: "active",
      expires_at: "2026-10-30T00:00:00Z",
      snapshot_sha256: "a".repeat(64),
    }));
    const links = Array.from({ length: 9 }, (_, i) => ({
      id: "link-" + i,
      organization_id: "company-" + (i % 7),
      campaign_id: "campaign-" + (i % 7),
      zone_id: "zone-" + i,
      status: "active",
      stale: false,
      start_at: "2026-10-01T00:00:00Z",
      end_at: "2026-10-02T00:00:00Z",
    }));
    let active = 0,
      peak = 0,
      details = 0;
    get.mockImplementation(
      async (path: string, options?: { params?: { path?: Record<string, string> } }) => {
        if (path === "/api/v1/admin/retargeting-sources")
          return { data: { items: sources, total: sources.length } };
        if (path === "/api/v1/admin/retargeting-source-links")
          return { data: { items: links, total: links.length } };
        active++;
        details++;
        peak = Math.max(peak, active);
        await new Promise((resolve) => setTimeout(resolve, 5));
        active--;
        const ids = options?.params?.path;
        if (path === "/api/v1/admin/advertiser-organizations/{organization_id}/company")
          return { data: { id: ids?.organization_id, name: "Named " + ids?.organization_id } };
        if (path === "/api/v1/admin/campaigns/{campaign_id}")
          return { data: { id: ids?.campaign_id, name: "Named " + ids?.campaign_id } };
        if (path === "/api/v1/admin/campaigns/{campaign_id}/zone-insights")
          return { data: { campaign_id: ids?.campaign_id } };
        if (path === "/api/v1/admin/retargeting-source-links/{link_id}/recommendations")
          return {
            data: { state: "ready", recommendations: [{ coverage_cell: "cell-" + ids?.link_id }] },
          };
        throw new Error("Unexpected detail read");
      },
    );
    render(await AdminPlanningSourcesPage());
    expect(details).toBe(30);
    expect(active).toBe(0);
    expect(peak).toBe(4);
    expect(screen.getAllByText(/Area detail campaign-/)).toHaveLength(7);
    for (const link of links) expect(screen.getByText("cell-" + link.id)).toBeVisible();
    expect(screen.getAllByRole("link", { name: "Named company-6" })).toHaveLength(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
