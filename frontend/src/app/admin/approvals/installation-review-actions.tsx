"use client";

import { useActionState, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { reviewInstallationEvidenceAction, type CampaignReviewActionState } from "./actions";
import { DecisionButtons } from "./decision-buttons";

const initialState: CampaignReviewActionState = {};

// The backend only accepts sniffed JPEG, PNG and WebP installation evidence.
const VIEWABLE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const RETRIEVAL_FAILED = "The signed evidence photo could not be retrieved. Try again.";

type PhotoResult = { blob: Blob } | { error: string };

/**
 * Issues an audited signed read through the BFF, then retrieves the private
 * bytes directly so they render as a same-page blob: image (production CSP
 * allows blob: images and connect-src to object storage, never remote images).
 */
async function loadEvidencePhoto(fileId: string): Promise<PhotoResult> {
  let issued: Response;
  try {
    // Bodyless by contract: the BFF mutation boundary rejects any body or content type.
    issued = await fetch(`/api/admin/files/${fileId}/installation-review`, { method: "POST" });
  } catch {
    return { error: "Could not reach the evidence service. Try again." };
  }
  const body = (await issued.json().catch(() => undefined)) as
    { url?: string; error?: { message?: string } } | undefined;
  if (!issued.ok || !body?.url) {
    return { error: body?.error?.message ?? "The evidence photo could not be opened. Try again." };
  }
  let file: Response;
  try {
    // No custom headers, so the cross-origin read stays a simple CORS GET.
    file = await fetch(body.url, {
      cache: "no-store",
      credentials: "omit",
      referrerPolicy: "no-referrer",
    });
  } catch {
    return { error: RETRIEVAL_FAILED };
  }
  if (!file.ok) return { error: RETRIEVAL_FAILED };
  const blob = await file.blob().catch(() => undefined);
  if (!blob) return { error: RETRIEVAL_FAILED };
  if (!VIEWABLE_TYPES.has(blob.type))
    return { error: "The evidence file is not a viewable image." };
  return { blob };
}

function viewLabel(view: string): string {
  const label = view.replaceAll("_", " ");
  return label.charAt(0).toUpperCase() + label.slice(1);
}

export function InstallationReviewActions({
  submissionId,
  photos,
}: {
  submissionId: string;
  photos: { view: string; stored_file_id: string }[];
}) {
  const [state, formAction] = useActionState(reviewInstallationEvidenceAction, initialState);
  const [openingFileId, setOpeningFileId] = useState<string>();
  const [preview, setPreview] = useState<{ view: string; url: string }>();
  const [previewError, setPreviewError] = useState<string>();
  const latestRequest = useRef(0);

  useEffect(() => {
    if (!preview) return;
    return () => URL.revokeObjectURL(preview.url);
  }, [preview]);

  useEffect(() => {
    const request = latestRequest;
    return () => {
      request.current += 1;
    };
  }, []);

  async function openPhoto(photo: { view: string; stored_file_id: string }) {
    const requestId = ++latestRequest.current;
    setOpeningFileId(photo.stored_file_id);
    setPreviewError(undefined);
    setPreview(undefined);
    const result = await loadEvidencePhoto(photo.stored_file_id);
    if (requestId !== latestRequest.current) return;
    setOpeningFileId(undefined);
    if ("error" in result) {
      setPreviewError(result.error);
      return;
    }
    setPreview({ view: photo.view, url: URL.createObjectURL(result.blob) });
  }

  return (
    <form action={formAction} className="flex w-full max-w-sm flex-col items-end gap-2">
      <input type="hidden" name="submission_id" value={submissionId} />
      <div className="flex w-full flex-wrap gap-2">
        {photos.map((photo) => (
          <Button
            key={photo.stored_file_id}
            type="button"
            variant="ghost"
            className="h-8 px-2 text-xs capitalize"
            disabled={openingFileId !== undefined}
            onClick={() => openPhoto(photo)}
          >
            {openingFileId === photo.stored_file_id
              ? "Opening…"
              : `View ${photo.view.replaceAll("_", " ")}`}
          </Button>
        ))}
      </div>
      {previewError ? (
        <p role="alert" className="text-coral w-full text-xs">
          {previewError}
        </p>
      ) : null}
      {preview ? (
        <figure className="border-edge bg-bg w-full rounded-lg border p-2">
          {/* eslint-disable-next-line @next/next/no-img-element -- private blob: evidence cannot use the image optimizer */}
          <img
            src={preview.url}
            alt={`${viewLabel(preview.view)} installation evidence`}
            className="max-h-80 w-full rounded object-contain"
          />
          <figcaption className="mt-2 flex items-center justify-between gap-2">
            <span className="micro text-muted">{viewLabel(preview.view)} view</span>
            <Button
              type="button"
              variant="ghost"
              className="h-7 px-2 text-xs"
              aria-label="Close photo"
              onClick={() => setPreview(undefined)}
            >
              Close
            </Button>
          </figcaption>
        </figure>
      ) : null}
      <label className="flex w-full flex-col gap-1">
        <span className="micro text-muted">Rejection reason</span>
        <textarea
          name="reason"
          maxLength={2000}
          aria-label="Installation evidence rejection reason"
          placeholder="Explain which installation view must change"
          className="border-edge bg-raised text-ink focus:border-amber min-h-20 w-full rounded-lg border px-3 py-2 text-sm focus:outline-none"
        />
      </label>
      <DecisionButtons />
      <div aria-live="polite">
        {state.error ? (
          <p role="alert" className="text-coral text-right text-xs">
            {state.error}
          </p>
        ) : null}
        {state.done && !state.error ? (
          <p className="text-green text-right text-xs">✓ {state.done}</p>
        ) : null}
      </div>
    </form>
  );
}
