export const driverEarningsStatus = {
  available: { label: "Released", tone: "green" },
  paid: { label: "Paid", tone: "green" },
  pending: { label: "Pending", tone: "amber" },
  voided: { label: "Voided", tone: "coral" },
  reversed: { label: "Reversed", tone: "default" },
} as const;
