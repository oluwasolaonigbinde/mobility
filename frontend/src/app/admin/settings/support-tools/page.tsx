import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { formatDate } from "@/lib/format";
import { SearchSelect } from "../../search-select";
import { ProcessTripForm } from "../../payouts/process-trip-form";
import { QueueUnavailable } from "../../queue-search";
import { HubDrawer } from "../../hub-drawer";
import { completePages, worklistHref } from "../../worklist-reads";
export default async function SupportTools({
  searchParams,
}: {
  searchParams: Promise<{ driver_profile_id?: string; offset?: string; trip?: string }>;
}) {
  const p = await searchParams;
  const api = createApiClient(await getSessionToken());
  const offset = Number.isFinite(Number(p.offset)) ? Math.max(0, Math.floor(Number(p.offset))) : 0;
  const read = (offset: number, limit = 25) =>
    api.GET("/api/v1/admin/payout-calculations", {
      params: { query: { driver_profile_id: p.driver_profile_id!, limit, offset } },
    });
  const trips = p.driver_profile_id
    ? await read(offset)
        .then(({ data }) => data)
        .catch(() => undefined)
    : undefined;
  const all =
    p.driver_profile_id && p.trip
      ? await completePages((next) => read(next, 100)).catch(() => undefined)
      : undefined;
  const selected = all?.find(
    (row) => row.trip_session_id === p.trip && row.driver_profile_id === p.driver_profile_id,
  );
  const href = (changes: { offset?: string; trip?: string }) =>
    worklistHref("/admin/settings/support-tools", p, changes);
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Support tools" eyebrow="Recalculate a driver's trip" />
      <form className="mb-6 grid gap-3">
        <SearchSelect kind="driver_any" name="driver_profile_id" label="Find driver" />
        <button className="bg-amber text-bg rounded-lg p-3">Show trips</button>
      </form>
      {p.driver_profile_id ? (
        !trips ? (
          <QueueUnavailable />
        ) : (
          <>
            {!trips.items.length ? (
              <p>No calculated trips for this driver.</p>
            ) : (
              <ul className="grid gap-3">
                {trips.items.map((trip) => (
                  <li key={trip.id}>
                    <Link
                      className="border-edge block rounded-xl border p-4"
                      href={href({ trip: trip.trip_session_id })}
                    >
                      {formatDate(trip.trip_started_at)} · {trip.campaign_name}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            <Pagination
              total={trips.total}
              limit={25}
              offset={offset}
              hrefFor={(o) => href({ offset: String(o), trip: undefined })}
            />
          </>
        )
      ) : null}
      {p.trip ? (
        <HubDrawer title="Recalculate this trip" closeHref={href({ trip: undefined })}>
          {!all ? (
            <QueueUnavailable />
          ) : !selected ? (
            <p>Trip not found for this driver.</p>
          ) : (
            <>
              <p className="mb-4">
                {formatDate(selected.trip_started_at)} · {selected.campaign_name}
              </p>
              <ProcessTripForm tripId={selected.trip_session_id} />
            </>
          )}
        </HubDrawer>
      ) : null}
    </div>
  );
}
