/**
 * Display formatting for backend values.
 * The API serializes decimals as strings (exact precision) — parse at the
 * display boundary only, never for arithmetic.
 */

const numberFmt = new Intl.NumberFormat("en-NG");

export function formatCount(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "—";
  return numberFmt.format(Math.round(n));
}

export function formatMoney(
  value: string | number | null | undefined,
  currency: string = "NGN",
): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-NG", {
    style: "currency",
    currency,
    maximumFractionDigits: n >= 1000 ? 0 : 2,
  }).format(n);
}

/** 0–1 score → percentage string */
export function formatScore(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "—";
  return `${Math.round(n * 100)}%`;
}

export function formatKm(meters: string | number | null | undefined): string {
  if (meters === null || meters === undefined) return "—";
  const n = typeof meters === "string" ? Number(meters) : meters;
  if (!Number.isFinite(n)) return "—";
  return `${numberFmt.format(Math.round(n / 1000))} km`;
}
