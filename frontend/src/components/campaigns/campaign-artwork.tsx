"use client";

import Image from "next/image";
import { useState } from "react";

/** Authenticated artwork never falls back to an unreviewed external asset URL. */
export function CampaignArtwork({
  fileId,
  name,
  className = "",
}: {
  fileId?: string | null;
  name: string;
  className?: string;
}) {
  const [failedFile, setFailedFile] = useState<string | null>(null);
  const actual = fileId && fileId !== failedFile;
  return (
    <Image
      src={
        actual
          ? `/api/advertiser/artwork/${fileId}`
          : "/marketing/terrax/hero-vehicle-placeholder.svg"
      }
      alt={actual ? `${name} artwork` : "Illustration of a car carrying an advertising panel"}
      width={1024}
      height={actual ? 720 : 1280}
      unoptimized
      className={`campaign-artwork ${className}`}
      onError={() => {
        if (fileId) setFailedFile(fileId);
      }}
    />
  );
}
