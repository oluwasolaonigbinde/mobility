import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { QueueSearch, QueueUnavailable } from "../queue-search";
import { IssueMeasurementForm } from "./issue-form";
export default async function MeasurementQueue({
  searchParams,
}: {
  searchParams: Promise<{ offset?: string; q?: string }>;
}) {
  const p = await searchParams;
  const offset = Math.max(0, Math.floor(Number(p.offset) || 0));
  const { data } = await createApiClient(await getSessionToken())
    .GET("/api/v1/admin/measurement-runs", { params: { query: { limit: 25, offset, q: p.q } } })
    .catch(() => ({ data: undefined }));
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Campaign Performance Analysis" eyebrow="Measurement and report work" />
      <p className="text-muted mb-5">
        Verified operations and estimated advertising results remain distinct. Missing or gated data
        is not a zero result.
      </p>
      <QueueSearch q={p.q} />
      <IssueMeasurementForm />
      {!data ? (
        <QueueUnavailable />
      ) : data.items.length === 0 ? (
        <p>
          No matching measurement runs. Prepare a run when its source evidence and reporting
          approvals are available.
        </p>
      ) : (
        <div className="grid gap-3">
          {data.items.map((r) => (
            <Link
              key={r.id}
              href={`/admin/measurement/${r.id}${r.report_issuance_id ? `?report=${r.report_issuance_id}` : ""}`}
              className="border-edge rounded-xl border p-4"
            >
              <h2 className="font-medium">{r.campaign_name}</h2>
              <p>
                {formatDate(r.period_start_at)} – {formatDate(r.period_end_at)} · Recorded{" "}
                {formatDate(r.created_at)}
              </p>
              <p className="text-muted text-sm">
                {r.test_only ? "Synthetic test · " : ""}
                {!r.reproducible
                  ? "Reproduction mismatch — do not issue"
                  : r.superseded
                    ? "Superseded snapshot"
                    : "Reproducible snapshot"}{" "}
                · Downloads: {r.report_status ?? "Not requested"}
              </p>
            </Link>
          ))}
        </div>
      )}
      {data ? (
        <Pagination
          total={data.total}
          limit={25}
          offset={offset}
          hrefFor={(o) =>
            `/admin/measurement?${new URLSearchParams({ q: p.q ?? "", offset: String(o) })}`
          }
        />
      ) : null}
    </div>
  );
}
