import type { Metadata } from "next";
import { requireRole } from "@/lib/auth/current-user";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/errors";
import { formatMoney } from "@/lib/format";
import { Stat } from "@/components/ui/stat";
import { Panel } from "@/components/ui/panel";

export const metadata: Metadata = { title: "Driver" };

export default async function DriverHomePage() {
  const me = await requireRole("driver");
  const api = createApiClient(await getSessionToken());

  // A freshly-created driver user may not have a profile yet — that's a
  // legitimate state, not an error.
  let earnings = null;
  try {
    const { data } = await api.GET("/api/v1/driver/earnings/summary");
    earnings = data ?? null;
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 404)) throw error;
  }

  const totals = earnings?.totals_by_currency ?? [];

  return (
    <div className="animate-rise mx-auto max-w-3xl">
      <p className="micro text-muted">Good day</p>
      <h1 className="font-display mt-1 mb-8 text-3xl font-semibold tracking-tight">
        {me.user.full_name}
      </h1>

      {totals.length === 0 ? (
        <Panel className="p-6">
          <p className="text-muted text-sm">
            No earnings yet. Once you accept and activate a campaign assignment, your verified trips
            will start generating earnings here.
          </p>
        </Panel>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {totals.map((t) => (
            <div key={t.currency} className="contents">
              <Stat
                label={`Available · ${t.currency}`}
                value={formatMoney(t.available_amount, t.currency)}
                tone="green"
              />
              <Stat
                label={`Pending · ${t.currency}`}
                value={formatMoney(t.pending_amount, t.currency)}
                tone="amber"
              />
              <Stat
                label={`Lifetime · ${t.currency}`}
                value={formatMoney(t.lifetime_earned_amount, t.currency)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
