import { formatCount, formatDate, formatDateRange } from "@/lib/format";
import { IconTile } from "@/components/brand/portal-icon";

export type DistanceDay = { date: string; distance_m: string | null };
export function PerformanceCard({
  estimatedViews,
  cars,
  days,
  scans,
  period,
  unavailable = false,
  withheld = false,
  daysWithheld = false,
  compact = false,
}: {
  estimatedViews: string | null;
  cars: number | null;
  days: DistanceDay[] | null;
  scans: number | null;
  period?: { start_at: string | null; end_at: string | null };
  unavailable?: boolean;
  withheld?: boolean;
  daysWithheld?: boolean;
  compact?: boolean;
}) {
  const values =
    days?.map((day) => (day.distance_m === null ? null : Number(day.distance_m) / 1000)) ?? [];
  const maximum = Math.max(
    1,
    ...values.filter((value): value is number => value !== null && Number.isFinite(value)),
  );
  return (
    <section aria-label="Campaign performance" className={compact ? "p-4 md:p-5" : "p-5 md:p-6"}>
      {!compact ? (
        <div className="mb-5 flex items-center gap-3">
          <IconTile name="chart" tone="gold" />
          <div>
            <h2 className="font-display text-lg font-semibold">Campaign performance</h2>
            <p className="text-muted mt-1 text-sm">
              {period?.start_at && period.end_at
                ? Date.parse(period.end_at) < Date.parse(period.start_at)
                  ? "No results yet"
                  : formatDateRange(period.start_at, period.end_at)
                : "Campaign results so far"}
            </p>
          </div>
        </div>
      ) : null}
      <dl
        className={
          scans !== null && scans > 0 ? "grid grid-cols-3 gap-3" : "grid grid-cols-2 gap-5"
        }
      >
        <div>
          <dt className="text-muted text-sm">Estimated views</dt>
          <dd className="font-display mt-1 text-2xl font-semibold">
            {formatCount(estimatedViews)}
          </dd>
          {!compact ? (
            <p className="text-muted mt-1 text-xs">An estimate, not a count of people</p>
          ) : null}
        </div>
        <div>
          <dt className="text-muted text-sm">Cars on the road</dt>
          <dd className="font-display mt-1 text-2xl font-semibold">{formatCount(cars)}</dd>
          <p className="text-muted mt-1 text-xs">As of about 15 minutes ago</p>
        </div>
        {scans !== null && scans > 0 ? (
          <div>
            <dt className="text-muted text-sm">QR scans</dt>
            <dd className="font-display mt-1 text-2xl font-semibold">{formatCount(scans)}</dd>
            {!compact ? (
              <p className="text-muted mt-1 text-xs">Scans, not unique visitors</p>
            ) : null}
          </div>
        ) : null}
      </dl>
      {withheld ? (
        <p className="text-muted mt-4 text-sm">Not enough cars yet to show estimated views.</p>
      ) : null}
      {unavailable ? (
        <p className="text-muted mt-4 text-sm" role="status">
          Some performance figures couldn&apos;t be loaded. Refresh to try again.
        </p>
      ) : null}
      <div className="border-edge mt-4 border-t pt-3">
        {!daysWithheld ? (
          <>
            <h3 className="text-sm font-semibold">Distance driven · last 7 days</h3>
            <p className="text-muted mt-1 text-xs">Daily distance in kilometres · Today so far</p>
          </>
        ) : null}
        {daysWithheld ? (
          <p className="text-muted text-sm">Not enough cars yet to show daily distance.</p>
        ) : null}
        {!daysWithheld && days ? (
          <>
            <div
              className="mt-3 grid h-20 grid-cols-7 items-end gap-2"
              role="img"
              aria-label="Daily distance chart; values below"
            >
              {days.map((day, i) => (
                <div key={day.date} className="flex h-full flex-col justify-end gap-1 text-center">
                  <div
                    className={
                      values[i] === null
                        ? "bg-edge mx-auto h-1 w-full max-w-10 rounded"
                        : "bg-green/80 mx-auto w-full max-w-10 rounded-t-md"
                    }
                    style={
                      values[i] === null
                        ? undefined
                        : {
                            height: `${Math.max(values[i] === 0 ? 2 : 5, (values[i]! / maximum) * 76)}%`,
                          }
                    }
                  />
                  <span className="text-muted text-[11px]">
                    {new Date(`${day.date}T12:00:00Z`).getUTCDate()}
                  </span>
                </div>
              ))}
            </div>
            <details className="mt-3 text-sm">
              <summary className="text-green cursor-pointer">Daily figures</summary>
              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2">
                {days.map((day, i) => (
                  <div key={day.date} className="contents">
                    <dt>{formatDate(day.date)}</dt>
                    <dd>
                      {values[i] === null
                        ? "Not enough cars yet"
                        : `${values[i]!.toLocaleString("en-NG", { maximumFractionDigits: 1 })} km`}
                    </dd>
                  </div>
                ))}
              </dl>
            </details>
          </>
        ) : !daysWithheld ? (
          <p className="text-muted mt-4 text-sm">Daily distance couldn&apos;t be loaded.</p>
        ) : null}
      </div>
    </section>
  );
}
