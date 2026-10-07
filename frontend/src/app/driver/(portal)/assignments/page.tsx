import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate, formatDateRange, formatMoneyExact } from "@/lib/format";
import { dailyRateSentences, offerTermLines } from "@/lib/assignments/offer-terms";
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
  accepted: "Accepted. Terrax Media still needs to start this campaign for you.",
  declined: "Declined. This offer cannot be activated or tracked.",
  expired: "Expired. This offer cannot be accepted or tracked.",
  active: "Activated. Cardvert checks you're still ready each time you press Start.",
  deactivated: "Deactivated. New tracking is unavailable.",
  cancelled: "Cancelled. New campaign work is unavailable.",
  completed: "Completed. This campaign is kept for your records only.",
};

export default async function DriverAssignmentsPage({
  searchParams,
}: {
  searchParams?: Promise<{ assignment_id?: string }>;
}) {
  const selectedAssignmentId = (await searchParams)?.assignment_id;
  const api = createApiClient(await getSessionToken());
  const [campaignJourney, assignments] = await Promise.all([
    readDriverApi(() => loadDriverCampaignJourney().then((data) => ({ data }))),
    readDriverApi(() =>
      selectedAssignmentId
        ? api
            .GET("/api/v1/driver/campaign-assignments/{assignment_id}", {
              params: { path: { assignment_id: selectedAssignmentId } },
            })
            .then(({ data, error }) => ({
              data: data ? { items: [data], total: 1, limit: 1, offset: 0 } : undefined,
              error,
            }))
        : api.GET("/api/v1/driver/campaign-assignments", { params: { query: { limit: 50 } } }),
    ),
  ]);

  if (campaignJourney.state === "auth" || assignments.state === "auth") redirect("/login");
  if (campaignJourney.state !== "ready" || assignments.state !== "ready") {
    return (
      <div className="animate-rise flex flex-col gap-4">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Campaign jobs</h1>
        <DriverDataUnavailable
          title="Campaign history is unavailable"
          detail="Cardvert couldn't load your current or completed jobs. Try again shortly."
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
          detail="Cardvert couldn't load your installation photos and pending checks, so job actions are unavailable. Try again shortly."
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
          detail="Cardvert couldn't load your installation photo history, so job actions are unavailable. Try again shortly."
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
      refreshKey={crypto.randomUUID()}
      title="Current campaign history hidden while offline"
      detail="Reconnect to check your current and completed jobs."
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
              Campaign offers appear here once our team assigns your vehicle.
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
                  <p className="micro text-faint">Pay and job terms</p>
                  {dailyRateSentences(a.offer_terms).length ? (
                    <ul className="mt-2 grid gap-1 text-xs">
                      {dailyRateSentences(a.offer_terms).map((sentence) => (
                        <li key={sentence}>{sentence}</li>
                      ))}
                    </ul>
                  ) : null}
                  <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
                    <p>Currency: {String(a.offer_terms.currency ?? "—")}</p>
                    {dailyRateSentences(a.offer_terms).length ? null : (
                      <>
                        <p>
                          Base:{" "}
                          {formatMoneyExact(
                            String(
                              (a.offer_terms.payout as Record<string, unknown> | null | undefined)
                                ?.hourly_rate_naira ?? "—",
                            ) || "—",
                          )}
                          /hr
                        </p>
                        <p>
                          Premium:{" "}
                          {formatMoneyExact(
                            String(
                              (a.offer_terms.payout as Record<string, unknown> | null | undefined)
                                ?.premium_hourly_rate_naira ?? "—",
                            ) || "—",
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
                      </>
                    )}
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
                      Artwork:{" "}
                      {String(
                        (a.offer_terms.creative as Record<string, unknown> | null | undefined)
                          ?.name ?? "—",
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
                  <details className="mt-3">
                    <summary className="text-muted cursor-pointer text-[11px]">
                      Full job terms
                    </summary>
                    <dl className="mt-2 grid gap-1 text-[11px]">
                      {offerTermLines(a.offer_terms).map((line) => (
                        <div key={line.label} className="flex flex-wrap gap-x-2">
                          <dt className="text-faint">{line.label}</dt>
                          <dd>{line.value}</dd>
                        </div>
                      ))}
                    </dl>
                  </details>
                </div>
              ) : null}
              {a.notes ? <p className="text-muted mt-3 text-xs leading-5">{a.notes}</p> : null}
              <p className="text-muted mt-3 text-xs leading-5">{statusExplanation[a.status]}</p>
              {!a.offer_terms && a.status !== "offered" ? (
                <p className="text-faint mt-3 text-[11px]">
                  This older job doesn&apos;t have its pay terms saved in Cardvert.
                </p>
              ) : null}
              <AssignmentActions
                assignmentId={a.id}
                campaignName={a.campaign?.name ?? "this campaign"}
                status={a.status}
                canAccept={Boolean(a.offer_terms && a.offer_terms_sha256)}
              />
              {evidencePolicy.data.configured && evidencePolicy.data.can_upload ? (
                <InstallationEvidenceActions
                  assignmentId={a.id}
                  status={a.status}
                  requiredViews={evidencePolicy.data.required_views}
                  latestEvidenceStatus={evidenceByAssignment.get(a.id)?.at(-1)?.status}
                  pendingChallengeDueAt={pendingByAssignment.get(a.id)?.due_at ?? undefined}
                  proofAvailable={evidencePolicy.data.display_proof_challenge_ttl_seconds != null}
                />
              ) : ["accepted", "active", "deactivated"].includes(a.status) ? (
                <p className="text-muted border-edge mt-4 border-t pt-3 text-xs">
                  Installation photos can&apos;t be uploaded yet.
                </p>
              ) : null}
            </Panel>
          ))
        )}
      </div>
    </FreshDriverAuthority>
  );
}
