import { expect, it } from "vitest";
import { adminStatus, adminTone } from "./admin";
it("uses context-specific staff words without leaking internal keys", () => {
  expect(adminStatus("pending", "driver")).toBe("Applicant");
  expect(adminStatus("pending_review", "campaign")).toBe("For review");
  expect(adminStatus("active", "campaign")).toBe("Live");
  expect(adminStatus("reserved")).toBe("Waiting for approval");
  expect(adminStatus("acknowledged", "review")).toBe("Looking into it");
  expect(adminStatus("confirmed", "review")).toBe("Problem confirmed");
  expect(adminStatus("dismissed", "review")).toBe("Cleared");
  expect(adminStatus("quarantined")).toBe("Late upload");
  expect(adminStatus("open", "contact")).toBe("Needs contact");
  expect(adminStatus("completed", "contact")).toBe("Completed");
  expect(adminStatus("open", "complaint")).toBe("Needs a reply");
  expect(adminStatus("answered", "complaint")).toBe("Waiting on them");
  expect(adminStatus("resolved", "complaint")).toBe("Resolved");
  expect(adminStatus("new_internal_state")).toBe("Unknown status");
  expect(adminStatus(undefined)).toBe("Not recorded");
  expect(adminTone("paid")).toBe("green");
  expect(adminTone("failed")).toBe("coral");
  expect(adminTone("held")).toBe("amber");
  expect(adminTone("unknown")).toBe("default");
});

it("preserves provider payment meanings and hides unrecognized wire outcomes", () => {
  expect(adminStatus("queued", "payment_outcome")).toBe("Queued — not submitted");
  expect(adminStatus("reserved", "payment_outcome")).toBe("Waiting for approval");
  expect(adminStatus("submitted", "payment_outcome")).toBe("Submitted — awaiting verification");
  expect(adminStatus("provider_unknown", "payment_outcome")).toBe("Provider outcome unknown");
  expect(adminStatus("unknown", "payment_outcome")).toBe("Provider outcome unknown");
  expect(adminStatus("succeeded", "payment_outcome")).toBe("Verified paid");
  expect(adminStatus("failed", "payment_outcome")).toBe("Failed");
  expect(adminStatus("void", "payment_outcome")).toBe("Voided");
  expect(adminStatus("private_internal_state", "payment_outcome")).toBe("Unknown status");
});
