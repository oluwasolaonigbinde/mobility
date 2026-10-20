import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate, formatDuration, formatMoneyExact } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import type { components } from "@/lib/api/schema";
import { DriverDataUnavailable } from "@/components/driver/data-unavailable";
import { FreshDriverAuthority } from "@/components/driver/fresh-authority";
import { readDriverApi } from "@/lib/driver/api-read";
import { driverEarningsStatus } from "@/lib/status/driver";
import { DisputeForm } from "./dispute-form";

export const metadata: Metadata = { title: "Trip earnings" };

type LedgerStatus = components["schemas"]["EarningsLedgerEntryStatus"];
type DriverFraudHold = components["schemas"]["DriverFraudHoldRead"];
type DriverFraudPublicStatus = DriverFraudHold["public_status"];
type NotificationType = components["schemas"]["NotificationType"];

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
  assessment_pending: {
    label: "Being checked",
    tone: "amber",
  },
  under_review: {
    label: "Under review",
    tone: "amber",
  },
  issue_confirmed: {
    label: "Problem found",
    tone: "coral",
  },
  review_cleared: {
    label: "Cleared",
    tone: "green",
  },
};

const noticeCopy: Partial<Record<NotificationType, string>> = {
  assignment_offered: "You got a job offer.",
  assignment_accepted: "You accepted the job.",
  payout_released: "Pay for this trip was released.",
  fraud_hold_raised: "This trip was put on hold for a check.",
  fraud_review_resolved: "Terrax Media finished checking this trip.",
  fraud_dispute_replied: "Terrax Media replied to you.",
  activity_floor_breached: "You drove less than the weekly minimum.",
  activity_floor_recovered: "You're back above the weekly minimum.",
  assignment_inactive: "No trips were recorded on this job for 7 days.",
  assignment_activity_recovered: "Trips started again on this job.",
};

const EXCLUSION_LABELS: Record<string, string> = {
  gps_gap: "Phone lost its location",
  low_accuracy: "Location too rough to use",
  teleport: "Location jumped too far",
  out_of_window: "Outside campaign window",
  out_of_area: "Outside campaign area",
  stationary: "Parked too long",
};

const METRES_PER_MILE = 1609.344;

function formatMiles(metres: number): string {
  return (metres / METRES_PER_MILE).toFixed(1);
}

