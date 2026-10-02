import Link from "next/link";
import { notFound } from "next/navigation";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { adminActivity, adminStatus, adminTone } from "@/lib/status/admin";
import { formatDate, formatDateRange, formatMoneyExact } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { StatusChip } from "@/components/ui/status-chip";
import { Pagination } from "@/components/ui/pagination";
import { HubChecklist, HubNav, HubSection } from "../../hub-section";
import { HubDrawer } from "../../hub-drawer";
import { QueueUnavailable } from "../../queue-search";
import { ReviewActions } from "../../approvals/review-actions";
import { CreativeReviewActions } from "../../approvals/creative-review-actions";
import { CampaignChangeReviewActions } from "../../approvals/campaign-change-review-actions";
import { InstallationReviewActions } from "../../approvals/installation-review-actions";
import { ActivateAssignmentButton } from "../../assignments/activate-button";
import { CancelAssignmentButton } from "../../assignments/cancel-button";
import { AssignmentForm } from "../../assignments/new/assignment-form";
import PayTermsSection from "../pay-terms-section";
import BillingSection from "../../billing/[campaignId]/content";
import InvoiceContent from "../../billing/[campaignId]/invoices/[invoiceId]/content";
import CloseoutContent from "../../billing/[campaignId]/closeout/content";
import MeasurementContent from "../../measurement/[runId]/content";
import { IssueMeasurementForm } from "../../measurement/issue-form";
import { ResumeForm } from "../resume-form";
import { ArtworkPreview } from "../artwork-preview";

