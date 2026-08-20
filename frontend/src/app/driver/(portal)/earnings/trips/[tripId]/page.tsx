import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/errors";
import { formatDate, formatDuration, formatMoneyExact } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import type { components } from "@/lib/api/schema";

export const metadata: Metadata = { title: "Trip earnings" };

type LedgerStatus = components["schemas"]["EarningsLedgerEntryStatus"];

const statusTone: Record<LedgerStatus, "green" | "amber" | "coral" | "default"> = {
  available: "green",
  pending: "amber",
  voided: "coral",
  reversed: "default",
};

const EXCLUSION_LABELS: Record<string, string> = {
  gps_gap: "GPS signal gaps",
  low_accuracy: "Weak GPS accuracy",
  teleport: "Impossible movement",
  out_of_window: "Outside campaign window",
  out_of_area: "Outside campaign area",
  stationary: "Parked beyond the grace period",
};

export default async function DriverTripEarningsPage({
  params,
}: {
  params: Promise<{ tripId: string }>;
}) {
  const { tripId } = await params;
  const api = createApiClient(await getSessionToken());
  const breakdown = await api
    .GET("/api/v1/driver/trips/{trip_id}/earnings-breakdown", {
      params: { path: { trip_id: tripId } },
    })
    .catch((e) => {
      if (e instanceof ApiError && e.status === 404) return { data: undefined };
      throw e;
    });
  const data = breakdown.data;
  if (!data) notFound();

  const isV3 = data.formula_version === "payout_v3";
  const isHourly = data.formula_version === "payout_v2" || isV3;
  const hasTierBreakdown =
    isV3 &&
    data.base_payable_seconds != null &&
    data.premium_payable_seconds != null &&
    data.base_hourly_rate != null &&
    data.base_amount != null &&
    data.premium_amount != null;
  const excluded = Object.entries(data.excluded_seconds_by_reason ?? {});
  const capPct =
    data.cap && data.cap.cap_seconds > 0
      ? Math.min(100, Math.round((data.cap.day_payable_seconds / data.cap.cap_seconds) * 100))
      : null;

  return (
    <div className="animate-rise flex flex-col gap-4">
      <div>
        <Link href="/driver/earnings" className="micro text-faint hover:text-muted">
          ← Earnings
        </Link>
        <h1 className="font-display mt-1 text-2xl font-semibold tracking-tight">
          Trip earnings
        </h1>
      </div>

      <Panel className="p-5">
        <p className="micro text-faint">This trip earned</p>
        <p className="font-display text-green mt-1 text-3xl font-semibold">
          {formatMoneyExact(data.amount, data.currency)}
        </p>
        {isV3 ? (
          <p className="text-muted mt-2 text-sm">
            Payout v3 · frozen base/premium terms from assignment acceptance
          </p>
        ) : isHourly ? (
          <p className="text-muted mt-2 text-sm">
            {formatMoneyExact(data.hourly_rate, data.currency)}/hour ×{" "}
            {formatDuration(data.capped_seconds)} verified time
          </p>
        ) : (
          <p className="text-muted mt-2 text-sm">
            Computed under the previous per-km formula.
          </p>
        )}
        {data.superseded_by_recompute ? (
          <p className="micro text-amber mt-2">
            Updated by an operations review — the entries below show every change.
          </p>
        ) : null}
      </Panel>

      {isHourly ? (
        <>
          {hasTierBreakdown ? (
            <Panel className="p-5">
              <h2 className="micro text-muted mb-3">Frozen tier breakdown</h2>
              <div className="divide-edge/60 divide-y">
                <div className="grid grid-cols-[1fr_auto] gap-4 py-2.5">
                  <div>
                    <p className="text-sm font-medium">Base tier</p>
                    <p className="micro text-faint mt-0.5">
                      {formatDuration(data.base_payable_seconds)} at{" "}
                      {formatMoneyExact(data.base_hourly_rate, data.currency)}/hour
                    </p>
                  </div>
                  <p className="font-mono text-sm">
                    {formatMoneyExact(data.base_amount, data.currency)}
                  </p>
                </div>
                <div className="grid grid-cols-[1fr_auto] gap-4 py-2.5">
                  <div>
                    <p className="text-sm font-medium">Premium tier</p>
                    <p className="micro text-faint mt-0.5">
                      {formatDuration(data.premium_payable_seconds)} at{" "}
                      {data.premium_hourly_rate != null
                        ? `${formatMoneyExact(data.premium_hourly_rate, data.currency)}/hour`
                        : `the base rate (${formatMoneyExact(data.base_hourly_rate, data.currency)}/hour)`}
                    </p>
                  </div>
                  <p className="font-mono text-sm">
                    {formatMoneyExact(data.premium_amount, data.currency)}
                  </p>
                </div>
              </div>
            </Panel>
          ) : null}

          <Panel className="p-5">
            <h2 className="micro text-muted mb-3">Verified time</h2>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="micro text-faint">Eligible</p>
                <p className="font-mono mt-0.5 text-lg">
                  {formatDuration(data.eligible_seconds)}
                </p>
              </div>
              <div>
                <p className="micro text-faint">Paid (after daily cap)</p>
                <p className="font-mono mt-0.5 text-lg">
                  {formatDuration(data.capped_seconds)}
                </p>
              </div>
            </div>
            {excluded.length > 0 ? (
              <div className="border-edge/60 mt-4 border-t pt-3">
                <p className="micro text-faint mb-2">Time that didn&apos;t count</p>
                <ul className="flex flex-col gap-1.5">
                  {excluded.map(([reason, seconds]) => (
                    <li key={reason} className="flex items-center justify-between text-sm">
                      <span className="text-muted">
                        {EXCLUSION_LABELS[reason] ?? reason.replace(/_/g, " ")}
                      </span>
                      <span className="font-mono">{formatDuration(seconds)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </Panel>

          {data.cap && capPct !== null ? (
            <Panel className="p-5">
              <div className="flex items-center justify-between">
                <h2 className="micro text-muted">Daily cap · {formatDate(data.cap.lagos_day)}</h2>
                <span className="font-mono text-sm">
                  {formatDuration(data.cap.day_payable_seconds)} /{" "}
                  {formatDuration(data.cap.cap_seconds)}
                </span>
              </div>
              <div
                role="progressbar"
                aria-valuenow={capPct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Daily payable-hours cap progress"
                className="bg-raised mt-3 h-2 overflow-hidden rounded-full"
              >
                <div className="bg-amber h-full rounded-full" style={{ width: `${capPct}%` }} />
              </div>
              <p className="micro text-faint mt-2">
                Once the day&apos;s cap fills, extra driving time no longer adds pay.
              </p>
            </Panel>
          ) : null}
        </>
      ) : null}

      <Panel className="overflow-hidden">
        <div className="border-edge border-b px-5 py-3.5">
          <h2 className="micro text-muted">Entries for this trip</h2>
        </div>
        <ul className="divide-edge/60 divide-y">
          {data.entries.map((e) => (
            <li key={e.id} className="flex items-center justify-between gap-3 px-5 py-3.5">
              <div className="min-w-0">
                <p className="truncate text-sm">
                  {e.description ?? e.entry_type.replace(/_/g, " ")}
                </p>
                <p className="micro text-faint mt-0.5">{formatDate(e.occurred_at)}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className="font-mono text-sm">
                  {e.entry_type === "reversal" ? "−" : ""}
                  {formatMoneyExact(e.amount, e.currency)}
                </span>
                <StatusChip tone={statusTone[e.status]}>{e.status}</StatusChip>
              </div>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
