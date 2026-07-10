import type { components } from "@/lib/api/schema";

export type CampaignStatus = components["schemas"]["CampaignStatus"];

export const CAMPAIGN_STATUSES: readonly CampaignStatus[] = [
  "draft",
  "scheduled",
  "active",
  "paused",
  "completed",
  "cancelled",
] as const;

export const statusLabel: Record<CampaignStatus, string> = {
  draft: "Draft",
  scheduled: "Scheduled",
  active: "Live",
  paused: "Paused",
  completed: "Completed",
  cancelled: "Cancelled",
};

export const statusTone: Record<CampaignStatus, "default" | "amber" | "cyan" | "green" | "coral"> =
  {
    draft: "default",
    scheduled: "cyan",
    active: "green",
    paused: "amber",
    completed: "default",
    cancelled: "coral",
  };

/**
 * Actions we surface per current status. The API allows any transition;
 * this is a product decision to keep the UI honest (no "activate" on a
 * cancelled campaign, terminal states stay terminal).
 */
export const statusActions: Record<
  CampaignStatus,
  Array<{ to: CampaignStatus; label: string; destructive?: boolean }>
> = {
  draft: [
    { to: "scheduled", label: "Schedule" },
    { to: "active", label: "Launch now" },
    { to: "cancelled", label: "Cancel", destructive: true },
  ],
  scheduled: [
    { to: "active", label: "Launch now" },
    { to: "draft", label: "Back to draft" },
    { to: "cancelled", label: "Cancel", destructive: true },
  ],
  active: [
    { to: "paused", label: "Pause" },
    { to: "completed", label: "Complete" },
  ],
  paused: [
    { to: "active", label: "Resume" },
    { to: "completed", label: "Complete" },
    { to: "cancelled", label: "Cancel", destructive: true },
  ],
  completed: [],
  cancelled: [],
};

export function isCampaignStatus(value: string): value is CampaignStatus {
  return (CAMPAIGN_STATUSES as readonly string[]).includes(value);
}