const sections = [
  { id: "overview", title: "Overview" },
  { id: "artwork", title: "Artwork" },
  { id: "drivers", title: "Drivers" },
  { id: "pay-terms", title: "Pay terms" },
  { id: "money", title: "Money" },
  { id: "results", title: "Results" },
  { id: "trip-reviews", title: "Trip reviews" },
  { id: "activity", title: "Activity" },
];
type Query = {
  job?: string;
  drawer?: string;
  invoice?: string;
  run?: string;
  report?: string;
  jobs_offset?: string;
  artwork_offset?: string;
  results_offset?: string;
  activity_offset?: string;
  history_offset?: string;
  reviews_offset?: string;
  page?: string;
  error?: string;
  saved?: string;
};
export default async function CampaignHub({
  params,
  searchParams,
}: {
  params: Promise<{ campaignId: string }>;
  searchParams: Promise<Query>;
}) {
  const { campaignId } = await params;
  if (!z.string().uuid().safeParse(campaignId).success) notFound();
  const query = await searchParams;
  const api = createApiClient(await getSessionToken());
  let campaign;
  try {
    campaign = (
      await api.GET("/api/v1/admin/campaigns/{campaign_id}", {
        params: { path: { campaign_id: campaignId } },
      })
    ).data;
  } catch (error) {
    if (error instanceof ApiError && [403, 404, 422].includes(error.status)) notFound();
    throw error;
  }
  if (!campaign) notFound();
  const offset = (value?: string) =>
    Number.isFinite(Number(value)) ? Math.max(0, Math.floor(Number(value))) : 0;
  const [commercial, artwork, jobs, history, changes, results, reviews, activity, rules] =
    await Promise.all([
      api
        .GET("/api/v1/admin/campaigns/{campaign_id}/commercial", {
          params: { path: { campaign_id: campaignId } },
        })
        .catch(() => ({ data: undefined })),
      api
        .GET("/api/v1/admin/campaigns/{campaign_id}/creatives", {
          params: {
            path: { campaign_id: campaignId },
            query: { limit: 25, offset: offset(query.artwork_offset) },
          },
        })
        .catch(() => ({ data: undefined })),
      api
        .GET("/api/v1/admin/campaign-assignments", {
          params: {
            query: { campaign_id: campaignId, limit: 25, offset: offset(query.jobs_offset) },
          },
        })
        .catch(() => ({ data: undefined })),
      api
        .GET("/api/v1/admin/campaigns/{campaign_id}/review-history", {
          params: {
            path: { campaign_id: campaignId },
            query: { limit: 25, offset: offset(query.history_offset) },
          },
        })
        .catch(() => ({ data: undefined })),
      api.GET("/api/v1/admin/campaign-change-requests/pending").catch(() => ({ data: undefined })),
      api
        .GET("/api/v1/admin/measurement-runs", {
          params: {
            query: { campaign_id: campaignId, limit: 25, offset: offset(query.results_offset) },
          },
        })
        .catch(() => ({ data: undefined })),
      api
        .GET("/api/v1/admin/fraud-flags", {
          params: {
            query: { campaign_id: campaignId, limit: 25, offset: offset(query.reviews_offset) },
          },
        })
        .catch(() => ({ data: undefined })),
      api
        .GET("/api/v1/admin/audit-events", {
          params: {
            query: {
              entity_type: "campaign",
              entity_id: campaignId,
              limit: 25,
              offset: offset(query.activity_offset),
            },
          },
        })
        .catch(() => ({ data: undefined })),
      api
        .GET("/api/v1/admin/campaigns/{campaign_id}/payout-rules", {
          params: { path: { campaign_id: campaignId }, query: { limit: 100 } },
        })
        .catch(() => ({ data: undefined })),
    ]);
  const drawer = ["invoice", "closeout"].includes(query.drawer ?? "")
    ? query.drawer
    : query.job
      ? "job"
      : query.run
        ? "run"
        : undefined;
  const rows = (jobs.data?.items ?? []).map((job) => ({ job }));
  let selectedJob = drawer === "job" ? rows.find((row) => row.job.id === query.job) : undefined;
  let jobLookupFailed = false;
  if (
    drawer === "job" &&
    query.job &&
    !selectedJob &&
    z.string().uuid().safeParse(query.job).success
  ) {
    const candidate = (
      await api
        .GET("/api/v1/admin/campaign-assignments/{assignment_id}", {
          params: { path: { assignment_id: query.job } },
        })
        .catch(() => ({ data: undefined }))
    ).data;
    jobLookupFailed = !candidate;
    if (candidate?.campaign_id === campaignId) selectedJob = { job: candidate };
  }
  const [selectedReadiness, selectedPhotos] = selectedJob
    ? await Promise.all([
        api
          .GET("/api/v1/admin/campaign-assignments/{assignment_id}/readiness", {
            params: { path: { assignment_id: selectedJob.job.id } },
          })
          .catch(() => ({ data: undefined })),
        api
          .GET("/api/v1/admin/campaign-assignments/{assignment_id}/installation-evidence", {
            params: { path: { assignment_id: selectedJob.job.id } },
          })
          .catch(() => ({ data: undefined })),
      ])
    : [{ data: undefined }, { data: undefined }];
  const root = `/admin/campaigns/${campaignId}`;

  const closeHref = (section: string) =>
    `${root}?${new URLSearchParams(Object.entries(query).filter(([key]) => !["drawer", "invoice", "job", "run", "report", "page"].includes(key)))}#${section}`;
  const hrefFor = (key: string, value: number, anchor: string) =>
    `${root}?${new URLSearchParams({ ...query, [key]: String(value) })}#${anchor}`;
  const latestBudget = commercial.data?.budget_evaluations.at(-1);
  const spent = latestBudget?.billing_spend_amount;
  const budget = campaign.budget_amount;
  const percentage =
    spent != null && budget != null && Number(budget) > 0
      ? Math.min(100, Math.max(0, (Number(spent) / Number(budget)) * 100))
      : undefined;
  const rule = rules.data?.items.find((r) => r.status === "active");
  let selectedRun =
    drawer === "run" ? results.data?.items.find((run) => run.id === query.run) : undefined;
  let runLookupFailed = false;
  if (
    drawer === "run" &&
    query.run &&
    !selectedRun &&
    z.string().uuid().safeParse(query.run).success
  ) {
    const candidate = (
      await api
        .GET("/api/v1/admin/measurement-runs/{run_id}", { params: { path: { run_id: query.run } } })
        .catch(() => ({ data: undefined }))
    ).data;
    runLookupFailed = !candidate;
    if (candidate?.campaign_id === campaignId)
      selectedRun = {
        ...candidate,
        campaign_name: campaign.name,
        report_status: null,
        report_issuance_id: null,
        superseded: false,
      };
  }
  return (
    <div className="mx-auto max-w-6xl">
      <Link href="/admin/campaigns" className="text-cyan text-sm">
        ← Campaigns
      </Link>
      <PageHeader
        title={campaign.name}
        eyebrow={formatDateRange(campaign.start_at, campaign.end_at)}
        actions={
          campaign.status === "pending_review" ? (
            <ReviewActions campaignId={campaignId} />
          ) : campaign.status === "paused" && latestBudget?.resume_allowed ? (
            <ResumeForm campaignId={campaignId} />
          ) : undefined
        }
      />
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <StatusChip tone={adminTone(campaign.status)}>
          {adminStatus(campaign.status, "campaign")}
        </StatusChip>
        <Link
          className="text-cyan text-sm underline"
          href={`/admin/advertisers/${campaign.organization.id}`}
        >
          {campaign.organization.name}
        </Link>
      </div>
      {percentage !== undefined ? (
        <div className="mb-5">
          <label htmlFor="campaign-budget" className="text-muted text-sm">
            Budget used: {formatMoneyExact(spent, campaign.currency)} of{" "}
            {formatMoneyExact(budget, campaign.currency)}
          </label>
          <progress
            id="campaign-budget"
            value={percentage}
            max={100}
            className="mt-2 block h-2 w-full"
          />
        </div>
      ) : null}
      {artwork.data && commercial.data && jobs.data && rules.data ? (
        <HubChecklist
          title="Launch checklist"
          items={[
            {
              label: "Details approved",
              state: adminStatus(campaign.status, "campaign"),
              done: ["approved", "scheduled", "active", "paused", "completed"].includes(
                campaign.status,
              ),
              section: "overview",
            },
            {
              label: "Artwork approved",
              state: `${artwork.data.items.filter((c) => c.status === "approved").length} approved on this page`,
              done: Boolean(
                artwork.data &&
                artwork.data.total > 0 &&
                artwork.data.items.length === artwork.data.total &&
                artwork.data.items.every((c) => c.status === "approved"),
              ),
              section: "artwork",
            },
            {
              label: "Quotation accepted",
              state: commercial.data?.terms ? "Accepted" : "Review quotation",
              done: Boolean(commercial.data?.terms),
              section: "money",
            },
            {
              label: "Payment or approved credit",
              state: commercial.data?.financial_authority
                ? "Funding authorization recorded"
                : "Review funding",
              done: Boolean(commercial.data?.financial_authority),
              section: "money",
            },
            {
              label: "Pay terms set",
              state: rule ? "Current pay terms recorded" : "Review pay terms",
              done: Boolean(rule),
              section: "pay-terms",
            },
            {
              label: "Drivers on board",
              state: `${jobs.data.total} jobs recorded`,
              done: Boolean(
                jobs.data &&
                jobs.data.total > 0 &&
                rows.length === jobs.data.total &&
                rows.every((row) => ["accepted", "active"].includes(row.job.status)),
              ),
              section: "drivers",
            },
            {
              label: "Installation photos approved",
              state: "Check each driver's current installation",
              done: false,
              section: "drivers",
            },
          ]}
        />
      ) : null}
      <HubNav sections={sections} />
      <div className="space-y-5">
        <HubSection id="overview" title="Overview">
          <p className="mb-4">{campaign.description ?? "No description recorded."}</p>
          {!history.data || !changes.data ? (
            <QueueUnavailable />
          ) : (
            <details>
              <summary className="cursor-pointer">Review history</summary>
              {history.data.items.map((event) => (
                <p key={event.id} className="mt-2 text-sm">
                  {formatDate(event.created_at)} · {adminStatus(event.new_status, "campaign")}
                  {event.rejection_reason ? ` · ${event.rejection_reason}` : ""}
                </p>
              ))}
              <Pagination
                total={history.data.total}
                limit={25}
                offset={offset(query.history_offset)}
                hrefFor={(n) => hrefFor("history_offset", n, "overview")}
              />
            </details>
          )}
          {history.data && changes.data
            ? changes.data.items
                .filter((change) => change.campaign_id === campaignId)
                .map((change) => (
                  <div key={change.id} className="border-edge mt-4 rounded-lg border p-4">
                    <h3 className="mb-2 font-medium">
                      Change request · {adminStatus(change.status)}
                    </h3>
                    <CampaignChangeReviewActions
                      requestId={change.id}
                      initialReason={change.review_reason ?? undefined}
                    />
                  </div>
                ))
            : null}
        </HubSection>
        <HubSection id="artwork" title="Artwork">
          {!artwork.data ? (
            <QueueUnavailable />
          ) : (
            <>
              {!artwork.data.items.length ? (
                <p>No artwork submitted.</p>
              ) : (
                artwork.data.items.map((creative) => (
                  <div className="border-edge mb-3 rounded-lg border p-4" key={creative.id}>
                    <h3 className="font-medium">{creative.name}</h3>
                    <p className="text-muted my-2 text-sm">
                      {adminStatus(creative.status, "review")}
                    </p>
                    {creative.stored_file_id && creative.scan_status === "clean" ? (
                      <ArtworkPreview fileId={creative.stored_file_id} name={creative.name} />
                    ) : (
                      <p className="text-muted text-sm">
                        Artwork cannot be opened until its file checks pass.
                      </p>
                    )}
                    {creative.status === "pending_review" ? (
                      <CreativeReviewActions creativeId={creative.id} />
                    ) : null}
                  </div>
                ))
              )}
              <Pagination
                total={artwork.data.total}
                limit={25}
                offset={offset(query.artwork_offset)}
                hrefFor={(n) => hrefFor("artwork_offset", n, "artwork")}
              />
            </>
          )}
        </HubSection>
        <HubSection id="drivers" title="Drivers">
          {!jobs.data ? (
            <QueueUnavailable />
          ) : (
            <>
              {!rows.length ? (
                <p>No driver jobs recorded.</p>
              ) : (
                rows.map(({ job }) => (
                  <div
                    key={job.id}
                    id={`job-${job.id}`}
                    className="border-edge mb-3 rounded-lg border p-4"
                  >
                    <div className="flex flex-wrap justify-between gap-3">
                      <div>
                        <Link
                          className="text-cyan font-medium"
                          href={`/admin/drivers/${job.driver_profile_id}#jobs`}
                        >
                          {job.driver_profile?.full_name ?? "Driver"}
                        </Link>
                        <p className="text-muted mt-1 text-sm">
                          {job.vehicle?.plate_number ?? "No car recorded"} ·{" "}
                          {adminStatus(job.status, "job")}
                        </p>
                      </div>
                      <div className="flex items-start gap-4">
                        {["offered", "accepted", "active"].includes(job.status) ? (
                          <CancelAssignmentButton
                            assignmentId={job.id}
                            assignmentLabel={job.driver_profile?.full_name ?? "this job"}
                          />
                        ) : null}
                      </div>
                    </div>
                    {job.activity_flags?.map((flag) => (
                      <p key={flag.id} className="text-muted mb-2 text-sm">
                        {flag.flag_type === "inactivity"
                          ? "No recent verified activity"
                          : "Verified driving hours below the target"}{" "}
                        · {flag.status === "recovered" ? "Recovered" : "Needs attention"} ·{" "}
                        {formatDateRange(flag.window_start, flag.window_end)}
                      </p>
                    ))}
                    <Link
                      className="text-cyan text-sm underline"
                      href={`${root}?job=${job.id}#drivers`}
                    >
                      Installation photos and job details
                    </Link>
                  </div>
                ))
              )}
              <Pagination
                total={jobs.data.total}
                limit={25}
                offset={offset(query.jobs_offset)}
                hrefFor={(n) => hrefFor("jobs_offset", n, "drivers")}
              />
            </>
          )}
          <details className="mt-4">
            <summary className="text-cyan cursor-pointer">Offer a job · Find drivers</summary>
            <div className="mt-4">
              <AssignmentForm campaignId={campaignId} />
            </div>
          </details>
        </HubSection>
        <HubSection id="pay-terms" title="Pay terms">
          <PayTermsSection campaignId={campaignId} />
        </HubSection>
        <HubSection id="money" title="Money">
          {commercial.data ? (
            <BillingSection
              embedded
              params={Promise.resolve({ campaignId })}
              searchParams={Promise.resolve({ error: query.error, saved: query.saved })}
            />
          ) : (
            <QueueUnavailable />
          )}
        </HubSection>
        <HubSection id="results" title="Results">
          <IssueMeasurementForm campaignId={campaignId} />
          {!results.data ? (
            <QueueUnavailable />
          ) : (
            <>
              {!results.data.items.length ? (
                <p>No results calculations recorded.</p>
              ) : (
                results.data.items.map((run) => (
                  <Link
                    key={run.id}
                    className="border-edge mb-3 block rounded-lg border p-3"
                    href={`${root}?run=${run.id}${run.report_issuance_id ? `&report=${run.report_issuance_id}` : ""}#results`}
                  >
                    <p>{formatDateRange(run.period_start_at, run.period_end_at)}</p>
                    <p className="text-muted text-sm">
                      {run.test_only ? "Synthetic test · " : ""}
                      {run.superseded ? "Replaced results · " : ""}
                      {run.reproducible
                        ? "Saved results can be reproduced"
                        : "Results cannot be reproduced — do not issue a report"}{" "}
                      · Report:{" "}
                      {run.report_status ? adminStatus(run.report_status) : "Not requested"}
                    </p>
                  </Link>
                ))
              )}
              <Pagination
                total={results.data.total}
                limit={25}
                offset={offset(query.results_offset)}
                hrefFor={(n) => hrefFor("results_offset", n, "results")}
              />
            </>
          )}
        </HubSection>
        <HubSection id="trip-reviews" title="Trip reviews">
          {!reviews.data ? (
            <QueueUnavailable />
          ) : (
            <>
              {!reviews.data.items.length ? (
                <p>No matching trip reviews.</p>
              ) : (
                reviews.data.items.map((review) => (
                  <div
                    className="border-edge mb-2 block rounded-lg border p-3"
                    key={review.id}
                  >
                    <p>
                      {review.description} · {adminStatus(review.status, "review")}
                    </p>
                  </div>
                ))
              )}
              <Pagination
                total={reviews.data.total}
                limit={25}
                offset={offset(query.reviews_offset)}
                hrefFor={(n) => hrefFor("reviews_offset", n, "trip-reviews")}
              />
            </>
          )}
        </HubSection>
        <HubSection id="activity" title="Activity">
          {!activity.data ? (
            <QueueUnavailable />
          ) : (
            <>
              {!activity.data.items.length ? (
                <p>No campaign activity recorded.</p>
              ) : (
                activity.data.items.map((event) => (
                  <p className="mb-2 text-sm" key={event.id}>
                    {formatDate(event.created_at)} · {adminActivity(event.action)} ·{" "}
                    {event.actor_email ?? "System"}
                  </p>
                ))
              )}
              <Pagination
                total={activity.data.total}
                limit={25}
                offset={offset(query.activity_offset)}
                hrefFor={(n) => hrefFor("activity_offset", n, "activity")}
              />
            </>
          )}
        </HubSection>
        <details className="text-muted text-xs">
          <summary>Technical reference</summary>
          {activity.data?.items.map((event) => (
            <p key={event.id}>
              {formatDate(event.created_at)} · {event.action}
            </p>
          ))}
          <p className="mt-2 break-all">Campaign: {campaignId}</p>
        </details>
      </div>
      {drawer === "job" ? (
        selectedJob ? (
          <HubDrawer
            title={`Installation photos · ${selectedJob.job.driver_profile?.full_name ?? "Driver"}`}
            closeHref={closeHref("drivers")}
          >
            {!selectedReadiness.data || !selectedPhotos.data ? (
              <QueueUnavailable />
            ) : (
              <>
                {selectedReadiness.data ? (
                  <div className="mb-4">
                    <p>Ready to start? {selectedReadiness.data.message}</p>
                    {selectedReadiness.data.ready ? (
                      <ActivateAssignmentButton assignmentId={selectedJob.job.id} />
                    ) : null}
                  </div>
                ) : null}
                {!selectedPhotos.data.items.length ? (
                  <p>No installation photos submitted.</p>
                ) : (
                  selectedPhotos.data.items.map((photo) => (
                    <div key={photo.id} className="mb-5">
                      <h3 className="mb-2">
                        Version {photo.revision} · {adminStatus(photo.status, "review")}
                      </h3>
                      <InstallationReviewActions
                        submissionId={photo.id}
                        photos={photo.photos}
                        canReview={photo.status === "pending_review"}
                      />
                    </div>
                  ))
                )}
              </>
            )}
          </HubDrawer>
        ) : jobLookupFailed ? (
          <QueueUnavailable />
        ) : (
          <p role="alert">That job does not belong to this campaign.</p>
        )
      ) : null}
      {drawer === "invoice" ? (
        query.invoice &&
        commercial.data?.invoices.some((invoice) => invoice.id === query.invoice) ? (
          <HubDrawer title="Invoice" closeHref={closeHref("money")}>
            <InvoiceContent params={Promise.resolve({ campaignId, invoiceId: query.invoice })} />
          </HubDrawer>
        ) : !commercial.data ? (
          <QueueUnavailable />
        ) : (
          <p role="alert">That invoice is not part of this campaign.</p>
        )
      ) : null}
      {drawer === "closeout" ? (
        <HubDrawer title="Close-out" closeHref={closeHref("money")}>
          <CloseoutContent
            params={Promise.resolve({ campaignId })}
            searchParams={Promise.resolve({ page: query.page })}
          />
        </HubDrawer>
      ) : null}
      {drawer === "run" ? (
        selectedRun ? (
          <HubDrawer title="Results and reports" closeHref={closeHref("results")}>
            <MeasurementContent
              params={Promise.resolve({ runId: selectedRun.id })}
              searchParams={Promise.resolve({ report: query.report })}
            />
          </HubDrawer>
        ) : runLookupFailed ? (
          <QueueUnavailable />
        ) : (
          <p role="alert">That results calculation does not belong to this campaign.</p>
        )
      ) : null}
    </div>
  );
}
