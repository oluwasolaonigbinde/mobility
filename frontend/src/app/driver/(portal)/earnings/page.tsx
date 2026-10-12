import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate, formatMoneyExact } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { DriverDataUnavailable } from "@/components/driver/data-unavailable";
import { FreshDriverAuthority } from "@/components/driver/fresh-authority";
import { loadDailyEarnings } from "@/lib/driver/load-daily-earnings";

export const metadata: Metadata = { title: "Earnings" };
export default async function DriverEarningsPage() {
  const result = await loadDailyEarnings(createApiClient(await getSessionToken()));
  if (result.state === "auth") redirect("/login");
  return (
    <FreshDriverAuthority
      refreshKey={crypto.randomUUID()}
      title="Reconnect to check earnings"
      detail="Current amounts are hidden while offline."
      retryHref="/driver/earnings"
    >
      <div className="animate-rise flex flex-col gap-4">
        <h1 className="font-display text-2xl font-semibold">Earnings</h1>
        {result.state !== "ready" ? (
          <DriverDataUnavailable
            title="Earnings unavailable"
            detail="Your complete daily history could not be verified."
            retryHref="/driver/earnings"
          />
        ) : result.data.length === 0 ? (
          <Panel className="p-5 text-sm">No earnings yet.</Panel>
        ) : (
          <Panel className="overflow-hidden">
            <ul className="divide-edge divide-y">
              {result.data.map((day) => (
                <li key={`${day.day}:${day.currency}`} className="px-5 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-medium">{formatDate(day.day)}</p>
                    <p className="font-mono">{formatMoneyExact(day.amount, day.currency)}</p>
                  </div>
                  <div className="mt-1 flex items-center justify-between gap-3">
                    <p
                      className={`text-sm ${day.status.startsWith("Paid") ? "text-green" : "text-muted"}`}
                    >
                      {day.status}
                    </p>
                    {day.status.startsWith("On hold") ? (
                      <Link href="/driver/help" className="text-amber text-sm">
                        Help
                      </Link>
                    ) : null}
                  </div>
                  {day.tripIds.length ? (
                    <details className="mt-2 text-sm">
                      <summary className="text-muted cursor-pointer">Trips</summary>
                      <ul className="mt-2 grid gap-2">
                        {day.tripIds.map((id, index) => (
                          <li key={id}>
                            <Link href={`/driver/earnings/trips/${id}`} className="text-amber">
                              Trip {index + 1}
                            </Link>
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </div>
    </FreshDriverAuthority>
  );
}
