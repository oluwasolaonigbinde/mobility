import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ get: vi.fn(), role: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: mocks.role }));
vi.mock("./actions", () => ({
  switchAutomaticPayoutsAction: vi.fn(async () => ({})),
  releaseUnsentAction: vi.fn(async () => ({})),
  resolveAlertAction: vi.fn(async () => ({})),
}));

import AutomaticPayoutsPage from "./page";

const NOT_SET_UP = {
  switched_on: false,
  frequency: null,
  batch_limit: null,
  currency: "NGN",
  missing_settings: [
    "PAYOUT_AUTOMATIC_APPROVAL_ENABLED",
    "PAYOUT_AUTOMATIC_FREQUENCY",
    "PAYOUT_AUTOMATIC_BATCH_LIMIT_NGN",
  ],
  paused: false,
  pause_reason: null,
  pause_changed_by_name: null,
  pause_changed_at: null,
  identity_ready: true,
  provider_ready: false,
  runnable: false,
  last_run: null,
  open_alert_count: 0,
  unsent_count: 0,
};
const RUNNING = {
  ...NOT_SET_UP,
  switched_on: true,
  frequency: "weekly",
  batch_limit: "50000.00",
  missing_settings: [],
  provider_ready: true,
  runnable: true,
  last_run: {
    id: "run",
    period_key: "2026-W40",
    created_at: "2026-09-28T00:05:00Z",
    batch_count: 2,
    line_count: 3,
    total_amount: "12000.00",
  },
};
const ALERT = {
  id: "7f9c1f4e-8a5b-4c3d-9e2f-1a2b3c4d5e6f",
  kind: "daily_limit",
  created_at: "2026-09-28T00:05:00Z",
  driver_name: "Bola Driver",
  lagos_day: "2026-09-27",
  amount: "6000.00",
  currency: "NGN",
  batch_id: "batch-1",
  line_id: null,
  detail: { earned: "12000.00", ceiling: "10000.00" },
  resolved_at: null,
  resolved_by_name: null,
  resolution_note: null,
};
const DAY = {
  day: "2026-09-28",
  runs: [RUNNING.last_run],
  outcomes: [
    { outcome: "submitted", count: 2, amount: "8000.00" },
    { outcome: "succeeded", count: 1, amount: "4000.00" },
  ],
  provider_evidence: [
    { outcome: "succeeded", applied: true, count: 1 },
    { outcome: "succeeded", applied: false, count: 1 },
  ],
  awaiting_provider_count: 2,
  alerts_raised: [{ kind: "daily_limit", count: 1 }],
  kept_for_manual_review: [{ reason: "fraud_flag", count: 1, amount: "3000.00" }],
  lines: [
    {
      id: "line-1",
      batch_id: "batch-1",
      driver_name: "Ada Driver",
      amount: "4000.00",
      currency: "NGN",
      outcome: "succeeded",
      provider_transfer_reference: "ref",
      last_provider_evidence_at: "2026-09-28T01:00:00Z",
    },
  ],
  total: 3,
  limit: 100,
  offset: 0,
};

function api({
  status = NOT_SET_UP as object | null,
  alerts = [] as object[] | null,
  day = { ...DAY, runs: [], outcomes: [], lines: [], total: 0 } as object | null,
} = {}) {
  mocks.get.mockImplementation(async (path: string) => {
    if (path.endsWith("/status")) {
      if (status === null) throw new Error("down");
      return { data: status };
    }
    if (path.endsWith("/alerts")) {
      if (alerts === null) throw new Error("down");
      return { data: { items: alerts, total: alerts.length, limit: 50, offset: 0 } };
    }
    if (path.endsWith("/reconciliation")) {
      if (day === null) return {};
      return { data: day };
    }
    throw new Error(`Unexpected ${path}`);
  });
}

const page = (day?: string) => AutomaticPayoutsPage({ searchParams: Promise.resolve({ day }) });

