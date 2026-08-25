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
import { DisputeForm } from "./dispute-form";

export const metadata: Metadata = { title: "Trip earnings" };

type LedgerStatus = components["schemas"]["EarningsLedgerEntryStatus"];
type DriverFraudHold = components["schemas"]["DriverFraudHoldRead"];
type DriverFraudPublicStatus = DriverFraudHold["public_status"];
type DriverNoticeType = components["schemas"]["NotificationType"];

const statusTone: Record<LedgerStatus, "green" | "amber" | "coral" | "default"> = {
  available: "green",
  paid: "green",
  pending: "amber",
  voided: "coral",
  reversed: "default",
};

const holdStatus: Record<
  DriverFraudPublicStatus,
  { label: string; tone: "green" | "amber" | "coral" | "default" }
> = {
  assessment_pending: { label: "Assessment pending", tone: "amber" },
  under_review: { label: "Under review", tone: "amber" },
  issue_confirmed: { label: "Issue confirmed", tone: "coral" },
  review_cleared: { label: "Review cleared", tone: "green" },
};

const noticeCopy: Record<DriverNoticeType, string> = {
  fraud_hold_raised: "This trip was placed under review.",
  fraud_review_resolved: "Staff completed their review of this trip.",
  fraud_dispute_replied: "Staff replied to your dispute.",
  activity_floor_breached: "Your verified activity was below the configured weekly floor.",
  activity_floor_recovered: "Your verified activity recovered to the configured weekly floor.",
  assignment_inactive: "This assignment had no verified activity for seven consecutive days.",
  assignment_activity_recovered: "Verified activity resumed for this assignment.",
};

const EXCLUSION_LABELS: Record<string, string> = {
  gps_gap: "GPS signal gaps",
  low_accuracy: "Weak GPS accuracy",
  teleport: "Impossible movement",
  out_of_window: "Outside campaign window",
  out_of_area: "Outside campaign area",
  stationary: "Parked beyond the grace period",
  stationary_rolling_displacement:
    "Stationary after two 2-minute movement checks (shared grace applied)",
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
  const holdsResponse = await api.GET("/api/v1/driver/fraud-holds", {
    params: { query: { trip_session_id: tripId } },
  });
  const holds = holdsResponse.data?.items ?? [];

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
        <h1 className="font-display mt-1 text-2xl font-semibold tracking-tight">Trip earnings</h1>
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
          <p className="text-muted mt-2 text-sm">Computed under the previous per-km formula.</p>
        )}
        {data.superseded_by_recompute ? (
          <p className="micro text-amber mt-2">
            Updated by an operations review — the entries below show every change.
          </p>
        ) : null}
      </Panel>

      {holds.map((hold) => {
        const status = holdStatus[hold.public_status];
        return (
          <Panel key={hold.id} className="p-5" data-testid={`driver-fraud-hold-${hold.id}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="micro text-faint">Earnings review</p>
                <h2 className="mt-1 text-lg font-semibold">{hold.reason.title}</h2>
              </div>
              <StatusChip tone={status.tone}>{status.label}</StatusChip>
            </div>
            <p className="text-muted mt-2 text-sm">{hold.reason.body}</p>

            {hold.notices && hold.notices.length > 0 ? (
              <div className="border-edge/60 mt-4 border-t pt-3">
                <h3 className="micro text-faint mb-2">Updates</h3>
                <ul className="flex flex-col gap-2">
                  {hold.notices.map((notice) => (
                    <li key={notice.id} className="text-sm">
                      <p>{noticeCopy[notice.type_key]}</p>
                      <p className="micro text-faint mt-0.5">{formatDate(notice.created_at)}</p>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {hold.dispute ? (
              <div className="border-edge/60 mt-4 border-t pt-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="micro text-muted">Your dispute</h3>
                  <StatusChip tone={hold.dispute.status === "replied" ? "green" : "amber"}>
                    {hold.dispute.status === "replied" ? "Staff replied" : "Awaiting reply"}
                  </StatusChip>
                </div>
                <p className="mt-2 text-sm whitespace-pre-wrap">{hold.dispute.message}</p>
                {hold.dispute.reply ? (
                  <div className="bg-raised mt-3 rounded-lg p-3">
                    <p className="micro text-faint">Staff reply</p>
                    <p className="mt-1 text-sm whitespace-pre-wrap">{hold.dispute.reply}</p>
                  </div>
                ) : null}
              </div>
            ) : hold.public_status === "review_cleared" ? (
              <p className="micro text-green mt-4">
                This review is closed and no dispute is needed.
              </p>
            ) : (
              <DisputeForm flagId={hold.id} tripId={tripId} />
            )}
          </Panel>
        );
      })}

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
                <p className="mt-0.5 font-mono text-lg">{formatDuration(data.eligible_seconds)}</p>
              </div>
              <div>
                <p className="micro text-faint">Paid (after daily cap)</p>
                <p className="mt-0.5 font-mono text-lg">{formatDuration(data.capped_seconds)}</p>
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
