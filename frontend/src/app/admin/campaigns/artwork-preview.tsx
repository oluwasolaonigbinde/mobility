"use client";
import Image from "next/image";
import { useEffect, useState, useTransition } from "react";
import { previewOperatorArtwork } from "../queue-options";

export function ArtworkPreview({ fileId, name }: { fileId: string; name: string }) {
  const [result, setResult] = useState<{ url?: string; error?: string }>();
  const [pending, start] = useTransition();
  useEffect(() => {
    if (!result?.url) return;
    const timer = window.setTimeout(() => setResult(undefined), 60_000);
    return () => window.clearTimeout(timer);
  }, [result]);
  return (
    <div className="my-3">
      <button
        type="button"
        className="text-cyan text-sm underline"
        disabled={pending}
        onClick={() => start(async () => setResult(await previewOperatorArtwork(fileId)))}
      >
        {pending ? "Opening artwork…" : "View artwork"}
      </button>
      {result?.url ? (
        <Image
          src={result.url}
          alt={name}
          width={480}
          height={320}
          unoptimized
          className="mt-3 max-w-full rounded object-contain"
        />
      ) : null}
      {result?.error ? <p role="alert">{result.error}</p> : null}
    </div>
  );
}
