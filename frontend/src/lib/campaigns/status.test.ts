import { describe, expect, it } from "vitest";
import { CAMPAIGN_STATUSES, isCampaignStatus, statusLabel, statusTone } from "./status";

describe("campaign review statuses", () => {
  it("keeps all generated review statuses available to filters and status chips", () => {
    expect(CAMPAIGN_STATUSES).toEqual(
      expect.arrayContaining(["draft", "pending_review", "approved", "rejected"]),
    );
    expect(statusLabel.pending_review).toBe("Pending review");
    expect(statusLabel.approved).toBe("Approved");
    expect(statusLabel.rejected).toBe("Changes requested");
    expect(statusTone.pending_review).toBe("amber");
    expect(statusTone.approved).toBe("cyan");
    expect(statusTone.rejected).toBe("coral");
  });

  it("recognizes every lifecycle value represented in the generated contract", () => {
    for (const status of CAMPAIGN_STATUSES) {
      expect(isCampaignStatus(status)).toBe(true);
    }
  });
});
