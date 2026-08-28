import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.hoisted(() => vi.fn());
const governedMap = vi.hoisted(() =>
  vi.fn(({ zones }: { zones: Array<{ rank: number; name: string }> }) => (
    <div data-testid="governed-zone-map">{zones.map((zone) => zone.name).join(",")}</div>
  )),
);

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("./heatmap-view", () => ({ GovernedZoneMap: governedMap }));

import CampaignMapPage from "./page";

const CAMPAIGN_ID = "00000000-0000-4000-8000-000000000001";
const RANKED_ZONE_ID = "00000000-0000-4000-8000-000000000002";
const SECOND_RANKED_ZONE_ID = "00000000-0000-4000-8000-000000000006";

function reportWithState(state: "ready" | "suppressed") {
  return {
    campaign_id: CAMPAIGN_ID,
    measurement_run: {
      id: "00000000-0000-4000-8000-000000000003",
      mode: "performance_only",
      formula_version: "measurement-result-v1",
      method_revision: "measurement-contract-v1",
      roi_method_revision: null,
      period_start_at: "2026-08-01T00:00:00Z",
      period_end_at: "2026-08-02T00:00:00Z",
      input_manifest_sha256: "a".repeat(64),
      result_manifest_sha256: "b".repeat(64),
      proof_manifest_sha256: "c".repeat(64),
      report_snapshot_sha256: "d".repeat(64),
      reissue_of_run_id: null,
      created_at: "2026-08-03T00:00:00Z",
    },
    measurement_result: {
      schema_version: "measurement-result-v1",
      title: "Campaign Performance Analysis",
      mode: "performance_only",
      formula_version: "measurement-result-v1",
      method_revision: "measurement-contract-v1",
      period: { start_at: "2026-08-01T00:00:00Z", end_at: "2026-08-02T00:00:00Z" },
      metrics: [
        {
          id: "verified_vehicle_movement",
          label: "Verified vehicle movement",
          class: "measured_operational_fact",
          trip_count: 4,
          distance_m: "12000.00",
          active_tracking_seconds: 3600,
        },
        {
          id: "modelled_potential_contacts",
          label: "Modelled potential contacts",
          class: "modelled_measure",
          value: "900.00",
          formula_versions: ["impressions_v1"],
          uncertainty: "Modelled value.",
        },
        {
          id: "driver_campaign_cost",
          label: "Driver campaign cost",
          class: "measured_financial_fact",
          totals_by_currency: [{ currency: "NGN", value: "1200.00" }],
        },
      ],
      proof_manifest_sha256: "c".repeat(64),
      roi: null,
      roi_gate: { decision: "OMIT" },
    },
    exposure_score:
      state === "ready"
        ? {
            formula_version: "exposure_v1",
            formula_fingerprint: "f".repeat(64),
            input_fingerprint: "1".repeat(64),
            result_fingerprint: "2".repeat(64),
            measurement_input_sha256: "a".repeat(64),
            measurement_result_sha256: "b".repeat(64),
            measurement_proof_sha256: "c".repeat(64),
            reproducible: true,
            stale: false,
            result: {
              formula_version: "exposure_v1",
              formula_fingerprint: "f".repeat(64),
              input_fingerprint: "1".repeat(64),
              status: "scored",
              score: "80.00",
              provenance: {
                measurement_run_id: "00000000-0000-4000-8000-000000000003",
                measurement_input_sha256: "a".repeat(64),
                measurement_result_sha256: "b".repeat(64),
                measurement_proof_sha256: "c".repeat(64),
              },
            },
          }
        : null,
    high_exposure_zone_insights: {
      state,
      campaign_id: CAMPAIGN_ID,
      campaign_exposure_score: state === "ready" ? "80.00" : null,
      items:
        state === "ready"
          ? [
              {
                rank: 1,
                zone_id: RANKED_ZONE_ID,
                zone_name: "Central Abuja",
                modelled_potential_contacts: "900.00",
                trip_count: 4,
              },
              {
                rank: 2,
                zone_id: SECOND_RANKED_ZONE_ID,
                zone_name: "Airport Road",
                modelled_potential_contacts: "500.00",
                trip_count: 3,
              },
            ]
          : [],
      provenance:
        state === "ready"
          ? {
              formula_version: "high_exposure_zone_v1",
              formula_fingerprint: "e".repeat(64),
              measurement_run_id: "00000000-0000-4000-8000-000000000003",
              exposure_score_id: "00000000-0000-4000-8000-000000000004",
              exposure_formula_version: "exposure_v1",
              exposure_formula_fingerprint: "f".repeat(64),
              exposure_input_fingerprint: "1".repeat(64),
              source_segments: [
                {
                  segment_id: "00000000-0000-4000-8000-000000000007",
                  segment_version: 1,
                  segment_snapshot_sha256: "3".repeat(64),
                  reissue_of_segment_id: null,
                },
              ],
            }
          : null,
      uncertainty: null,
      disclaimer: "Ranks disclosure-cleared zones by modelled potential contacts.",
    },
  };
}

