"use client";
import { useArtworkPreview } from "../use-artwork-preview";

export function ArtworkPreview({ fileId, name }: { fileId: string; name: string }) {
  const { preview, loading, open } = useArtworkPreview();
  return (
    <div className="my-3">
      <button
        type="button"
        className="text-cyan text-sm underline"
        disabled={loading}
        onClick={() => open(fileId)}
      >
        {loading ? "Opening artwork…" : "View artwork"}
      </button>
      {preview?.url && preview.isPdf ? (
        <a
          href={preview.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-cyan mt-3 block text-sm underline"
        >
          Open PDF artwork
        </a>
      ) : preview?.url ? (
        /* eslint-disable-next-line @next/next/no-img-element -- private blob: artwork cannot use the image optimizer */
        <img
          src={preview.url}
          alt={name}
          width={480}
          height={320}
          className="mt-3 max-w-full rounded object-contain"
        />
      ) : null}
      {preview?.error ? <p role="alert">{preview.error}</p> : null}
    </div>
  );
}
