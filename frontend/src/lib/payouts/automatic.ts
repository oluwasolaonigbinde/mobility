import type { components } from "@/lib/api/schema";

export type AutomaticStatus = components["schemas"]["AutomaticPayoutStatusRead"];
export type AutomaticAlert = components["schemas"]["AutomaticPayoutAlertRead"];
export type AutomaticReconciliation = components["schemas"]["AutomaticReconciliationRead"];

const WAT = "Africa/Lagos";

const watDateTime = new Intl.DateTimeFormat("en-NG", {
  timeZone: WAT,
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** An instant shown in Nigeria time; callers label it "(WAT)". */
export function formatWat(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : watDateTime.format(d);
}

/** Today's calendar day in Nigeria (WAT), as YYYY-MM-DD. */
export function todayInWat(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: WAT }).format(now);
}

/** A valid YYYY-MM-DD from the query string, else today in WAT. */
export function reconciliationDay(raw: string | undefined, now: Date = new Date()): string {
  if (raw && /^\d{4}-\d{2}-\d{2}$/.test(raw) && !Number.isNaN(Date.parse(`${raw}T00:00:00Z`))) {
    return raw;
  }
  return todayInWat(now);
}

const ALERT_LABELS: Record<string, string> = {
  business_health: "Business health needs attention",
  failed_payment: "A payment failed",
  duplicate_payment: "A possible duplicate payment",
  daily_limit: "Above one day's pay — kept for a person to check",
  run_failed: "Automatic payouts could not run",
  submission_blocked: "A payment could not be sent",
};

export function alertLabel(kind: string): string {
  return ALERT_LABELS[kind] ?? "Payment problem to review";
}

const REASON_LABELS: Record<string, string> = {
  fraud_hold: "Trip under review",
  fraud_flag: "Trip had a review flag",
  open_dispute: "Driver has an open dispute",
  assessment_not_current: "Trip check not up to date",
  payee_unverified: "Check and verify the driver’s bank details before paying",
  new_bank_destination: "First payment to this bank account",
  debt_outstanding: "Driver owes money back",
  adjusted_trip: "Pay was corrected",
  not_daily_rate: "Not daily-rate pay",
  daily_limit: "Above one day's pay",
};

export function manualReasonLabel(reason: string): string {
  return REASON_LABELS[reason] ?? "Payment needs a staff review";
}

const OUTCOME_LABELS: Record<string, string> = {
  reserved: "Waiting to send",
  unknown: "Payment result not known",
  queued: "Waiting to send",
  provider_unknown: "Sent — result not known yet",
  submitted: "Sent — waiting for the bank",
  succeeded: "Paid",
  failed: "Failed",
  void: "Moved to manual review",
};

export function outcomeText(outcome: string): string {
  return OUTCOME_LABELS[outcome] ?? "Payment result not known";
}

export function alertDetail(alert: AutomaticAlert): string | null {
  const detail = alert.detail as Record<string, unknown>;
  if (alert.kind === "business_health") {
    const checks: Record<string, string> = {
      stuck_payouts: "Payments have stopped making progress",
      unprocessed_webhooks: "Payment updates are waiting to be processed",
      paused_payouts: "Automatic payouts have been paused for over a day",
      gps_rejections: "An unusual share of GPS uploads was rejected",
      gps_telemetry_unavailable: "GPS upload monitoring is unavailable",
      stale_trips: "Trips need an evidence or activity review",
      partition_coverage: "GPS storage needs its next partition",
      email_failures: "Emails failed or are waiting too long",
    };
    const label = typeof detail.check === "string" ? checks[detail.check] : undefined;
    return label &&
      typeof detail.count === "number" &&
      Number.isSafeInteger(detail.count) &&
      detail.count > 0
      ? `${label} (${detail.count >= 1000 ? "1,000+" : detail.count}). Follow the operations runbook.`
      : "Review the operations runbook.";
  }
  if (alert.kind === "daily_limit") {
    if (detail.rates_differ) return "The driver's campaigns have different day rates that day.";
    if (detail.other_pay_type_same_day) return "The driver also earned hourly pay that day.";
    if (typeof detail.earned === "string" && typeof detail.ceiling === "string") {
      return `Earned ₦${detail.earned} against a day rate of ₦${detail.ceiling}.`;
    }
    return null;
  }
  if (alert.kind === "run_failed") {
    return detail.reason === "provider_unavailable"
      ? "No payment provider is connected yet."
      : "The Cardvert payout identity is missing or was changed.";
  }
  return null;
}
