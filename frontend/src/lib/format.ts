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

const dateFmt = new Intl.DateTimeFormat("en-NG", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : dateFmt.format(d);
}

export function formatDateRange(
  start: string | null | undefined,
  end: string | null | undefined,
): string {
  if (!start && !end) return "No window set";
  return `${formatDate(start)} → ${formatDate(end)}`;
}

export function formatKm(meters: string | number | null | undefined): string {
  if (meters === null || meters === undefined) return "—";
  const n = typeof meters === "string" ? Number(meters) : meters;
  if (!Number.isFinite(n)) return "—";
  return `${numberFmt.format(Math.round(n / 1000))} km`;
}

/** Whole seconds → "2h 41m" (sub-minute values show seconds). */
export function formatDuration(seconds: string | number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const n = typeof seconds === "string" ? Number(seconds) : seconds;
  if (!Number.isFinite(n) || n < 0) return "—";
  const whole = Math.floor(n);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  if (hours === 0 && minutes === 0) return `${whole}s`;
  if (hours === 0) return `${minutes}m`;
  return `${hours}h ${minutes}m`;
}

/** Money with kobo always shown — for surfaces that prove an equation. */
export function formatMoneyExact(
  value: string | number | null | undefined,
  currency: string = "NGN",
): string {
  if (value === null || value === undefined) return "—";
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-NG", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);
}
