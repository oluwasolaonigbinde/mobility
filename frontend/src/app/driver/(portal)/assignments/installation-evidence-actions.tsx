"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { postJson, uploadInstallationImage } from "@/lib/files/installation-evidence-upload";

function deviceId(): string {
  const key = "cardvert-installation-device-id";
  const existing = window.localStorage.getItem(key);
  if (existing) return existing;
  const created = crypto.randomUUID();
  window.localStorage.setItem(key, created);
  return created;
}

export function InstallationEvidenceActions({
  assignmentId,
  status,
  requiredViews,
  latestEvidenceStatus,
  pendingChallengeDueAt,
}: {
  assignmentId: string;
  status: string;
  requiredViews: string[];
  latestEvidenceStatus?: string;
  pendingChallengeDueAt?: string;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string>();
  const [done, setDone] = useState<string>();
  const [files, setFiles] = useState<Record<string, File>>({});
  const [proofFile, setProofFile] = useState<File>();

  const maySubmit = ["accepted", "active", "deactivated"].includes(status);
  const active = status === "active";

  function submitEvidence() {
    setError(undefined);
    setDone(undefined);
    startTransition(async () => {
      try {
        if (requiredViews.some((view) => !files[view])) {
          throw new Error("Add every required view before submitting.");
        }
        const photos = [];
        for (const view of requiredViews) {
          photos.push({ view, stored_file_id: await uploadInstallationImage(files[view]!) });
        }
        await postJson(`/api/driver/assignments/${assignmentId}/installation-evidence`, {
          client_request_id: crypto.randomUUID(),
          device_id: deviceId(),
          captured_at: new Date().toISOString(),
          photos,
          metadata: { capture_surface: "driver_pwa" },
        });
        setDone("Evidence submitted for operations review.");
        router.refresh();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Evidence could not be submitted.");
      }
    });
  }

  function submitProof() {
    setError(undefined);
    setDone(undefined);
    startTransition(async () => {
      try {
        if (!proofFile) throw new Error("Take or choose a current display photo.");
        const boundDeviceId = deviceId();
        const challenge = await postJson<{
          challenge_id: string;
          nonce: string;
        }>(`/api/driver/assignments/${assignmentId}/display-proof/challenge`, {
          device_id: boundDeviceId,
        });
        const storedFileId = await uploadInstallationImage(proofFile);
        await postJson(`/api/driver/assignments/${assignmentId}/display-proof`, {
          challenge_id: challenge.challenge_id,
          nonce: challenge.nonce,
          device_id: boundDeviceId,
          stored_file_id: storedFileId,
          metadata: { capture_surface: "driver_pwa" },
        });
        setDone("Display verified for this shift.");
        router.refresh();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Display proof could not be verified.");
      }
    });
  }

  if (!maySubmit) return null;
  return (
    <section className="border-edge bg-raised mt-4 rounded-lg border p-3">
      <p className="text-sm font-medium">Installation evidence</p>
      {pendingChallengeDueAt ? (
        <div className="border-amber/40 bg-amber/10 mt-2 rounded-lg border p-2" role="status">
          <p className="text-amber text-xs font-medium">Fresh display proof required</p>
          <p className="text-muted mt-1 text-xs">
            Complete the current-photo challenge before{" "}
            {new Date(pendingChallengeDueAt).toLocaleString()}. This verifies fresh assignment-bound
            evidence; phone GPS is not treated as proof that the branded vehicle moved.
          </p>
        </div>
      ) : null}
      <p className="text-muted mt-1 text-xs">
        Latest review: {latestEvidenceStatus?.replaceAll("_", " ") ?? "not submitted"}
      </p>
      {latestEvidenceStatus !== "pending_review" ? (
        <div className="mt-3 flex flex-col gap-3">
          {requiredViews.map((view) => (
            <label key={view} className="text-xs">
              <span className="mb-1 block capitalize">{view.replaceAll("_", " ")}</span>
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                capture="environment"
                disabled={pending}
                onChange={(event) => {
                  const file = event.currentTarget.files?.[0];
                  if (file) setFiles((current) => ({ ...current, [view]: file }));
                }}
                className="text-muted block w-full text-xs"
              />
            </label>
          ))}
          <Button type="button" disabled={pending} onClick={submitEvidence} className="h-10 w-full">
            {pending ? "Checking and uploading…" : "Submit installation photos"}
          </Button>
        </div>
      ) : (
        <p className="text-muted mt-3 text-xs">Operations review is pending.</p>
      )}
      {active && latestEvidenceStatus === "approved" ? (
        <div className="border-edge mt-4 border-t pt-3">
          <label className="text-xs">
            <span className="mb-1 block">Current display photo</span>
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              capture="environment"
              disabled={pending}
              onChange={(event) => setProofFile(event.currentTarget.files?.[0])}
              className="text-muted block w-full text-xs"
            />
          </label>
          <Button
            type="button"
            disabled={pending}
            onClick={submitProof}
            className="mt-3 h-10 w-full"
          >
            {pending
              ? "Verifying…"
              : pendingChallengeDueAt
                ? "Complete required display challenge"
                : "Verify display for this shift"}
          </Button>
        </div>
      ) : null}
      <div aria-live="polite" className="mt-2">
        {error ? (
          <p role="alert" className="text-coral text-xs">
            {error}
          </p>
        ) : null}
        {done ? <p className="text-green text-xs">✓ {done}</p> : null}
      </div>
    </section>
  );
}
