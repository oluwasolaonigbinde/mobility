"use client";
import Image from "next/image";
import { useState } from "react";

export function JobArtwork({
  assignmentId,
  kind,
  compact,
}: {
  assignmentId?: string;
  kind: "image" | "document" | "video" | null;
  compact: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const source = assignmentId ? `/api/driver/jobs/${assignmentId}/artwork` : null;
  return (
    <div>
      <div className={`relative overflow-hidden ${compact ? "h-28" : "h-36"}`}>
        {!loaded ? (
          <Image
            src="/marketing/terrax/hero-vehicle-placeholder.svg"
            width={1024}
            height={1280}
            alt="Illustration of a car carrying an advert"
            className="h-full w-full object-cover object-[center_95%]"
          />
        ) : null}
        {source && kind === "image" && !failed ? (
          // eslint-disable-next-line @next/next/no-img-element -- authenticated no-store preview; never give a signed URL to the image optimizer
          <img
            src={source}
            loading="lazy"
            alt={loaded ? "Advert for this job" : ""}
            className={`absolute inset-0 h-full w-full object-cover ${loaded ? "" : "opacity-0"}`}
            onLoad={() => setLoaded(true)}
            onError={() => {
              setFailed(true);
              setLoaded(false);
            }}
          />
        ) : null}
      </div>
      {source && (kind === "document" || kind === "video") ? (
        <a
          className="text-green inline-block p-3 text-sm underline"
          href={source}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open this job’s advert
        </a>
      ) : null}
    </div>
  );
}
