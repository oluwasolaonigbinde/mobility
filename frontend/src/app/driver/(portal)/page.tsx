import type { Metadata } from "next";
import Link from "next/link";
import { requireRole } from "@/lib/auth/current-user";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/errors";
import { formatDate, formatMoney } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";

export const metadata: Metadata = { title: "Home" };

export default async function DriverHomePage() {
  const me = await requireRole("driver");
  const api = createApiClient(await getSessionToken());

  // A fresh driver user may not have a profile/assignment yet — 404s here
  // are legitimate states, not failures.
  const [earnings, active, current, assignments, ledger] = await Promise.all([
    api.GET("/api/v1/driver/earnings/summary").catch((e) => {
      if (e instanceof ApiError && e.status === 404) return { data: undefined };
      throw e;
    }),
    api.GET("/api/v1/driver/campaign-assignments/active").catch((e) => {
      if (e instanceof ApiError && e.status === 404) return { data: undefined };
      throw e;
    }),
    api.GET("/api/v1/driver/trips/current").catch((e) => {
      if (e instanceof ApiError && e.status === 404) return { data: undefined };
      throw e;
    }),
    api
      .GET("/api/v1/driver/campaign-assignments", { params: { query: { limit: 50 } } })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) return { data: undefined };
        throw e;
      }),
    api.GET("/api/v1/driver/earnings/ledger", { params: { query: { limit: 6 } } }).catch((e) => {
      if (e instanceof ApiError && e.status === 404) return { data: undefined };
      throw e;
    }),
  ]);

  const totals = earnings.data?.totals_by_currency ?? [];
  const assignment = active.data?.assignment ?? null;
  const trip = current.data?.trip ?? null;
  const allAssignments = assignments.data?.items ?? [];
  const recentEntries = ledger.data?.items ?? [];
  const campaignNames = new Map(
    allAssignments.map((item) => [item.campaign_id, item.campaign?.name ?? "Campaign"]),
  );
  const completedCampaigns = allAssignments.filter((item) => item.status === "completed").length;
  const tripCount = recentEntries.filter((entry) => entry.trip_session_id).length;
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  return (
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
          <p className="font-display mt-1 text-2xl font-semibold">{allAssignments.length}</p>
          <p className="text-muted mt-0.5 text-[11px]">{completedCampaigns} completed</p>
        </Panel>
        <Panel className="p-3.5">
          <p className="micro text-faint">Trip entries</p>
          <p className="font-display mt-1 text-2xl font-semibold">{tripCount}</p>
          <p className="text-muted mt-0.5 text-[11px]">recent ledger</p>
        </Panel>
        <Panel className="p-3.5">
          <p className="micro text-faint">Standing</p>
          <p className="font-display text-green mt-1 text-sm font-semibold">READY</p>
          <p className="text-muted mt-1 text-[11px]">vehicle active</p>
        </Panel>
      </div>

      {/* Live trip banner */}
      {trip ? (
        <Link href="/driver/track">
          <Panel className="border-green/40 shadow-glow-cyan flex items-center justify-between p-4">
            <div>
              <p className="micro text-green flex items-center gap-1.5">
                <span className="animate-pulse-dot bg-green inline-block size-1.5 rounded-full" />
                Trip in progress
              </p>
              <p className="mt-1 text-sm">
                {trip.ping_count} pings recorded — tap to manage tracking
              </p>
            </div>
            <span aria-hidden className="text-green text-xl">
              →
            </span>
          </Panel>
        </Link>
      ) : null}

      {/* Earnings snapshot */}
      <Panel className="p-5">
        <p className="micro text-muted">Batch-payable earnings</p>
        {totals.length === 0 ? (
          <>
            <p className="font-display mt-1 text-3xl font-semibold">₦0</p>
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
                {formatMoney(t.carry_forward_debt_amount, t.currency)} carried debt ·{" "}
                {formatMoney(t.lifetime_earned_amount, t.currency)} lifetime
              </p>
            </div>
          ))
        )}
        <Link href="/driver/earnings" className="micro text-amber mt-3 inline-block">
          View ledger →
        </Link>
      </Panel>

      {/* Active campaign */}
      <Panel className="p-5">
        <div className="flex items-center justify-between">
          <p className="micro text-muted">Active campaign</p>
          {assignment ? <StatusChip tone="green">ACTIVE</StatusChip> : null}
        </div>
        {assignment?.campaign ? (
          <>
            <p className="mt-2 text-base font-medium">{assignment.campaign.name}</p>
            <p className="micro text-faint mt-1">
              {assignment.vehicle?.plate_number ?? "—"} ·{" "}
              {assignment.vehicle?.vehicle_type ?? "vehicle"}
            </p>
            <Link href="/driver/track" className="micro text-amber mt-3 inline-block">
              {trip ? "Manage live trip →" : "Start a trip →"}
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
            <p className="text-muted mt-1 text-xs">Every earning links back to a verified trip.</p>
          </div>
          <Link href="/driver/earnings" className="micro text-amber">
            All activity →
          </Link>
        </div>
        {recentEntries.length === 0 ? (
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
  );
}
