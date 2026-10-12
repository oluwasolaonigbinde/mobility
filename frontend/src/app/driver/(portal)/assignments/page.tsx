import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatDate, formatDateRange, formatMoney } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { StatusChip } from "@/components/ui/status-chip";
import { AssignmentActions } from "./assignment-actions";
import { InstallationEvidenceActions } from "./installation-evidence-actions";
import type { components } from "@/lib/api/schema";
import { readDriverApi } from "@/lib/driver/api-read";
import { DriverDataUnavailable } from "@/components/driver/data-unavailable";
import { FreshDriverAuthority } from "@/components/driver/fresh-authority";

export const metadata: Metadata = { title: "Jobs" };

type AssignmentStatus = components["schemas"]["CampaignAssignmentStatus"];
type Assignment = components["schemas"]["CampaignAssignmentRead"];
type EvidencePolicy = components["schemas"]["InstallationEvidencePolicyRead"];
type Evidence = components["schemas"]["InstallationEvidenceRead"];

const statusMeta: Record<
  AssignmentStatus,
  { label: string; tone: "default" | "amber" | "cyan" | "green" | "coral" }
> = {
  offered: { label: "Offer", tone: "cyan" },
  accepted: { label: "Accepted", tone: "amber" },
  declined: { label: "Declined", tone: "coral" },
  expired: { label: "Expired", tone: "default" },
  active: { label: "Running", tone: "green" },
  deactivated: { label: "Stopped", tone: "default" },
  cancelled: { label: "Cancelled", tone: "coral" },
  completed: { label: "Finished", tone: "default" },
};

const CURRENT: AssignmentStatus[] = ["active", "accepted", "deactivated"];
const OFFERS: AssignmentStatus[] = ["offered"];

function JobTerms({ a }: { a: Assignment }) {
  const payout = a.offer_terms?.payout as Record<string, unknown> | undefined;
  const daily = payout?.formula_version === "payout_v4";
  const rate = daily ? payout?.daily_rate_naira : payout?.hourly_rate_naira;
  return (
    <p className="mt-3 text-base font-semibold">
      {payout
        ? `${formatMoney(rate == null || rate === "" ? null : String(rate))} / ${daily ? "day" : "hour"}`
        : "Pay terms unavailable"}
    </p>
  );
}

