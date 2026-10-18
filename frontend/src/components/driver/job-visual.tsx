import Image from "next/image";
import { frozenJob } from "@/lib/driver/frozen-job";

/** Phase 1 uses a local vehicle illustration until the scoped artwork API arrives. */
export function JobVisual({ terms, compact = false }: { terms: unknown; compact?: boolean }) {
  const job = frozenJob(terms);
  return (
    <div className="border-edge mt-4 overflow-hidden rounded-2xl border">
      <Image
        src="/marketing/terrax/hero-vehicle-placeholder.svg"
        width={1024}
        height={1280}
        alt="Illustration of a car carrying an advert"
        className={`w-full object-cover object-[center_95%] ${compact ? "h-28" : "h-36"}`}
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
