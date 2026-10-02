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
import { readableEvidence } from "../fraud/evidence";
import { HubDrawer } from "../hub-drawer";
import { QueueUnavailable } from "../queue-search";
import { OperationForm } from "../operation-form";
import { completePages, worklistHref } from "../worklist-reads";
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
};
export default async function TripChecks({ searchParams }: { searchParams: Promise<Query> }) {
  const p = await searchParams;
  const tab = p.tab === "late" || p.tab === "in-person" ? p.tab : "suspicious";
  const offset = Number.isFinite(Number(p.offset)) ? Math.max(0, Math.floor(Number(p.offset))) : 0;
  const api = createApiClient(await getSessionToken());
  const href = (changes: Partial<Query>) =>
    worklistHref("/admin/trip-checks", { ...p, tab }, changes);
  const closeHref = href({ flag: undefined, late: undefined, check: undefined });
  const flagStatus = (["open", "acknowledged", "confirmed", "dismissed"] as const).find(
    (value) => value === p.status,
  );
  const lateStatus = ["quarantined", "applied", "discarded"].includes(p.status ?? "")
    ? p.status
    : "quarantined";
  const flagRead = (next: number, limit = 25) =>
    api.GET("/api/v1/admin/fraud-flags", {
      params: {
        query: {
          limit,
          offset: next,
          status: flagStatus,
          driver_profile_id: p.driver_profile_id,
          campaign_id: p.campaign_id,
        },
      },
    });
  const lateRead = (next: number, limit = 25) =>
    api.GET("/api/v1/admin/trips/quarantined-batches", {
      params: { query: { limit, offset: next, status: lateStatus } },
    });
  const checkRead = (next: number, limit = 25) =>
    api.GET("/api/v1/admin/evidence-verifications", {
      params: {
        query: { limit, offset: next, status: "pending", verification_type: "physical_spot_check" },
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
  const checks =
    tab === "in-person"
      ? await completePages((next) => checkRead(next, 100))
          .then((items) =>
            items.filter(
              (item) =>
                (!p.driver_profile_id || item.driver_profile_id === p.driver_profile_id) &&
                (!p.campaign_id || item.campaign_id === p.campaign_id),
            ),
          )
          .catch(() => undefined)
      : undefined;
  const allFlags =
    tab === "suspicious" && p.flag
      ? await completePages((next) => flagRead(next, 100)).catch(() => undefined)
      : undefined;
  const allLate =
    tab === "late" && (p.late || p.driver_profile_id || p.campaign_id)
      ? await completePages((next) => lateRead(next, 100)).catch(() => undefined)
      : undefined;
  const selectedFlag = allFlags?.find((item) => item.id === p.flag);
  const selectedLate = allLate?.find((item) => item.id === p.late);
  const selectedCheck = checks?.find((item) => item.id === p.check);
  const contexts = new Map<string, Awaited<ReturnType<typeof readTripContext>>>();
  const contextFailures = new Set<string>();
  const visibleChecks = checks?.slice(offset, offset + 25);
  const tripIds = new Set([
    ...(flags?.items ?? []).map((item) => item.trip_session_id),
    ...(allLate ?? late?.items ?? []).map((item) => item.trip_session_id),
    ...(visibleChecks ?? []).map((item) => item.source_trip_session_id),
    ...[
      selectedFlag?.trip_session_id,
      selectedLate?.trip_session_id,
      selectedCheck?.source_trip_session_id,
    ].filter((id): id is string => !!id),
  ]);
  const ids = [...tripIds];
  for (let index = 0; index < ids.length; index += 4)
    await Promise.all(
      ids.slice(index, index + 4).map(async (id) => {
        try {
          contexts.set(id, await readTripContext(api, id));
        } catch {
          contextFailures.add(id);
        }
      }),
    );
  let failed = contextFailures.size > 0;
  const scopedLate = (allLate ?? late?.items)?.filter((item) => {
    const context = contexts.get(item.trip_session_id);
    return (
      context &&
      (!p.driver_profile_id || context.analytics.driver_profile_id === p.driver_profile_id) &&
      (!p.campaign_id || context.analytics.campaign_id === p.campaign_id)
    );
  });
  const visibleLate = allLate ? scopedLate?.slice(offset, offset + 25) : scopedLate;
  const selectedContext = contexts.get(
    selectedFlag?.trip_session_id ??
      selectedLate?.trip_session_id ??
      selectedCheck?.source_trip_session_id ??
      "",
  );
  const selectedInScope =
    selectedContext &&
    (!p.driver_profile_id || selectedContext.analytics.driver_profile_id === p.driver_profile_id) &&
    (!p.campaign_id || selectedContext.analytics.campaign_id === p.campaign_id);
  for (const item of [...(flags?.items ?? []), ...(selectedFlag ? [selectedFlag] : [])]) {
    const context = contexts.get(item.trip_session_id);
    if (
      context &&
      (context.analytics.driver_profile_id !== item.driver_profile_id ||
        context.analytics.campaign_id !== item.campaign_id ||
        context.analytics.assignment_id !== item.assignment_id)
    )
      failed = true;
  }
  for (const item of [...(visibleChecks ?? []), ...(selectedCheck ? [selectedCheck] : [])]) {
    const context = contexts.get(item.source_trip_session_id);
    if (
      context &&
      (context.analytics.driver_profile_id !== item.driver_profile_id ||
        context.analytics.campaign_id !== item.campaign_id ||
        context.analytics.assignment_id !== item.assignment_id)
    )
      failed = true;
  }
  const disputes = selectedFlag
    ? await completePages(async (next) => {
        const response = await api.GET("/api/v1/admin/fraud-disputes", {
          params: { query: { flag_id: [selectedFlag.id], limit: 100, offset: next } },
        });
        if (
          response.data?.items.some(
            (item) =>
              item.fraud_flag_id !== selectedFlag.id ||
              item.driver_profile_id !== selectedFlag.driver_profile_id,
          )
        )
          throw new Error("Dispute identity mismatch");
        return response;
      }).catch(() => undefined)
    : undefined;
  const route =
    selectedFlag && selectedInScope && !failed
      ? await completePages(async (next) => {
          const response = await api.GET("/api/v1/admin/fraud-flags/{flag_id}/route", {
            params: { path: { flag_id: selectedFlag.id }, query: { limit: 500, offset: next } },
          });
          if (
            response.data &&
            (response.data.flag_id !== selectedFlag.id ||
              response.data.trip_session_id !== selectedFlag.trip_session_id)
          )
            throw new Error("Trip route identity mismatch");
          return response;
        }).catch(() => undefined)
      : undefined;
  const pendingChecks = selectedFlag
    ? await completePages((next) => checkRead(next, 100)).catch(() => undefined)
    : undefined;
  const pendingCheck = pendingChecks?.find(
    (item) => item.source_trip_session_id === selectedFlag?.trip_session_id,
  );
  const held = (flag: NonNullable<typeof selectedFlag>) =>
    flag.money_effect.held_currency
      ? formatMoneyExact(flag.money_effect.held_pending_net, flag.money_effect.held_currency)
      : "No pay held";
  const line = (tripId: string) => {
    const context = contexts.get(tripId)!;
    return (
      <>
        <p className="font-medium">
          {context.name} · {context.plate} · {context.campaign}
        </p>
        <p className="text-muted text-sm">Trip {formatDate(context.date)}</p>
      </>
    );
  };
  const total =
    tab === "suspicious"
      ? flags?.total
      : tab === "late"
        ? allLate
          ? scopedLate?.length
          : late?.total
        : checks?.length;
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
      {failed || total === undefined ? (
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
                        href={href({ flag: flag.id })}
                      >
                        {line(flag.trip_session_id)}
                        <p>{flag.description}</p>
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
                        href={href({ late: batch.id })}
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
                        href={href({ check: check.id })}
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
              <p className="my-4">{selectedFlag.description}</p>
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
              {route ? <RecordedRouteMap points={route} /> : <QueueUnavailable />}
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
              ) : disputes.length ? (
                <section aria-label="Driver dispute" className="mt-5">
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
          {!checks ? (
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
