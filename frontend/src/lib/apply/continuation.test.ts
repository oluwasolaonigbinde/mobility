import { describe, expect, it } from "vitest";
import { validContinuation } from "./continuation";

const later = new Date(Date.now() + 3600_000).toISOString();
const answer = (extra: Record<string, unknown> = {}) => ({
  step: "details",
  state: "details_needed",
  changes_reason: null,
  expires_at: later,
  ...extra,
});

describe("application continuation (REQ-195)", () => {
  it.each([
    ["details", "details_needed"],
    ["details", "details_in_review"],
    ["car", "car_needed"],
    ["car", "car_in_review"],
  ])("keeps %s / %s with no reason", (step, state) => {
    expect(validContinuation(answer({ step, state }))).toEqual({
      step,
      state,
      changes_reason: null,
      expires_at: later,
    });
  });
  it("keeps the changes reason exactly as given", () => {
    const reason = "Your ID details do not match. Please check them.";
    expect(
      validContinuation(answer({ state: "details_changes_needed", changes_reason: reason }))
        ?.changes_reason,
    ).toBe(reason);
  });
  it("drops fields it does not know", () => {
    expect(validContinuation({ ...answer(), token: "secret" })).not.toHaveProperty("token");
  });
  it.each([
    null,
    "details",
    answer({ step: "apply" }),
    answer({ state: "approved" }),
    answer({ step: "car", state: "details_needed" }),
    answer({ state: "toString" }),
    answer({ state: "details_changes_needed" }),
    answer({ state: "details_changes_needed", changes_reason: " " }),
    answer({ changes_reason: "Unexpected" }),
    answer({ expires_at: "bad" }),
    answer({ expires_at: new Date(Date.now() - 1000).toISOString() }),
  ])("rejects an inconsistent or expired answer %j", (value) => {
    expect(validContinuation(value)).toBeNull();
  });
});
