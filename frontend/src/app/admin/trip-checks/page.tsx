export const metadata = { title: "Trip checks" };
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { formatDate, formatMoneyExact } from "@/lib/format";
import { adminStatus } from "@/lib/status/admin";
import { ReviewActions } from "../fraud/review-actions";
import { DisputeReplyActions } from "../fraud/dispute-actions";
import { SpotCheckQueueForm, SpotCheckResultForm } from "../fraud/spot-check-actions";
import { readableEvidence, tripReviewReason } from "../fraud/evidence";
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
          status: "pending",
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
      item.id === p.check &&
      scoped(item) &&
      item.status === "pending" &&
      item.verification_type === "physical_spot_check",
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
  const pendingChecks =
    selectedFlag && selectedInScope
      ? await checkRead(0, 1, undefined, selectedFlag.trip_session_id)
          .then(({ data }) => data?.items)
          .catch(() => undefined)
      : undefined;
  const pendingCheck = pendingChecks?.find(
    (item) => item.source_trip_session_id === selectedFlag?.trip_session_id,
  );
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
  const line = (tripId: string) => {
    const context = summaries.get(tripId);
    return context ? (
      <>
        <p className="font-medium">
          {context.name} · {context.plate} · {context.campaign}
        </p>
        <p className="text-muted text-sm">Trip {formatDate(context.date)}</p>
      </>
    ) : (
      <QueueUnavailable />
    );
  };
  const total =
    tab === "suspicious" ? flags?.total : tab === "late" ? late?.total : checkPage?.total;
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title="Trip checks" />
      <nav aria-label="Trip check lists" className="mb-5 flex flex-wrap gap-3">
        {[
          ["suspicious", "Suspicious trips"],
          ["late", "Late uploads"],
          ["in-person", "In-person checks"],
        ].map(([value, label]) => (
          <Link
            key={value}
            className="border-edge rounded-lg border p-2"
            href={href({
              tab: value,
              offset: undefined,
              status: undefined,
              flag: undefined,
              late: undefined,
              check: undefined,
              route_offset: undefined,
              disputes_offset: undefined,
            })}
          >
            {label}
          </Link>
        ))}
      </nav>
      {tab !== "in-person" ? (
        <nav aria-label="Status" className="mb-5 flex flex-wrap gap-3">
          {(tab === "suspicious"
            ? ["open", "acknowledged", "confirmed", "dismissed"]
            : ["quarantined", "applied", "discarded"]
          ).map((status) => (
            <Link
              key={status}
              className="text-cyan underline"
              href={href({ status, offset: undefined, flag: undefined, late: undefined })}
            >
              {adminStatus(status)}
            </Link>
          ))}
        </nav>
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
                        <p>{tripReviewReason(flag.flag_type, flag.evidence)}</p>
                        <p className="text-muted text-sm">
                          {adminStatus(flag.status)} · Pay held: {held(flag)}
                        </p>
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
                        <p>
                          Late upload · received {formatDate(batch.received_at)} ·{" "}
                          {batch.ping_count} location records
                        </p>
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
                        <p>In-person check · requested {formatDate(check.issued_at)}</p>
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
              <ul aria-label="Detection evidence" className="mb-4 text-sm">
                {readableEvidence(selectedFlag.evidence).map((text) => (
                  <li key={text}>{text}</li>
                ))}
              </ul>
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
              />
              {selectedFlag.status === "open" || selectedFlag.status === "acknowledged" ? (
                !pendingChecks ? (
                  <QueueUnavailable />
                ) : pendingCheck ? (
                  <Link
                    className="text-cyan my-5 block underline"
                    href={href({ tab: "in-person", flag: undefined, check: pendingCheck.id })}
                  >
                    In-person check waiting — record the result
                  </Link>
                ) : (
                  <details className="my-5">
                    <summary>Ask for an in-person check</summary>
                    <SpotCheckQueueForm
                      trip={{
                        assignmentId: selectedFlag.assignment_id,
                        tripSessionId: selectedFlag.trip_session_id,
                      }}
                    />
                  </details>
                )
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
                <p className="text-muted mt-5">No driver dispute.</p>
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
              <SpotCheckResultForm verificationId={selectedCheck.id} />
            </>
          )}
        </HubDrawer>
      ) : null}
    </div>
  );
}
