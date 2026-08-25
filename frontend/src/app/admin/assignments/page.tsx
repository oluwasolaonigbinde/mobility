import type { Metadata } from "next";
import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { Pagination } from "@/components/ui/pagination";
import { CancelAssignmentButton } from "./cancel-button";
import { ActivateAssignmentButton } from "./activate-button";
import type { components } from "@/lib/api/schema";

export const metadata: Metadata = { title: "Assignments" };

const PAGE_SIZE = 25;
type AStatus = components["schemas"]["CampaignAssignmentStatus"];

const tone: Record<AStatus, "green" | "amber" | "cyan" | "coral" | "default"> = {
  offered: "cyan",
  accepted: "amber",
  declined: "coral",
  expired: "default",
  active: "green",
  deactivated: "default",
  cancelled: "coral",
  completed: "default",
};

export default async function AdminAssignmentsPage({
  searchParams,
}: {
  searchParams: Promise<{ offset?: string }>;
}) {
  const params = await searchParams;
  const rawOffset = Number(params.offset ?? 0);
  const offset = Number.isFinite(rawOffset) && rawOffset > 0 ? Math.floor(rawOffset) : 0;

  const api = createApiClient(await getSessionToken());
  const { data } = await api.GET("/api/v1/admin/campaign-assignments", {
    params: { query: { limit: PAGE_SIZE, offset } },
  });
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="animate-rise mx-auto max-w-6xl">
      <PageHeader
        title="Assignments"
        eyebrow={`${total} campaign–vehicle pairing${total === 1 ? "" : "s"}`}
        actions={
          <Link
            href="/admin/assignments/new"
            className="bg-amber text-bg hover:bg-amber-soft shadow-glow-amber inline-flex h-11 items-center rounded-lg px-5 text-sm font-medium transition-colors"
          >
            + Offer assignment
          </Link>
        }
      />

      <Panel className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-sm">
            <thead>
              <tr className="border-edge micro text-muted border-b text-left">
                <th className="px-5 py-3.5 font-normal">Campaign</th>
                <th className="px-5 py-3.5 font-normal">Driver</th>
                <th className="px-5 py-3.5 font-normal">Vehicle</th>
                <th className="px-5 py-3.5 font-normal">Status</th>
                <th className="px-5 py-3.5 font-normal">Activity operations</th>
                <th className="px-5 py-3.5 font-normal">Offered</th>
                <th className="px-5 py-3.5 text-right font-normal">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.id} className="border-edge/60 border-b last:border-0">
                  <td className="px-5 py-3.5 font-medium">{a.campaign?.name ?? "—"}</td>
                  <td className="text-muted px-5 py-3.5 font-mono text-xs">
                    {a.driver_profile ? `${a.driver_profile.id.slice(0, 8)}…` : "—"}
                  </td>
                  <td className="px-5 py-3.5 font-mono text-xs">
                    {a.vehicle?.plate_number ?? "—"}
                  </td>
                  <td className="px-5 py-3.5">
                    <StatusChip tone={tone[a.status]}>{a.status}</StatusChip>
                  </td>
                  <td className="px-5 py-3.5">
                    {a.activity_flags?.length ? (
                      <div className="space-y-1.5">
                        {a.activity_flags.map((flag) => (
                          <div key={flag.id} className="text-xs">
                            <span className={flag.status === "open" ? "text-coral" : "text-green"}>
                              {flag.flag_type === "inactivity"
                                ? "7-day inactivity"
                                : "Weekly floor"}{" "}
                              {flag.status}
                            </span>
                            <div className="text-muted font-mono text-[10px]">
                              {flag.observed_seconds}s observed · {flag.evidence_event_count}{" "}
                              evidence event
                              {flag.evidence_event_count === 1 ? "" : "s"}
                            </div>
                            {flag.recovered_at ? (
                              <div className="text-faint text-[10px]">
                                Recovered {formatDate(flag.recovered_at)}
                              </div>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <span className="text-faint text-xs">Clear</span>
                    )}
                  </td>
                  <td className="text-muted px-5 py-3.5 font-mono text-xs">
                    {formatDate(a.offered_at)}
                    {a.expires_at ? <div>Expires {formatDate(a.expires_at)}</div> : null}
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    {a.status === "accepted" || a.status === "deactivated" ? (
                      <ActivateAssignmentButton assignmentId={a.id} />
                    ) : null}
                    {["offered", "accepted", "active", "deactivated"].includes(a.status) ? (
                      <CancelAssignmentButton assignmentId={a.id} />
                    ) : null}
                    {a.offer_terms_sha256 ? (
                      <p
                        className="text-faint mt-1 max-w-36 truncate font-mono text-[10px]"
                        title={a.offer_terms_sha256}
                      >
                        Evidence {a.offer_terms_sha256.slice(0, 12)}…
                      </p>
                    ) : null}
                    {a.offer_terms ? (
                      <details className="mt-1 text-left">
                        <summary className="text-muted cursor-pointer text-[11px]">
                          Frozen terms
                        </summary>
                        <pre className="border-edge/60 bg-bg/50 mt-1 max-h-48 max-w-64 overflow-auto rounded border p-2 font-mono text-[10px] leading-4 whitespace-pre-wrap">
                          {JSON.stringify(a.offer_terms, null, 2)}
                        </pre>
                      </details>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <Pagination
        total={total}
        limit={PAGE_SIZE}
        offset={offset}
        hrefFor={(o) => (o ? `/admin/assignments?offset=${o}` : "/admin/assignments")}
      />
    </div>
  );
}
