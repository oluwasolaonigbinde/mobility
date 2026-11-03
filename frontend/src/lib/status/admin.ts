/** Staff vocabulary. Context matters: an applicant is not a waiting payment. */
const common: Record<string, string> = {
  active: "Active",
  approved: "Approved",
  suspended: "Suspended",
  disabled: "Disabled",
  invited: "Invited",
  inactive: "Retired",
  draft: "Draft",
  pending_review: "Needs review",
  rejected: "Not approved",
  scheduled: "Scheduled",
  paused: "Paused",
  finished: "Finished",
  cancelled: "Cancelled",
  open: "Needs attention",
  confirmed: "Problem confirmed",
  dismissed: "Cleared",
  clean: "Clear",
  flagged: "On hold",
  applied: "Added to trip",
  discarded: "Ignored",
  offered: "Offered",
  accepted: "Accepted",
  declined: "Declined",
  expired: "Expired",
  reserved: "Waiting for approval",
  manual: "Manual approval",
  pending: "Waiting",
  processing: "Being checked",
  available: "Ready for payout",
  held: "On hold",
  paid: "Paid",
  reversal: "Taken back",
  failed: "Failed",
  passed: "Passed",
  not_submitted: "Not submitted",
  not_started: "Not started",
  verified: "Verified",
  unverified: "Not verified",
  submitted: "Submitted",
  requested: "Requested",
  sent: "Sent",
  received: "Received",
  refunded: "Refunded",
  voided: "Voided",
  issued: "Issued",
  published: "Published",
  recovered: "Recovered",
  superseded: "Replaced",
  succeeded: "Completed",
  error: "Needs attention",
  ready: "Ready",
  unpaid: "Unpaid",
  part_paid: "Part-paid",
  settled: "Settled",
  pending_approval: "Needs approval",
  pending_execution: "Ready to run",
  executing: "Running",
  executed: "Completed",
  partially_paid: "Part-paid",
  reversed: "Taken back",
  pending_admin: "Needs staff review",
  pending_funding: "Waiting for funding",
  deactivated: "Stopped",
  needs_review: "Needs review",
  approved_for_execution: "Ready to run",
};
const contexts: Record<string, Record<string, string>> = {
  report_kind: {
    weekly: "Weekly report",
    final: "Final report",
    custom: "Custom report",
    issued: "Issued report",
  },
  receipt: {
    observed: "Received",
    recorded: "Received",
    confirmed: "Confirmed",
    reversed: "Reversed",
  },
  payment_outcome: {
    reserved: "Waiting to send",
    queued: "Waiting to send",
    provider_unknown: "Payment result not known",
    unknown: "Payment result not known",
    succeeded: "Paid",
    failed: "Failed",
    submitted: "Sent — awaiting confirmation",
    void: "Voided",
  },
  payment_run: {
    completed: "Completed",
    void: "Voided",
    reserved: "Waiting to send",
    reconciled: "Payment results recorded",
  },
  correction: {
    stale: "Needs a new preview",
    executed: "Completed",
  },
  invoice: { paid: "Paid", part_paid: "Part-paid", unpaid: "Unpaid", void: "Voided" },
  audience: {
    ready: "Ready",
    stale: "Needs refresh",
    suppressed: "Hidden by privacy checks",
    empty: "No matching audience",
  },
  driver: { pending: "Applicant", rejected: "Not approved" },
  campaign: { active: "Running", pending_review: "For review", finished: "Finished" },
  job: { active: "Running", accepted: "Accepted" },
  review: { pending: "Needs review", pending_review: "Needs review" },
  report: { queued: "Being prepared", processing: "Being prepared", ready: "Ready" },
  complaint: { open: "Needs a reply", answered: "Waiting on them", resolved: "Resolved" },
  contact: { open: "Needs contact", completed: "Completed" },
  payment_class: {
    standard_prepaid: "Pay before production",
    approved_corporate_credit: "Approved company credit",
  },
  acceptance_method: {
    in_platform: "Accepted in Cardvert",
    external_recorded: "Acceptance recorded by staff",
  },
  correction_type: { credit_note: "Credit note", debit_note: "Debit note" },
  settlement: {
    refund_recorded: "Refund recorded",
    credit_settlement_recorded: "Credit settlement recorded",
  },
  cancellation: {
    cash_refund_due: "Cash refund due",
    cash_refund_not_due: "No cash refund due",
    credit_settlement_due: "Credit settlement due",
    no_settlement: "No settlement due",
  },
  production_authority: {
    standard_window_elapsed: "Waiting period completed",
    advertiser_expedited_waiver: "Advertiser approved an earlier start",
    approved_credit: "Approved company credit",
  },
};
export function adminStatus(value: string | null | undefined, context = "record"): string {
  if (!value) return "Not recorded";
  return contexts[context]?.[value] ?? common[value] ?? "Unknown status";
}
/** A run stays reserved until it is sent; approval is recorded separately (approved_at). */
export function paymentRunStatus(run: { status: string; approved_at: string | null }): string {
  if (run.status !== "reserved") return adminStatus(run.status, "payment_run");
  return run.approved_at ? "Approved — not sent yet" : "Waiting for approval";
}
const documents: Record<string, string> = {
  driver_license: "driving licence",
  driver_photo: "driver photo",
  registration: "car registration",
  insurance: "car insurance",
  vehicle_photo: "car photo",
};
export function adminDocumentLabel(value: string): string {
  return documents[value] ?? "document";
}
export function adminTone(value: string): "green" | "amber" | "coral" | "default" {
  if (["active", "approved", "available", "paid", "clean", "dismissed", "verified"].includes(value))
    return "green";
  if (["rejected", "suspended", "failed", "confirmed", "error"].includes(value)) return "coral";
  if (["pending", "pending_review", "reserved", "held", "paused", "flagged"].includes(value))
    return "amber";
  return "default";
}
const actions: Record<string, string> = {
  "auth.login.succeeded": "Signed in",
  "auth.login.failed": "Sign-in unsuccessful",
  "auth.login.rate_limited": "Sign-in temporarily limited",
  "admin.campaign.resumed": "Campaign resumed",
  "admin.campaign.paused": "Campaign paused",
  "driver.profile.updated": "Driver updated their details",
  "admin.driver_profile.created": "Driver profile created",
  "admin.driver_profile.updated": "Driver details or status updated",
  "advertiser.campaign.created": "Campaign created",
  "advertiser.campaign.updated": "Campaign details updated",
  "advertiser.campaign.submitted_for_review": "Campaign sent for review",
  "admin.campaign.approved": "Campaign approved",
  "admin.campaign.rejected": "Campaign not approved",
  "admin.campaign.scheduled": "Campaign scheduled",
  "admin.campaign.activated": "Campaign started",
};
export const activityFilterOptions = Object.entries(actions).map(([value, label]) => ({
  value,
  label,
}));
const otherActions: Record<string, string> = {
  "admin.payout_batch.created": "Payment run created",
  "admin.payout_batch.reserved": "Payment run saved",
  "admin.payout_batch.approved": "Payment run approved",
  "admin.payout_batch.submission_queued": "Payment run waiting to send",
  "admin.payout_batch.submitted": "Payments sent",
  "admin.payout_batch.replacement_reserved": "Replacement payment run saved",
  "admin.payout_batch.voided": "Payment run cancelled",
  "admin.payout_line.reconciled": "Payment result recorded",
  "provider.payout_line.reconciled": "Payment result received",
  "system.payout_batch.automatically_approved": "Payment run approved automatically",
  "system.payout_automatic_run.completed": "Automatic payment run finished",
  "system.payout_automatic_alert.created": "Payment needs attention",
  "admin.payout_automatic_alert.resolved": "Payment problem resolved",
  "admin.payout_automatic.paused": "Automatic payouts paused",
  "admin.payout_automatic.resumed": "Automatic payouts resumed",
  "admin.payout_automatic.released_to_manual": "Payments moved to staff review",
  "admin.payout_correction_order.created": "Pay correction created",
  "admin.payout_correction_order.approved": "Pay correction approved",
  "admin.payout_correction_order.stale": "Pay correction needs a new preview",
  "admin.campaign_payout_rule.created": "Campaign pay set",
  "admin.payout_rule_revision.created": "Campaign pay updated",
  "admin.payout_calculation.created": "Trip pay calculated",
  "driver.campaign_assignment.accepted": "Job accepted",
  "driver.campaign_assignment.declined": "Job declined",
  "admin.campaign_assignment.activated": "Job started",
  "driver.campaign_assignment.deactivated": "Job stopped",
  "driver.kyc.renewal_reuse": "Driver documents sent for review",
  "driver.vehicle_profile.submitted": "Car details sent for review",
  "admin.driver_person_payee.approved": "Driver details approved",
  "admin.driver_person_payee.rejected": "Driver details need changes",
  "admin.driver_vehicle.approved": "Car approved",
  "admin.driver_vehicle.rejected": "Car needs changes",
  "system.driver_vehicle.expired": "Car approval expired",
};
export function adminActivity(action: string): string {
  return actions[action] ?? otherActions[action] ?? "Activity recorded";
}
