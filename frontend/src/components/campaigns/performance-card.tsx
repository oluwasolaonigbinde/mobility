import { formatCount, formatDate } from "@/lib/format";
import type { PerformanceDay } from "@/lib/advertiser/performance";
export function Trend({ value }: { value: number | null }) {
  return value === null ? null : (
    <span className={value < 0 ? "text-muted text-xs" : "text-green text-xs"}>
      {value < 0 ? "↓" : "↑"} {Math.abs(value).toFixed(0)}%
    </span>
  );
}
export function PerformanceCard({
  estimatedViews,
  distance,
  cars,
  days,
  viewChange,
  distanceChange,
  windowLabel,
  dailyMessage,
  unavailable = false,
  compact = false,
}: {
  estimatedViews: string | null;
  distance: string | null;
  cars: number | null;
  days: PerformanceDay[] | null;
  viewChange: number | null;
  distanceChange: number | null;
  windowLabel: string;
  dailyMessage: string | null;
  unavailable?: boolean;
  compact?: boolean;
}) {
  const maximum = Math.max(1, ...(days ?? []).map((d) => Number(d.estimated_impressions)));
  const rawStep = maximum / 3;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const step = Math.max(1, [1, 2, 5, 10].find((n) => n * magnitude >= rawStep)! * magnitude);
  const ceiling = Math.ceil(maximum / step) * step;
  const ticks = Array.from({ length: Math.round(ceiling / step) + 1 }, (_, i) => i * step);
  const x = (i: number) => ((i + 0.5) / (days?.length ?? 1)) * 100;
  const y = (value: number) => 92 - (value / ceiling) * 84;
  const points = (days ?? [])
    .map((d, i) => `${x(i)},${y(Number(d.estimated_impressions))}`)
    .join(" ");
  const axisLabel = (value: number) =>
    value >= 1000 ? `${Number((value / 1000).toFixed(1))}k` : String(value);
  const dateLabel = (date: string, index: number) => {
    const value = new Date(`${date}T12:00:00Z`);
    return index === 0 || value.getUTCDate() === 1
      ? new Intl.DateTimeFormat("en-GB", {
          day: "numeric",
          month: "short",
          timeZone: "UTC",
        }).format(value)
      : String(value.getUTCDate());
  };
  return (
    <section
      aria-label="Campaign performance"
      className={compact ? "min-w-0 p-4 md:p-5" : "min-w-0 p-5 md:p-6"}
    >
      {compact ? (
        <p className="text-muted mb-4 text-sm">{windowLabel}</p>
      ) : (
        <header className="mb-4 flex items-center justify-between gap-2">
          <h2 className="font-display min-w-0 text-base font-semibold sm:text-lg">
            Campaign performance
          </h2>
          <span className="text-green bg-green/10 inline-flex shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium whitespace-nowrap">
            {windowLabel}
          </span>
        </header>
      )}
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <div>
          <dt className="text-muted text-sm">Estimated views</dt>
          <dd className="font-display text-2xl font-semibold">{formatCount(estimatedViews)}</dd>
          <Trend value={viewChange} />
        </div>
        <div>
          <dt className="text-muted text-sm">Distance driven</dt>
          <dd className="font-display text-2xl font-semibold">
            {distance === null ? "—" : `${formatCount(Number(distance) / 1000)} km`}
          </dd>
          <Trend value={distanceChange} />
        </div>
        <div>
          <dt className="text-muted text-sm">Cars on the road</dt>
          <dd className="font-display text-2xl font-semibold">{formatCount(cars)}</dd>
          <p className="text-muted text-xs">About 15 minutes ago</p>
        </div>
      </dl>
      <p className="text-muted mt-3 text-xs">An estimate, not a count of people</p>
      {unavailable && (
        <p role="status" className="text-muted mt-3 text-sm">
          Some performance figures couldn&apos;t be loaded. Refresh to try again.
        </p>
      )}
      <div className="border-edge mt-4 border-t pt-3">
        {days ? (
          <>
            <h3 className="text-sm font-semibold">Estimated views per day</h3>
            <div
              className="mt-3 grid grid-cols-[2.25rem_minmax(0,1fr)] gap-x-1"
              role="img"
              aria-label="Estimated views per day; daily figures below"
            >
              <div className="text-muted relative h-36 text-[11px]">
                {ticks.map((tick) => (
                  <span
                    key={tick}
                    className="absolute right-1 -translate-y-1/2"
                    style={{ top: `${y(tick)}%` }}
                  >
                    {axisLabel(tick)}
                  </span>
                ))}
              </div>
              <div className="relative h-36 min-w-0">
                <svg
                  className="h-full w-full"
                  viewBox="0 0 100 100"
                  preserveAspectRatio="none"
                  aria-hidden="true"
                >
                  {ticks.map((tick) => (
                    <line
                      key={tick}
                      x1="0"
                      x2="100"
                      y1={y(tick)}
                      y2={y(tick)}
                      stroke="#dce5d8"
                      strokeWidth="1"
                      vectorEffect="non-scaling-stroke"
                    />
                  ))}
                  <polygon
                    points={`${x(0)},92 ${points} ${x((days?.length ?? 1) - 1)},92`}
                    fill="#e4f0df"
                    fillOpacity="0.7"
                  />
                  <polyline
                    points={points}
                    fill="none"
                    stroke="#235b3b"
                    strokeWidth="2"
                    vectorEffect="non-scaling-stroke"
                  />
                </svg>
                {days.map((d, i) => (
                  <span
                    key={d.date}
                    aria-hidden="true"
                    className="bg-green absolute size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-white"
                    style={{ left: `${x(i)}%`, top: `${y(Number(d.estimated_impressions))}%` }}
                  />
                ))}
              </div>
              <div
                className="text-muted col-start-2 grid text-center text-[11px] sm:text-xs"
                style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0,1fr))` }}
              >
                {days.map((d, i) => (
                  <time key={d.date} dateTime={d.date} className="whitespace-nowrap">
                    {dateLabel(d.date, i)}
                  </time>
                ))}
              </div>
            </div>
            <details className="mt-4 text-sm">
              <summary className="text-green cursor-pointer">Daily figures</summary>
              <dl className="mt-3 grid grid-cols-2 gap-2">
                {days.map((d) => (
                  <div key={d.date} className="contents">
                    <dt>{formatDate(d.date)}</dt>
                    <dd>{formatCount(d.estimated_impressions)} views</dd>
                  </div>
                ))}
              </dl>
            </details>
          </>
        ) : (
          dailyMessage && <p className="text-muted text-sm">{dailyMessage}</p>
        )}
      </div>
    </section>
  );
}
