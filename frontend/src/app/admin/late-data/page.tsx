import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { QueueUnavailable } from "../queue-search";
import { OperationForm } from "../operation-form";
export default async function LateDataQueue({
  searchParams,
}: {
  searchParams: Promise<{ offset?: string; status?: string }>;
}) {
  const p = await searchParams;
  const offset = Math.max(0, Math.floor(Number(p.offset) || 0));
  const status = ["quarantined", "applied", "discarded"].includes(p.status ?? "")
    ? p.status!
    : "quarantined";
  const { data } = await createApiClient(await getSessionToken())
    .GET("/api/v1/admin/trips/quarantined-batches", {
      params: { query: { limit: 25, offset, status } },
    })
    .catch(() => ({ data: undefined }));
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="Late trip evidence" eyebrow="Quarantined batches" />
      <p className="text-muted mb-5">
        Review evidence received after a trip was sealed. Applying it never reprices earnings or
        edits an issued report. Any later financial correction or report reissue follows its
        separate approval workflow.
      </p>
      <form className="mb-5 flex flex-wrap gap-3">
        <label>
          Status{" "}
          <select
            name="status"
            defaultValue={status}
            className="border-edge bg-raised rounded border p-2"
          >
            <option value="quarantined">Pending review</option>
            <option value="applied">Applied history</option>
            <option value="discarded">Discarded history</option>
          </select>
        </label>
        <button className="text-cyan">Apply filter</button>
      </form>
      {!data ? (
        <QueueUnavailable />
      ) : !data.items.length ? (
        <p>No {status} late-data batches.</p>
      ) : (
        <div className="grid gap-4">
          {data.items.map((b) => (
            <section key={b.id} className="border-edge rounded-xl border p-4">
              <h2 className="font-medium">
                {b.campaign_name ?? "Campaign unavailable"} ·{" "}
                {b.driver_name ?? "Driver unavailable"}
              </h2>
              <p>
                {b.vehicle_plate ?? "Vehicle unavailable"} · {b.ping_count} samples · Received{" "}
                {formatDate(b.received_at)}
              </p>
              <p className="text-muted text-sm">
                {b.status} · Trip reference {b.trip_session_id.slice(0, 8)}
              </p>
              {b.resolution_note ? <p>{b.resolution_note}</p> : null}
              {b.status === "quarantined" ? (
                <OperationForm id={b.id} trip={b.trip_session_id} />
              ) : (
                <p>Reviewed {b.resolved_at ? formatDate(b.resolved_at) : "date unavailable"}</p>
              )}
            </section>
          ))}
        </div>
      )}
      {data ? (
        <Pagination
          total={data.total}
          limit={25}
          offset={offset}
          hrefFor={(o) => `/admin/late-data?status=${status}&offset=${o}`}
        />
      ) : null}
    </div>
  );
}
