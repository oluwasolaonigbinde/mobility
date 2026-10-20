export const metadata = { title: "Trip checks" };
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { FilterChips, ViewTabs } from "@/components/ui/tabs";
import { formatDate, formatDateTime, formatMoneyExact } from "@/lib/format";
import { adminStatus } from "@/lib/status/admin";
import { ReviewActions } from "../fraud/review-actions";
import { DisputeReplyActions } from "../fraud/dispute-actions";
import { SpotCheckForm } from "../fraud/spot-check-actions";
import {
  evidenceVerificationId,
  matchedTripIds,
  readableEvidence,
  tripReviewReason,
} from "../fraud/evidence";
import { HubDrawer } from "../hub-drawer";
import { QueueUnavailable } from "../queue-search";
import { OperationForm } from "../operation-form";
import { worklistHref } from "../worklist-reads";
import { readTripContext } from "./reads";
import { RecordedRouteMap } from "./route-map";
type Query = {
  tab?: string;
  status?: string;
  offset?: string;
  driver_profile_id?: string;
  campaign_id?: string;
  flag?: string;
  late?: string;
  check?: string;
  route_offset?: string;
  disputes_offset?: string;
};
export default async function TripChecks({ searchParams }: { searchParams: Promise<Query> }) {
  const p = await searchParams;
  const tab = p.tab === "late" || p.tab === "in-person" ? p.tab : "suspicious";
  const offset = Number.isFinite(Number(p.offset)) ? Math.max(0, Math.floor(Number(p.offset))) : 0;
  const api = createApiClient(await getSessionToken());
  const href = (changes: Partial<Query>) =>
    worklistHref("/admin/trip-checks", { ...p, tab }, changes);
  const closeHref = href({
    flag: undefined,
    late: undefined,
    check: undefined,
    route_offset: undefined,
    disputes_offset: undefined,
  });
  const flagStatus = (["open", "acknowledged", "confirmed", "dismissed"] as const).find(
    (value) => value === p.status,
  );
  const lateStatus = ["quarantined", "applied", "discarded"].includes(p.status ?? "")
    ? p.status
    : "quarantined";
  const flagRead = (next: number, limit = 25, flag_id?: string) =>
    api.GET("/api/v1/admin/fraud-flags", {
      params: {
        query: {
          limit,
          offset: next,
          flag_id,
          status: flagStatus,
          driver_profile_id: p.driver_profile_id,
          campaign_id: p.campaign_id,
        },
      },
    });
  const lateRead = (next: number, limit = 25, quarantine_id?: string) =>
    api.GET("/api/v1/admin/trips/quarantined-batches", {
      params: {
        query: {
          limit,
          offset: next,
          status: lateStatus,
          quarantine_id,
          driver_profile_id: p.driver_profile_id,
          campaign_id: p.campaign_id,
        },
      },
    });
  const checkRead = (
    next: number,
    limit = 25,
    verification_id?: string,
    trip_session_id?: string,
  ) =>
    api.GET("/api/v1/admin/evidence-verifications", {
      params: {
        query: {
          limit,
          offset: next,
          verification_type: "physical_spot_check",
          verification_id,
          trip_session_id,
          driver_profile_id: p.driver_profile_id,
          campaign_id: p.campaign_id,
        },
      },
    });
  const flags =
    tab === "suspicious"
      ? await flagRead(offset)
          .then(({ data }) => data)
          .catch(() => undefined)
      : undefined;
  const late =
    tab === "late"
      ? await lateRead(offset)
          .then(({ data }) => data)
          .catch(() => undefined)
      : undefined;
  const checkPage =
    tab === "in-person"
      ? await checkRead(offset)
          .then(({ data }) => data)
          .catch(() => undefined)
      : undefined;
  const checks = checkPage?.items;
  const [allFlags, allLate, selectedChecks] = await Promise.all([
    tab === "suspicious" && p.flag
      ? flagRead(0, 1, p.flag)
          .then(({ data }) => data?.items)
          .catch(() => undefined)
      : Promise.resolve(undefined),
    tab === "late" && p.late
      ? lateRead(0, 1, p.late)
          .then(({ data }) => data?.items)
          .catch(() => undefined)
      : Promise.resolve(undefined),
    tab === "in-person" && p.check
      ? checkRead(0, 1, p.check)
          .then(({ data }) => data?.items)
          .catch(() => undefined)
      : Promise.resolve(undefined),
  ]);
  const scoped = (row: { driver_profile_id?: string | null; campaign_id?: string | null }) =>
    (!p.driver_profile_id || row.driver_profile_id === p.driver_profile_id) &&
    (!p.campaign_id || row.campaign_id === p.campaign_id);
  const selectedFlag = allFlags?.find(
    (item) => item.id === p.flag && scoped(item) && (!flagStatus || item.status === flagStatus),
  );
  const selectedLate = allLate?.find(
    (item) => item.id === p.late && scoped(item) && item.status === lateStatus,
  );
  const selectedCheck = selectedChecks?.find(
    (item) =>
      item.id === p.check && scoped(item) && item.verification_type === "physical_spot_check",
  );
  const visibleChecks = checks;
  const visibleLate = late?.items;
  const selectedTrip =
    selectedFlag?.trip_session_id ??
    selectedLate?.trip_session_id ??
    selectedCheck?.source_trip_session_id;
  let selectedContext;
  if (selectedTrip) {
    try {
      selectedContext = await readTripContext(api, selectedTrip, {
        driver_profile_id: p.driver_profile_id,
        campaign_id: p.campaign_id,
      });
    } catch {
      /* Only the opened section fails. */
    }
  }
  const selectedRecord = selectedFlag ?? selectedLate ?? selectedCheck;
  const selectedInScope =
    selectedContext &&
    selectedRecord &&
    selectedContext.analytics.driver_profile_id === selectedRecord.driver_profile_id &&
    selectedContext.analytics.campaign_id === selectedRecord.campaign_id &&
    selectedContext.analytics.assignment_id === selectedRecord.assignment_id;
  const failed = Boolean(selectedTrip && !selectedInScope);
  const pageOffset = (value?: string) => Math.max(0, Math.floor(Number(value) || 0));
  const disputePage =
    selectedFlag && selectedInScope
      ? await api
          .GET("/api/v1/admin/fraud-disputes", {
            params: {
              query: {
                flag_id: [selectedFlag.id],
                limit: 25,
                offset: pageOffset(p.disputes_offset),
              },
            },
          })
          .then(({ data }) => data)
          .catch(() => undefined)
      : undefined;
  const disputes = disputePage?.items.every(
    (item) =>
      item.fraud_flag_id === selectedFlag?.id &&
      item.driver_profile_id === selectedFlag.driver_profile_id,
  )
    ? disputePage.items
    : undefined;
  const routePage =
    selectedFlag && selectedInScope
      ? await api
          .GET("/api/v1/admin/fraud-flags/{flag_id}/route", {
            params: {
              path: { flag_id: selectedFlag.id },
              query: { limit: 500, offset: pageOffset(p.route_offset) },
            },
          })
          .then(({ data }) =>
            data && data.flag_id === selectedFlag.id && data.trip_session_id === selectedTrip
              ? data
              : undefined,
          )
          .catch(() => undefined)
      : undefined;
  const route = routePage?.items;
  const held = (flag: NonNullable<typeof selectedFlag>) =>
    flag.money_effect.held_currency
      ? formatMoneyExact(flag.money_effect.held_pending_net, flag.money_effect.held_currency)
      : "No pay held";
  const summaries = new Map<
    string,
    { name: string; plate: string; campaign: string; date: string }
  >();
  function addSummary(
    trip: string,
    row: {
      driver_name?: string | null;
      vehicle_plate?: string | null;
      campaign_name?: string | null;
      trip_started_at?: string | null;
    },
  ) {
    if (row.driver_name && row.vehicle_plate && row.campaign_name && row.trip_started_at)
      summaries.set(trip, {
        name: row.driver_name,
        plate: row.vehicle_plate,
        campaign: row.campaign_name,
        date: row.trip_started_at,
      });
  }
  for (const row of flags?.items ?? []) addSummary(row.trip_session_id, row);
  for (const row of visibleLate ?? []) addSummary(row.trip_session_id, row);
  for (const row of visibleChecks ?? []) addSummary(row.source_trip_session_id, row);
  if (selectedTrip && selectedContext) summaries.set(selectedTrip, selectedContext);
  // Driver, trip time and the plain reason come first; IDs stay available but secondary (D38c).
  const line = (tripId: string) => {
    const context = summaries.get(tripId);
    return context ? (
      <>
        <p className="text-ink font-semibold">{context.name}</p>
        <p className="text-muted text-sm">
          Trip {formatDateTime(context.date)} · {context.plate} · {context.campaign}
        </p>
      </>
    ) : (
      <QueueUnavailable />
    );
  };
  const ids = (...pairs: [string, string | null | undefined][]) => (
    <p className="text-faint mt-2 text-xs break-all">
      {pairs
        .filter((pair): pair is [string, string] => Boolean(pair[1]))
        .map(([label, value]) => `${label} ${value}`)
        .join(" · ")}
    </p>
  );
  const total =
    tab === "suspicious" ? flags?.total : tab === "late" ? late?.total : checkPage?.total;
  const listHref = (changes: Partial<Query>) =>
    href({
      offset: undefined,
      flag: undefined,
      late: undefined,
      check: undefined,
      route_offset: undefined,
      disputes_offset: undefined,
      ...changes,
    });
  const statusChips =
    tab === "suspicious"
      ? [
          { href: listHref({ status: undefined }), label: "All", active: !flagStatus },
          ...(["open", "acknowledged", "confirmed", "dismissed"] as const).map((status) => ({
            href: listHref({ status }),
            label: adminStatus(status),
            active: flagStatus === status,
          })),
        ]
      : tab === "late"
        ? ["quarantined", "applied", "discarded"].map((status) => ({
            href: listHref({ status }),
            label: adminStatus(status),
            active: lateStatus === status,
          }))
        : [];
  const matchedTrips =
    selectedFlag && selectedInScope && selectedFlag.flag_type === "route_replay"
      ? await Promise.all(
          matchedTripIds(selectedFlag.evidence).map(async (id) => ({
            id,
            context: await readTripContext(api, id).catch(() => undefined),
          })),
        )
      : [];
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Trip checks" />
      <ViewTabs
        label="Trip check lists"
        items={(
          [
            ["suspicious", "Suspicious trips"],
            ["late", "Late uploads"],
            ["in-person", "In-person checks"],
          ] as const
        ).map(([value, label]) => ({
          href: listHref({ tab: value, status: undefined }),
          label,
          active: tab === value,
        }))}
      />
      {statusChips.length ? (
        <FilterChips label="Status" visibleLabel="Show" items={statusChips} />
      ) : null}
      {total === undefined ? (
        <QueueUnavailable />
      ) : (
        <>
          {!total ? (
            <p>Nothing matches these filters.</p>
          ) : (
            <ul className="grid gap-3">
              {tab === "suspicious"
                ? flags?.items.map((flag) => (
                    <li key={flag.id}>
                      <Link
                        className="border-edge block rounded-xl border p-4"
                        href={href({
                          flag: flag.id,
                          route_offset: undefined,
                          disputes_offset: undefined,
                        })}
                      >
                        {line(flag.trip_session_id)}
                        <p className="mt-2">{tripReviewReason(flag.flag_type, flag.evidence)}</p>
                        <p className="text-muted text-sm">
                          {adminStatus(flag.status)} · Pay held: {held(flag)}
                        </p>
                        {ids(
                          ["Trip", flag.trip_session_id],
                          ["Review", flag.id],
                          ["Check", evidenceVerificationId(flag.evidence)],
                        )}
                      </Link>
                    </li>
                  ))
                : null}
              {tab === "late"
                ? visibleLate?.map((batch) => (
                    <li key={batch.id}>
                      <Link
                        className="border-edge block rounded-xl border p-4"
                        href={href({
                          late: batch.id,
                          route_offset: undefined,
                          disputes_offset: undefined,
                        })}
                      >
                        {line(batch.trip_session_id)}
                        <p className="mt-2">
                          Locations uploaded late · received {formatDateTime(batch.received_at)} ·{" "}
                          {batch.ping_count} location records
                        </p>
                        {ids(["Trip", batch.trip_session_id])}
                      </Link>
                    </li>
                  ))
                : null}
              {tab === "in-person"
                ? visibleChecks?.map((check) => (
                    <li key={check.id}>
                      <Link
                        className="border-edge block rounded-xl border p-4"
                        href={href({
                          check: check.id,
                          route_offset: undefined,
                          disputes_offset: undefined,
                        })}
                      >
                        {line(check.source_trip_session_id)}
                        <p className="mt-2">
                          {adminStatus(check.status)} inspection · recorded{" "}
                          {formatDateTime(check.issued_at)}
                        </p>
                        {ids(["Trip", check.source_trip_session_id])}
                      </Link>
                    </li>
                  ))
                : null}
            </ul>
          )}
          <Pagination
            total={total}
            limit={25}
            offset={offset}
            hrefFor={(o) =>
              href({ offset: String(o), flag: undefined, late: undefined, check: undefined })
            }
          />
        </>
      )}
      {p.flag && tab === "suspicious" ? (
        <HubDrawer title="Suspicious trip" closeHref={closeHref}>
          {!allFlags ? (
            <QueueUnavailable />
          ) : !selectedFlag ? (
            <p>Trip review not found for these filters.</p>
          ) : !selectedInScope || failed ? (
            <QueueUnavailable />
          ) : (
            <>
              {line(selectedFlag.trip_session_id)}
              <p className="my-4">
                {tripReviewReason(selectedFlag.flag_type, selectedFlag.evidence)}
              </p>
              <p className="text-muted mb-4 text-sm">
                Detected {formatDate(selectedFlag.detected_at)} · Review due{" "}
                {formatDate(selectedFlag.review_due_at)}
              </p>
              {selectedFlag.escalated_at ? (
                <p className="text-amber mb-4 text-sm">
                  {selectedFlag.status === "open" || selectedFlag.status === "acknowledged"
                    ? "Review deadline passed — this review is unresolved and pay stays held."
                    : "The review deadline passed before this decision."}
                </p>
              ) : null}
              {selectedFlag.resolution_note ? (
                <p className="mb-4">Decision: {selectedFlag.resolution_note}</p>
              ) : null}
              <ul aria-label="Detection evidence" className="mb-4 list-disc pl-5 text-sm">
                {readableEvidence(selectedFlag.evidence).map((text) => (
                  <li key={text}>{text}</li>
                ))}
              </ul>
              {matchedTrips.length ? (
                <section aria-label="Matching trips" className="mb-4 text-sm">
                  <h3 className="mb-2 font-semibold">Trips with the same route</h3>
                  <ul className="grid gap-2">
                    {matchedTrips.map(({ id, context }) => (
                      <li key={id} className="border-edge rounded-lg border p-3">
                        {context ? (
                          <>
                            <p className="font-medium">{context.name}</p>
                            <p className="text-muted">
                              Trip {formatDateTime(context.date)} · {context.plate} ·{" "}
                              {context.campaign}
                            </p>
                          </>
                        ) : (
                          <p className="text-muted">Trip details couldn&apos;t be loaded.</p>
                        )}
                        {ids(["Trip", id])}
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}
              <p className="mb-4">
                {adminStatus(selectedFlag.status)} · Pay held: {held(selectedFlag)}
              </p>
              {route && routePage ? (
                <>
                  <RecordedRouteMap points={route} />
                  {routePage.total > route.length ? (
                    <p className="text-muted my-3 text-sm">
                      Showing part of the recorded route. Open the next page for more location
                      records.
                    </p>
                  ) : null}
                  <Pagination
                    total={routePage.total}
                    limit={500}
                    offset={pageOffset(p.route_offset)}
                    hrefFor={(o) => href({ route_offset: String(o) })}
                  />
                </>
              ) : (
                <QueueUnavailable />
              )}
              <ReviewActions
                flagId={selectedFlag.id}
                status={selectedFlag.status}
                reversalRecommended={selectedFlag.money_effect.reversal_recommended}
                reversalRecorded={!!selectedFlag.money_effect.reversal_entry_id}
                reversalAmount={
                  selectedFlag.money_effect.currency
                    ? formatMoneyExact(
                        selectedFlag.money_effect.available_net,
                        selectedFlag.money_effect.currency,
                      )
                    : undefined
                }
              />
              {selectedFlag.status === "open" || selectedFlag.status === "acknowledged" ? (
                <details className="my-5">
                  <summary>Record an in-person check</summary>
                  <SpotCheckForm
                    trip={{
                      assignmentId: selectedFlag.assignment_id,
                      tripSessionId: selectedFlag.trip_session_id,
                    }}
                  />
                </details>
              ) : null}
              {!disputes ? (
                <QueueUnavailable />
              ) : disputePage && disputePage.total ? (
                <section aria-label="Driver dispute" className="mt-5">
                  <Pagination
                    total={disputePage?.total ?? 0}
                    limit={25}
                    offset={pageOffset(p.disputes_offset)}
                    hrefFor={(o) => href({ disputes_offset: String(o) })}
                  />
                  {!disputes.length ? <p>No disputes on this page.</p> : null}
                  {disputes.map((dispute) => (
                    <div key={dispute.id}>
                      <p>{dispute.message}</p>
                      {dispute.reply ? (
                        <p className="mt-3">Reply: {dispute.reply}</p>
                      ) : (
                        <DisputeReplyActions disputeId={dispute.id} />
                      )}
                    </div>
                  ))}
                </section>
              ) : (
                <p className="text-muted mt-5">The driver hasn&apos;t disputed this.</p>
              )}
              {ids(
                ["Trip", selectedFlag.trip_session_id],
                ["Review", selectedFlag.id],
                ["Job", selectedFlag.assignment_id],
                ["Check", evidenceVerificationId(selectedFlag.evidence)],
              )}
            </>
          )}
        </HubDrawer>
      ) : null}
      {p.late && tab === "late" ? (
        <HubDrawer title="Late upload" closeHref={closeHref}>
          {!allLate ? (
            <QueueUnavailable />
          ) : !selectedLate || (selectedContext && !selectedInScope) ? (
            <p>Late upload not found for these filters.</p>
          ) : !selectedContext || failed ? (
            <QueueUnavailable />
          ) : (
            <>
              {line(selectedLate.trip_session_id)}
              <p className="mt-3">
                {adminStatus(selectedLate.status)} · received {formatDate(selectedLate.received_at)}
              </p>
              {selectedLate.status === "quarantined" ? (
                <OperationForm id={selectedLate.id} trip={selectedLate.trip_session_id} />
              ) : (
                <p className="mt-4">{selectedLate.resolution_note}</p>
              )}
              {ids(["Trip", selectedLate.trip_session_id], ["Upload", selectedLate.id])}
            </>
          )}
        </HubDrawer>
      ) : null}
      {p.check && tab === "in-person" ? (
        <HubDrawer title="In-person check" closeHref={closeHref}>
          {!selectedChecks ? (
            <QueueUnavailable />
          ) : !selectedCheck ? (
            <p>In-person check not found for these filters.</p>
          ) : !selectedInScope || failed ? (
            <QueueUnavailable />
          ) : (
            <>
              {line(selectedCheck.source_trip_session_id)}
              <p className="mt-3">
                {adminStatus(selectedCheck.status)} · {selectedCheck.result_note}
              </p>
              {ids(["Trip", selectedCheck.source_trip_session_id], ["Check", selectedCheck.id])}
            </>
          )}
        </HubDrawer>
      ) : null}
    </div>
  );
}
