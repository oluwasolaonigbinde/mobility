import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate, formatDateTime, formatMoneyExact } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { Pagination } from "@/components/ui/pagination";
import { cx } from "@/lib/cx";
import type { components } from "@/lib/api/schema";
import { ReviewActions } from "./review-actions";
import { DisputeReplyActions } from "./dispute-actions";
import { SpotCheckQueueForm, SpotCheckResultForm } from "./spot-check-actions";
import { readableEvidence } from "./evidence";

export const metadata: Metadata = { title: "Fraud" };

const PAGE_SIZE = 25;
type FStatus = components["schemas"]["FraudFlagStatus"];
type FSeverity = components["schemas"]["FraudFlagSeverity"];

const STATUSES: FStatus[] = ["open", "acknowledged", "confirmed", "dismissed"];
const sevTone: Record<FSeverity, "coral" | "amber" | "default"> = {
  high: "coral",
  medium: "amber",
  low: "default",
};

const typeLabel: Record<string, string> = {
  insufficient_pings: "Insufficient pings",
  impossible_speed: "Impossible speed",
  poor_accuracy: "Poor accuracy",
  stationary_trip: "Stationary trip",
  excessive_ping_gap: "Ping gap",
  future_timestamp: "Future timestamp",
  route_looping: "Route looping",
  route_replay: "Route replay",
  exclusion_zone_presence: "Exclusion zone",
  missed_display_challenge: "Missed display challenge",
  concurrent_session_day: "Concurrent sessions",
  physical_spot_check_failed: "Failed physical spot check",
};

function href(params: { status?: string; offset?: number }): string {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.offset) qs.set("offset", String(params.offset));
  const s = qs.toString();
  return s ? `/admin/fraud?${s}` : "/admin/fraud";
}

