import { expect, it } from "vitest";
import { jobStartMessage } from "./start-message";

it("uses ready and blocker codes without exposing backend text", () => {
  expect(jobStartMessage({ ready: true })).toBe("Everything is ready. You can start this job.");
  expect(jobStartMessage({ blocker_code: "FROZEN_PAYOUT_BINDING_REQUIRED" })).toBe(
    "Pay terms are missing. Send a new offer.",
  );
  expect(jobStartMessage({ blocker_code: "INSTALLATION_EVIDENCE_EXPIRED" })).toBe(
    "New installation photos are needed.",
  );
  expect(jobStartMessage({ blocker_code: "APPROVED_INSTALLATION_EVIDENCE_REQUIRED" })).toBe(
    "Installation photos must be approved first.",
  );
  expect(jobStartMessage({ blocker_code: "NEW_INTERNAL_CODE" })).not.toContain("NEW_INTERNAL_CODE");
});