describe("AutomaticPayoutsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.role.mockResolvedValue({ user: { id: "admin" } });
  });

  it("says plainly that nothing runs until every setting is supplied", async () => {
    api();
    render(await page());
    expect(mocks.role).toHaveBeenCalledWith("admin");
    expect(screen.getByText("Not set up yet — nothing is paid automatically.")).toBeVisible();
    expect(screen.getByText("The automatic payout switch is off")).toBeVisible();
    expect(screen.getByText("The most one automatic run may pay has not been set")).toBeVisible();
    expect(screen.getByText(/No payment provider is connected yet/)).toBeVisible();
    expect(screen.getByText("Nothing to follow up.")).toBeVisible();
    expect(screen.getByText("No automatic payouts ran on this day.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Pause automatic payouts" })).toBeVisible();
    expect(screen.getAllByText("Not set")).toHaveLength(2);
  });

  it("shows a running status, open problems and the day's reconciliation", async () => {
    api({ status: RUNNING, alerts: [ALERT], day: DAY });
    render(await page("2026-09-28"));
    expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/payouts/automatic/reconciliation", {
      params: { query: { day: "2026-09-28", limit: 100 } },
    });
    expect(screen.getByText(/Running — Cardvert pays clean daily-rate earnings/)).toBeVisible();
    expect(screen.getByText("Weekly")).toBeVisible();
    expect(screen.getByText("₦50,000.00")).toBeVisible();
    expect(screen.getByText(/3 payments · ₦12,000.00/)).toBeVisible();
    const problem = screen
      .getByText("Above one day's pay — kept for a person to check")
      .closest("li")!;
    expect(within(problem).getByText(/Raised by Cardvert/)).toHaveTextContent("Bola Driver");
    expect(within(problem).getByText(/day 2026-09-27 \(WAT\)/)).toBeVisible();
    expect(
      within(problem).getByText("Earned ₦12000.00 against a day rate of ₦10000.00."),
    ).toBeVisible();
    expect(within(problem).getByRole("link", { name: "Open the payout batch" })).toHaveAttribute(
      "href",
      "/admin/payouts/batches/batch-1",
    );
    expect(within(problem).getByRole("button", { name: "Mark as followed up" })).toBeVisible();
    expect(screen.getByText("Sent — waiting for the bank")).toBeVisible();
    expect(screen.getByText(/Bank answers recorded: Paid 1 · Paid 1 \(no change\)/)).toBeVisible();
    expect(screen.getByText("Trip had a review flag: 1 · ₦3,000.00")).toBeVisible();
    expect(screen.getByRole("link", { name: "Ada Driver" })).toHaveAttribute(
      "href",
      "/admin/payouts/batches/batch-1",
    );
    expect(screen.getByText("3 automatic payments started this day.")).toBeVisible();
  });

  it("offers resume and moving unsent payments while paused, naming who paused and why", async () => {
    api({
      status: {
        ...RUNNING,
        paused: true,
        runnable: false,
        pause_reason: "Bank holiday",
        pause_changed_by_name: "Funmi Finance",
        pause_changed_at: "2026-09-28T08:00:00Z",
        unsent_count: 2,
      },
    });
    render(await page());
    expect(screen.getByText("Paused — Cardvert is not sending automatic payouts.")).toBeVisible();
    expect(screen.getByText(/Paused by Terrax Media \(Funmi Finance\)/)).toHaveTextContent(
      "“Bank holiday”",
    );
    expect(screen.getByRole("button", { name: "Resume automatic payouts" })).toBeVisible();
    expect(
      screen.getByRole("textbox", { name: "Why move the 2 unsent payments to manual review?" }),
    ).toBeVisible();
  });

  it("confirms before moving unsent payments", async () => {
    api({ status: { ...NOT_SET_UP, unsent_count: 1 } });
    render(await page());
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    fireEvent.submit(
      screen
        .getByRole("button", { name: "Move unsent payments to manual review" })
        .closest("form")!,
    );
    expect(confirm).toHaveBeenCalledWith("Move every unsent automatic payment to manual review?");
    confirm.mockRestore();
  });

  it("warns when the Cardvert identity was changed and when set up but not running", async () => {
    api({ status: { ...RUNNING, runnable: false, identity_ready: false } });
    render(await page());
    expect(screen.getByText("Set up, but not running yet.")).toBeVisible();
    expect(screen.getByText(/payout identity is missing or was changed/)).toBeVisible();
  });

  it("keeps each panel's failure separate", async () => {
    api({ status: null, alerts: null, day: null });
    render(await page("not-a-day"));
    expect(screen.getByText("Couldn't load the status. Refresh to try again.")).toBeVisible();
    expect(screen.getByText("Couldn't load problems. Refresh to try again.")).toBeVisible();
    expect(screen.getByText("Couldn't load this day. Refresh to try again.")).toBeVisible();
  });
});
