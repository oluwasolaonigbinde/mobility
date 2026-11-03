export const driverEarningsStatus = {
  available: { label: "Ready", tone: "green" },
  paid: { label: "Paid", tone: "green" },
  pending: { label: "Being checked", tone: "amber" },
  voided: { label: "Cancelled", tone: "coral" },
  reversed: { label: "Deduction", tone: "default" },
} as const;
