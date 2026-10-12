import type { Metadata } from "next";
import { requireRole } from "@/lib/auth/current-user";
import { loadDriverCampaignJourney } from "@/lib/driver/load-campaign-journey";
import { TripTracker } from "./trip-tracker";

export const metadata: Metadata = { title: "Track" };
export default async function DriverTrackPage() {
  const me = await requireRole("driver");
  const work = await loadDriverCampaignJourney();
  return (
    <div className="animate-rise flex flex-col gap-4">
      <h1 className="font-display text-2xl font-semibold">Track</h1>
      <TripTracker
        assignment={work.trackerAssignment}
        initialTrip={work.currentTrip}
        driverId={me.user.id}
        startUnavailableMessage={
          work.journey.steps.find((step) => step.state !== "complete" && step.id !== "tracking")
            ?.title ?? "Check Jobs before starting."
        }
        pausedCampaignName={work.activationAssignment?.campaignName}
      />
    </div>
  );
}
