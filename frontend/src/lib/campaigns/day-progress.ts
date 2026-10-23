import { formatDate } from "@/lib/format";

const nigeriaDate = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Africa/Lagos",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});
function day(iso: string) {
  const value = new Date(iso);
  if (!Number.isFinite(value.getTime())) return null;
  return Date.parse(nigeriaDate.format(value));
}

/** Presentation only; trips, extension approval and campaign status stay server-owned. */
export function campaignDay(
  start: string | null | undefined,
  end: string | null | undefined,
  now = new Date(),
): string | null {
  if (!start || !end || !Number.isFinite(now.getTime())) return null;
  const startTime = Date.parse(start),
    endTime = Date.parse(end);
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime) || endTime < startTime) return null;
  const first = day(start),
    last = day(end),
    today = day(now.toISOString());
  if (first === null || last === null || today === null || last < first) return null;
  if (now.getTime() < startTime) return `Starts ${formatDate(start)}`;
  const duration = Math.floor((last - first) / 86_400_000) + 1;
  const elapsed = Math.min(duration, Math.floor((today - first) / 86_400_000) + 1);
  return `Day ${elapsed} of ${duration}`;
}
