import { describe, expect, it } from "vitest";
import { presentApplicationStage } from "./application-status";

describe("presentApplicationStage", () => {
  it.each([
    ["not_submitted", "Not sent yet"],
    ["pending_review", "Being checked"],
    ["approved", "Approved"],
    ["rejected", "Changes needed"],
    ["expired", "Send again"],
  ])("presents %s as a human progress state", (status, label) => {
    expect(presentApplicationStage(status).label).toBe(label);
  });

  it("does not invent progress for an unknown backend state", () => {
    expect(presentApplicationStage("future_state")).toEqual(
      expect.objectContaining({ label: "Status unavailable" }),
    );
  });
});
