import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("./issue-form", () => ({ IssueMeasurementForm: () => <div>Prepare run form</div> }));

import MeasurementQueue from "./page";

const run = {
  id: "run-1",
  campaign_name: "Airtel Lagos Commute",
  period_start_at: "2026-09-01T00:00:00Z",
  period_end_at: "2026-10-01T00:00:00Z",
  created_at: "2026-10-02T00:00:00Z",
  test_only: false,
  reproducible: true,
  superseded: false,
  report_issuance_id: null,
  report_status: null,
};

const props = (params: { offset?: string; q?: string } = {}) => ({
  searchParams: Promise.resolve(params),
});

describe("measurement work list", () => {
  beforeEach(() => mocks.get.mockReset());

  it("lists named runs with reproducibility, supersession and download state", async () => {
    mocks.get.mockResolvedValue({
      data: {
        items: [
          run,
          {
            ...run,
            id: "run-2",
            campaign_name: "PalmPay Market Routes",
            superseded: true,
            test_only: true,
            report_issuance_id: "report-9",
            report_status: "published",
          },
          { ...run, id: "run-3", campaign_name: "Mismatch Campaign", reproducible: false },
        ],
        total: 3,
      },
    });
    render(await MeasurementQueue(props({ q: "Lagos", offset: "abc" })));
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/measurement-runs", {
      params: { query: { limit: 25, offset: 0, q: "Lagos" } },
    });
    expect(screen.getByLabelText("Search this work list")).toHaveValue("Lagos");
    expect(screen.getByText("Prepare run form")).toBeTruthy();

    const current = screen.getByRole("link", { name: /Airtel Lagos Commute/ });
    expect(current).toHaveAttribute("href", "/admin/measurement/run-1");
    expect(current).toHaveTextContent("Reproducible snapshot · Downloads: Not requested");

    const superseded = screen.getByRole("link", { name: /PalmPay Market Routes/ });
    expect(superseded).toHaveAttribute("href", "/admin/measurement/run-2?report=report-9");
    expect(superseded).toHaveTextContent("Synthetic test · Superseded snapshot");
    expect(superseded).toHaveTextContent("Downloads: published");

    expect(screen.getByRole("link", { name: /Mismatch Campaign/ })).toHaveTextContent(
      "Reproduction mismatch — do not issue",
    );
  });

  it("keeps the search term in pagination links", async () => {
    mocks.get.mockResolvedValue({ data: { items: [run], total: 60 } });
    render(await MeasurementQueue(props({ q: "Lagos", offset: "25" })));
    const hrefs = screen
      .getAllByRole("link")
      .map((link) => link.getAttribute("href") ?? "")
      .filter((href) => href.startsWith("/admin/measurement?"));
    expect(hrefs.length).toBeGreaterThan(0);
    expect(hrefs.every((href) => href.includes("q=Lagos"))).toBe(true);
  });

  it("separates no matching runs from an unavailable work list", async () => {
    mocks.get.mockResolvedValue({ data: { items: [], total: 0 } });
    const { unmount } = render(await MeasurementQueue(props()));
    expect(screen.getByText(/No matching measurement runs/)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    unmount();

    mocks.get.mockResolvedValue({ data: undefined });
    render(await MeasurementQueue(props()));
    expect(screen.getByRole("alert")).toHaveTextContent("No empty or complete result");
    expect(screen.queryByText(/No matching measurement runs/)).toBeNull();
  });
});
