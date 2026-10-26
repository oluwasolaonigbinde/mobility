import type { Metadata } from "next";
import Link from "next/link";
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
import { frozenJob } from "@/lib/driver/frozen-job";
import { JobVisual } from "@/components/driver/job-visual";
import { PortalIcon } from "@/components/brand/portal-icon";

export const metadata: Metadata = { title: "Jobs" };

type AssignmentStatus = components["schemas"]["CampaignAssignmentRead"]["status"];
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
  cancelled: { label: "Cancelled", tone: "coral" },
  finished: { label: "Finished", tone: "default" },
};

const CURRENT: AssignmentStatus[] = ["active", "accepted"];
const OFFERS: AssignmentStatus[] = ["offered"];

function JobTerms({ a }: { a: Assignment }) {
  const terms = frozenJob(a.offer_terms);
  return (
    <p className="mt-3 flex items-center gap-2 text-base font-semibold">
      <PortalIcon name="wallet" />
      {terms.rate && terms.currency
        ? `${formatMoney(terms.rate, terms.currency)} / day`
        : "Pay terms unavailable"}
    </p>
  );
}

function JobCard({
  a,
  policy,
  evidence,
  activeId,
  photoStatus,
  now,
}: {
  a: Assignment;
  policy: EvidencePolicy;
  evidence: Evidence | undefined;
  activeId?: string;
  photoStatus?: string;
  now: number;
}) {
  const installationApproved =
    evidence?.status === "approved" &&
    (!evidence.approved_until || Date.parse(evidence.approved_until) > now);
  const needsInstallation =
    ["accepted", "active", "deactivated"].includes(a.status) &&
    ((!installationApproved && evidence?.status !== "pending_review") ||
      (a.id === activeId && photoStatus === "installation_required"));
  const readyToDrive =
    a.status === "active" && a.id === activeId && photoStatus === "ready" && installationApproved;
  let sentence = "Open Home to check your next step.";
  if (a.status === "offered") sentence = "A new job for you. Take a look and decide.";
  else if (evidence?.status === "pending_review")
    sentence = "Terrax Media is checking your photos.";
  else if (evidence?.status === "rejected" && ["accepted", "active"].includes(a.status))
    sentence = "Your photos weren’t approved. Send clear new photos of the advert on your car.";
  else if (needsInstallation)
    sentence = `Next, send ${policy.required_views.length} photos of the advert on your car.`;
  else if (a.status === "accepted")
    sentence = "Your photos are approved. Terrax Media will confirm when to start.";
  else if (readyToDrive) sentence = "You’re ready to drive. Start your trip from Home.";
  return (
    <Panel className="p-5" id={`photos-${a.id}`}>
      <p className="mb-4 rounded-xl bg-[#f0f7ed] p-3 text-sm leading-6">{sentence}</p>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-base font-semibold">{a.campaign?.name ?? "Campaign"}</h3>
          <p className="text-muted mt-1 text-sm">
            {frozenJob(a.offer_terms).startAt && frozenJob(a.offer_terms).endAt
              ? formatDateRange(frozenJob(a.offer_terms).startAt, frozenJob(a.offer_terms).endAt)
              : "Job dates unavailable"}
          </p>
          <p className="text-muted mt-0.5 text-sm">Car {a.vehicle?.plate_number ?? "—"}</p>
        </div>
        <StatusChip tone={statusMeta[a.status].tone}>{statusMeta[a.status].label}</StatusChip>
      </div>
      <JobTerms a={a} />
      <JobVisual
        job={frozenJob(a.offer_terms)}
        assignmentId={["offered", "accepted", "active"].includes(a.status) ? a.id : undefined}
      />
      <InstallationEvidenceActions
        assignmentId={a.id}
        status={a.status}
        requiredViews={policy.required_views}
        latestEvidenceStatus={evidence?.status}
        rejectionReason={evidence?.rejection_reason ?? undefined}
        approvedUntil={evidence?.approved_until ?? undefined}
      />
      {readyToDrive ? (
        <Link href="/driver" className="brand-action mt-4 w-full">
          Go to Home →
        </Link>
      ) : null}
      {a.status === "active" ? (
        <details className="border-edge mt-4 border-t pt-3">
          <summary className="text-muted cursor-pointer text-sm">Job options</summary>
          <AssignmentActions
            assignmentId={a.id}
            campaignName={a.campaign?.name ?? "this job"}
            status={a.status}
          />
        </details>
      ) : a.status === "accepted" || a.status === "finished" ? null : (
        <AssignmentActions
          assignmentId={a.id}
          campaignName={a.campaign?.name ?? "this job"}
          status={a.status}
          canAccept={Boolean(a.offer_terms && a.offer_terms_sha256)}
        />
      )}
    </Panel>
  );
}

function PastJob({ a }: { a: Assignment }) {
  const endedAt =
    (a.status === "finished" ? a.campaign?.end_at : undefined) ??
    a.deactivated_at ??
    a.cancelled_at ??
    a.declined_at ??
    a.expired_at;
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
          detail="Cardvert couldn't load your current or finished jobs. Try again shortly."
          retryHref="/driver/assignments"
        />
      </div>
    );
  }

  const items = assignments.data.items;
  const evidencePolicy = await readDriverApi(() =>
    api.GET("/api/v1/driver/installation-evidence/policy"),
  );
  if (evidencePolicy.state === "auth") redirect("/login");
  if (evidencePolicy.state !== "ready") {
    return (
      <div className="animate-rise flex flex-col gap-4">
        <h1 className="font-display text-2xl font-semibold tracking-tight">Jobs</h1>
        <DriverDataUnavailable
          title="Campaign history is unavailable"
          detail="Cardvert couldn't load your installation photos, so job actions are unavailable. Try again shortly."
          retryHref="/driver/assignments"
        />
      </div>
    );
  }
  const evidenceHistories = await Promise.all(
    items.map(async (assignment) => {
      const history = await readDriverApi(() =>
        api.GET("/api/v1/driver/campaign-assignments/{assignment_id}/installation-evidence", {
          params: { path: { assignment_id: assignment.id } },
        }),
      );
      return [assignment.id, history] as const;
    }),
  );
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
  const now = new Date().getTime();
  const card = (a: Assignment) => (
    <JobCard
      key={a.id}
      a={a}
      now={now}
      activeId={active.state === "ready" ? active.data.assignment?.id : undefined}
      photoStatus={active.state === "ready" ? active.data.photo_status : undefined}
      policy={evidencePolicy.data}
      evidence={evidenceByAssignment.get(a.id)}
    />
  );

  return (
    <FreshDriverAuthority
      refreshKey={crypto.randomUUID()}
      title="Current campaign history hidden while offline"
      detail="Reconnect to check your current and finished jobs."
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
