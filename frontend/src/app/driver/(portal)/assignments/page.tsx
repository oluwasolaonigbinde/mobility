import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate, formatDateRange } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { AssignmentActions } from "./assignment-actions";
import { InstallationEvidenceActions } from "./installation-evidence-actions";
import type { components } from "@/lib/api/schema";
import { CampaignJourneyPanel } from "@/components/driver/campaign-journey-panel";
import { loadDriverCampaignJourney } from "@/lib/driver/load-campaign-journey";
import { readDriverApi } from "@/lib/driver/api-read";
import { DriverDataUnavailable } from "@/components/driver/data-unavailable";
import { FreshDriverAuthority } from "@/components/driver/fresh-authority";

export const metadata: Metadata = { title: "Jobs" };

type AssignmentStatus = components["schemas"]["CampaignAssignmentStatus"];

const statusMeta: Record<
  AssignmentStatus,
  { label: string; tone: "default" | "amber" | "cyan" | "green" | "coral" }
> = {
  offered: { label: "Offered", tone: "cyan" },
  accepted: { label: "Accepted", tone: "amber" },
  declined: { label: "Declined", tone: "coral" },
  expired: { label: "Expired", tone: "default" },
  active: { label: "Active", tone: "green" },
  deactivated: { label: "Deactivated", tone: "default" },
  cancelled: { label: "Cancelled", tone: "coral" },
  completed: { label: "Completed", tone: "default" },
};

const statusExplanation: Record<AssignmentStatus, string> = {
  offered: "Decision required. This offer does not grant campaign work.",
  accepted: "Accepted — waiting for the independent admin activation gate.",
  declined: "Declined. This offer cannot be activated or tracked.",
  expired: "Expired. This offer cannot be accepted or tracked.",
  active: "Admin activated. Start still rechecks current server and PWA authority.",
  deactivated: "Deactivated. New tracking is unavailable.",
  cancelled: "Cancelled. New campaign work is unavailable.",
  completed: "Completed. This is historical campaign evidence only.",
};

