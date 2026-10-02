import type { components } from "@/lib/api/schema";
import { driverEarningsStatus } from "@/lib/status/driver";

type LedgerEntry = components["schemas"]["EarningsLedgerEntryRead"];
type DriverFraudHold = components["schemas"]["DriverFraudHoldRead"];

const ACTIVE_HOLD_STATES = new Set<DriverFraudHold["public_status"]>([
  "assessment_pending",
  "under_review",
  "issue_confirmed",
]);

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
    status: isHeld
      ? ({ label: "Held", tone: "coral" } as const)
      : driverEarningsStatus[entry.status],
    typeLabel: entryTypePresentation[entry.entry_type],
  };
}
