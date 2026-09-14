import { describe, expect, it } from "vitest";
import { presentApplicationStage } from "./application-status";

describe("presentApplicationStage", () => {
  it.each([
    ["not_submitted", "Not submitted"],
    ["pending_review", "Under review"],
    ["approved", "Approved"],
    ["rejected", "Changes needed"],
    ["expired", "Renewal needed"],
  ])("presents %s as a human progress state", (status, label) => {
    expect(presentApplicationStage(status).label).toBe(label);
  });

  it("does not invent progress for an unknown backend state", () => {
    expect(presentApplicationStage("future_state")).toEqual(
      expect.objectContaining({ label: "Status unavailable" }),
    );
  });
});