export default async function DriverTripEarningsPage({
  params,
}: {
  params: Promise<{ tripId: string }>;
}) {
  const { tripId } = await params;
  const api = createApiClient(await getSessionToken());
  const breakdown = await readDriverApi(
    () =>
      api.GET("/api/v1/driver/trips/{trip_id}/earnings-breakdown", {
        params: { path: { trip_id: tripId } },
      }),
    { notFoundIsMissing: true },
  );
  if (breakdown.state === "auth") redirect("/login");
  if (breakdown.state === "missing") notFound();
  if (breakdown.state !== "ready") {
    return (
      <div className="animate-rise flex flex-col gap-4">
        <div>
          <Link href="/driver/earnings" className="micro text-faint hover:text-muted">
            ← Earnings
          </Link>
          <h1 className="font-display mt-1 text-2xl font-semibold tracking-tight">Trip earnings</h1>
        </div>
        <DriverDataUnavailable
          title="Trip earnings are unavailable"
          detail="Cardvert could not verify the current payout breakdown. No saved amount is shown as current."
          retryHref={`/driver/earnings/trips/${tripId}`}
        />
      </div>
    );
  }
  const holdsResponse = await readDriverApi(() =>
    api.GET("/api/v1/driver/fraud-holds", {
      params: { query: { trip_session_id: tripId } },
    }),
  );
  if (holdsResponse.state === "auth") redirect("/login");
  if (holdsResponse.state !== "ready") {
    return (
      <div className="animate-rise flex flex-col gap-4">
        <div>
          <Link href="/driver/earnings" className="micro text-faint hover:text-muted">
            ← Earnings
          </Link>
          <h1 className="font-display mt-1 text-2xl font-semibold tracking-tight">Trip earnings</h1>
        </div>
        <DriverDataUnavailable
          title="Trip review status is unavailable"
          detail="Cardvert calculated this trip but couldn't check whether this trip is under review, so the amount isn't shown. Try again shortly."
          retryHref={`/driver/earnings/trips/${tripId}`}
        />
      </div>
    );
  }
  const data = breakdown.data;
  const holds = holdsResponse.data.items ?? [];

  const excluded = Object.entries(data.excluded_seconds_by_reason ?? {});

  return (
    <FreshDriverAuthority
      refreshKey={crypto.randomUUID()}
      title="Current trip earnings hidden while offline"
      detail="Reconnect to see the latest pay, review and dispute status. Earlier review details and dispute actions are hidden while offline."
      retryHref={`/driver/earnings/trips/${tripId}`}
    >
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
          {data.superseded_by_recompute ? (
            <p className="micro text-amber mt-2">
              Updated after a Terrax Media review — the entries below show every change.
            </p>
          ) : null}
        </Panel>

        {holds.map((hold) => {
          const status = holdStatus[hold.public_status];
          return (
            <Panel key={hold.id} className="p-5" data-testid={`driver-fraud-hold-${hold.id}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-muted text-sm">Trip check</p>
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
                        <p>
                          {noticeCopy[notice.type_key] ?? "A Cardvert account update was recorded."}
                        </p>
                        <p className="micro text-faint mt-0.5">{formatDate(notice.created_at)}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {hold.dispute ? (
                <div className="border-edge/60 mt-4 border-t pt-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold">What you told Terrax Media</h3>
                    <StatusChip tone={hold.dispute.status === "replied" ? "green" : "amber"}>
                      {hold.dispute.status === "replied" ? "Replied" : "Waiting for a reply"}
                    </StatusChip>
                  </div>
                  <p className="mt-2 text-sm whitespace-pre-wrap">{hold.dispute.message}</p>
                  {hold.dispute.reply ? (
                    <div className="bg-raised mt-3 rounded-lg p-3">
                      <p className="text-muted text-sm font-medium">Terrax Media replied</p>
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

        <Panel className="p-5">
          <h2 className="micro text-muted mb-3">Miles counted</h2>
          {data.daily_rate_days && data.daily_rate_days.length > 0 ? (
            <ul className="divide-edge/60 divide-y">
              {data.daily_rate_days.map((day) => (
                <li key={day.lagos_day} className="grid grid-cols-[1fr_auto] gap-4 py-2.5">
                  <div>
                    <p className="text-sm font-medium">{formatDate(day.lagos_day)}</p>
                    <p className="micro text-faint mt-0.5">
                      {formatMiles(day.distance_m)} miles counted on this trip (Nigeria time, WAT)
                    </p>
                  </div>
                  <p className="font-mono text-sm">{formatMoneyExact(day.amount, data.currency)}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted text-sm">No miles counted on this trip.</p>
          )}
          {excluded.length > 0 ? (
            <div className="border-edge/60 mt-4 border-t pt-3">
              <p className="text-muted mb-1 text-sm font-medium">Time that didn&apos;t count</p>
              <ul className="flex flex-col gap-1.5">
                {excluded.map(([reason, seconds]) => (
                  <li key={reason} className="flex items-center justify-between text-sm">
                    <span className="text-muted">
                      {reason === "stationary"
                        ? "Stops longer than 5 minutes"
                        : (EXCLUSION_LABELS[reason] ?? reason.replace(/_/g, " "))}
                    </span>
                    <span className="font-mono">{formatDuration(seconds)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </Panel>

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
                  <StatusChip tone={statusTone[e.status]}>
                    {driverEarningsStatus[e.status]?.label ?? "Unknown"}
                  </StatusChip>
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </FreshDriverAuthority>
  );
}
