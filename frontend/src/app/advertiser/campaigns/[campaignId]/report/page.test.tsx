import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const get = vi.hoisted(() => vi.fn());
const notFound = vi.hoisted(() =>
  vi.fn(() => {
    throw new Error("NOT_FOUND");
  }),
);

vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("next/navigation", () => ({ notFound }));

import CampaignReportPage from "./page";
import { dailyMetricPublishable, FrozenDailyMetricChart } from "./frozen-daily-metric-chart";

describe("CampaignReportPage fail-closed states", () => {
  beforeEach(() => {
    get.mockReset();
    notFound.mockClear();
  });

  it("says no report exists yet when no frozen run has been issued", async () => {
    get.mockResolvedValue({ data: { measurement_run: null, measurement_result: null } });
    render(
      await CampaignReportPage({
        params: Promise.resolve({ campaignId: "00000000-0000-4000-8000-000000000001" }),
      }),
    );
    expect(screen.getByText("Your campaign report is being prepared")).toBeInTheDocument();
    expect(screen.queryByText(/integrity check/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/daily breakdown/i)).not.toBeInTheDocument();
  });

  it("explains the privacy gate rather than implying corrupted data", async () => {
    get.mockRejectedValue(new ApiError(503, { code: "PROVIDER_UNAVAILABLE", message: "blocked" }));
    render(
      await CampaignReportPage({
        params: Promise.resolve({ campaignId: "00000000-0000-4000-8000-000000000001" }),
      }),
    );
    expect(screen.getByText("Campaign results can't be shown")).toBeInTheDocument();
    expect(screen.queryByText(/could not be verified|integrity/i)).not.toBeInTheDocument();
  });

  it("withholds a half-issued report as an integrity failure", async () => {
    get.mockResolvedValue({
      data: { measurement_run: { id: "run-1" }, measurement_result: null },
    });
    render(
      await CampaignReportPage({
        params: Promise.resolve({ campaignId: "00000000-0000-4000-8000-000000000001" }),
      }),
    );
    expect(screen.getByText(/failed its integrity check/i)).toBeInTheDocument();
    expect(screen.getByText(/Terrax Media needs to reissue the analysis/)).toBeInTheDocument();
    expect(screen.queryByText(/fail-closed/i)).not.toBeInTheDocument();
    expect(screen.queryByText("MEASUREMENT_RUN_INTEGRITY_FAILURE")).not.toBeInTheDocument();
    expect(screen.queryByText(/daily breakdown/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/modelled potential contacts/i)).not.toBeInTheDocument();
  });

  it("renders an explicit unavailable state for a pending analysis", async () => {
    get.mockRejectedValue(
      new ApiError(503, {
        code: "CAMPAIGN_REPORT_PENDING",
        message: "blocked",
      }),
    );
    render(
      await CampaignReportPage({
        params: Promise.resolve({ campaignId: "00000000-0000-4000-8000-000000000001" }),
      }),
    );
    expect(screen.getByText("Your campaign report is being prepared")).toBeInTheDocument();
    expect(screen.getByText(/Check back/)).toBeInTheDocument();
    expect(screen.queryByText(/daily breakdown/i)).not.toBeInTheDocument();
  });

  it("preserves non-enumerating not-found behavior", async () => {
    get.mockRejectedValue(new ApiError(404, { code: "CAMPAIGN_NOT_FOUND", message: "not found" }));
    await expect(
      CampaignReportPage({
        params: Promise.resolve({ campaignId: "00000000-0000-4000-8000-000000000001" }),
      }),
    ).rejects.toThrow("NOT_FOUND");
    expect(notFound).toHaveBeenCalledOnce();
  });
});

describe("CampaignReportPage frozen daily metrics", () => {
  it("withholds a suppressed daily chart behind the exact frozen omission label", () => {
    render(
      <FrozenDailyMetricChart
        title="Modelled potential contacts · daily"
        description="Frozen model"
        suppressed
      >
        <div data-testid="daily-chart">fabricated chart</div>
      </FrozenDailyMetricChart>,
    );

    expect(screen.getByText("Not enough data")).toBeInTheDocument();
    expect(screen.queryByTestId("daily-chart")).not.toBeInTheDocument();
  });

  it("withholds daily rows for a mixed cohort even when its qualifying total is not suppressed", () => {
    expect(
      dailyMetricPublishable({
        complete: true,
        suppressed: false,
        in_progress_trip_count: 1,
        insufficient_data_trip_count: 0,
        excluded_trip_count: 0,
      }),
    ).toBe(false);
  });

  it("does not authorize one daily cost series for multiple frozen currencies", () => {
    const completeness = {
      complete: true,
      suppressed: false,
      in_progress_trip_count: 0,
      insufficient_data_trip_count: 0,
      excluded_trip_count: 0,
    };

    expect(dailyMetricPublishable(completeness) && ["NGN", "USD"].length === 1).toBe(false);
  });
});