export default async function DriverAssignmentsPage() {
  const api = createApiClient(await getSessionToken());
  const [campaignJourney, assignments] = await Promise.all([
    readDriverApi(() => loadDriverCampaignJourney().then((data) => ({ data }))),
    readDriverApi(() =>
      api.GET("/api/v1/driver/campaign-assignments", { params: { query: { limit: 50 } } }),
    ),
  ]);

  if (campaignJourney.state === "auth" || assignments.state === "auth") redirect("/login");
  if (campaignJourney.state !== "ready" || assignments.state !== "ready") {
    return (
      <div className="animate-rise flex flex-col gap-4">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Campaign jobs</h1>
        <DriverDataUnavailable
          title="Campaign history is unavailable"
          detail="Cardvert could not verify your current or completed jobs. No empty history or work authority is being inferred."
          retryHref="/driver/assignments"
        />
      </div>
    );
  }

  const items = assignments.data.items;
  const [evidencePolicy, pendingVerifications] = await Promise.all([
    readDriverApi(() => api.GET("/api/v1/driver/installation-evidence/policy")),
    readDriverApi(() => api.GET("/api/v1/driver/evidence-verifications/pending")),
  ]);
  if (evidencePolicy.state === "auth" || pendingVerifications.state === "auth") redirect("/login");
  if (evidencePolicy.state !== "ready" || pendingVerifications.state !== "ready") {
    return (
      <div className="animate-rise flex flex-col gap-4">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Campaign jobs</h1>
        <DriverDataUnavailable
          title="Campaign history is unavailable"
          detail="Cardvert could not verify installation evidence and pending review authority. Job actions remain unavailable."
          retryHref="/driver/assignments"
        />
      </div>
    );
  }
  const pendingByAssignment = new Map(
    pendingVerifications.data.items.map((item) => [item.assignment_id, item]),
  );
  const evidenceHistories = evidencePolicy.data.configured
    ? await Promise.all(
        items.map(async (assignment) => {
          const history = await readDriverApi(() =>
            api.GET("/api/v1/driver/campaign-assignments/{assignment_id}/installation-evidence", {
              params: { path: { assignment_id: assignment.id } },
            }),
          );
          return [assignment.id, history] as const;
        }),
      )
    : [];
  if (evidenceHistories.some(([, history]) => history.state === "auth")) redirect("/login");
  if (evidenceHistories.some(([, history]) => history.state !== "ready")) {
    return (
      <div className="animate-rise flex flex-col gap-4">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Campaign jobs</h1>
        <DriverDataUnavailable
          title="Campaign history is unavailable"
          detail="Cardvert could not verify the current evidence history. Job actions remain unavailable."
          retryHref="/driver/assignments"
        />
      </div>
    );
  }
  const evidenceByAssignment = new Map(
    evidenceHistories.map(([id, history]) => [
      id,
      history.state === "ready" ? history.data.items : [],
    ]),
  );
  const activeCount = items.filter((item) => item.status === "active").length;
  const offeredCount = items.filter((item) => item.status === "offered").length;
  const completedCount = items.filter((item) => item.status === "completed").length;

  return (
    <FreshDriverAuthority
      title="Current campaign history hidden while offline"
      detail="Reconnect to verify current and completed jobs. Previously loaded job authority and assignment actions are hidden."
      retryHref="/driver/assignments"
    >
      <div className="animate-rise flex flex-col gap-4">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Campaign jobs</h1>
        <p className="text-muted -mt-2 text-sm">
          Offers, active work, and your completed campaign history in one place.
        </p>
        <CampaignJourneyPanel journey={campaignJourney.data.journey} compact />

        <div className="grid grid-cols-3 gap-3">
          {[
            ["Active", activeCount, "text-green"],
            ["Offers", offeredCount, "text-cyan"],
            ["Completed", completedCount, ""],
          ].map(([label, count, tone]) => (
            <Panel key={String(label)} className="p-3.5 text-center">
              <p className="micro text-faint">{label}</p>
              <p className={`font-display mt-1 text-2xl font-semibold ${String(tone)}`}>{count}</p>
            </Panel>
          ))}
        </div>

        {items.length === 0 ? (
          <Panel className="p-6 text-center">
            <p className="text-sm font-medium">No jobs yet</p>
            <p className="text-muted mt-1 text-xs">
              Campaign offers appear here once ops assigns your vehicle.
            </p>
          </Panel>
        ) : (
          items.map((a) => (
            <Panel key={a.id} className="p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-base font-medium">{a.campaign?.name ?? "Campaign"}</p>
                  <p className="micro text-faint mt-1">
                    {formatDateRange(a.campaign?.start_at, a.campaign?.end_at)}
                  </p>
                  <p className="micro text-faint mt-0.5">
                    {a.vehicle?.plate_number ?? "—"} · {a.vehicle?.vehicle_type ?? "vehicle"}
                  </p>
                </div>
                <StatusChip tone={statusMeta[a.status].tone}>
                  {statusMeta[a.status].label}
                </StatusChip>
              </div>
              <div className="border-edge/70 mt-4 grid grid-cols-2 gap-3 border-y py-3">
                <div>
                  <p className="micro text-faint">Offered</p>
                  <p className="mt-1 text-xs">{formatDate(a.offered_at)}</p>
                </div>
                <div>
                  <p className="micro text-faint">
                    {a.status === "completed"
                      ? "Completed"
                      : a.expires_at
                        ? "Offer expires"
                        : "Campaign window"}
                  </p>
                  <p className="mt-1 text-xs">
                    {a.status === "completed"
                      ? formatDate(a.completed_at)
                      : a.expires_at
                        ? formatDate(a.expires_at)
                        : formatDate(a.campaign?.end_at)}
                  </p>
                </div>
              </div>
              {a.offer_terms ? (
                <div className="bg-raised border-edge mt-4 rounded-lg border p-3">
                  <p className="micro text-faint">Frozen offer terms</p>
                  <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
                    <p>Currency: {String(a.offer_terms.currency ?? "—")}</p>
                    <p>
                      Base:{" "}
                      {String(
                        (a.offer_terms.payout as Record<string, unknown> | null | undefined)
                          ?.hourly_rate_naira ?? "—",
                      )}
                      /hr
                    </p>
                    <p>
                      Premium:{" "}
                      {String(
                        (a.offer_terms.payout as Record<string, unknown> | null | undefined)
                          ?.premium_hourly_rate_naira ?? "—",
                      )}
                      /hr
                    </p>
                    <p>
                      Daily cap:{" "}
                      {String(
                        (a.offer_terms.payout as Record<string, unknown> | null | undefined)
                          ?.daily_payable_hours_cap ?? "—",
                      )}
                      h
                    </p>
                    <p>
                      Window: {formatDate(a.offer_terms.campaign_window_start_at ?? null)} –{" "}
                      {formatDate(a.offer_terms.campaign_window_end_at ?? null)}
                    </p>
                    <p>
                      Area:{" "}
                      {String(
                        (a.offer_terms.service_area as Record<string, unknown> | null | undefined)
                          ?.city ?? "—",
                      )}
                    </p>
                    <p className="col-span-2">
                      Creative:{" "}
                      {String(
                        (a.offer_terms.creative as Record<string, unknown> | null | undefined)
                          ?.name ?? "—",
                      )}{" "}
                      ·{" "}
                      {String(
                        (a.offer_terms.creative as Record<string, unknown> | null | undefined)
                          ?.checksum ?? "no checksum",
                      )}
                    </p>
                    <p className="col-span-2">
                      Zones:{" "}
                      {Array.isArray(
                        (a.offer_terms.zones as Record<string, unknown> | null | undefined)?.target,
                      )
                        ? `${((a.offer_terms.zones as Record<string, unknown>).target as unknown[]).length} target · ${Array.isArray((a.offer_terms.zones as Record<string, unknown>).exclusion) ? ((a.offer_terms.zones as Record<string, unknown>).exclusion as unknown[]).length : 0} exclusion`
                        : "—"}
                    </p>
                  </div>
                  {a.offer_terms_sha256 ? (
                    <p className="text-faint mt-2 truncate font-mono text-[10px]">
                      Evidence {a.offer_terms_sha256}
                    </p>
                  ) : null}
                  <details className="mt-3">
                    <summary className="text-muted cursor-pointer text-[11px]">
                      View complete frozen snapshot
                    </summary>
                    <pre className="border-edge/60 bg-bg/50 mt-2 max-h-64 overflow-auto rounded border p-2 font-mono text-[10px] leading-4 whitespace-pre-wrap">
                      {JSON.stringify(a.offer_terms, null, 2)}
                    </pre>
                  </details>
                </div>
              ) : null}
              {a.notes ? <p className="text-muted mt-3 text-xs leading-5">{a.notes}</p> : null}
              <p className="text-muted mt-3 text-xs leading-5">{statusExplanation[a.status]}</p>
              {!a.offer_terms ? (
                <p className="text-faint mt-3 text-[11px]">
                  This legacy assignment has no complete frozen offer terms.
                </p>
              ) : null}
              <AssignmentActions assignmentId={a.id} status={a.status} />
              {evidencePolicy.data.configured && evidencePolicy.data.can_upload ? (
                <InstallationEvidenceActions
                  assignmentId={a.id}
                  status={a.status}
                  requiredViews={evidencePolicy.data.required_views}
                  latestEvidenceStatus={evidenceByAssignment.get(a.id)?.at(-1)?.status}
                  pendingChallengeDueAt={pendingByAssignment.get(a.id)?.due_at ?? undefined}
                />
              ) : ["accepted", "active", "deactivated"].includes(a.status) ? (
                <p className="text-muted border-edge mt-4 border-t pt-3 text-xs">
                  Installation evidence is waiting for the operations policy to be configured.
                </p>
              ) : null}
            </Panel>
          ))
        )}
      </div>
    </FreshDriverAuthority>
  );
}
