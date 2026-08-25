import type { Metadata } from "next";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { requireRole } from "@/lib/auth/current-user";
import { ApiError } from "@/lib/api/errors";
import { formatDate, formatMoney } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { TripTracker } from "./trip-tracker";

export const metadata: Metadata = { title: "Track" };

export default async function DriverTrackPage() {
  const me = await requireRole("driver");
  const api = createApiClient(await getSessionToken());

  const [active, current, assignments, ledger] = await Promise.all([
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
    api.GET("/api/v1/driver/earnings/ledger", { params: { query: { limit: 4 } } }).catch((e) => {
      if (e instanceof ApiError && e.status === 404) return { data: undefined };
      throw e;
    }),
  ]);
  const assignmentItems = assignments.data?.items ?? [];
  const campaignNames = new Map(
    assignmentItems.map((item) => [item.campaign_id, item.campaign?.name ?? "Campaign"]),
  );
  const recentEntries = ledger.data?.items ?? [];

  return (
    <div className="animate-rise flex flex-col gap-4">
      <h1 className="font-display text-2xl font-semibold tracking-tight">Trip tracking</h1>
      <TripTracker
        assignment={active.data?.assignment ?? null}
        initialTrip={current.data?.trip ?? null}
        driverId={me.user.id}
      />

      <Panel className="p-5">
        <p className="micro text-muted">How a trip becomes earnings</p>
        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
          {[
            ["1", "Drive", "Start tracking"],
            ["2", "Verify", "Route analysed"],
            ["3", "Earn", "Ledger updated"],
          ].map(([step, label, detail]) => (
            <div key={step} className="bg-raised rounded-lg px-2 py-3">
              <span className="bg-amber/15 text-amber mx-auto flex size-6 items-center justify-center rounded-full font-mono text-xs">
                {step}
              </span>
              <p className="mt-2 text-xs font-medium">{label}</p>
              <p className="text-faint mt-0.5 text-[10px]">{detail}</p>
            </div>
          ))}
        </div>
        <p className="text-muted mt-4 text-xs leading-5">
          Tracking only runs after you start a trip and while Cardvert Driver stays open on screen.
        </p>
      </Panel>

      <Panel className="overflow-hidden">
        <div className="border-edge border-b px-5 py-3.5">
          <p className="micro text-muted">Recent verified activity</p>
        </div>
        {recentEntries.length === 0 ? (
          <p className="text-muted px-5 py-8 text-center text-sm">No completed trips yet.</p>
        ) : (
          <ul className="divide-edge/60 divide-y">
            {recentEntries.map((entry) => (
              <li key={entry.id} className="flex items-center justify-between gap-3 px-5 py-3.5">
                <div className="min-w-0">
                  <p className="truncate text-sm">
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
