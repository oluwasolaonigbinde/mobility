import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { requireRole } from "@/lib/auth/current-user";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { formatMoney } from "@/lib/format";
import { Panel } from "@/components/ui/panel";
import { DriverDataUnavailable } from "@/components/driver/data-unavailable";
import { FreshDriverAuthority } from "@/components/driver/fresh-authority";
import { PhonePrompt } from "@/components/driver/phone-prompt";
import { loadDriverCampaignJourney } from "@/lib/driver/load-campaign-journey";
import { loadDailyEarnings } from "@/lib/driver/load-daily-earnings";
import { watDay } from "@/lib/driver/daily-earnings";
import { TripTracker } from "./track/trip-tracker";
import { InstallationEvidenceActions } from "./assignments/installation-evidence-actions";
import { JobVisual } from "@/components/driver/job-visual";
import { frozenJob } from "@/lib/driver/frozen-job";

export const metadata: Metadata = { title: "Home" };
const actionClass =
  "bg-amber text-accent-ink inline-flex h-14 w-full items-center justify-center rounded-lg text-base font-medium";

export default async function DriverHomePage() {
  const me = await requireRole("driver");
  const api = createApiClient(await getSessionToken());
  const [work, earnings] = await Promise.all([loadDriverCampaignJourney(), loadDailyEarnings(api)]);
  if (earnings.state === "auth") redirect("/login");
  const assignment = work.activationAssignment;
  const next =
    work.journey.steps.find((step) => step.state === "degraded") ??
    work.journey.steps.find((step) => step.state !== "complete" && step.id !== "tracking");
  const now = new Date();
  const today = watDay(now);
  const yesterday = watDay(new Date(now.getTime() - 86400000));
  const days = earnings.state === "ready" ? earnings.data : null;
  const todayDays = days?.filter((day) => day.day === today && Number(day.amount) !== 0) ?? [];
  const lastPaid = days
    ?.filter((day) => day.paidAt && Number(day.amount) > 0)
    .sort((a, b) => Date.parse(b.paidAt!) - Date.parse(a.paidAt!))[0];
  const lastPaidLabel =
    lastPaid?.paidAt && watDay(new Date(lastPaid.paidAt)) === yesterday
      ? "Paid yesterday"
      : lastPaid?.status;
  const photoDue =
    work.photoStatus === "display_required" && work.journey.canStart && !work.currentTrip;
  const noOffer = next?.id === "offer" && /^No (current|campaign) offer/.test(next.title);
  return (
    <FreshDriverAuthority
      refreshKey={crypto.randomUUID()}
      title="Reconnect to check today"
      detail="Your current job and earnings are hidden while offline."
      retryHref="/driver"
    >
      <div className="animate-rise flex flex-col gap-4">
        <div>
          <p className="text-ink mb-1 text-base font-medium">
            Hello, {me.user.full_name.split(" ")[0]}
          </p>
          <h1 className="font-display text-2xl font-semibold">
            {work.currentTrip
              ? "You’re on a trip now."
              : assignment
                ? "Here’s your current job."
                : noOffer
                  ? "No job yet."
                  : "Here’s your next step."}
          </h1>
        </div>
        <Panel className="p-5">
          <h2 className="font-display text-xl font-semibold">
            {assignment?.campaignName ?? "Your next job"}
          </h2>
          {assignment ? (
            <p className="text-ink mt-1 text-base">Car {assignment.plateNumber}</p>
          ) : null}
          {noOffer ? (
            <p className="text-ink mt-3 text-base leading-6">
              {work.needsServiceCity
                ? "Add the city you drive in so Terrax Media can find a job for you."
                : "You’re all set. We’ll message you when a job is ready."}
            </p>
          ) : null}
          {assignment ? (
            <JobVisual
              compact
              assignmentId={assignment.id}
              job={
                work.visualAssignment?.id === assignment.id
                  ? work.visualAssignment.job
                  : frozenJob(null)
              }
            />
          ) : null}
          <div className="mt-5">
            {work.currentTrip ? (
              <Link href="/driver/track" className={actionClass}>
                View live trip
              </Link>
            ) : photoDue ? (
              <InstallationEvidenceActions
                assignmentId={assignment!.id}
                status="active"
                requiredViews={[]}
                latestEvidenceStatus="approved"
                displayOnly
                primaryPhoto
              />
            ) : work.journey.canStart && work.photoStatus === "ready" ? (
              <TripTracker
                assignment={work.trackerAssignment}
                initialTrip={null}
                driverId={me.user.id}
                compact
              />
            ) : (
              <Link
                href={
                  work.photoStatus === "installation_required"
                    ? `/driver/assignments#photos-${assignment?.id}`
                    : noOffer && work.needsServiceCity
                      ? "/driver/profile"
                      : (next?.href ?? "/driver/assignments")
                }
                className={actionClass}
              >
                {work.journey.canStart && work.photoStatus === "unavailable"
                  ? "Check photo status"
                  : work.photoStatus === "installation_required"
                    ? "Send installation photos"
                    : noOffer
                      ? work.needsServiceCity
                        ? "Add your city"
                        : "See jobs"
                      : (next?.title ?? "See jobs")}
              </Link>
            )}
          </div>
        </Panel>
        {days === null ? (
          <DriverDataUnavailable
            title="Today’s earnings unavailable"
            detail="Try again to check your complete earnings history."
            retryHref="/driver"
          />
        ) : (
          <Panel className="p-5">
            {todayDays.length ? (
              todayDays.map((day) => (
                <div key={day.currency}>
                  <p className="font-display text-2xl font-semibold">
                    Today {formatMoney(day.amount, day.currency)}
                  </p>
                  {Number(day.amount) !== 0 ? (
                    <p className="text-muted mt-1 text-base">{day.status}</p>
                  ) : null}
                </div>
              ))
            ) : (
              <p className="font-display text-2xl font-semibold">
                {lastPaid
                  ? `${lastPaidLabel} ${formatMoney(lastPaid.amount, lastPaid.currency)}`
                  : days.length
                    ? "See your earnings"
                    : "No earnings yet"}
              </p>
            )}
            {todayDays.length && lastPaid ? (
              <p className="text-muted mt-3 text-base">
                {lastPaidLabel} · {formatMoney(lastPaid.amount, lastPaid.currency)}
              </p>
            ) : null}
            <Link
              href="/driver/earnings"
              className="text-amber mt-3 inline-block text-base font-medium"
            >
              Earnings
            </Link>
          </Panel>
        )}
        <PhonePrompt driverId={me.user.id} />
      </div>
    </FreshDriverAuthority>
  );
}
