import type { components } from "@/lib/api/schema";

type LedgerEntry = components["schemas"]["EarningsLedgerEntryRead"];
type DriverFraudHold = components["schemas"]["DriverFraudHoldRead"];

const ACTIVE_HOLD_STATES = new Set<DriverFraudHold["public_status"]>([
  "assessment_pending",
  "under_review",
  "issue_confirmed",
]);

const statusPresentation = {
  available: { label: "Released", tone: "green" },
  paid: { label: "Paid", tone: "green" },
  pending: { label: "Pending", tone: "amber" },
  voided: { label: "Voided", tone: "coral" },
  reversed: { label: "Reversed", tone: "default" },
} as const;

const entryTypePresentation: Record<LedgerEntry["entry_type"], string | null> = {
  trip_payout: null,
  adjustment: "Adjustment",
  reversal: "Reversal",
  debt_remainder: "Debt carried",
};

export function activeHeldTripIds(holds: DriverFraudHold[]): Set<string> {
  return new Set(
    holds
      .filter((hold) => ACTIVE_HOLD_STATES.has(hold.public_status))
      .map((hold) => hold.trip_session_id),
  );
}

export function presentLedgerEntry(entry: LedgerEntry, heldTripIds: Set<string>) {
  const isHeld =
    entry.status === "pending" &&
    entry.trip_session_id !== null &&
    heldTripIds.has(entry.trip_session_id);
  return {
    status: isHeld ? ({ label: "Held", tone: "coral" } as const) : statusPresentation[entry.status],
    typeLabel: entryTypePresentation[entry.entry_type],
  };
}
