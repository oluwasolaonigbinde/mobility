import { describe, expect, it } from "vitest";
import {
  alertDetail,
  alertLabel,
  formatWat,
  manualReasonLabel,
  missingSettingLabel,
  outcomeText,
  reconciliationDay,
  todayInWat,
  type AutomaticAlert,
} from "./automatic";

function alert(kind: string, detail: Record<string, unknown>): AutomaticAlert {
  return {
    id: "a",
    kind: kind as AutomaticAlert["kind"],
    created_at: "2026-09-28T09:00:00Z",
    driver_name: null,
    lagos_day: null,
    amount: null,
    currency: null,
    batch_id: null,
    line_id: null,
    detail,
    resolved_at: null,
    resolved_by_name: null,
    resolution_note: null,
  };
}

describe("automatic payout copy helpers", () => {
  it("uses Nigeria time for instants and days", () => {
    // 23:30 UTC is already the next day at 00:30 WAT.
    expect(todayInWat(new Date("2026-09-27T23:30:00Z"))).toBe("2026-09-28");
    expect(formatWat("2026-09-27T23:30:00Z")).toMatch(/28 Sept? 2026/);
    expect(formatWat(null)).toBe("—");
    expect(formatWat("not a date")).toBe("—");
  });

  it("accepts only a real YYYY-MM-DD day and otherwise uses today in WAT", () => {
    const now = new Date("2026-09-28T09:00:00Z");
    expect(reconciliationDay("2026-09-20", now)).toBe("2026-09-20");
    expect(reconciliationDay("2026-13-45", now)).toBe("2026-09-28");
    expect(reconciliationDay("yesterday", now)).toBe("2026-09-28");
    expect(reconciliationDay(undefined, now)).toBe("2026-09-28");
  });

  it("names settings, alerts, reasons and outcomes in plain words", () => {
    expect(missingSettingLabel("PAYOUT_AUTOMATIC_FREQUENCY")).toBe(
      "How often drivers are paid has not been set",
    );
    expect(missingSettingLabel("SOMETHING_ELSE")).toBe(
      "An automatic payout setting has not been supplied",
    );
    expect(alertLabel("duplicate_payment")).toBe("A possible duplicate payment");
    expect(alertLabel("new_kind")).toBe("Payment problem to review");
    expect(manualReasonLabel("open_dispute")).toBe("Driver has an open dispute");
    expect(manualReasonLabel("other_reason")).toBe("Payment needs a staff review");
    expect(outcomeText("succeeded")).toBe("Paid");
    expect(outcomeText("some_state")).toBe("Payment result not known");
  });

  it("explains each alert's detail without codes", () => {
    expect(alertDetail(alert("daily_limit", { rates_differ: true }))).toMatch(
      /different day rates/,
    );
    expect(alertDetail(alert("daily_limit", { other_pay_type_same_day: true }))).toMatch(/hourly/);
    expect(alertDetail(alert("daily_limit", { earned: "9000.00", ceiling: "8000.00" }))).toBe(
      "Earned ₦9000.00 against a day rate of ₦8000.00.",
    );
    expect(alertDetail(alert("daily_limit", {}))).toBeNull();
    expect(
      alertDetail(alert("batch_limit", { limit: "5000.00", reason: "above_run_limit" })),
    ).toMatch(/larger than the run limit/);
    expect(
      alertDetail(alert("batch_limit", { limit: "5000.00", reason: "run_limit_reached" })),
    ).toMatch(/wait for the next run/);
    expect(alertDetail(alert("run_failed", { reason: "provider_unavailable" }))).toMatch(
      /No payment provider/,
    );
    expect(alertDetail(alert("run_failed", { reason: "actor_changed" }))).toMatch(/identity/);
    expect(alertDetail(alert("failed_payment", {}))).toBeNull();
  });
});
