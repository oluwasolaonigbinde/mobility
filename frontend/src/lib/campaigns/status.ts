import type { components } from "@/lib/api/schema";

export type CampaignStatus = components["schemas"]["CampaignStatus"];

export const CAMPAIGN_STATUSES: readonly CampaignStatus[] = [
  "draft",
  "pending_review",
  "approved",
  "rejected",
  "scheduled",
  "active",
  "paused",
  "completed",
  "cancelled",
] as const;

export const statusLabel: Record<CampaignStatus, string> = {
  draft: "Draft",
  pending_review: "Pending review",
  approved: "Approved",
  rejected: "Changes requested",
  scheduled: "Scheduled",
  active: "Live",
  paused: "Paused",
  completed: "Completed",
  cancelled: "Cancelled",
};

export const statusTone: Record<CampaignStatus, "default" | "amber" | "cyan" | "green" | "coral"> =
  {
    draft: "default",
    pending_review: "amber",
    approved: "cyan",
    rejected: "coral",
    scheduled: "cyan",
    active: "green",
    paused: "amber",
    completed: "default",
    cancelled: "coral",
  };

export function isCampaignStatus(value: string): value is CampaignStatus {
  return (CAMPAIGN_STATUSES as readonly string[]).includes(value);
}
