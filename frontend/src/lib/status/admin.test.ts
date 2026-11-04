import { readdirSync, readFileSync } from "node:fs";
import { resolve, join } from "node:path";
import { expect, it } from "vitest";
import { adminStatus, adminTone, paymentRunStatus } from "./admin";
import { advertiserStatus } from "./advertiser";
import { adminActivity } from "./admin";

it.each([
  ["stored_file.read", "Private document viewed"],
  ["installation_evidence.read", "Installation photo viewed"],
  ["auth.session.refreshed", "Sign-in session renewed"],
  ["billing.receipt.observed", "Transfer recorded"],
  ["campaign_report.ready", "Campaign report ready"],
])("labels the visible activity %s", (action, label) => expect(adminActivity(action)).toBe(label));
it("matches advertiser receipt labels without implying an unchecked payment is confirmed", () => {
  expect(adminStatus("recorded", "receipt")).toBe("Recorded – being checked");
  expect(adminStatus("confirmed", "receipt")).toBe("Confirmed");
  expect(adminStatus("confirmed", "receipt")).toBe("Confirmed");
  expect(adminStatus("unrecognised_receipt_state", "receipt")).toBe("Unknown status");
});
it("uses context-specific staff words without leaking internal keys", () => {
  expect(adminStatus("pending", "driver")).toBe("Applicant");
  expect(adminStatus("pending_review", "campaign")).toBe("For review");
  expect(adminStatus("active", "campaign")).toBe("Running");
  expect(adminStatus("reserved")).toBe("Waiting for approval");
  expect(adminStatus("open", "review")).toBe("Needs attention");
  expect(adminStatus("confirmed", "review")).toBe("Problem confirmed");
  expect(adminStatus("dismissed", "review")).toBe("Cleared");
  expect(adminStatus("manual")).toBe("Manual approval");
  expect(adminStatus("open", "contact")).toBe("Needs contact");
  expect(adminStatus("completed", "contact")).toBe("Completed");
  expect(adminStatus("open", "complaint")).toBe("Needs a reply");
  expect(adminStatus("answered", "complaint")).toBe("Waiting on them");
  expect(adminStatus("resolved", "complaint")).toBe("Resolved");
  expect(adminStatus("queued", "report")).toBe("Being prepared");
  expect(adminStatus("processing", "report")).toBe("Being prepared");
  expect(adminStatus("ready", "report")).toBe("Ready");
  expect(adminStatus("failed", "report")).toBe("Failed");
  expect(adminStatus("new_internal_state")).toBe("Unknown status");
  expect(adminStatus(undefined)).toBe("Not recorded");
  expect(adminTone("paid")).toBe("green");
  expect(adminTone("failed")).toBe("coral");
  expect(adminTone("held")).toBe("amber");
  expect(adminTone("unknown")).toBe("default");
});

it("preserves provider payment meanings and hides unrecognized wire outcomes", () => {
  expect(adminStatus("queued", "payment_outcome")).toBe("Waiting to send");
  expect(adminStatus("reserved", "payment_outcome")).toBe("Waiting to send");
  expect(paymentRunStatus({ status: "reserved", approved_at: null })).toBe("Saved, not sent yet");
  expect(adminStatus("reserved", "payment_run")).toBe("Saved, not sent yet");
  expect(paymentRunStatus({ status: "reserved", approved_at: "2026-10-26T12:00:00Z" })).toBe(
    "Approved — not sent yet",
  );
  expect(paymentRunStatus({ status: "reconciled", approved_at: "2026-10-26T12:00:00Z" })).toBe(
    "Payment results recorded",
  );
  expect(adminStatus("submitted", "payment_outcome")).toBe("Sent — awaiting confirmation");
  expect(adminStatus("provider_unknown", "payment_outcome")).toBe("Payment result not known");
  expect(adminStatus("unknown", "payment_outcome")).toBe("Payment result not known");
  expect(adminStatus("succeeded", "payment_outcome")).toBe("Paid");
  expect(adminStatus("failed", "payment_outcome")).toBe("Failed");
  expect(adminStatus("void", "payment_outcome")).toBe("Voided");
  expect(adminStatus("private_internal_state", "payment_outcome")).toBe("Unknown status");
});

it.each([
  ["pending_admin", "Needs staff review"],
  ["pending_funding", "Waiting for funding"],
])("shows the approved advertiser campaign-change label for %s", (state, label) => {
  expect(advertiserStatus(state)).toBe(label);
});

it("retains advertiser labels and its fallback outside the two approved change states", () => {
  expect(advertiserStatus("active")).toBe("Running");
  expect(advertiserStatus("applied")).toBe("Applied");
  expect(advertiserStatus("pending")).toBe("Waiting");
  expect(advertiserStatus("held")).toBe("Status unavailable");
  expect(advertiserStatus("new_internal_state")).toBe("Status unavailable");
});

