/** Staff-facing job readiness copy; backend messages remain internal. */
export function jobStartMessage(
  result: { ready?: boolean; blocker_code?: string | null } | null | undefined,
): string {
  if (result?.ready) return "Everything is ready. You can start this job.";
  const messages: Record<string, string> = {
    CAMPAIGN_REVIEW_APPROVAL_REQUIRED: "Approve the campaign first.",
    PRODUCTION_FINANCIAL_AUTHORITY_REQUIRED: "Accept the quotation and approve production first.",
    CAMPAIGN_NOT_ACTIVE: "The campaign isn't running yet.",
    CAMPAIGN_NOT_STARTED: "The campaign hasn't started yet.",
    CAMPAIGN_EXPIRED: "The campaign has ended.",
    DRIVER_PROFILE_NOT_ACTIVE: "The driver isn't active.",
    VEHICLE_NOT_ACTIVE: "The car isn't active.",
    VEHICLE_DRIVER_PROFILE_MISMATCH: "This car belongs to a different driver.",
    INVALID_ASSIGNMENT_TRANSITION: "The driver must accept the job first.",
    ASSIGNMENT_ALREADY_ACTIVE: "This job has already started.",
    FROZEN_OFFER_TERMS_REQUIRED: "Send a new offer with the current artwork and pay terms.",
    APPROVED_CAMPAIGN_CREATIVE_REQUIRED: "Approve the artwork and send a new offer.",
    OFFER_CREATIVE_CHANGED: "Artwork has changed. Send a new offer.",
    FROZEN_PAYOUT_BINDING_REQUIRED: "Pay terms are missing. Send a new offer.",
    ASSIGNMENT_FUNDING_REQUIRED: "Not enough funding for this job.",
    NEW_WORK_NOT_FINANCIALLY_AUTHORIZED: "Not enough funding for this job.",
    CREDIT_AUTHORITY_EXPIRED: "The approved company credit has expired.",
    APPROVED_INSTALLATION_EVIDENCE_REQUIRED: "New installation photos are needed.",
    INSTALLATION_EVIDENCE_EXPIRED: "New installation photos are needed.",
  };
  return (
    (Object.hasOwn(messages, result?.blocker_code ?? "")
      ? messages[result?.blocker_code ?? ""]
      : undefined) ?? "Check the driver, car, artwork, payment and installation photos."
  );
}
