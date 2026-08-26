"use client";

import { useActionState, useState } from "react";
import { Button } from "@/components/ui/button";
import { reviewInstallationEvidenceAction, type CampaignReviewActionState } from "./actions";

const initialState: CampaignReviewActionState = {};

export function InstallationReviewActions({
  submissionId,
  photos,
}: {
  submissionId: string;
  photos: { view: string; stored_file_id: string }[];
}) {
  const [state, formAction, pending] = useActionState(
    reviewInstallationEvidenceAction,
    initialState,
  );
  const [previewError, setPreviewError] = useState<string>();

  async function openPhoto(fileId: string) {
    setPreviewError(undefined);
    const response = await fetch(`/api/admin/files/${fileId}/installation-review`, {
      method: "POST",
    });
    const body = (await response.json()) as {
      url?: string;
      error?: { message?: string };
    };
    if (!response.ok || !body.url) {
      setPreviewError(body.error?.message ?? "The evidence photo could not be opened.");
      return;
    }
    window.open(body.url, "_blank", "noopener,noreferrer");
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
            onClick={() => openPhoto(photo.stored_file_id)}
          >
            View {photo.view.replaceAll("_", " ")}
          </Button>
        ))}
      </div>
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
      <div className="flex gap-2">
        <Button
          type="submit"
          name="intent"
          value="approve"
          disabled={pending}
          className="h-9 px-3 text-xs"
        >
          {pending ? "Reviewing…" : "Approve"}
        </Button>
        <Button
          type="submit"
          name="intent"
          value="reject"
          variant="danger"
          disabled={pending}
          className="h-9 px-3 text-xs"
        >
          Reject
        </Button>
      </div>
      <div aria-live="polite">
        {previewError || state.error ? (
          <p role="alert" className="text-coral text-right text-xs">
            {previewError ?? state.error}
          </p>
        ) : null}
        {state.done && !state.error ? (
          <p className="text-green text-right text-xs">✓ {state.done}</p>
        ) : null}
      </div>
    </form>
  );
}
