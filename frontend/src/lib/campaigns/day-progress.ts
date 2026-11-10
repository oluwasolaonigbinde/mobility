import { formatDate } from "@/lib/format";

const nigeriaDate = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Africa/Lagos",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});
export function nigeriaDay(iso: string) {
  const value = new Date(iso);
  if (!Number.isFinite(value.getTime())) return null;
  return Date.parse(nigeriaDate.format(value));
}

/** Presentation only; trips, extension approval and campaign status stay server-owned. */
export function campaignDay(
  start: string | null | undefined,
  end: string | null | undefined,
  status: string,
  now = new Date(),
): string | null {
  if (!["active", "paused", "finished", "completed"].includes(status)) return null;
  if (!start || !end || !Number.isFinite(now.getTime())) return null;
  const progress = campaignDayProgress(start, end, now);
  if (!progress) return null;
  if (now.getTime() < Date.parse(start)) return `Starts ${formatDate(start)}`;
  const { duration, elapsed } = progress;
  return `Day ${elapsed} of ${duration}`;
}

export function campaignDayProgress(start: string, end: string, now = new Date()) {
  if (
    !Number.isFinite(now.getTime()) ||
    !Number.isFinite(Date.parse(start)) ||
    !Number.isFinite(Date.parse(end)) ||
    Date.parse(end) < Date.parse(start)
  )
    return null;
  const first = nigeriaDay(start),
    last = nigeriaDay(end),
    today = nigeriaDay(now.toISOString());
  if (first === null || last === null || today === null || last < first) return null;
  const duration = Math.floor((last - first) / 86400000) + 1;
  const elapsed =
    now.getTime() < Date.parse(start)
      ? 0
      : Math.max(0, Math.min(duration, Math.floor((today - first) / 86400000) + 1));
  return { duration, elapsed };
}
