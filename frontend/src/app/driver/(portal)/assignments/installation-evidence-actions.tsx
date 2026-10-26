"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { FilePicker, type FilePickerState } from "@/components/ui/file-picker";
import { installationViewLabel } from "@/lib/assignments/installation-views";
import { postJson, uploadInstallationImage } from "@/lib/files/installation-evidence-upload";

const PHOTO_TYPES = "image/png,image/jpeg,image/webp";

function deviceId(): string {
  const key = "cardvert-installation-device-id";
  const existing = window.localStorage.getItem(key);
  if (existing) return existing;
  const created = crypto.randomUUID();
  window.localStorage.setItem(key, created);
  return created;
}

/** Weekly installation photos for staff approval. */
export function InstallationEvidenceActions({
  assignmentId,
  status,
  requiredViews,
  latestEvidenceStatus,
  rejectionReason,
  approvedUntil,
}: {
  assignmentId: string;
  status: string;
  requiredViews: string[];
  latestEvidenceStatus?: string;
  rejectionReason?: string;
  approvedUntil?: string;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string>();
  const [done, setDone] = useState<string>();
  const [files, setFiles] = useState<Record<string, File>>({});
  const [fileStates, setFileStates] = useState<Record<string, FilePickerState>>({});

  const [now] = useState(() => Date.now());

  const maySubmit = ["accepted", "active", "deactivated"].includes(status);
  const approved =
    latestEvidenceStatus === "approved" &&
    (!approvedUntil || new Date(approvedUntil).getTime() > now);
  const inReview = latestEvidenceStatus === "pending_review";
  const showUpload = !inReview && !approved;

  function submitEvidence() {
    setError(undefined);
    setDone(undefined);
    startTransition(async () => {
      try {
        const missing = requiredViews.filter((view) => !files[view]);
        if (missing.length) {
          throw new Error(
            `Add these photos before sending: ${missing.map(installationViewLabel).join(", ")}.`,
          );
        }
        const photos = [];
        for (const view of requiredViews) {
          setFileStates((current) => ({ ...current, [view]: "uploading" }));
          try {
            photos.push({
              view,
              stored_file_id: await uploadInstallationImage(files[view]!, {
                onStatus: () => setFileStates((current) => ({ ...current, [view]: "checking" })),
              }),
            });
          } catch (caught) {
            setFileStates((current) => ({ ...current, [view]: "failed" }));
            throw caught;
          }
          setFileStates((current) => ({ ...current, [view]: "uploaded" }));
        }
        await postJson(`/api/driver/assignments/${assignmentId}/installation-evidence`, {
          client_request_id: crypto.randomUUID(),
          device_id: deviceId(),
          captured_at: new Date().toISOString(),
          photos,
          metadata: { capture_surface: "driver_pwa" },
        });
        setDone("Photos sent to Terrax Media for review.");

        router.refresh();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Photos could not be sent.");
      }
    });
  }

  if (!maySubmit) return null;
  return (
    <div className="mt-4 flex flex-col gap-3">
      {!approved && !inReview ? (
        <section
          aria-labelledby={`installation-photos-${assignmentId}`}
          className="border-edge bg-raised rounded-lg border p-3"
        >
          <h4 id={`installation-photos-${assignmentId}`} className="text-sm font-semibold">
            Installation photos
          </h4>
          {latestEvidenceStatus === "rejected" && rejectionReason?.trim() ? (
            <p className="mt-2 text-sm leading-5">{rejectionReason}</p>
          ) : null}
          <p className="text-muted mt-1 text-sm leading-5">
            {latestEvidenceStatus === "expired"
              ? "New photos are due. Take one photo of each side of the car."
              : latestEvidenceStatus === "rejected"
                ? "Your last photos weren't approved. Take new ones of each side of the car."
                : "Take one photo of each side of the car so Terrax Media can approve the advert."}
          </p>
          {showUpload ? (
            <div className="mt-3 flex flex-col gap-3">
              {requiredViews.map((view) => (
                <FilePicker
                  key={view}
                  label={installationViewLabel(view)}
                  accept={PHOTO_TYPES}
                  capture="environment"
                  disabled={pending}
                  state={fileStates[view] ?? "idle"}
                  onFile={(file) => {
                    setFiles((current) => {
                      const next = { ...current };
                      if (file) next[view] = file;
                      else delete next[view];
                      return next;
                    });
                    setFileStates((current) => ({ ...current, [view]: "idle" }));
                  }}
                />
              ))}
              <Button
                type="button"
                disabled={pending}
                onClick={submitEvidence}
                className="h-11 w-full"
              >
                {pending ? "Sending…" : "Send installation photos"}
              </Button>
            </div>
          ) : null}
        </section>
      ) : null}

      <div aria-live="polite">
        {error ? (
          <p role="alert" className="text-coral text-sm">
            {error}
          </p>
        ) : null}
        {done ? <p className="text-green text-sm">✓ {done}</p> : null}
      </div>
    </div>
  );
}
