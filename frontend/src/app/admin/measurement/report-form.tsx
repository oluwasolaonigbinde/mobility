"use client";
import { useActionState, useEffect, useState } from "react";
import { manageReport, type ReportState } from "./actions";
import { formatDate } from "@/lib/format";

const reportStatus: Record<string, string> = {
  queued: "Being prepared",
  processing: "Being prepared",
  ready: "Ready",
  failed: "Failed",
};

function TemporaryDownload({ download }: { download: NonNullable<ReportState["download"]> }) {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const timer = setTimeout(() => setVisible(false), 60000);
    return () => clearTimeout(timer);
  }, []);
  return visible ? (
    <a href={download.url} rel="noreferrer" onClick={() => setVisible(false)}>
      Download {download.filename}
    </a>
  ) : null;
}

export function ReportForm({
  runId,
  initialReport,
  canIssue,
}: {
  runId: string;
  initialReport?: ReportState["report"];
  canIssue: boolean;
}) {
  const [request] = useState(() => crypto.randomUUID());
  const [state, action, pending] = useActionState(manageReport, { report: initialReport });
  const report = state.report ?? initialReport;
  return (
    <section className="border-edge my-6 rounded-xl border p-4">
      <h2 className="font-medium">Report and downloads</h2>
      <p className="text-muted text-sm">
        {report
          ? `${reportStatus[report.status] ?? "Being prepared"} · Requested ${formatDate(report.created_at)}`
          : "Prepare a report to download these results."}
      </p>
      {report?.error_code ? (
        <p role="alert">The report couldn’t be prepared. Try again or contact support.</p>
      ) : null}
      <form action={action} className="mt-3 grid gap-3">
        <input type="hidden" name="run" value={runId} />
        <input type="hidden" name="request" value={request} />
        <input type="hidden" name="issuance" value={report?.id ?? ""} />
        {report ? (
          <button
            name="command"
            value="refresh"
            disabled={pending}
            className="border-edge rounded border p-2"
          >
            Refresh report status
          </button>
        ) : (
          <button
            name="command"
            value="issue"
            disabled={pending || !canIssue}
            className="bg-amber text-bg rounded p-2"
          >
            Prepare report files
          </button>
        )}
        {report?.status === "ready" ? (
          <>
            <label>
              Reason for report access
              <input
                name="reason"
                minLength={10}
                maxLength={500}
                className="border-edge bg-raised block w-full rounded border p-2"
              />
            </label>
            <div className="flex flex-wrap gap-2">
              {report.artifacts.map((a) => (
                <button
                  key={a.format}
                  name="command"
                  value={a.format}
                  disabled={pending}
                  className="border-edge rounded border p-2"
                >
                  Authorize {a.format.toUpperCase()} download
                </button>
              ))}
            </div>
          </>
        ) : null}
        {state.error ? <p role="alert">{state.error}</p> : null}
        {state.download ? (
          <TemporaryDownload key={state.download.url} download={state.download} />
        ) : null}
      </form>
      <p className="text-muted mt-3 text-sm">
        Preparation uses the existing approved reporting method. Downloads remain subject to current
        access, privacy, and checks before a report can be issued.
      </p>
    </section>
  );
}
