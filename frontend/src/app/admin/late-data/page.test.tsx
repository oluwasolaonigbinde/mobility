import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("../operation-form", () => ({
  OperationForm: ({ id, trip }: { id: string; trip: string }) => (
    <div>
      Review controls {id} {trip}
    </div>
  ),
}));

import LateDataQueue from "./page";

const batch = {
  id: "batch-1",
  trip_session_id: "abcdef12-3456-4789-8abc-def012345678",
  campaign_name: "Airtel Lagos Commute",
  driver_name: "Ada Driver",
  vehicle_plate: "ABJ-101",
  ping_count: 42,
  received_at: "2026-09-14T10:00:00Z",
  status: "quarantined",
  resolution_note: null,
  resolved_at: null,
};

const props = (params: { offset?: string; status?: string } = {}) => ({
  searchParams: Promise.resolve(params),
});

describe("late trip evidence queue", () => {
  beforeEach(() => mocks.get.mockReset());

  it("defaults to pending review with named context and review controls", async () => {
    mocks.get.mockResolvedValue({ data: { items: [batch], total: 1 } });
    render(await LateDataQueue(props({ offset: "-4", status: "bogus" })));
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/trips/quarantined-batches", {
      params: { query: { limit: 25, offset: 0, status: "quarantined" } },
    });
    expect(screen.getByRole("combobox", { name: "Status" })).toHaveValue("quarantined");
    const row = screen.getByRole("heading", { name: /Airtel Lagos Commute/ }).parentElement!;
    expect(row).toHaveTextContent("Airtel Lagos Commute · Ada Driver");
    expect(row).toHaveTextContent("ABJ-101 · 42 samples");
    expect(row).toHaveTextContent("Trip reference abcdef12");
    expect(within(row).getByText(/Review controls batch-1/)).toBeTruthy();
    expect(screen.getByText(/never reprices earnings or\s+edits an issued report/)).toBeTruthy();
  });

  it("shows reviewed history without review controls and with missing context labelled", async () => {
    mocks.get.mockResolvedValue({
      data: {
        items: [
          {
            ...batch,
            id: "batch-2",
            status: "applied",
            campaign_name: null,
            driver_name: null,
            vehicle_plate: null,
            resolution_note: "Applied after operator review",
            resolved_at: "2026-09-14T12:00:00Z",
          },
          { ...batch, id: "batch-3", status: "applied", resolved_at: null },
        ],
        total: 60,
      },
    });
    render(await LateDataQueue(props({ status: "applied", offset: "25" })));
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/trips/quarantined-batches", {
      params: { query: { limit: 25, offset: 25, status: "applied" } },
    });
    expect(screen.getByText("Campaign unavailable · Driver unavailable")).toBeTruthy();
    expect(screen.getByText(/Vehicle unavailable/)).toBeTruthy();
    expect(screen.getByText("Applied after operator review")).toBeTruthy();
    expect(screen.getByText("Reviewed date unavailable")).toBeTruthy();
    expect(screen.queryByText(/Review controls/)).toBeNull();
    const pageLinks = screen
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"))
      .filter(Boolean);
    expect(pageLinks).toContain("/admin/late-data?status=applied&offset=0");
    expect(pageLinks.every((href) => href!.startsWith("/admin/late-data?status=applied"))).toBe(
      true,
    );
  });

  it("reports an empty queue as empty, not unavailable", async () => {
    mocks.get.mockResolvedValue({ data: { items: [], total: 0 } });
    render(await LateDataQueue(props({ status: "discarded" })));
    expect(screen.getByText("No discarded late-data batches.")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("reports an unavailable queue without implying an empty result", async () => {
    mocks.get.mockResolvedValue({ data: undefined, error: { code: "UNAVAILABLE" } });
    render(await LateDataQueue(props()));
    expect(screen.getByRole("alert")).toHaveTextContent("No empty or complete result");
    expect(screen.queryByText(/late-data batches\./)).toBeNull();
  });
});
