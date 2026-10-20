import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({ read: vi.fn(), get: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/api/audit-batch2", () => ({ readCampaignPerformance: mocks.read }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "session" }));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("not-found");
  },
  redirect: (path: string) => {
    throw new Error(`redirect:${path}`);
  },
}));
vi.mock("./report-issuance-panel", () => ({
  ReportIssuancePanel: ({ measurementRunId }: { measurementRunId: string }) => (
    <p data-testid="download">Download available for {measurementRunId}</p>
  ),
}));
import CampaignReportPage from "./page";
const campaignId = "00000000-0000-4000-8000-000000000001";
const report = {
  campaign_id: campaignId,
  start_at: null,
  end_at: null,
  totals: { distance_m: "25000", trip_count: 2, driving_days: 1, estimated_views: "250" },
  areas: [],
  completeness: "Some trips are still being checked.",
  uncertainty: "Views are estimates, not measured people.",
  measurement_run_id: null,
  report_issuance_id: null,
  report_status: null,
};
const page = () => CampaignReportPage({ params: Promise.resolve({ campaignId }) });
beforeEach(() => {
  vi.resetAllMocks();
  mocks.read.mockResolvedValue({ data: report });
});
it.each([1, 2, 3])(
  "shows authorised campaign totals for %s cars without legacy fine-result requests",
  async (cars) => {
    mocks.read.mockResolvedValue({
      data: { ...report, totals: { ...report.totals, trip_count: cars } },
    });
    const { container } = render(await page());
    expect(screen.getByText("25 km")).toBeInTheDocument();
    expect(screen.getByText("Estimated views")).toBeInTheDocument();
    expect(screen.getByText("250")).toBeInTheDocument();
    expect(screen.getByText(report.uncertainty)).toBeInTheDocument();
    expect(screen.getByText(/Area results aren’t available/)).toBeInTheDocument();
    expect(container).not.toHaveTextContent(
      /driver cost|rank|fingerprint|measurement-run|Not enough cars/i,
    );
    expect(mocks.get).not.toHaveBeenCalled();
    expect(mocks.read).toHaveBeenCalledTimes(1);
  },
);
it("preserves genuine zero totals and unknown estimated views", async () => {
  mocks.read.mockResolvedValue({
    data: {
      ...report,
      totals: { distance_m: "0", trip_count: 0, driving_days: 0, estimated_views: null },
    },
  });
  render(await page());
  expect(screen.getByText("0 km")).toBeInTheDocument();
  expect(screen.getAllByText("0")).toHaveLength(2);
  expect(screen.getByText("—")).toBeInTheDocument();
});
it("renders only the server-returned safe areas with a nullable estimate", async () => {
  mocks.read.mockResolvedValue({
    data: {
      ...report,
      areas: [
        { area_id: "safe", name: "Wuse II", trip_count: 2, modelled_potential_contacts: null },
      ],
    },
  });
  render(await page());
  expect(screen.getByRole("rowheader", { name: "Wuse II" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "—" })).toBeInTheDocument();
});
it("keeps existing report download authority when a run handle exists", async () => {
  mocks.read.mockResolvedValue({ data: { ...report, measurement_run_id: "run" } });
  render(await page());
  expect(screen.getByTestId("download")).toHaveTextContent("Download available for run");
});
it.each([409, 503])("shows unavailable rather than inventing totals on %s", async (status) => {
  mocks.read.mockRejectedValue(
    new ApiError(status, {
      code: status === 409 ? "CAMPAIGN_REPORT_PENDING" : "UNAVAILABLE",
      message: "private detail",
    }),
  );
  const { container } = render(await page());
  expect(screen.getByRole("status", { name: "Results unavailable" })).toBeInTheDocument();
  expect(screen.queryByText("25 km")).toBeNull();
  expect(container).not.toHaveTextContent("private detail");
});
it("rejects another campaign's response", async () => {
  mocks.read.mockResolvedValue({ data: { ...report, campaign_id: "other" } });
  await expect(page()).rejects.toThrow("not-found");
});
it("redirects an expired session", async () => {
  mocks.read.mockRejectedValue(new ApiError(401, { code: "EXPIRED", message: "expired" }));
  await expect(page()).rejects.toThrow("redirect:/login");
});
