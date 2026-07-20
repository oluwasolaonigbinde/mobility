import type { Metadata } from "next";
import Link from "next/link";
import { requireRole } from "@/lib/auth/current-user";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/errors";
import { formatMoney } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";

export const metadata: Metadata = { title: "Home" };

export default async function DriverHomePage() {
  const me = await requireRole("driver");
  const api = createApiClient(await getSessionToken());

  // A fresh driver user may not have a profile/assignment yet — 404s here
  // are legitimate states, not failures.
  const [earnings, active, current] = await Promise.all([
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
  ]);

  const totals = earnings.data?.totals_by_currency ?? [];
  const assignment = active.data?.assignment ?? null;
  const trip = current.data?.trip ?? null;
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
        <p className="micro text-muted">Available earnings</p>
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
                {formatMoney(t.available_amount, t.currency)}
              </p>
              <p className="text-muted mt-1 text-xs">
                {formatMoney(t.pending_amount, t.currency)} pending ·{" "}
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
    </div>
  );
}
