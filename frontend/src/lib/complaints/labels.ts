import type { components } from "@/lib/api/schema";

export type ComplaintCategory = components["schemas"]["ComplaintCategory"];
export type ComplaintStatus = components["schemas"]["ComplaintStatus"];
export type ComplaintParty = "driver" | "advertiser";
export type ComplaintReferenceType = components["schemas"]["ComplaintReferenceType"];

/**
 * Neutral default categories (Batch E). The client has not supplied a list;
 * the server holds the same set and decides which apply to each account.
 */
export const CATEGORY_LABELS: Record<ComplaintCategory, string> = {
  pay_or_payout: "Pay or payouts",
  trip_or_tracking: "Trips and tracking",
  campaign_or_job: "A campaign or job",
  billing_or_invoice: "Billing or invoices",
  account: "My account",
  other: "Something else",
};

export const PARTY_CATEGORIES: Record<ComplaintParty, ComplaintCategory[]> = {
  driver: ["pay_or_payout", "trip_or_tracking", "campaign_or_job", "account", "other"],
  advertiser: ["campaign_or_job", "billing_or_invoice", "account", "other"],
};

/** Complainant-facing status: who the conversation is waiting on. */
export const COMPLAINANT_STATUS: Record<ComplaintStatus, { label: string; tone: Tone }> = {
  open: { label: "With Customer Service", tone: "amber" },
  answered: { label: "Terrax Media replied", tone: "cyan" },
  resolved: { label: "Resolved", tone: "green" },
};

/** Staff-facing status. */
export const STAFF_STATUS: Record<ComplaintStatus, { label: string; tone: Tone }> = {
  open: { label: "Needs a reply", tone: "amber" },
  answered: { label: "Waiting on them", tone: "cyan" },
  resolved: { label: "Resolved", tone: "green" },
};

type Tone = "default" | "amber" | "cyan" | "green" | "coral";

export const REFERENCE_TYPE_LABELS: Record<ComplaintReferenceType, string> = {
  campaign: "Campaign",
  trip: "Trip",
  payout: "Payout",
};

/** "Campaign: Lagos Launch", "Payout: Trip pay ₦…"; trip labels already say "Trip on …". */
export function referenceText(type: ComplaintReferenceType | null, label: string | null): string {
  if (!type) return "No record chosen";
  if (!label) return `${REFERENCE_TYPE_LABELS[type]} (details unavailable)`;
  return type === "trip" ? label : `${REFERENCE_TYPE_LABELS[type]}: ${label}`;
}

export const SENDER_LABELS = {
  you: "You",
  your_team: "Someone in your team",
  terrax_media: "Terrax Media",
} as const;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const watParts = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Africa/Lagos",
  day: "numeric",
  month: "numeric",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** "3 Sep 2026, 08:15 WAT" — complaint times always read in Nigeria time. */
export function formatWat(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const part = Object.fromEntries(watParts.formatToParts(date).map((p) => [p.type, p.value]));
  return `${Number(part.day)} ${MONTHS[Number(part.month) - 1]} ${part.year}, ${part.hour}:${part.minute} WAT`;
}
