"use client";

import { useActionState, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { uploadCreativeFile, type CreativeUploadPhase } from "@/lib/files/creative-upload";
import {
  replaceCreativeAndSubmitAction,
  submitCreativeForReviewAction,
  type CampaignReviewActionState,
} from "./actions";

export function CreativeStatusActions({
  campaignId,
  creativeId,
  status,
}: {
  campaignId: string;
  creativeId: string;
  status: string;
}) {
  const initialState: CampaignReviewActionState = {};
  const [state, formAction, pending] = useActionState(submitCreativeForReviewAction, initialState);
  const [replaceState, replaceAction, replacing] = useActionState(
    replaceCreativeAndSubmitAction,
    initialState,
  );
  const [replacement, setReplacement] = useState<{
    storedFileId?: string;
    creativeType?: "image" | "video" | "other";
    phase?: CreativeUploadPhase;
    error?: string;
  }>({});
  const uploadRequest = useRef<{ fingerprint: string; id: string } | undefined>(undefined);

  async function uploadReplacement(file: File | undefined) {
    if (!file) return;
    const fingerprint = `${file.name}:${file.type}:${file.size}:${file.lastModified}`;
    if (uploadRequest.current?.fingerprint !== fingerprint) {
      uploadRequest.current = { fingerprint, id: crypto.randomUUID() };
    }
    setReplacement({ phase: "hashing" });
    try {
      const uploaded = await uploadCreativeFile(file, (phase) => setReplacement({ phase }), {
        clientRequestId: uploadRequest.current.id,
      });
      setReplacement({
        phase: "clean",
        storedFileId: uploaded.storedFileId,
        creativeType: uploaded.creativeType,
      });
    } catch (error) {
      setReplacement({
        error: error instanceof Error ? error.message : "The replacement upload failed. Retry it.",
      });
    }
  }

  if (status === "pending_review") {
    return <p className="micro text-amber text-right">Under admin review</p>;
  }
  if (status === "approved") {
    return <p className="micro text-green text-right">Admin approved</p>;
  }
  if (status !== "draft" && status !== "rejected") {
    return null;
  }

  return (
    <div className="flex max-w-72 flex-col items-end gap-2">
      <form action={formAction} className="flex flex-col items-end gap-1.5">
        <input type="hidden" name="campaign_id" value={campaignId} />
        <input type="hidden" name="creative_id" value={creativeId} />
        <Button type="submit" disabled={pending} className="h-8 px-3 text-xs">
          {pending
            ? "Submitting…"
            : status === "rejected"
              ? "Resubmit current artwork"
              : "Submit creative"}
        </Button>
        {state.error ? (
          <p role="alert" className="text-coral max-w-56 text-right text-xs">
            {state.error}
          </p>
        ) : null}
        {state.done && !state.error ? (
          <p className="text-green max-w-56 text-right text-xs">✓ {state.done}</p>
        ) : null}
      </form>
      <label className="micro text-muted text-right">
        Replace artwork
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp,video/mp4,application/pdf"
          className="border-edge mt-1 block w-full rounded border p-1 text-xs"
          onChange={(event) => void uploadReplacement(event.currentTarget.files?.[0])}
        />
      </label>
      {replacement.phase ? (
        <p className="text-muted text-right text-xs" aria-live="polite">
          {replacement.phase === "clean"
            ? "✓ Replacement passed security scan"
            : `${replacement.phase}…`}
        </p>
      ) : null}
      {replacement.error ? (
        <p role="alert" className="text-coral text-right text-xs">
          {replacement.error}
        </p>
      ) : null}
      {replacement.storedFileId && replacement.creativeType ? (
        <form action={replaceAction} className="flex flex-col items-end gap-1.5">
          <input type="hidden" name="campaign_id" value={campaignId} />
          <input type="hidden" name="creative_id" value={creativeId} />
          <input type="hidden" name="stored_file_id" value={replacement.storedFileId} />
          <input type="hidden" name="creative_type" value={replacement.creativeType} />
          <Button type="submit" disabled={replacing} className="h-8 px-3 text-xs">
            {replacing ? "Replacing…" : "Replace and submit"}
          </Button>
          {replaceState.error ? (
            <p role="alert" className="text-coral max-w-56 text-right text-xs">
              {replaceState.error}
            </p>
          ) : null}
          {replaceState.done ? (
            <p className="text-green max-w-56 text-right text-xs">✓ {replaceState.done}</p>
          ) : null}
        </form>
      ) : null}
    </div>
  );
}
