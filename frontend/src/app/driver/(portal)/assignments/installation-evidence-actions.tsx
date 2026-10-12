"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { FilePicker, type FilePickerState } from "@/components/ui/file-picker";
import { installationViewLabel } from "@/lib/assignments/installation-views";
import { formatDate, formatDateTime } from "@/lib/format";
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

/**
 * The driver's photo tasks for one job: the installation photos Compliance approves (client
 * answers item 4), and the display photo Start needs before each shift once those are approved.
 */
export function InstallationEvidenceActions({
  assignmentId,
  status,
  requiredViews,
  latestEvidenceStatus,
  approvedUntil,
  pendingChallengeDueAt,
  proofAvailable = true,
  displayDue = true,
  displayOnly = false,
  primaryPhoto = false,
}: {
  assignmentId: string;
  status: string;
  requiredViews: string[];
  latestEvidenceStatus?: string;
  approvedUntil?: string;
  pendingChallengeDueAt?: string;
  /** Display proof needs its own configured windows (still an open policy input). */
  proofAvailable?: boolean;
  displayDue?: boolean;
  displayOnly?: boolean;
  primaryPhoto?: boolean;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string>();
  const [done, setDone] = useState<string>();
  const [files, setFiles] = useState<Record<string, File>>({});
  const [fileStates, setFileStates] = useState<Record<string, FilePickerState>>({});
  const [proofFile, setProofFile] = useState<File>();
  const [proofState, setProofState] = useState<FilePickerState>("idle");

  const [photoOpen, setPhotoOpen] = useState(!primaryPhoto);
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
        if (requiredViews.some((view) => !files[view])) {
          throw new Error("Add a photo for every view before sending.");
        }
        const photos = [];
        for (const view of requiredViews) {
          setFileStates((current) => ({ ...current, [view]: "uploading" }));
          try {
            photos.push({ view, stored_file_id: await uploadInstallationImage(files[view]!) });
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

  function submitProof() {
    setError(undefined);
    setDone(undefined);
    startTransition(async () => {
      try {
        if (!proofFile) throw new Error("Take a photo of the advert on your car first.");
        const boundDeviceId = deviceId();
        const challenge = await postJson<{
          challenge_id: string;
          nonce: string;
        }>(`/api/driver/assignments/${assignmentId}/display-proof/challenge`, {
          device_id: boundDeviceId,
        });
        setProofState("uploading");
        let storedFileId: string;
        try {
          storedFileId = await uploadInstallationImage(proofFile);
        } catch (caught) {
          setProofState("failed");
          throw caught;
        }
        setProofState("uploaded");
        await postJson(`/api/driver/assignments/${assignmentId}/display-proof`, {
          challenge_id: challenge.challenge_id,
          nonce: challenge.nonce,
          device_id: boundDeviceId,
          stored_file_id: storedFileId,
          metadata: { capture_surface: "driver_pwa" },
        });
        setDone("Display photo accepted. You can start your trip.");
        router.refresh();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "The display photo was not accepted.");
      }
    });
  }

  if (!maySubmit) return null;
  if (primaryPhoto && !photoOpen)
    return (
      <Button type="button" onClick={() => setPhotoOpen(true)} className="h-14 w-full text-base">
        Take today’s photo
      </Button>
    );
  return (
    <div className="mt-4 flex flex-col gap-3">
      {proofAvailable &&
      status === "active" &&
      approved &&
      (displayDue || pendingChallengeDueAt) ? (
        <section
          aria-labelledby={`display-photo-${assignmentId}`}
          className={
            pendingChallengeDueAt
              ? "border-amber/50 bg-amber/10 rounded-lg border p-3"
              : "border-edge bg-raised rounded-lg border p-3"
          }
        >
          <h4 id={`display-photo-${assignmentId}`} className="text-sm font-semibold">
            Today&apos;s display photo
          </h4>
          <p className="text-muted mt-1 text-sm leading-5">
            {pendingChallengeDueAt
              ? `Terrax Media asked for a new photo. Send it before ${formatDateTime(pendingChallengeDueAt)}.`
              : "Before each shift, take one photo showing the advert on your car. You need it to start a trip."}
          </p>
          <div className="mt-3">
            <FilePicker
              label="Photo of the advert on your car"
              accept={PHOTO_TYPES}
              capture="environment"
              disabled={pending}
              state={proofState}
              onFile={(file) => {
                setProofFile(file);
                setProofState("idle");
              }}
            />
          </div>
          <Button
            type="button"
            disabled={pending}
            onClick={submitProof}
            className="mt-3 h-11 w-full"
          >
            {pending ? "Sending…" : "Send display photo"}
          </Button>
        </section>
      ) : null}

      {!displayOnly && !approved && !inReview ? (
        <section
          aria-labelledby={`installation-photos-${assignmentId}`}
          className="border-edge bg-raised rounded-lg border p-3"
        >
          <h4 id={`installation-photos-${assignmentId}`} className="text-sm font-semibold">
            Installation photos
          </h4>
          {inReview ? (
            <p className="text-muted mt-1 text-sm">Terrax Media is checking your photos.</p>
          ) : approved ? (
            <p className="text-green mt-1 text-sm">
              Approved{approvedUntil ? ` until ${formatDate(approvedUntil)}` : ""}.
            </p>
          ) : (
            <p className="text-muted mt-1 text-sm leading-5">
              {latestEvidenceStatus === "expired"
                ? "New photos are due. Take one photo of each side of the car."
                : latestEvidenceStatus === "rejected"
                  ? "Your last photos weren't approved. Take new ones of each side of the car."
                  : "Take one photo of each side of the car so Terrax Media can approve the advert."}
            </p>
          )}
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
