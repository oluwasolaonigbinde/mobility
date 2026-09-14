import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { requireRole } from "@/lib/auth/current-user";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate, formatMoney } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { CampaignJourneyPanel } from "@/components/driver/campaign-journey-panel";
import { DriverDataUnavailable } from "@/components/driver/data-unavailable";
import { FreshDriverAuthority } from "@/components/driver/fresh-authority";
import { readDriverApi } from "@/lib/driver/api-read";
import { loadDriverCampaignJourney } from "@/lib/driver/load-campaign-journey";

export const metadata: Metadata = { title: "Home" };

export default async function DriverHomePage() {
  const me = await requireRole("driver");
  const api = createApiClient(await getSessionToken());

  const [campaignJourney, earnings, assignments, ledger] = await Promise.all([
    loadDriverCampaignJourney(),
    readDriverApi(() => api.GET("/api/v1/driver/earnings/summary")),
    readDriverApi(() =>
      api.GET("/api/v1/driver/campaign-assignments", { params: { query: { limit: 50 } } }),
    ),
    readDriverApi(() =>
      api.GET("/api/v1/driver/earnings/ledger", { params: { query: { limit: 6 } } }),
    ),
  ]);

  if ([earnings, assignments, ledger].some((source) => source.state === "auth")) {
    redirect("/login");
  }

  const totals = earnings.state === "ready" ? earnings.data.totals_by_currency : null;
  const assignment = campaignJourney.activationAssignment;
  const trip = campaignJourney.currentTrip;
  const allAssignments = assignments.state === "ready" ? assignments.data.items : null;
  const recentEntries = ledger.state === "ready" ? ledger.data.items : null;
  const campaignNames = new Map(
    (allAssignments ?? []).map((item) => [item.campaign_id, item.campaign?.name ?? "Campaign"]),
  );
  const completedCampaigns = allAssignments?.filter((item) => item.status === "completed").length;
  const tripCount = recentEntries?.filter((entry) => entry.trip_session_id).length;
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  return (
    <FreshDriverAuthority
      refreshKey={crypto.randomUUID()}
      title="Current driver status hidden while offline"
      detail="Reconnect while Cardvert is open to verify your current trip, work status and earnings. Previously loaded authority is not shown as current."
      retryHref="/driver"
    >
      <div className="animate-rise flex flex-col gap-4">
        <div>
          <p className="micro text-muted">{greeting}</p>
          <h1 className="font-display text-2xl font-semibold tracking-tight">
            {me.user.full_name.split(" ")[0]}
          </h1>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <Panel className="p-3.5">
            <p className="micro text-faint">Campaigns</p>
            <p className="font-display mt-1 text-2xl font-semibold">
              {allAssignments?.length ?? "—"}
            </p>
            <p className="text-muted mt-0.5 text-[11px]">
              {completedCampaigns === undefined
                ? "history unavailable"
                : `${completedCampaigns} completed`}
            </p>
          </Panel>
          <Panel className="p-3.5">
            <p className="micro text-faint">Trip entries</p>
            <p className="font-display mt-1 text-2xl font-semibold">{tripCount ?? "—"}</p>
            <p className="text-muted mt-0.5 text-[11px]">
              {tripCount === undefined ? "history unavailable" : "recent ledger"}
            </p>
          </Panel>
          <Panel className="p-3.5">
            <p className="micro text-faint">Standing</p>
            <p
              className={`font-display mt-1 text-sm font-semibold ${campaignJourney.journey.standing === "READY" ? "text-green" : campaignJourney.journey.standing === "BLOCKED" ? "text-coral" : "text-amber"}`}
            >
              {campaignJourney.journey.standing}
            </p>
            <p className="text-muted mt-1 text-[11px]">
              {campaignJourney.journey.canStart ? "Can start a trip" : "Can't start a trip yet"}
            </p>
          </Panel>
        </div>

        <CampaignJourneyPanel journey={campaignJourney.journey} />

        {/* Live trip banner */}
        {trip ? (
          <Link href="/driver/track">
            <Panel className="border-green/40 shadow-glow-cyan flex items-center justify-between p-4">
              <div>
                <p className="micro text-green flex items-center gap-1.5">
                  <span className="animate-pulse-dot bg-green inline-block size-1.5 rounded-full" />
                  Trip in progress
                </p>
                <p className="mt-1 text-sm">Confirmed by Cardvert — tap to manage your trip</p>
              </div>
              <span aria-hidden className="text-green text-xl">
                →
              </span>
            </Panel>
          </Link>
        ) : null}

        {/* Earnings snapshot */}
        {totals === null ? (
          <DriverDataUnavailable
            title="Current earnings are unavailable"
            detail="Cardvert couldn't verify your latest earnings summary, so no balance is shown. Your trip and work status remain available above."
            retryHref="/driver"
          />
        ) : (
          <Panel className="p-5">
            <p className="micro text-muted">Available for payment</p>
            {totals.length === 0 ? (
              <>
                <p className="font-display mt-1 text-xl font-semibold">No earnings balance yet</p>
                <p className="text-muted mt-2 text-xs">
                  Accept a campaign and start tracking trips to earn.
                </p>
              </>
            ) : (
              totals.map((t) => (
                <div key={t.currency}>
                  <p className="font-display text-green mt-1 text-3xl font-semibold">
                    {formatMoney(t.batch_payable_amount, t.currency)}
                  </p>
                  <p className="text-muted mt-1 text-xs">
                    {formatMoney(t.pending_amount, t.currency)} pending ·{" "}
                    {formatMoney(t.carry_forward_debt_amount, t.currency)} owed, taken from your
                    payouts · {formatMoney(t.lifetime_earned_amount, t.currency)} earned in total
                  </p>
                </div>
              ))
            )}
            <Link href="/driver/earnings" className="micro text-amber mt-3 inline-block">
              View earnings →
            </Link>
          </Panel>
        )}

        {/* Active campaign */}
        <Panel className="p-5">
          <div className="flex items-center justify-between">
            <p className="micro text-muted">Active campaign</p>
            {assignment ? <StatusChip tone="green">ACTIVE</StatusChip> : null}
          </div>
          {assignment ? (
            <>
              <p className="mt-2 text-base font-medium">{assignment.campaignName}</p>
              <p className="micro text-faint mt-1">{assignment.plateNumber} · assigned vehicle</p>
              <Link href="/driver/track" className="micro text-amber mt-3 inline-block">
                {trip
                  ? "Manage live trip →"
                  : campaignJourney.journey.canStart
                    ? "Open Start checks →"
                    : "Review readiness →"}
              </Link>
            </>
          ) : (
            <>
              <p className="text-muted mt-2 text-sm">No active campaign on your vehicle.</p>
              <Link href="/driver/assignments" className="micro text-amber mt-3 inline-block">
                See offers →
              </Link>
            </>
          )}
        </Panel>

        <Panel className="overflow-hidden">
          <div className="border-edge flex items-center justify-between border-b px-5 py-3.5">
            <div>
              <p className="micro text-muted">Recent activity</p>
              <p className="text-muted mt-1 text-xs">
                Every earning links back to a verified trip.
              </p>
            </div>
            <Link href="/driver/earnings" className="micro text-amber">
              All activity →
            </Link>
          </div>
          {recentEntries === null ? (
            <div className="px-5 py-5">
              <DriverDataUnavailable
                title="Recent activity unavailable"
                detail="Cardvert couldn't load the optional recent activity list. Current trip and earnings authority remain unchanged."
                retryHref="/driver"
              />
            </div>
          ) : recentEntries.length === 0 ? (
            <p className="text-muted px-5 py-8 text-center text-sm">
              Your completed trips will appear here.
            </p>
          ) : (
            <ul className="divide-edge/60 divide-y">
              {recentEntries.slice(0, 4).map((entry) => (
                <li key={entry.id} className="flex items-center justify-between gap-4 px-5 py-3.5">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {campaignNames.get(entry.campaign_id) ?? "Campaign trip"}
                    </p>
                    <p className="micro text-faint mt-0.5">{formatDate(entry.occurred_at)}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-sm">{formatMoney(entry.amount, entry.currency)}</p>
                    <p
                      className={`micro mt-0.5 ${
                        entry.status === "available" || entry.status === "paid"
                          ? "text-green"
                          : "text-amber"
                      }`}
                    >
                      {entry.status}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </FreshDriverAuthority>
  );
}
