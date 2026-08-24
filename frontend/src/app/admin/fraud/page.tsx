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

export const metadata: Metadata = { title: "Fraud console" };

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
};

function evidenceLabel(key: string): string {
  return key.replaceAll("_", " ");
}

function evidenceValue(value: unknown): string {
  let rendered: string;
  if (typeof value === "string") rendered = value;
  else if (typeof value === "number" || typeof value === "boolean") rendered = String(value);
  else {
    try {
      rendered = JSON.stringify(value) ?? "Unavailable";
    } catch {
      rendered = "Unavailable";
    }
  }
  return rendered.length > 120 ? `${rendered.slice(0, 117)}…` : rendered;
}

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
  const { data } = await api.GET("/api/v1/admin/fraud-flags", {
    params: { query: { limit: PAGE_SIZE, offset, ...(status ? { status } : {}) } },
  });
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

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Fraud console"
        eyebrow={`${total} flag${total === 1 ? "" : "s"} — open, acknowledged and confirmed flags hold affected money; only dismissal releases the hold`}
      />

      <div className="mb-4 flex gap-1" role="group" aria-label="Filter by status">
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
          <p className="text-muted mt-1 text-sm">The detection engine is watching every trip.</p>
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
                    {Object.keys(f.evidence ?? {}).length > 0 ? (
                      <dl
                        className="border-edge mt-3 grid max-w-2xl grid-cols-[auto_1fr] gap-x-3 gap-y-1 border-l pl-3 text-xs"
                        aria-label="Detection evidence"
                      >
                        {Object.entries(f.evidence ?? {})
                          .slice(0, 6)
                          .map(([key, value]) => (
                            <div key={key} className="contents">
                              <dt className="text-faint capitalize">{evidenceLabel(key)}</dt>
                              <dd
                                className="text-muted min-w-0 truncate font-mono"
                                title={evidenceValue(value)}
                              >
                                {evidenceValue(value)}
                              </dd>
                            </div>
                          ))}
                      </dl>
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