// Read-only enumeration from the preview seed at b46c14e0 (REQ-298).
it.each([
  "admin.advertiser_organization.created",
  "admin.bank_account.payout_verified",
  "admin.bank_account.read",
  "admin.campaign.approved",
  "admin.campaign.cancelled",
  "admin.campaign.paused",
  "admin.campaign_creative.approved",
  "admin.campaign_creative.rejected",
  "admin.campaign_payout_rule.created",
  "admin.complaint.replied",
  "admin.driver_account_setup.initiated",
  "admin.driver_application.approved",
  "admin.driver_application.rejected",
  "admin.driver_person_payee.approved",
  "admin.driver_person_payee.rejected",
  "admin.driver_vehicle.approved",
  "admin.driver_vehicle.expired",
  "admin.fraud_flag.resolved",
  "admin.kyc.nin_read",
  "admin.payout_automatic.paused",
  "admin.payout_automatic.resumed",
  "admin.payout_correction_order.approved",
  "admin.payout_line.reconciled",
  "admin.payout_rule_revision.created",
  "advertiser.campaign.created",
  "advertiser.campaign.submitted_for_review",
  "advertiser.campaign_change.requested",
  "advertiser.campaign_creative.created",
  "advertiser.campaign_creative.submitted_for_review",
  "advertiser.campaign_zone.created",
  "advertiser.complaint.created",
  "advertiser.login_invite.sent",
  "auth.driver_application.created",
  "auth.login.succeeded",
  "auth.password_reset.requested",
  "billing.expedited_waiver.accepted",
  "billing.liability_reservation.recorded",
  "billing.receipt.reversed",
  "billing.refund.recorded",
  "campaign.created",
  "campaign.updated",
  "campaign_assignment.created",
  "campaign_report.downloaded",
  "campaign_report.ready",
  "campaign_report.requested",
  "commercial.quotation_revision.recorded",
  "commercial.quote_request.created",
  "commercial.terms.accepted",
  "driver.campaign_assignment.accepted",
  "driver.kyc.submitted",
  "driver.trip.ended",
  "driver.trip.started",
  "driver.vehicle_evidence.submitted",
  "driver.vehicle_profile.submitted",
  "driver_application.bank_account.captured",
  "driver_application.payee.created",
  "evidence_verification.spot_check_recorded",
  "installation_evidence.history_read",
  "installation_evidence.queue_read",
  "installation_evidence.submitted",
  "provider.payout_line.reconciled",
  "stored_file.confirmed",
  "stored_file.read",
  "stored_file.scan_completed",
  "stored_file.upload_requested",
  "system.payout_automatic_alert.created",
  "trip.sealed",
  "worker.earnings.released",
  "worker.trip_processing.completed",
])("labels seeded activity %s without the fallback", (code) => {
  expect(adminActivity(code)).not.toBe("Activity recorded");
});

it("labels the literal action codes written by application flows", () => {
  function sourceFiles(directory: string): string[] {
    return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
      const path = join(directory, entry.name);
      return entry.isDirectory() ? sourceFiles(path) : entry.name.endsWith(".py") ? [path] : [];
    });
  }
  const codes = new Set<string>();
  for (const path of sourceFiles(resolve(process.cwd(), "../app"))) {
    for (const match of readFileSync(path, "utf8").matchAll(
      /(?:action|audit_action)\s*=\s*["']([a-z_]+(?:\.[a-z_]+)+)["']/g,
    ))
      codes.add(match[1]!);
  }
  expect(codes.size).toBeGreaterThan(150);
  for (const code of codes) expect(adminActivity(code), code).not.toBe("Activity recorded");
  // Dynamic writers use the finite complaint parties and review decisions.
  for (const code of [
    "admin.earnings.offset_settled",
    "admin.payout.recovery_offset",
    "trip.late_data.accepted",
    "admin.campaign.approved",
    "admin.campaign.rejected",
    "admin.campaign_creative.approved",
    "admin.campaign_creative.rejected",
    "driver.complaint.created",
    "driver.complaint.message_added",
    "advertiser.complaint.message_added",
    "admin.driver_person_payee.approved",
    "admin.driver_person_payee.rejected",
    "admin.driver_vehicle.approved",
    "admin.driver_vehicle.rejected",
    "admin.driver_application.approved",
    "admin.driver_application.rejected",
  ])
    expect(adminActivity(code), code).not.toBe("Activity recorded");
});
import { adminActor } from "./admin";
it("maps automation actors consistently while keeping human names and addresses", () => {
  expect(adminActor("report-automation@cardvert.invalid", "Report automation")).toBe("System");
  expect(adminActor("automatic-payouts@cardvert.invalid")).toBe("System");
  expect(adminActor("staff@example.test", "Ada")).toBe("Ada");
  expect(adminActor("staff@example.test")).toBe("staff@example.test");
});

it.each([
  ["void", "invoice", "Voided"],
  ["archived", "review", "Archived"],
  ["calculated", "payout_calculation", "Calculated"],
  ["insufficient_data", "payout_calculation", "Not enough trip data"],
  ["blocked", "payout_calculation", "Pay calculation blocked"],
])("labels the reachable %s status in %s", (value, context, label) => {
  expect(adminStatus(value, context)).toBe(label);
});
