"use client";

import { useState } from "react";

/** The approved illustration, with the real authenticated artwork fitted to its panel. */
export function VanPreview({
  source,
  label = "Your advert on a car",
  terrax = false,
}: {
  source?: string | null;
  label?: string;
  terrax?: boolean;
}) {
  const [failed, setFailed] = useState<string | null>(null);
  return (
    <svg
      viewBox="0 0 640 300"
      role="img"
      aria-label={source && failed === source ? "Artwork preview unavailable" : label}
      className="van-preview"
      preserveAspectRatio="xMidYMid meet"
    >
      <image href="/portal/van-scene.svg" width="640" height="300" />
      {terrax ? (
        <image href="/portal/terrax-panel.svg" x="123.7" y="109.3" width="230.5" height="73.2" />
      ) : source && failed !== source ? (
        <>
          <rect x="123.7" y="109.3" width="230.5" height="73.2" fill="#ffffff" />
          <image
            href={source}
            x="123.7"
            y="109.3"
            width="230.5"
            height="73.2"
            preserveAspectRatio="xMidYMid slice"
            onError={() => setFailed(source)}
          />
        </>
      ) : null}
      {source && failed === source ? (
        <text x="320" y="282" textAnchor="middle" fontSize="22" fill="#ffffff">
          Artwork preview unavailable
        </text>
      ) : null}
    </svg>
  );
}
