import type { components } from "@/lib/api/schema";
import { adminStatus } from "./admin";

export type CampaignStatus = components["schemas"]["AdvertiserCampaignRead"]["status"];

export const CAMPAIGN_STATUSES: readonly CampaignStatus[] = [
  "draft",
  "pending_review",
  "approved",
  "rejected",
  "active",
  "paused",
  "finished",
  "cancelled",
] as const;

export const statusLabel: Record<CampaignStatus, string> = {
  draft: "Draft",
  pending_review: "Pending review",
  approved: "Approved",
  rejected: "Changes requested",
  active: "Running",
  paused: "Paused",
  finished: "Finished",
  cancelled: "Cancelled",
};

export const statusTone: Record<CampaignStatus, "default" | "amber" | "cyan" | "green" | "coral"> =
  {
    draft: "default",
    pending_review: "amber",
    approved: "cyan",
    rejected: "coral",
    active: "green",
    paused: "amber",
    finished: "default",
    cancelled: "coral",
  };

export function isCampaignStatus(value: string): value is CampaignStatus {
  return (CAMPAIGN_STATUSES as readonly string[]).includes(value);
}

export function advertiserStatus(value: string): string {
  if (value === "pending_admin" || value === "pending_funding") {
    return adminStatus(value);
  }
  return (
    statusLabel[value as CampaignStatus] ??
    (
      {
        pending: "Waiting",
        pending_review: "Pending review",
        applied: "Applied",
        rejected: "Not approved",
        cancelled: "Cancelled",
      } as Record<string, string>
    )[value] ??
    "Status unavailable"
  );
}
