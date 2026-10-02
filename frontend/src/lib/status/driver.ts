const labels: Record<string, string> = {
  pending: "Being checked",
  available: "Ready for payout",
  held: "On hold",
  paid: "Paid",
  reversal: "Taken back",
  offered: "Job offer",
  accepted: "Ready to start",
  active: "Live",
  cancelled: "Cancelled",
  completed: "Ended",
  declined: "Declined",
  expired: "Expired",
  pending_review: "Being reviewed",
  approved: "Approved",
  rejected: "Not approved",
  not_submitted: "Not submitted",
};
export function driverStatus(value: string): string {
  return labels[value] ?? "Status unavailable";
}
export const driverEarningsStatus = {
  available: { label: "Released", tone: "green" },
  paid: { label: "Paid", tone: "green" },
  pending: { label: "Pending", tone: "amber" },
  voided: { label: "Voided", tone: "coral" },
  reversed: { label: "Reversed", tone: "default" },
} as const;
