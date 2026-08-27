import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "admin-token") }));

import AdminPlanningSourcesPage from "./page";

const SOURCE_ID = "00000000-0000-4000-8000-000000000011";
const LINK_ID = "00000000-0000-4000-8000-000000000012";
const CAMPAIGN_ID = "00000000-0000-4000-8000-000000000013";
const ZONE_ID = "00000000-0000-4000-8000-000000000014";

describe("AdminPlanningSourcesPage", () => {
  beforeEach(() => get.mockReset());

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

    expect(screen.getAllByText("stale", { selector: "span" })).not.toHaveLength(0);
    expect(screen.queryByText("grid-500m:10:20")).not.toBeInTheDocument();
  });
});
