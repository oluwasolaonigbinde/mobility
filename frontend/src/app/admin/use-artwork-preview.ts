"use client";
import { useEffect, useRef, useState } from "react";
import { previewOperatorArtwork } from "./queue-options";

// Admin artwork previews render as same-page blob: images. The production CSP
// allows connect-src to object storage but never remote images, so the signed
// URL is read with fetch and never placed in an <img> src.
const VIEWABLE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const UNAVAILABLE = "Artwork preview is unavailable.";
const PREVIEW_LIFETIME_MS = 60_000;

export type ArtworkPreviewState = { url?: string; isPdf?: boolean; error?: string };

async function loadArtwork(fileId: string): Promise<{ blob: Blob } | { error: string }> {
  try {
    const issued = await previewOperatorArtwork(fileId);
    if (issued.error || !issued.url) return { error: issued.error ?? UNAVAILABLE };
    const file = await fetch(issued.url, {
      cache: "no-store",
      credentials: "omit",
      referrerPolicy: "no-referrer",
    });
    if (!file.ok) return { error: UNAVAILABLE };
    const blob = await file.blob();
    if (!VIEWABLE_TYPES.has(blob.type) && blob.type !== "application/pdf") {
      return { error: UNAVAILABLE };
    }
    return { blob };
  } catch {
    return { error: UNAVAILABLE };
  }
}

export function useArtworkPreview() {
  const [preview, setPreview] = useState<ArtworkPreviewState>();
  const [loading, setLoading] = useState(false);
  const latest = useRef(0);

  useEffect(() => {
    const url = preview?.url;
    if (!url) return;
    const timer = window.setTimeout(() => setPreview(undefined), PREVIEW_LIFETIME_MS);
    return () => {
      window.clearTimeout(timer);
      URL.revokeObjectURL(url);
    };
  }, [preview]);

  useEffect(() => {
    const request = latest;
    return () => {
      request.current += 1;
    };
  }, []);

  async function open(fileId: string) {
    const id = ++latest.current;
    setLoading(true);
    setPreview(undefined);
    const result = await loadArtwork(fileId);
    if (id !== latest.current) return;
    setLoading(false);
    setPreview(
      "error" in result
        ? { error: result.error }
        : {
            url: URL.createObjectURL(result.blob),
            isPdf: result.blob.type === "application/pdf",
          },
    );
  }

  function clear() {
    latest.current += 1;
    setLoading(false);
    setPreview(undefined);
  }

  return { preview, loading, open, clear };
}
