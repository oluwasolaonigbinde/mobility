"use client";
import { useActionState, useRef } from "react";
import { rerunReportAction, type RerunState } from "./actions";
import { ReportForm } from "./report-form";

export function RerunReportForm({ campaignId }: { campaignId: string }) {
  const sending = useRef(false);
  const [state, action, pending] = useActionState(async (previous: RerunState) => {
    try {
      return await rerunReportAction(campaignId, previous);
    } catch {
      return { unknownOutcome: true };
    } finally {
      sending.current = false;
    }
  }, {} as RerunState);
  return (
    <section className="border-edge mb-6 rounded-xl border p-4">
      <h2 className="font-medium">Campaign results</h2>
      <p className="text-muted mt-2 text-sm">
        Reports are prepared each week and when a campaign ends. You can also create a fresh report.
      </p>
      <form
        action={action}
        onSubmit={(event) => {
          if (sending.current) event.preventDefault();
          else sending.current = true;
        }}
        className="mt-4"
      >
        <button
          type="submit"
          disabled={pending}
          className="bg-amber text-bg rounded px-4 py-3 text-sm"
        >
          {pending
            ? "Requesting report…"
            : state.report || state.unknownOutcome
              ? "Create another results report"
              : "Create results report"}
        </button>
      </form>
      {state.error ? (
        <p role="alert" className="text-coral mt-3 text-sm">
          {state.error}
        </p>
      ) : null}
      {state.unknownOutcome ? (
        <p role="alert" className="text-muted mt-3 text-sm">
          We couldn’t confirm whether the report was requested.{" "}
          {/* A full load, so results requested before the lost response are shown. */}
          <a className="text-green underline" href={`/admin/campaigns/${campaignId}#results`}>
            Check the campaign’s results
          </a>{" "}
          before creating another.
        </p>
      ) : null}
      {state.report ? (
        <>
          <p role="status" className="mt-3 text-sm">
            Report requested.
          </p>
          <ReportForm
            key={state.report.id}
            runId={state.report.measurement_run_id}
            initialReport={state.report}
            canIssue={false}
          />
        </>
      ) : null}
    </section>
  );
}
