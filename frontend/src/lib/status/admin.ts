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
  completed: "Ended",
  cancelled: "Cancelled",
  open: "Needs attention",
  acknowledged: "Looking into it",
  confirmed: "Problem confirmed",
  dismissed: "Cleared",
  clean: "Clear",
  flagged: "On hold",
  quarantined: "Late upload",
  applied: "Added to trip",
  discarded: "Ignored",
  offered: "Offered",
  accepted: "Accepted",
  declined: "Declined",
  expired: "Expired",
  reserved: "Waiting for approval",
  maker_checker: "Needs a second approval",
  pending: "Waiting",
  processing: "Being checked",
  available: "Ready for payout",
  held: "On hold",
  paid: "Paid",
  reversal: "Taken back",
  failed: "Failed",
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
  pending_approval: "Needs a second approval",
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
  payment_outcome: {
    reserved: "Waiting for approval",
    queued: "Queued — not submitted",
    provider_unknown: "Provider outcome unknown",
    unknown: "Provider outcome unknown",
    succeeded: "Verified paid",
    failed: "Failed",
    submitted: "Submitted — awaiting verification",
    void: "Voided",
  },
  payment_run: {
    completed: "Completed",
    void: "Voided",
    reserved: "Waiting for approval",
    reconciled: "Provider results recorded",
  },
  correction: {
    stale: "Needs a new preview",
    executed: "Completed",
    approved: "Ready to run",
    pending_approval: "Needs a second approval",
  },
  invoice: { paid: "Paid", part_paid: "Part-paid", unpaid: "Unpaid", void: "Voided" },
  audience: {
    ready: "Ready",
    stale: "Needs refresh",
    suppressed: "Hidden by privacy checks",
    empty: "No matching audience",
  },
  driver: { pending: "Applicant", rejected: "Not approved" },
  campaign: { active: "Live", pending_review: "For review", completed: "Ended" },
  job: { active: "Live", accepted: "Accepted" },
  review: { pending: "Needs review", pending_review: "Needs review" },
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
const documents: Record<string, string> = {
  driver_license: "driving licence",
  driver_photo: "driver photo",
  signed_agreement: "signed agreement",
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
export function adminActivity(action: string): string {
  return actions[action] ?? "Activity recorded";
}