export default async function AdminFraudPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; offset?: string }>;
}) {
  const params = await searchParams;
  const status = STATUSES.includes(params.status as FStatus)
    ? (params.status as FStatus)
    : undefined;
  const rawOffset = Number(params.offset ?? 0);
  const offset = Number.isFinite(rawOffset) && rawOffset > 0 ? Math.floor(rawOffset) : 0;

  const api = createApiClient(await getSessionToken());
  const [{ data }, { data: verificationData }] = await Promise.all([
    api.GET("/api/v1/admin/fraud-flags", {
      params: { query: { limit: PAGE_SIZE, offset, ...(status ? { status } : {}) } },
    }),
    api.GET("/api/v1/admin/evidence-verifications", {
      params: { query: { status: "pending", verification_type: "physical_spot_check" } },
    }),
  ]);
  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const disputeResponse =
    items.length > 0
      ? await api.GET("/api/v1/admin/fraud-disputes", {
          params: {
            query: { flag_id: items.map((flag) => flag.id), limit: PAGE_SIZE, offset: 0 },
          },
        })
      : undefined;
  const disputeByFlagId = new Map(
    (disputeResponse?.data?.items ?? []).map((dispute) => [dispute.fraud_flag_id, dispute]),
  );
  const tripsWithPendingCheck = new Set(
    (verificationData?.items ?? []).map((item) => item.source_trip_session_id),
  );

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Fraud"
        eyebrow="Trip reviews — earnings stay on hold until a review is dismissed"
      />
      <p className="text-muted -mt-2 mb-5 text-sm">
        {total} trip review{total === 1 ? "" : "s"}
      </p>

      <Panel className="mb-5 p-5">
        <h2 className="font-medium">Physical display checks</h2>
        <p className="text-muted mt-1 text-sm">
          Request an in-person check from a trip review below. A failed result enters the same
          authoritative fraud-review hold; location data alone is never treated as proof that a
          branded vehicle moved.
        </p>
        <details className="mt-4">
          <summary className="text-muted cursor-pointer text-xs">
            Check a trip without a flag
          </summary>
          <div className="mt-3">
            <SpotCheckQueueForm />
          </div>
        </details>
        {(verificationData?.items ?? []).length > 0 ? (
          <div className="border-edge mt-5 border-t pt-4">
            <h3 className="micro text-muted">Pending physical checks</h3>
            {(verificationData?.items ?? []).length >= 100 ? (
              <p className="text-muted mt-1 text-xs">
                Showing the newest 100 pending checks. Resolve these to see older ones.
              </p>
            ) : null}
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {(verificationData?.items ?? []).map((item) => (
                <div key={item.id} className="border-edge rounded-lg border p-3 text-xs">
                  <p className="font-medium">Assignment {item.assignment_id.slice(0, 8)}</p>
                  <p className="text-muted mt-1 font-mono">
                    trip {item.source_trip_session_id.slice(0, 8)} · queued{" "}
                    {formatDate(item.issued_at)}
                  </p>
                  <p className="text-muted mt-2">{item.result_note}</p>
                  <SpotCheckResultForm verificationId={item.id} />
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </Panel>

      <div className="mb-4 flex flex-wrap gap-1" role="group" aria-label="Filter by status">
        <Link
          href={href({})}
          className={cx(
            "micro rounded-lg px-3 py-2 transition-colors",
            !status ? "bg-raised text-amber" : "text-muted hover:text-ink",
          )}
        >
          All
        </Link>
        {STATUSES.map((s) => (
          <Link
            key={s}
            href={href({ status: s })}
            className={cx(
              "micro rounded-lg px-3 py-2 capitalize transition-colors",
              status === s ? "bg-raised text-amber" : "text-muted hover:text-ink",
            )}
          >
            {s}
          </Link>
        ))}
      </div>

      {items.length === 0 ? (
        <Panel className="p-10 text-center">
          <p className="font-medium">No {status ?? ""} flags</p>
          <p className="text-muted mt-1 text-sm">
            Flagged trips appear here when they need review.
          </p>
        </Panel>
      ) : (
        <div className="flex flex-col gap-3">
          {items.map((f) => {
            const dispute = disputeByFlagId.get(f.id);
            const reviewActive = f.status === "open" || f.status === "acknowledged";
            return (
              <Panel key={f.id} className="p-5" data-testid={`fraud-flag-${f.id}`}>
                <div className="flex flex-wrap items-start justify-between gap-5">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <StatusChip tone={sevTone[f.severity]}>{f.severity}</StatusChip>
                      <p className="font-medium">{typeLabel[f.flag_type] ?? f.flag_type}</p>
                    </div>
                    <p className="text-muted mt-2 text-sm">{f.description}</p>
                    <p className="micro text-faint mt-2 font-mono">
                      trip {f.trip_session_id.slice(0, 8)} · detected {formatDate(f.detected_at)}
                    </p>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <p className="micro text-faint">
                        Review due {formatDateTime(f.review_due_at)}
                      </p>
                      {f.escalated_at ? (
                        <StatusChip tone={reviewActive ? "coral" : "default"}>
                          {reviewActive
                            ? "Review deadline passed"
                            : "SLA exceeded before resolution"}
                        </StatusChip>
                      ) : null}
                    </div>
                    {f.escalated_at && reviewActive ? (
                      <p className="text-coral mt-2 text-sm">
                        This review is unresolved. Earnings remain held; escalation never releases
                        them automatically.
                      </p>
                    ) : null}
                    {readableEvidence(f.evidence).length > 0 ? (
                      <ul
                        className="border-edge text-muted mt-3 flex max-w-2xl flex-col gap-1 border-l pl-3 text-xs"
                        aria-label="Detection evidence"
                      >
                        {readableEvidence(f.evidence)
                          .slice(0, 6)
                          .map((line) => (
                            <li key={line}>{line}</li>
                          ))}
                      </ul>
                    ) : null}
                    {reviewActive && tripsWithPendingCheck.has(f.trip_session_id) ? (
                      <p className="text-muted mt-3 text-xs">
                        Physical check requested — see Pending physical checks above.
                      </p>
                    ) : null}
                    {reviewActive && !tripsWithPendingCheck.has(f.trip_session_id) ? (
                      <details className="mt-3">
                        <summary className="text-cyan cursor-pointer text-xs">
                          Request physical check
                        </summary>
                        <div className="mt-3">
                          <SpotCheckQueueForm
                            trip={{
                              assignmentId: f.assignment_id,
                              tripSessionId: f.trip_session_id,
                            }}
                          />
                        </div>
                      </details>
                    ) : null}
                    {f.reviewed_by_user_id && f.reviewed_at ? (
                      <p className="micro text-faint mt-3">
                        Reviewed by {f.reviewed_by_user_id.slice(0, 8)} ·{" "}
                        {formatDate(f.reviewed_at)}
                      </p>
                    ) : null}
                    {f.resolution_note ? (
                      <p className="text-muted mt-1 text-sm">Resolution: {f.resolution_note}</p>
                    ) : null}
                    <div
                      className="border-edge bg-raised mt-4 rounded-lg border p-3 text-sm"
                      aria-label="Earnings review effect"
                    >
                      {f.money_effect.reversal_recommended ? (
                        <p className="text-amber">
                          {formatMoneyExact(
                            f.money_effect.available_net,
                            f.money_effect.currency ?? "NGN",
                          )}{" "}
                          is already available. Confirming fraud posts one auditable reversal;
                          dismissing leaves it available.
                        </p>
                      ) : f.money_effect.reversal_entry_id ? (
                        <p className="text-green">
                          Released earnings were reversed when fraud was confirmed.
                        </p>
                      ) : f.status === "dismissed" ? (
                        <p className="text-muted">
                          The hold is removed. Eligible pending earnings release only after the
                          fraud assessment is current again.
                        </p>
                      ) : (
                        <p className="text-muted">
                          Earnings remain pending while this authoritative hold is active.
                        </p>
                      )}
                    </div>
                    {dispute ? (
                      <section
                        className="border-edge mt-4 border-t pt-4"
                        aria-label="Driver dispute"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="micro text-muted">Driver dispute</h3>
                          <StatusChip tone={dispute.status === "replied" ? "green" : "amber"}>
                            {dispute.status}
                          </StatusChip>
                        </div>
                        <p className="mt-2 text-sm whitespace-pre-wrap">{dispute.message}</p>
                        <p className="micro text-faint mt-1">
                          Submitted {formatDate(dispute.created_at)}
                        </p>
                        {dispute.reply ? (
                          <div className="bg-raised mt-3 rounded-lg p-3">
                            <p className="micro text-faint">Reply to driver</p>
                            <p className="mt-1 text-sm whitespace-pre-wrap">{dispute.reply}</p>
                          </div>
                        ) : (
                          <DisputeReplyActions disputeId={dispute.id} />
                        )}
                      </section>
                    ) : null}
                  </div>
                  <div className="flex min-w-60 flex-col items-end gap-3">
                    <StatusChip
                      tone={
                        f.status === "open" || f.status === "confirmed"
                          ? "coral"
                          : f.status === "acknowledged"
                            ? "amber"
                            : "default"
                      }
                    >
                      {f.status}
                    </StatusChip>
                    <ReviewActions
                      flagId={f.id}
                      status={f.status}
                      reversalRecommended={f.money_effect.reversal_recommended}
                      reversalRecorded={Boolean(f.money_effect.reversal_entry_id)}
                    />
                  </div>
                </div>
              </Panel>
            );
          })}
        </div>
      )}
      <Pagination
        total={total}
        limit={PAGE_SIZE}
        offset={offset}
        hrefFor={(o) => href({ status, offset: o })}
      />

      <p className="micro text-faint mt-6">
        Staff acknowledge each active hold, review its bounded evidence, then record one final
        confirmed or dismissed decision. The backend serializes every transition and remains the
        authority.
      </p>
    </div>
  );
}
