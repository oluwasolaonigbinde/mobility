// Advertiser-facing names for the retargeting source vocabulary. The API values
// stay unchanged; only what people read changes.

export const sourceTypeLabel: Record<string, string> = {
  "website-traffic": "Website visitors",
  "digital-campaign-audience": "Online ad audience",
  "CRM-upload-reference": "Customer list (size only)",
  "UTM-source": "Tracked link (UTM) traffic",
  "manual-insight": "Other insight you describe",
};

export const optionLabel: Record<string, string> = {
  "site-visitor": "Visited the site",
  "content-interest": "Interested in particular content",
  "conversion-intent": "Close to buying",
  "area-demand": "Demand in an area",
  "time-pattern": "Time-of-day pattern",
  "contextual-affinity": "Interest tied to a setting",
  search: "Search ads",
  social: "Social media",
  display: "Display ads",
  email: "Email",
  awareness: "Just becoming aware",
  consideration: "Considering",
  "0-99": "Fewer than 100 people",
  "100-999": "100 to 999 people",
  "1000-plus": "1,000 people or more",
  low: "Low",
  medium: "Medium",
  high: "High",
};

export const sourceStatusLabel: Record<string, string> = {
  active: "In use",
  expired: "Expired",
  deactivated: "Stopped",
};

export const linkStatusLabel: Record<string, string> = {
  active: "Connected",
  removed: "Disconnected",
};

export function labelFor(map: Record<string, string>, value: string): string {
  return map[value] ?? value.replaceAll("-", " ").replaceAll("_", " ");
}

const DESCRIBING_FIELDS = [
  "audience_category",
  "insight_category",
  "channel",
  "audience_stage",
  "campaign_stage",
  "record_count_band",
  "confidence_band",
] as const;

/** One readable line describing what the advertiser declared for a source. */
export function describeSource(snapshot: unknown): string {
  if (!snapshot || typeof snapshot !== "object") return "";
  const record = snapshot as Record<string, unknown>;
  const parts = DESCRIBING_FIELDS.flatMap((field) =>
    typeof record[field] === "string" ? [labelFor(optionLabel, record[field] as string)] : [],
  );
  if (typeof record.aggregation_window_days === "number") {
    parts.push(`last ${record.aggregation_window_days} days`);
  }
  return parts.join(" · ");
}
