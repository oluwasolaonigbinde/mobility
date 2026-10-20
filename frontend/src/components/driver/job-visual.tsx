import { JobArtwork } from "./job-artwork";
import { frozenJob } from "@/lib/driver/frozen-job";

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
      <JobArtwork
        key={assignmentId ?? "unavailable"}
        assignmentId={assignmentId}
        kind={job.artworkKind}
        compact={compact}
      />
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
          <p className="text-muted mt-3 text-sm">Avoid: {job.excluded.join(", ")}</p>
        ) : null}
      </section>
    </div>
  );
}