describe("CampaignMapPage", () => {
  beforeEach(() => {
    get.mockReset();
    governedMap.mockClear();
  });

  it("authorizes after the zone read and passes only ranked target geometry to the client", async () => {
    get
      .mockResolvedValueOnce({ data: { id: CAMPAIGN_ID, name: "Abuja", status: "active" } })
      .mockResolvedValueOnce({
        data: {
          items: [
            {
              id: SECOND_RANKED_ZONE_ID,
              name: "Airport Road",
              zone_type: "target",
              geometry: {},
            },
            {
              id: "00000000-0000-4000-8000-000000000005",
              name: "Hidden exclusion",
              zone_type: "exclusion",
              geometry: {},
            },
            { id: RANKED_ZONE_ID, name: "Central Abuja", zone_type: "target", geometry: {} },
          ],
        },
      })
      .mockResolvedValueOnce({ data: reportWithState("ready") });

    render(await CampaignMapPage({ params: Promise.resolve({ campaignId: CAMPAIGN_ID }) }));

    expect(get.mock.calls.map(([path]) => path)).toEqual([
      "/api/v1/advertiser/campaigns/{campaign_id}",
      "/api/v1/advertiser/campaigns/{campaign_id}/zones",
      "/api/v1/advertiser/campaigns/{campaign_id}/report",
    ]);
    expect(screen.getByTestId("governed-zone-map")).toHaveTextContent("Central Abuja,Airport Road");
    expect(governedMap.mock.calls[0]?.[0].zones.map((zone) => zone.rank)).toEqual([1, 2]);
    expect(screen.queryByText("Hidden exclusion")).not.toBeInTheDocument();
  });

  it("serializes no geometry for a suppressed frozen projection", async () => {
    get
      .mockResolvedValueOnce({ data: { id: CAMPAIGN_ID, name: "Abuja", status: "active" } })
      .mockResolvedValueOnce({
        data: {
          items: [{ id: RANKED_ZONE_ID, name: "Central Abuja", zone_type: "target", geometry: {} }],
        },
      })
      .mockResolvedValueOnce({ data: reportWithState("suppressed") });

    render(await CampaignMapPage({ params: Promise.resolve({ campaignId: CAMPAIGN_ID }) }));

    expect(governedMap).not.toHaveBeenCalled();
    expect(screen.getByText(/withheld by the disclosure floor/i)).toBeInTheDocument();
    expect(screen.queryByText("Central Abuja")).not.toBeInTheDocument();
  });

  it("fails closed when a ready projection contains no ranked zones", async () => {
    const report = reportWithState("ready");
    report.high_exposure_zone_insights.items = [];
    get
      .mockResolvedValueOnce({ data: { id: CAMPAIGN_ID, name: "Abuja", status: "active" } })
      .mockResolvedValueOnce({ data: { items: [] } })
      .mockResolvedValueOnce({ data: report });

    render(await CampaignMapPage({ params: Promise.resolve({ campaignId: CAMPAIGN_ID }) }));

    expect(governedMap).not.toHaveBeenCalled();
    expect(screen.getByText("MEASUREMENT_RUN_INTEGRITY_FAILURE")).toBeInTheDocument();
  });
});
