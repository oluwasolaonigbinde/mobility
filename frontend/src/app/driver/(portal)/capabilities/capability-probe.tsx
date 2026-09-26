"use client";

import { R14A_CONTRACT_VERSION } from "@/lib/pwa/capability-contract";
import { useCapabilityProbes, type Probe } from "./use-capability-probes";

/** Support-only R14-A probe (D38(b)): codes, statuses and the raw redacted report. */
export function CapabilityProbe() {
  const {
    passiveReady,
    busy,
    notice,
    assessment,
    report,
    probeQueue,
    probeLocks,
    probeWake,
    probeLocation,
    probeSession,
  } = useCapabilityProbes();

  if (!passiveReady) return <p role="status">Observing passive PWA capabilities…</p>;
  const buttons: Array<[Probe, string, () => void]> = [
    ["queue", "Test storage + queue", probeQueue],
    ["locks", "Test Web Locks", probeLocks],
    ["wake", "Test screen wake lock", probeWake],
    ["session", "Test BFF session", probeSession],
    ["location", "Test foreground location", probeLocation],
  ];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="micro text-amber">R14-A · contract {R14A_CONTRACT_VERSION}</p>
        <h1 className="mt-1 text-2xl font-semibold">Production PWA capability probe</h1>
        <p className="text-muted mt-2 text-sm leading-6">
          Probe-only: no trip mutation, ping upload, or location request before its button.
        </p>
      </div>

      <section className="rounded border p-4">
        <p className="micro text-muted">
          Readiness (probe evidence — no lock is held, no trip is active)
        </p>
        <p className="mt-2 text-lg font-semibold">Health: {assessment.health}</p>
        <p className="text-muted mt-1 text-sm">
          Start {assessment.actions.start ? "allowed" : "blocked"} · capture{" "}
          {assessment.actions.capture ? "allowed" : "paused"} · End{" "}
          {assessment.actions.end ? "allowed" : "blocked"}
        </p>
      </section>

      <div className="grid grid-cols-2 gap-2">
        {buttons.map(([name, label, action]) => (
          <button
            key={name}
            type="button"
            onClick={action}
            disabled={busy !== null}
            className="rounded border p-3 text-sm disabled:opacity-50"
          >
            {busy === name ? "Test…" : label}
          </button>
        ))}
      </div>
      <p role="status" className="text-muted text-sm">
        {notice}
      </p>

      <section aria-label="Capability decisions" className="flex flex-col gap-2">
        {assessment.results.map((item) => (
          <article
            key={item.id}
            data-testid={`capability-${item.id}`}
            data-status={item.status}
            className="rounded border p-3"
          >
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-medium">{item.label}</p>
              <code className="text-faint text-[10px]">{item.status}</code>
            </div>
            <p className="text-amber mt-1 font-mono text-[11px]">{item.code}</p>
            <p className="text-muted mt-1 text-xs leading-5">{item.summary}</p>
          </article>
        ))}
      </section>

      <section className="rounded border p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="micro text-muted">Redacted report</p>
          <button
            type="button"
            className="text-amber text-xs"
            onClick={() => void navigator.clipboard?.writeText(report)}
          >
            Copy
          </button>
        </div>
        <pre
          data-testid="capability-report"
          className="mt-3 max-h-96 overflow-auto text-[10px] leading-4 whitespace-pre-wrap"
        >
          {report}
        </pre>
      </section>

      <p className="rounded border p-3 text-xs leading-5">
        Automated build evidence exercises this contract. Physical Android/iPhone journeys, route
        accuracy and battery measurements are still required post-build before real pilot use; this
        probe does not claim they ran.
      </p>
    </div>
  );
}
