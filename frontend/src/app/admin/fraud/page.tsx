import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { Pagination } from "@/components/ui/pagination";
import { cx } from "@/lib/cx";
import type { components } from "@/lib/api/schema";

export const metadata: Metadata = { title: "Fraud console" };

const PAGE_SIZE = 25;
type FStatus = components["schemas"]["FraudFlagStatus"];
type FSeverity = components["schemas"]["FraudFlagSeverity"];

const STATUSES: FStatus[] = ["open", "acknowledged", "dismissed"];
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
  exclusion_zone_presence: "Exclusion zone",
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
  const { data } = await api.GET("/api/v1/admin/fraud-flags", {
    params: { query: { limit: PAGE_SIZE, offset, ...(status ? { status } : {}) } },
  });
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Fraud console"
        eyebrow={`${total} flag${total === 1 ? "" : "s"} — flagged trips are auto-discounted from billing and payouts`}
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
          {items.map((f) => (
            <Panel key={f.id} className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <StatusChip tone={sevTone[f.severity]}>{f.severity}</StatusChip>
                    <p className="font-medium">{typeLabel[f.flag_type] ?? f.flag_type}</p>
                  </div>
                  <p className="text-muted mt-2 text-sm">{f.description}</p>
                  <p className="micro text-faint mt-2 font-mono">
                    trip {f.trip_session_id.slice(0, 8)} · detected {formatDate(f.detected_at)}
                  </p>
                </div>
                <StatusChip tone={f.status === "open" ? "coral" : "default"}>{f.status}</StatusChip>
              </div>
            </Panel>
          ))}
        </div>
      )}
      <Pagination
        total={total}
        limit={PAGE_SIZE}
        offset={offset}
        hrefFor={(o) => href({ status, offset: o })}
      />

      <p className="micro text-faint mt-6">
        Flag statuses are set by the detection engine in this MVP — the hold-and-review workflow
        is planned work (architecture §17, slice S2).
      </p>
    </div>
  );
}
