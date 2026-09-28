import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { createApiClient } from "@/lib/api/client";
import { requireRole } from "@/lib/auth/current-user";
import { getSessionToken } from "@/lib/auth/session";
import { formatMoneyExact } from "@/lib/format";
import {
  alertDetail,
  alertLabel,
  formatWat,
  manualReasonLabel,
  missingSettingLabel,
  outcomeText,
  reconciliationDay,
  type AutomaticAlert,
  type AutomaticReconciliation,
  type AutomaticStatus,
} from "@/lib/payouts/automatic";
import { PauseSwitchForm, ReleaseUnsentForm, ResolveAlertForm } from "./controls";

export const metadata: Metadata = { title: "Automatic payouts" };

async function settle<T>(read: Promise<{ data?: T }>): Promise<T | null> {
  try {
    return (await read).data ?? null;
  } catch {
    return null;
  }
}

function StatusPanel({ status }: { status: AutomaticStatus }) {
  const notSetUp = status.missing_settings.length > 0;
  return (
    <Panel className="space-y-3 p-4 sm:p-6">
      <h2 className="font-display text-xl">Status</h2>
      {notSetUp ? (
        <div className="space-y-1">
          <p className="font-medium">Not set up yet — nothing is paid automatically.</p>
          <ul className="text-muted list-disc pl-5 text-sm">
            {status.missing_settings.map((name) => (
              <li key={name}>{missingSettingLabel(name)}</li>
            ))}
          </ul>
        </div>
      ) : status.paused ? (
        <p className="font-medium">Paused — Cardvert is not sending automatic payouts.</p>
      ) : status.runnable ? (
        <p className="font-medium">Running — Cardvert pays clean daily-rate earnings.</p>
      ) : (
        <p className="font-medium">Set up, but not running yet.</p>
      )}
      {!status.provider_ready ? (
        <p className="text-muted text-sm">
          No payment provider is connected yet, so no money can be sent.
        </p>
      ) : null}
      {!status.identity_ready ? (
        <p className="text-coral text-sm">
          The Cardvert payout identity is missing or was changed. Automatic payouts stay stopped
          until it is restored.
        </p>
      ) : null}
      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-muted">How often</dt>
          <dd>
            {status.frequency ? (status.frequency === "daily" ? "Daily" : "Weekly") : "Not set"}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Most one run may pay</dt>
          <dd>
            {status.batch_limit ? formatMoneyExact(status.batch_limit, status.currency) : "Not set"}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Last run</dt>
          <dd>
            {status.last_run
              ? `${formatWat(status.last_run.created_at)} (WAT) · ${status.last_run.line_count} payments · ${formatMoneyExact(status.last_run.total_amount, status.currency)}`
              : "No run yet"}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Waiting to send</dt>
          <dd>{status.unsent_count}</dd>
        </div>
      </dl>
      {status.paused ? (
        <p className="text-sm">
          Paused by Terrax Media ({status.pause_changed_by_name ?? "unknown"}) on{" "}
          {formatWat(status.pause_changed_at)} (WAT): “{status.pause_reason}”
        </p>
      ) : null}
      <p className="text-muted text-sm">
        Only clean daily-rate earnings are paid automatically: no review hold, flag or open dispute,
        a verified bank account, and never more than one day&apos;s rate per driver per day across
        campaigns. Everything else stays on{" "}
        <Link className="underline" href="/admin/payouts/batches">
          payout batches
        </Link>{" "}
        for a person to prepare and approve.
      </p>
      <PauseSwitchForm paused={status.paused} />
      {(status.paused || notSetUp) && status.unsent_count > 0 ? (
        <ReleaseUnsentForm count={status.unsent_count} />
      ) : null}
    </Panel>
  );
}

