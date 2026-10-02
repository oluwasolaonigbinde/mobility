import Link from "next/link";
import { notFound } from "next/navigation";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { adminActivity, adminStatus, adminTone } from "@/lib/status/admin";
import { formatDate, formatMoneyExact } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { StatusChip } from "@/components/ui/status-chip";
import { Pagination } from "@/components/ui/pagination";
import { HubChecklist, HubNav, HubSection } from "../hub-section";
import { HubDrawer } from "../hub-drawer";
import { QueueUnavailable } from "../queue-search";
import { PersonPayeeDecisionActions } from "../driver-applications/person-payee-decision-actions";
import { VehicleDecisionActions } from "../driver-applications/vehicle-decision-actions";
import { AccountSetupAction } from "../driver-applications/account-setup-action";
import { DriverOnboardingMenu } from "./onboarding-menu";
import { VehicleStatusMenu } from "../vehicles/vehicle-status-menu";
import { VehicleForm } from "../vehicles/new/vehicle-form";
import { AssignmentForm } from "../assignments/new/assignment-form";
import { CancelAssignmentButton } from "../assignments/cancel-button";
import { ProcessTripForm } from "../payouts/process-trip-form";
import { DriverDetailsForm } from "./details-form";

const sections = [
  { id: "details", title: "Details" },
  { id: "documents", title: "Documents" },
  { id: "cars", title: "Cars" },
  { id: "phone", title: "Phone" },
  { id: "jobs", title: "Campaign jobs" },
  { id: "trips-and-pay", title: "Trips and pay" },
  { id: "reviews", title: "Reviews" },
  { id: "activity", title: "Activity" },
];
export type DriverHubQuery = {
  application?: string;
  trip?: string;
  trips_offset?: string;
  cars_offset?: string;
  jobs_offset?: string;
  activity_offset?: string;
  reviews_offset?: string;
  currency?: string;
};
export default async function DriverHub({
  driverId,
  applicationId,
  query = {},
}: {
  driverId?: string;
  applicationId?: string;
  query?: DriverHubQuery;
}) {
  if (
    !z
      .string()
      .uuid()
      .safeParse(driverId ?? applicationId).success
  )
    notFound();
  const api = createApiClient(await getSessionToken());
  let application;
  let driver;
  try {
    if (applicationId) {
      application = (
        await api.GET("/api/v1/admin/driver-applications/{application_id}", {
          params: { path: { application_id: applicationId } },
        })
      ).data;
      if (!application) notFound();
      driverId = application.driver_profile_id;
    }
    if (driverId)
      driver = (
        await api.GET("/api/v1/admin/drivers/{driver_profile_id}", {
          params: { path: { driver_profile_id: driverId } },
        })
      ).data;
  } catch (error) {
    if (error instanceof ApiError && [403, 404, 422].includes(error.status)) notFound();
    throw error;
  }
  if (!driver && !application) notFound();
  const person = driver ?? application!;
  const id = driver?.id ?? application?.driver_profile_id;
  const userId = person.user_id;
  const root = driver ? `/admin/drivers/${driver.id}` : `/admin/drivers/applicant/${applicationId}`;
  const offset = (value?: string) =>
    Number.isFinite(Number(value)) ? Math.max(0, Math.floor(Number(value))) : 0;
  if (!application && query.application && z.string().uuid().safeParse(query.application).success) {
    const candidate = (
      await api
        .GET("/api/v1/admin/driver-applications/{application_id}", {
          params: { path: { application_id: query.application } },
        })
        .catch(() => ({ data: undefined }))
    ).data;
    if (candidate && candidate.driver_profile_id === id && candidate.user_id === userId)
      application = candidate;
  }
  let applicationAvailable = Boolean(application);
  if (!application) {
    const candidates = (
      await api
        .GET("/api/v1/admin/driver-applications", {
          params: { query: { driver_profile_id: id, user_id: userId, history: true, limit: 1 } },
        })
        .catch(() => ({ data: undefined }))
    ).data;
    application = candidates?.items.find((a) => a.driver_profile_id === id && a.user_id === userId);
    applicationAvailable = Boolean(candidates && (candidates.total === 0 || application));
  }
  const [cars, jobs, trips, reviews, activity, accounts] = await Promise.all([
    id
      ? api
          .GET("/api/v1/admin/vehicles", {
            params: {
              query: { driver_profile_id: id, limit: 25, offset: offset(query.cars_offset) },
            },
          })
          .catch(() => ({ data: undefined }))
      : Promise.resolve({ data: undefined }),
    id
      ? api
          .GET("/api/v1/admin/campaign-assignments", {
            params: {
              query: { driver_profile_id: id, limit: 25, offset: offset(query.jobs_offset) },
            },
          })
          .catch(() => ({ data: undefined }))
      : Promise.resolve({ data: undefined }),
    id
      ? api
          .GET("/api/v1/admin/payout-calculations", {
            params: {
              query: { driver_profile_id: id, limit: 25, offset: offset(query.trips_offset) },
            },
          })
          .catch(() => ({ data: undefined }))
      : Promise.resolve({ data: undefined }),
    id
      ? api
          .GET("/api/v1/admin/fraud-flags", {
            params: {
              query: { driver_profile_id: id, limit: 25, offset: offset(query.reviews_offset) },
            },
          })
          .catch(() => ({ data: undefined }))
      : Promise.resolve({ data: undefined }),
    id
      ? api
          .GET("/api/v1/admin/audit-events", {
            params: {
              query: {
                entity_type: "driver_profile",
                entity_id: id,
                limit: 25,
                offset: offset(query.activity_offset),
              },
            },
          })
          .catch(() => ({ data: undefined }))
      : Promise.resolve({ data: undefined }),
    api
      .GET("/api/v1/admin/users", {
        params: { query: { q: person.email, role: "driver", limit: 100 } },
      })
      .catch(() => ({ data: undefined })),
  ]);
  const account = accounts.data?.items.find((u) => u.id === userId);
  const p = application?.person_payee;
  const v = application?.vehicle;
  const status = driver?.onboarding_status ?? application!.status;
  const selectedTrip = query.trip
    ? trips.data?.items.find((t) => t.trip_session_id === query.trip)
    : undefined;
  const currencies = [...new Set(trips.data?.items.map((trip) => trip.currency) ?? [])];
  const currency = currencies.find((value) => value === query.currency) ?? currencies[0];
  const balance =
    id && currency
      ? (
          await api
            .GET("/api/v1/admin/payout-batches/debt-balances/{driver_profile_id}", {
              params: { path: { driver_profile_id: id }, query: { currency } },
            })
            .catch(() => ({ data: undefined }))
        ).data
      : undefined;
  const hrefFor = (key: keyof DriverHubQuery, value: number, anchor: string) =>
    `${root}?${new URLSearchParams({ ...query, [key]: String(value) })}#${anchor}`;
  return (
    <div className="mx-auto max-w-6xl">
      <Link href="/admin/drivers" className="text-cyan text-sm">
        ← Drivers
      </Link>
      <PageHeader
        title={person.full_name}
        eyebrow={[person.phone, person.service_city].filter(Boolean).join(" · ")}
        actions={
          driver ? (
            <DriverOnboardingMenu
              driverProfileId={driver.id}
              driverName={driver.full_name}
              status={driver.onboarding_status}
              activationBlocked={Boolean(application) || !applicationAvailable}
            />
          ) : undefined
        }
      />
      <StatusChip tone={adminTone(status)}>{adminStatus(status, "driver")}</StatusChip>
      {applicationAvailable && accounts.data ? (
        <p className="text-muted my-4 text-sm">
          {p?.status !== "approved"
            ? "Next: review identity documents and bank details."
            : v?.status !== "approved"
              ? "Next: check the car and its documents."
              : account?.status === "invited"
                ? "Next: complete sign-in setup."
                : "Current document and car decisions are recorded."}
        </p>
      ) : null}
      {applicationAvailable ? (
        <HubChecklist
          title="Ready to drive?"
          items={[
            {
              label: "Identity documents",
              state: adminStatus(p?.status, "review"),
              done: p?.status === "approved",
              section: "documents",
            },
            {
              label: "Bank details",
              state: p?.bank_account_verified ? "Verified" : "Check bank details",
              done: p?.bank_account_verified,
              section: "documents",
            },
            {
              label: "Car approved",
              state: adminStatus(v?.status, "review"),
              done: v?.status === "approved",
              section: "cars",
            },
          ]}
        />
      ) : null}
      <HubNav sections={sections} />
      <div className="space-y-5">
        <HubSection id="details" title="Details">
          {!accounts.data ? (
            <QueueUnavailable />
          ) : (
            <>
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-muted">Email</dt>
                  <dd className="break-all">{person.email}</dd>
                </div>
                <div>
                  <dt className="text-muted">Service area</dt>
                  <dd>{person.service_city ?? "Not recorded"}</dd>
                </div>
                <div>
                  <dt className="text-muted">Sign-in account</dt>
                  <dd>{account ? adminStatus(account.status) : "Not recorded"}</dd>
                </div>
                <div>
                  <dt className="text-muted">Licence</dt>
                  <dd>{driver?.license_number ?? "See identity documents"}</dd>
                </div>
              </dl>
              {application?.status === "approved" && account?.status === "invited" ? (
                <div className="mt-4">
                  <AccountSetupAction
                    applicationId={application.id}
                    applicantName={person.full_name}
                  />
                </div>
              ) : null}
              <p className="text-muted mt-3 text-sm">
                The driver can reset their password from the sign-in page.
              </p>
              {driver ? (
                <details className="mt-4">
                  <summary className="text-cyan cursor-pointer">Edit driver details</summary>
                  <DriverDetailsForm driver={driver} />
                </details>
              ) : null}
            </>
          )}
        </HubSection>
        <HubSection id="documents" title="Documents">
          <p className="text-muted mb-4 text-sm">
            Sensitive document access is logged and automatically hidden after one minute.
          </p>
          {p?.submission_id && p.bank_account_version_id ? (
            <PersonPayeeDecisionActions
              applicationId={application!.id}
              submissionId={p.submission_id}
              bankAccountVersionId={p.bank_account_version_id}
              bankAccountVerified={p.bank_account_verified}
              documentFileIds={p.document_file_ids ?? {}}
              status={p.status}
            />
          ) : !applicationAvailable ? (
            <QueueUnavailable />
          ) : (
            <p>No current identity submission is linked to this driver.</p>
          )}
        </HubSection>
        <HubSection id="cars" title="Cars">
          {!cars.data ? (
            id ? (
              <QueueUnavailable />
            ) : (
              <p>No cars recorded.</p>
            )
          ) : (
            <>
              {!cars.data.items.length ? (
                <p>No cars recorded.</p>
              ) : (
                cars.data.items.map((car) => (
                  <div key={car.id} className="border-edge mb-3 rounded-lg border p-3">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h3 className="font-medium">{car.plate_number}</h3>
                        <p className="text-muted text-sm">
                          {[car.make, car.model, car.color].filter(Boolean).join(" · ")} ·{" "}
                          {adminStatus(car.status)}
                        </p>
                      </div>
                      <VehicleStatusMenu
                        vehicleId={car.id}
                        vehicleLabel={car.plate_number}
                        status={car.status}
                        activationBlocked={!applicationAvailable || v?.vehicle_id === car.id}
                      />
                    </div>
                    {v?.vehicle_id === car.id &&
                    v.submission_id &&
                    ["approved", "pending_review"].includes(v.status) ? (
                      <div className="mt-3">
                        <VehicleDecisionActions
                          applicationId={application!.id}
                          vehicleId={car.id}
                          submissionId={v.submission_id}
                          documentFileIds={v.document_file_ids ?? {}}
                          status={v.status}
                        />
                      </div>
                    ) : null}
                  </div>
                ))
              )}
              <Pagination
                total={cars.data.total}
                limit={25}
                offset={offset(query.cars_offset)}
                hrefFor={(n) => hrefFor("cars_offset", n, "cars")}
              />
            </>
          )}
          <details className="mt-4">
            <summary className="text-cyan cursor-pointer">Add car</summary>
            <div className="mt-4">
              <VehicleForm users={[{ id: userId, label: person.full_name }]} fixedUserId={userId} />
            </div>
          </details>
        </HubSection>
        <HubSection id="phone" title="Phone">
          <p>{person.phone ?? "No phone recorded"}</p>
        </HubSection>
        <HubSection id="jobs" title="Campaign jobs">
          {!jobs.data ? (
            id ? (
              <QueueUnavailable />
            ) : (
              <p>No campaign jobs recorded.</p>
            )
          ) : (
            <>
              {!jobs.data.items.length ? (
                <p>No campaign jobs recorded.</p>
              ) : (
                jobs.data.items.map((job) => (
                  <div key={job.id} className="border-edge mb-3 rounded-lg border p-3">
                    <Link
                      className="text-cyan font-medium"
                      href={`/admin/campaigns/${job.campaign_id}?job=${job.id}#drivers`}
                    >
                      {job.campaign?.name ?? "Campaign"}
                    </Link>
                    <p className="my-2 text-sm">
                      {job.vehicle?.plate_number ?? "No car recorded"} ·{" "}
                      {adminStatus(job.status, "job")} · Offered {formatDate(job.offered_at)}
                    </p>
                    {job.activated_at ? (
                      <p className="text-muted text-sm">Started {formatDate(job.activated_at)}</p>
                    ) : null}
                    {job.deactivated_at ? (
                      <p className="text-muted text-sm">Stopped {formatDate(job.deactivated_at)}</p>
                    ) : null}
                    {job.cancelled_at ? (
                      <p className="text-muted text-sm">Cancelled {formatDate(job.cancelled_at)}</p>
                    ) : null}
                    {["offered", "accepted", "active"].includes(job.status) ? (
                      <CancelAssignmentButton
                        assignmentId={job.id}
                        assignmentLabel={job.campaign?.name ?? "this job"}
                      />
                    ) : null}
                  </div>
                ))
              )}
              <Pagination
                total={jobs.data.total}
                limit={25}
                offset={offset(query.jobs_offset)}
                hrefFor={(n) => hrefFor("jobs_offset", n, "jobs")}
              />
            </>
          )}
          <details className="mt-4">
            <summary className="text-cyan cursor-pointer">Offer a job</summary>
            <div className="mt-4">
              <AssignmentForm driverId={id} />
            </div>
          </details>
        </HubSection>
        <HubSection id="trips-and-pay" title="Trips and pay">
          {id && (!trips.data || (currency && !balance)) ? (
            <QueueUnavailable />
          ) : (
            <>
              {currencies.length ? (
                <nav aria-label="Pay currency" className="mb-4 flex flex-wrap gap-3">
                  {currencies.map((value) => (
                    <Link
                      key={value}
                      aria-current={value === currency ? "page" : undefined}
                      className="text-cyan underline"
                      href={`${root}?${new URLSearchParams({ ...query, currency: value })}#trips-and-pay`}
                    >
                      {value}
                    </Link>
                  ))}
                </nav>
              ) : null}
              {balance ? (
                <dl className="mb-5 grid gap-3 sm:grid-cols-3">
                  {[
                    ["Ready for payout", balance.batch_payable],
                    ["Recorded as paid", balance.cash_paid],
                    ["Amount owed", balance.carry_forward_debt],
                  ].map(([label, amount]) => (
                    <div key={label}>
                      <dt className="text-muted text-sm">{label}</dt>
                      <dd className="font-mono">{formatMoneyExact(amount, balance.currency)}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
              {balance ? (
                <p className="text-muted mb-4 text-sm">
                  Transfer confirmation is separate; this total does not confirm money reached the
                  driver.
                </p>
              ) : null}
              <h3 className="mb-3 font-medium">Recent trip pay calculations</h3>
              {trips.data ? (
                <>
                  {!trips.data.items.length ? (
                    <p>No calculated trip pay recorded.</p>
                  ) : (
                    trips.data.items.map((trip) => (
                      <Link
                        key={trip.id}
                        href={`${root}?${new URLSearchParams({ ...query, trip: trip.trip_session_id })}#trips-and-pay`}
                        className="border-edge hover:bg-raised mb-2 block rounded-lg border p-3"
                      >
                        <p>
                          Trip date {formatDate(trip.trip_started_at)} · {trip.campaign_name} ·{" "}
                          {formatMoneyExact(trip.final_payout, trip.currency)}
                        </p>
                        <p className="text-muted text-sm">
                          {adminStatus(trip.ledger_entry?.status ?? trip.status)} · Calculated{" "}
                          {formatDate(trip.calculated_at)}
                        </p>
                      </Link>
                    ))
                  )}
                  <Pagination
                    total={trips.data.total}
                    limit={25}
                    offset={offset(query.trips_offset)}
                    hrefFor={(n) => hrefFor("trips_offset", n, "trips-and-pay")}
                  />
                </>
              ) : (
                <p>No calculated trip pay recorded.</p>
              )}
            </>
          )}
        </HubSection>
        <HubSection id="reviews" title="Reviews">
          {id && !reviews.data ? (
            <QueueUnavailable />
          ) : (
            <>
              {!reviews.data?.items.length ? (
                <p>No matching trip reviews.</p>
              ) : (
                reviews.data?.items.map((review) => (
                  <div
                    key={review.id}
                    className="border-edge mb-2 block rounded-lg border p-3"
                  >
                    <p>
                      {adminStatus(review.status, "review")} · {formatDate(review.created_at)}
                    </p>
                    <p className="text-muted text-sm">{review.description}</p>
                  </div>
                ))
              )}
              <Pagination
                total={reviews.data?.total ?? 0}
                limit={25}
                offset={offset(query.reviews_offset)}
                hrefFor={(n) => hrefFor("reviews_offset", n, "reviews")}
              />
            </>
          )}
        </HubSection>
        <HubSection id="activity" title="Activity">
          {id && !activity.data ? (
            <QueueUnavailable />
          ) : (
            <>
              {!activity.data?.items.length ? (
                <p>No activity recorded for this driver.</p>
              ) : (
                activity.data?.items.map((event) => (
                  <p className="mb-2 text-sm" key={event.id}>
                    {formatDate(event.created_at)} · {adminActivity(event.action)} ·{" "}
                    {event.actor_email ?? "System"}
                  </p>
                ))
              )}
              <Pagination
                total={activity.data?.total ?? 0}
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
          <p className="mt-2 break-all">
            Driver: {id} · Account: {userId} · Application:{" "}
            {application?.id ?? "No linked application"}
          </p>
        </details>
      </div>
      {selectedTrip ? (
        <HubDrawer
          title={`Trip pay · ${formatDate(selectedTrip.calculated_at)}`}
          closeHref={`${root}?${new URLSearchParams(Object.entries(query).filter(([key]) => key !== "trip"))}#trips-and-pay`}
        >
          <p className="mb-4">
            {formatMoneyExact(selectedTrip.final_payout, selectedTrip.currency)} ·{" "}
            {adminStatus(selectedTrip.ledger_entry?.status ?? selectedTrip.status)}
          </p>
          <ProcessTripForm tripId={selectedTrip.trip_session_id} />
          <details className="mt-4">
            <summary>Technical reference</summary>
            <p>{selectedTrip.trip_session_id}</p>
            <pre className="overflow-auto text-xs">
              {JSON.stringify(selectedTrip.metadata, null, 2)}
            </pre>
          </details>
        </HubDrawer>
      ) : query.trip && trips.data ? (
        <p role="alert">
          That trip is not in the current driver’s results. Return to Trips and pay to select it.
        </p>
      ) : null}
    </div>
  );
}
