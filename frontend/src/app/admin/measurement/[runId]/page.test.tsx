import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ get: vi.fn(), reportForm: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("../report-form", () => ({
  ReportForm: (props: { runId: string; canIssue: boolean; initialReport?: { id: string } }) => {
    mocks.reportForm(props);
    return <div>Report form for {props.runId}</div>;
  },
}));

import MeasurementDetail from "./page";

const run = {
  id: "run-1",
  period_start_at: "2026-09-01T00:00:00Z",
  period_end_at: "2026-10-01T00:00:00Z",
  reproducible: true,
  test_only: false,
  method_revision: "method-3",
  formula_version: "formula-2",
  result_manifest: {
    metrics: [
      {
        id: "exposure",
        label: "Estimated ad exposure",
        class: "modelled_measure",
        value: "12,400",
        completeness: { complete: true, covered_trip_count: 8, denominator_trip_count: 8 },
      },
      {
        id: "hours",
        label: "Verified campaign hours",
        class: "recorded_fact",
        value: null,
        completeness: { complete: false, denominator_trip_count: 5 },
      },
      { label: "Zone contacts", completeness: { suppressed: true } },
    ],
  },
};

function props(report?: string) {
  return {
    params: Promise.resolve({ runId: "run-1" }),
    searchParams: Promise.resolve(report ? { report } : {}),
  };
}

describe("measurement run detail", () => {
  beforeEach(() => {
    mocks.get.mockReset();
    mocks.reportForm.mockReset();
  });

  it("shows unavailable instead of an empty result when the run cannot be read", async () => {
    mocks.get.mockRejectedValue(new Error("network"));
    render(await MeasurementDetail(props()));
    expect(screen.getByRole("alert")).toHaveTextContent("No empty or complete result");
  });

  it("separates estimates from facts and never renders missing evidence as complete", async () => {
    mocks.get.mockResolvedValue({ data: run });
    render(await MeasurementDetail(props()));
    expect(mocks.get).toHaveBeenCalledTimes(1);
    expect(screen.getByText("The saved snapshot can be reproduced.")).toBeTruthy();
    expect(screen.queryByText(/Synthetic test evidence/)).toBeNull();

    const exposure = screen.getByRole("heading", { name: "Estimated ad exposure" }).parentElement!;
    expect(exposure).toHaveTextContent("Estimated advertising result");
    expect(exposure).toHaveTextContent("12,400");
    expect(exposure).toHaveTextContent("Complete for this saved cohort");
    expect(exposure).toHaveTextContent("8 of 8 trips covered");

    const hours = screen.getByRole("heading", { name: "Verified campaign hours" }).parentElement!;
    expect(hours).toHaveTextContent("Recorded operational or financial facts");
    expect(hours).toHaveTextContent("a single total is not available");
    expect(hours).toHaveTextContent("Incomplete or unavailable evidence");
    expect(hours).not.toHaveTextContent("Complete for this saved cohort");
    expect(hours).toHaveTextContent("Unknown of 5 trips covered");

    const zone = screen.getByRole("heading", { name: "Zone contacts" }).parentElement!;
    expect(zone).toHaveTextContent("Suppressed: insufficient shareable evidence");
    expect(zone).not.toHaveTextContent("trips covered");

    expect(screen.getByText("Method method-3 · Formula formula-2")).toBeTruthy();
    expect(mocks.reportForm).toHaveBeenCalledWith({
      runId: "run-1",
      canIssue: true,
      initialReport: undefined,
    });
  });

  it("blocks issuance for a non-reproducible synthetic snapshot without metrics", async () => {
    mocks.get.mockResolvedValue({
      data: { ...run, reproducible: false, test_only: true, result_manifest: {} },
    });
    render(await MeasurementDetail(props()));
    expect(screen.getByText(/Reproduction mismatch. Do not rely on this snapshot/)).toBeTruthy();
    expect(screen.getByText(/Synthetic test evidence/)).toBeTruthy();
    expect(screen.queryByRole("heading", { level: 2 })).toBeNull();
    expect(mocks.reportForm).toHaveBeenCalledWith(expect.objectContaining({ canIssue: false }));
  });

  it("loads the selected report for the same snapshot", async () => {
    const report = { id: "report-1", measurement_run_id: "run-1" };
    mocks.get.mockResolvedValueOnce({ data: run }).mockResolvedValueOnce({ data: report });
    render(await MeasurementDetail(props("report-1")));
    expect(mocks.get).toHaveBeenLastCalledWith("/api/v1/admin/report-issuances/{issuance_id}", {
      params: { path: { issuance_id: "report-1" } },
    });
    expect(mocks.reportForm).toHaveBeenCalledWith(
      expect.objectContaining({ initialReport: report }),
    );
  });

  it("refuses a report selected from a different or unreadable snapshot", async () => {
    mocks.get
      .mockResolvedValueOnce({ data: run })
      .mockResolvedValueOnce({ data: { id: "report-2", measurement_run_id: "other-run" } });
    render(await MeasurementDetail(props("report-2")));
    expect(screen.getByRole("alert")).toHaveTextContent("belongs to a different snapshot");
    expect(mocks.reportForm).not.toHaveBeenCalled();

    mocks.get.mockReset();
    mocks.get.mockResolvedValueOnce({ data: run }).mockRejectedValueOnce(new Error("gone"));
    render(await MeasurementDetail(props("report-3")));
    expect(screen.getAllByRole("alert")).toHaveLength(2);
    expect(mocks.reportForm).not.toHaveBeenCalled();
  });
});