function AlertsPanel({ alerts }: { alerts: AutomaticAlert[] | null }) {
  return (
    <Panel className="space-y-3 p-4 sm:p-6">
      <h2 className="font-display text-xl">Problems to follow up</h2>
      {alerts === null ? (
        <p className="text-coral text-sm">Couldn&apos;t load problems. Refresh to try again.</p>
      ) : alerts.length === 0 ? (
        <p className="text-muted text-sm">Nothing to follow up.</p>
      ) : (
        <ul className="space-y-4">
          {alerts.map((alert) => {
            const detail = alertDetail(alert);
            return (
              <li key={alert.id} className="border-edge space-y-1 rounded-xl border p-4">
                <p className="font-medium">{alertLabel(alert.kind)}</p>
                <p className="text-muted text-sm">
                  Raised by Cardvert {formatWat(alert.created_at)} (WAT)
                  {alert.driver_name ? ` · ${alert.driver_name}` : ""}
                  {alert.lagos_day ? ` · day ${alert.lagos_day} (WAT)` : ""}
                  {alert.amount
                    ? ` · ${formatMoneyExact(alert.amount, alert.currency ?? "NGN")}`
                    : ""}
                </p>
                {detail ? <p className="text-sm">{detail}</p> : null}
                {alert.batch_id ? (
                  <Link
                    className="text-sm underline"
                    href={`/admin/payouts/batches/${alert.batch_id}`}
                  >
                    Open the payout batch
                  </Link>
                ) : null}
                <ResolveAlertForm alertId={alert.id} />
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

function ReconciliationPanel({ day, data }: { day: string; data: AutomaticReconciliation | null }) {
  return (
    <Panel className="space-y-4 p-4 sm:p-6">
      <h2 className="font-display text-xl">Daily reconciliation</h2>
      <form className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="block">Day, Nigeria time (WAT)</span>
          <input
            type="date"
            name="day"
            defaultValue={day}
            className="border-edge bg-raised rounded-lg border px-3 py-2"
          />
        </label>
        <button className="border-edge rounded-lg border px-4 py-2 text-sm">Show day</button>
      </form>
      {data === null ? (
        <p className="text-coral text-sm">Couldn&apos;t load this day. Refresh to try again.</p>
      ) : data.runs.length === 0 && data.total === 0 ? (
        <p className="text-muted text-sm">No automatic payouts ran on this day.</p>
      ) : (
        <>
          <section aria-label="Payments by result" className="grid gap-2 sm:grid-cols-3">
            {data.outcomes.map((row) => (
              <div key={row.outcome} className="border-edge rounded-lg border p-3 text-sm">
                <p className="text-muted">{outcomeText(row.outcome)}</p>
                <p className="font-medium">
                  {row.count} · {formatMoneyExact(row.amount)}
                </p>
              </div>
            ))}
          </section>
          <p className="text-sm">
            Still waiting for the bank&apos;s answer (all days): {data.awaiting_provider_count}
          </p>
          {data.provider_evidence.length ? (
            <p className="text-sm">
              Bank answers recorded:{" "}
              {data.provider_evidence
                .map(
                  (row) =>
                    `${outcomeText(row.outcome)} ${row.count}${row.applied ? "" : " (no change)"}`,
                )
                .join(" · ")}
            </p>
          ) : null}
          {data.kept_for_manual_review.length ? (
            <div className="text-sm">
              <p className="font-medium">Kept for a person to pay</p>
              <ul className="text-muted list-disc pl-5">
                {data.kept_for_manual_review.map((row) => (
                  <li key={row.reason}>
                    {manualReasonLabel(row.reason)}: {row.count} · {formatMoneyExact(row.amount)}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead>
                <tr className="text-muted border-edge border-b text-left">
                  <th className="py-2 font-normal">Driver</th>
                  <th className="py-2 text-right font-normal">Amount</th>
                  <th className="py-2 font-normal">Result</th>
                  <th className="py-2 font-normal">Last bank answer (WAT)</th>
                </tr>
              </thead>
              <tbody>
                {data.lines.map((line) => (
                  <tr key={line.id} className="border-edge/60 border-b last:border-0">
                    <td className="py-2">
                      <Link className="underline" href={`/admin/payouts/batches/${line.batch_id}`}>
                        {line.driver_name}
                      </Link>
                    </td>
                    <td className="py-2 text-right">
                      {formatMoneyExact(line.amount, line.currency)}
                    </td>
                    <td className="py-2">{outcomeText(line.outcome)}</td>
                    <td className="py-2">{formatWat(line.last_provider_evidence_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-muted text-xs">{data.total} automatic payments started this day.</p>
        </>
      )}
    </Panel>
  );
}

export default async function AutomaticPayoutsPage({
  searchParams,
}: {
  searchParams: Promise<{ day?: string }>;
}) {
  await requireRole("admin");
  const day = reconciliationDay((await searchParams).day);
  const api = createApiClient(await getSessionToken());
  const [status, alerts, reconciliation] = await Promise.all([
    settle(api.GET("/api/v1/admin/payouts/automatic/status")),
    settle(
      api.GET("/api/v1/admin/payouts/automatic/alerts", {
        params: { query: { alert_status: "open", limit: 50 } },
      }),
    ),
    settle(
      api.GET("/api/v1/admin/payouts/automatic/reconciliation", {
        params: { query: { day, limit: 100 } },
      }),
    ),
  ]);
  return (
    <div className="animate-rise mx-auto max-w-5xl space-y-6 pb-16">
      <nav aria-label="Breadcrumb" className="micro text-muted">
        <Link href="/admin/payouts">Payouts</Link> / Automatic payouts
      </nav>
      <PageHeader
        title="Automatic payouts"
        eyebrow="Cardvert pays clean driver earnings; Finance monitors, reconciles and follows up"
      />
      {status ? (
        <StatusPanel status={status} />
      ) : (
        <Panel className="p-4 sm:p-6">
          <p className="text-coral text-sm">Couldn&apos;t load the status. Refresh to try again.</p>
        </Panel>
      )}
      <AlertsPanel alerts={alerts ? alerts.items : null} />
      <ReconciliationPanel day={day} data={reconciliation} />
    </div>
  );
}
