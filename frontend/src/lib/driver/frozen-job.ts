import { frozenGeometry } from "@/lib/zones/frozen-geometry";

type ObjectValue = Record<string, unknown>;
function object(value: unknown): ObjectValue | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as ObjectValue)
    : null;
}
function date(value: unknown) {
  return typeof value === "string" && Number.isFinite(Date.parse(value)) ? value : null;
}
function names(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null;
  const result = value
    .map((item) => object(item)?.name)
    .filter((name): name is string => typeof name === "string" && Boolean(name.trim()))
    .map((name) => name.trim());
  if (result.length !== value.length) return null;
  return [...new Set(result)];
}

function mapAreas(target: unknown, exclusion: unknown) {
  if (!Array.isArray(target) || !target.length || !Array.isArray(exclusion)) return null;
  const rows = [
    ...target.map((row) => ({ row, zone_type: "target" })),
    ...exclusion.map((row) => ({ row, zone_type: "exclusion" })),
  ].map(({ row, zone_type }, index) => {
    const area = object(row);
    const geometry = frozenGeometry(area?.wkt);
    return geometry && typeof area?.name === "string" && area.name.trim()
      ? { id: String(index), name: area.name.trim(), zone_type, geometry }
      : null;
  });
  return rows.every((row) => row !== null) ? rows : null;
}

export function frozenJob(terms: unknown) {
  const source = object(terms);
  const zones = object(source?.zones);
  const payout = object(source?.payout);
  const target = names(zones?.target);
  const excluded = names(zones?.exclusion);
  const currency = payout?.currency ?? source?.currency;
  const rate = payout?.daily_rate_naira;
  const mime = object(object(source?.creative)?.content_identity)?.mime_type;
  return {
    startAt: date(source?.campaign_window_start_at),
    endAt: date(source?.campaign_window_end_at),
    areas: target?.length ? target : null,
    excluded,
    mapAreas: mapAreas(zones?.target, zones?.exclusion),
    artworkKind:
      typeof mime === "string" && ["image/png", "image/jpeg", "image/webp"].includes(mime)
        ? ("image" as const)
        : mime === "application/pdf"
          ? ("document" as const)
          : null,
    rate:
      payout?.formula_version === "payout_v4" &&
      typeof rate === "string" &&
      /^\d+(\.\d{1,2})?$/.test(rate)
        ? rate
        : null,
    currency: typeof currency === "string" && /^[A-Z]{3}$/.test(currency) ? currency : null,
  };
}
