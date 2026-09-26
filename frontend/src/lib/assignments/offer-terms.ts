import { formatDateTime } from "@/lib/format";

// D38(c): drivers see every accepted term in words, without the IDs, hashes,
// map geometry or version markers that the frozen offer also carries.
const HIDDEN_KEY =
  /(^id$|_id$|_ids$|sha256|fingerprint|checksum|hash|wkt|version|semantics|marker)/;

export type OfferTermLine = { label: string; value: string };

function humanise(key: string): string {
  const words = key.replaceAll("_", " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function scalar(value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value)) return formatDateTime(value);
  if (typeof value === "string" || typeof value === "number") return String(value);
  return null;
}

export function offerTermLines(terms: Record<string, unknown>, prefix = ""): OfferTermLine[] {
  const lines: OfferTermLine[] = [];
  for (const [key, value] of Object.entries(terms)) {
    if (HIDDEN_KEY.test(key)) continue;
    const label = prefix ? `${prefix} · ${humanise(key)}` : humanise(key);
    if (Array.isArray(value)) {
      const names = value
        .map((item) =>
          item && typeof item === "object"
            ? scalar((item as Record<string, unknown>).name)
            : scalar(item),
        )
        .filter((item): item is string => item !== null);
      if (names.length) lines.push({ label, value: names.join(", ") });
    } else if (value && typeof value === "object") {
      lines.push(...offerTermLines(value as Record<string, unknown>, label));
    } else {
      const text = scalar(value);
      if (text !== null) lines.push({ label, value: text });
    }
  }
  return lines;
}