function JobCard({
  a,
  policy,
  evidence,
  pendingDueAt,
  activeId,
  photoStatus,
}: {
  a: Assignment;
  policy: EvidencePolicy;
  evidence: Evidence | undefined;
  pendingDueAt: string | undefined;
  activeId?: string;
  photoStatus?: string;
}) {
  return (
    <Panel className="p-5" id={`photos-${a.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-base font-semibold">{a.campaign?.name ?? "Campaign"}</h3>
          <p className="text-muted mt-1 text-sm">
            {formatDateRange(a.campaign?.start_at, a.campaign?.end_at)}
          </p>
          <p className="text-muted mt-0.5 text-sm">Car {a.vehicle?.plate_number ?? "—"}</p>
        </div>
        <StatusChip tone={statusMeta[a.status].tone}>{statusMeta[a.status].label}</StatusChip>
      </div>
      <JobTerms a={a} />
      {policy.configured && policy.can_upload ? (
        <InstallationEvidenceActions
          assignmentId={a.id}
          status={a.status}
          requiredViews={policy.required_views}
          latestEvidenceStatus={evidence?.status}
          approvedUntil={evidence?.approved_until ?? undefined}
          pendingChallengeDueAt={pendingDueAt}
          proofAvailable={policy.display_proof_challenge_ttl_seconds != null}
          displayDue={a.id === activeId && photoStatus === "display_required"}
        />
      ) : ["accepted", "active", "deactivated"].includes(a.status) ? (
        <p className="text-muted border-edge mt-4 border-t pt-3 text-sm">
          Installation photos can&apos;t be sent yet.
        </p>
      ) : null}
      <AssignmentActions
        assignmentId={a.id}
        campaignName={a.campaign?.name ?? "this job"}
        status={a.status}
        canAccept={Boolean(a.offer_terms && a.offer_terms_sha256)}
      />
    </Panel>
  );
}

function PastJob({ a }: { a: Assignment }) {
  const endedAt =
    a.completed_at ?? a.deactivated_at ?? a.cancelled_at ?? a.declined_at ?? a.expired_at;
  const startedAt = a.activated_at ?? a.accepted_at ?? a.offered_at;
  const dates = endedAt
    ? `${statusMeta[a.status].label} ${formatDate(endedAt)}`
    : `${a.activated_at ? "Started" : a.accepted_at ? "Accepted" : "Offered"} ${formatDate(startedAt)}`;
  return (
    <li>
      <details className="border-edge bg-panel rounded-lg border">
        <summary className="flex cursor-pointer flex-wrap items-center justify-between gap-2 px-4 py-3">
          <span className="min-w-0">
            <span className="block text-sm font-medium">{a.campaign?.name ?? "Campaign"}</span>
            <span className="text-muted block text-xs">
              {dates} · Car {a.vehicle?.plate_number ?? "—"}
            </span>
          </span>
          {!endedAt ? (
            <StatusChip tone={statusMeta[a.status].tone}>{statusMeta[a.status].label}</StatusChip>
          ) : null}
        </summary>
        <div className="border-edge border-t px-4 pb-4">
          <p className="text-muted mt-1 text-sm">
            {a.activated_at ? "Started" : a.accepted_at ? "Accepted" : "Offered"}{" "}
            {formatDate(startedAt)}
            {endedAt ? ` – ${dates}` : ""}.
          </p>
          <JobTerms a={a} />
        </div>
      </details>
    </li>
  );
}

export default async function DriverAssignmentsPage({
  searchParams,
}: {
  searchParams?: Promise<{ assignment_id?: string }>;
}) {
  const selectedAssignmentId = (await searchParams)?.assignment_id;
  const api = createApiClient(await getSessionToken());
  const assignments = await readDriverApi(() =>
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
  );

  if (assignments.state === "auth") redirect("/login");
  if (assignments.state !== "ready") {
    return (
      <div className="animate-rise flex flex-col gap-4">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Jobs</h1>
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
        <h1 className="font-display text-2xl font-semibold tracking-tight">Jobs</h1>
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
        <h1 className="font-display text-2xl font-semibold tracking-tight">Jobs</h1>
        <DriverDataUnavailable
          title="Campaign history is unavailable"
          detail="Cardvert couldn't load your installation photo history, so job actions are unavailable. Try again shortly."
          retryHref="/driver/assignments"
        />
      </div>
    );
  }
  const active = await readDriverApi(() => api.GET("/api/v1/driver/campaign-assignments/active"));
  if (active.state === "auth") redirect("/login");
  if (
    active.state !== "ready" ||
    (active.data.assignment && active.data.photo_status === "unavailable")
  ) {
    return (
      <DriverDataUnavailable
        title="Photo status is unavailable"
        detail="Cardvert couldn't check your current photo task. Try again shortly."
        retryHref="/driver/assignments"
      />
    );
  }
  const evidenceByAssignment = new Map(
    evidenceHistories.map(([id, history]) => [
      id,
      history.state === "ready" ? history.data.items.at(-1) : undefined,
    ]),
  );
  const current = items.filter((item) => CURRENT.includes(item.status));
  const offers = items.filter((item) => OFFERS.includes(item.status));
  const past = items.filter(
    (item) => !CURRENT.includes(item.status) && !OFFERS.includes(item.status),
  );
  const card = (a: Assignment) => (
    <JobCard
      key={a.id}
      a={a}
      activeId={active.state === "ready" ? active.data.assignment?.id : undefined}
      photoStatus={active.state === "ready" ? active.data.photo_status : undefined}
      policy={evidencePolicy.data}
      evidence={evidenceByAssignment.get(a.id)}
      pendingDueAt={pendingByAssignment.get(a.id)?.due_at ?? undefined}
    />
  );

  return (
    <FreshDriverAuthority
      refreshKey={crypto.randomUUID()}
      title="Current campaign history hidden while offline"
      detail="Reconnect to check your current and completed jobs."
      retryHref="/driver/assignments"
    >
      <div className="animate-rise flex flex-col gap-6">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Jobs</h1>

        {items.length === 0 ? (
          <Panel className="p-6 text-center">
            <p className="text-sm font-medium">No jobs yet</p>
            <p className="text-muted mt-1 text-sm">
              Campaign offers appear here once our team assigns your vehicle.
            </p>
          </Panel>
        ) : null}

        {current.length ? (
          <section aria-labelledby="jobs-current" className="flex flex-col gap-3">
            <h2 id="jobs-current" className="font-display text-lg font-semibold">
              Current
            </h2>
            {current.map(card)}
          </section>
        ) : null}

        {offers.length ? (
          <section aria-labelledby="jobs-offers" className="flex flex-col gap-3">
            <h2 id="jobs-offers" className="font-display text-lg font-semibold">
              Offers
            </h2>
            {offers.map(card)}
          </section>
        ) : null}

        {past.length ? (
          <section aria-labelledby="jobs-past" className="flex flex-col gap-3">
            <h2 id="jobs-past" className="font-display text-lg font-semibold">
              Past jobs
            </h2>
            <ul className="grid gap-2">
              {past.map((a) => (
                <PastJob key={a.id} a={a} />
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </FreshDriverAuthority>
  );
}
