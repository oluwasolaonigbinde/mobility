import { describe, expect, it } from "vitest";
import { isCancellableCampaign } from "./cancellation";

describe("isCancellableCampaign", () => {
  it.each(["approved", "active", "paused"])("allows %s", (status) =>
    expect(isCancellableCampaign(status)).toBe(true),
  );
  it.each([
    "scheduled",
    "draft",
    "pending_review",
    "rejected",
    "completed",
    "cancelled",
    "unknown",
  ])("refuses %s", (status) => expect(isCancellableCampaign(status)).toBe(false));
});
