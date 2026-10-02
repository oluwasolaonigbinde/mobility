import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { QueueUnavailable } from "../../queue-search";
import { ReportForm } from "../report-form";

export default async function MeasurementDetail({
  params,
  searchParams,
}: {
  params: Promise<{ runId: string }>;
  searchParams: Promise<{ report?: string }>;
}) {
  const { runId } = await params;
  const { data } = await createApiClient(await getSessionToken())
    .GET("/api/v1/admin/measurement-runs/{run_id}", { params: { path: { run_id: runId } } })
    .catch(() => ({ data: undefined }));
  if (!data) return <QueueUnavailable />;
  const reportId = (await searchParams).report;
  const { data: report } = reportId
    ? await createApiClient(await getSessionToken())
        .GET("/api/v1/admin/report-issuances/{issuance_id}", {
          params: { path: { issuance_id: reportId } },
        })
        .catch(() => ({ data: undefined }))
    : { data: undefined };
  if (reportId && !report) return <QueueUnavailable />;
  const metrics = Array.isArray(data.result_manifest.metrics)
    ? (data.result_manifest.metrics as {
        id?: string;
        label?: string;
        class?: string;
        value?: string | null;
        completeness?: {
          complete?: boolean;
          suppressed?: boolean;
          covered_trip_count?: number;
          denominator_trip_count?: number;
        };
      }[])
    : [];
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="Campaign results"
        eyebrow={`${formatDate(data.period_start_at)} – ${formatDate(data.period_end_at)}`}
      />
      <p className={data.reproducible ? "text-green" : "text-coral"}>
        {data.reproducible
          ? "The saved results can be reproduced."
          : "The results could not be reproduced. Do not use them or issue a report."}
      </p>
      <p className="text-muted my-4">
        {data.test_only ? "Synthetic test evidence. " : ""}Reproducing the results does not prove
        that all source records are complete or give permission to publish a live report.
      </p>
      <div className="grid gap-3">
        {metrics.map((m, i) => (
          <section className="border-edge rounded-xl border p-4" key={m.id ?? i}>
            <h2 className="font-medium">{m.label ?? "Measure"}</h2>
            <p className="text-muted">
              {m.class === "modelled_measure"
                ? "Estimated advertising result"
                : "Recorded operational or financial facts"}
            </p>
            <p>{m.value ?? "See the saved results; this measure has no single total."}</p>
            <p className="text-muted text-sm">
              {m.completeness?.suppressed
                ? "Hidden: too few shareable records"
                : m.completeness?.complete === true
                  ? "Complete for this saved group"
                  : "Records are incomplete"}
            </p>
            {m.completeness?.denominator_trip_count != null ? (
              <p className="text-muted text-sm">
                {m.completeness.covered_trip_count ?? "Unknown"} of{" "}
                {m.completeness.denominator_trip_count} trips covered
              </p>
            ) : null}
          </section>
        ))}
      </div>
      <details className="mt-5">
        <summary>Method and saved results</summary>
        <p>
          Method {data.method_revision} · Formula {data.formula_version}
        </p>
        <pre className="border-edge mt-3 max-h-96 overflow-auto rounded border p-3 text-xs whitespace-pre-wrap">
          {JSON.stringify(data.result_manifest, null, 2)}
        </pre>
      </details>
      {reportId && (!report || report.measurement_run_id !== runId) ? (
        <p role="alert">
          The selected report belongs to a different results calculation. Return to the work list
          and select the current report.
        </p>
      ) : (
        <ReportForm runId={runId} canIssue={data.reproducible} initialReport={report} />
      )}
    </div>
  );
}
