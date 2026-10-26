import { JobArtwork } from "./job-artwork";
import { frozenJob } from "@/lib/driver/frozen-job";
import { CampaignMap } from "@/components/campaigns/campaign-map";

export function JobVisual({
  job,
  assignmentId,
  compact = false,
}: {
  job: ReturnType<typeof frozenJob>;
  assignmentId?: string;
  compact?: boolean;
}) {
  return (
    <div className="border-edge mt-4 overflow-hidden rounded-2xl border">
      <h3 className="bg-[#f8f3e7] px-4 pt-4 pb-3 text-base font-semibold">
        The advert on your car
      </h3>
      <JobArtwork
        key={assignmentId ?? "unavailable"}
        assignmentId={assignmentId}
        kind={job.artworkKind}
        compact={compact}
      />
      {job.mapAreas ? (
        <div className="border-edge h-48 overflow-hidden border-t" aria-label="Your job area map">
          <CampaignMap areas={job.mapAreas} />
        </div>
      ) : null}
      <section aria-label="Job areas" className="bg-[#f3f8f0] p-4">
        <h3 className="text-sm font-semibold">Where to drive</h3>
        {job.areas ? (
          <ul className="mt-2 flex flex-wrap gap-2">
            {job.areas.map((name) => (
              <li
                key={name}
                className="border-green/15 rounded-full border bg-white px-3 py-1.5 text-sm"
              >
                {name}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted mt-2 text-sm">
            Your job areas couldn&apos;t be loaded. Check Jobs or contact Terrax Media.
          </p>
        )}
        {job.excluded === null ? (
          <p className="text-muted mt-3 text-sm">
            Areas to avoid couldn&apos;t be loaded. Check Jobs or contact Terrax Media before
            driving.
          </p>
        ) : job.excluded.length ? (
          <div className="mt-4">
            <h3 className="text-sm font-semibold">Avoid</h3>
            <ul className="mt-2 flex flex-wrap gap-2">
              {job.excluded.map((name) => (
                <li
                  key={name}
                  className="rounded-full border border-[#edc8cd] bg-[#fff1f2] px-3 py-1.5 text-sm text-[#9c2330]"
                >
                  {name}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
    </div>
  );
}
