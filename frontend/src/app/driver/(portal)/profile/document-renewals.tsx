"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { BankPicker } from "@/components/driver/bank-picker";
import { DriverAgreement } from "@/components/driver/driver-agreement";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { formatDate } from "@/lib/format";
import { onboardingResponseJson, uploadDriverDocument } from "@/lib/files/onboarding-upload";
import { useDocumentUploads } from "@/lib/files/use-document-uploads";
import type { components } from "@/lib/api/schema";

type Documents = components["schemas"]["DriverDocumentsRead"];
const labels: Record<string, string> = {
  driver_license: "Driving licence",
  driver_photo: "Your photo",
  registration: "Vehicle registration",
  insurance: "Insurance",
  vehicle_photo: "Vehicle photo",
};
const reasons: Record<string, string> = {
  missing_evidence: "missing, upload this document",
  rejected_evidence: "not approved, upload a replacement",
  expired_evidence: "expired, upload a current document",
  unsafe_evidence: "file checks failed, upload another file",
  unreadable_evidence: "hard to read, upload a clearer photo",
  identity_mismatch: "identity details do not match, upload a replacement",
  owner_mismatch: "owner details do not match, upload a replacement",
  vehicle_identity_mismatch: "vehicle details do not match, upload a replacement",
  not_roadworthy: "contact Terrax about roadworthiness",
  not_pilot_eligible: "contact Terrax about pilot eligibility",
};

function RenewalForm({
  driverId,
  submissionId,
  vehicleId,
  onSent,
  kinds,
  replaceNin = false,
  replaceBank = false,
  needsAgreement = false,
}: {
  driverId: string;
  submissionId: string;
  vehicleId?: string;
  onSent: () => Promise<void>;
  kinds: string[];
  replaceNin?: boolean;
  replaceBank?: boolean;
  needsAgreement?: boolean;
}) {
  const requestId = useRef(crypto.randomUUID());
  const uploads = useDocumentUploads();
  const generation = useRef(0);
  const context = JSON.stringify([driverId, submissionId, vehicleId ?? null]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [uploadStatus, setUploadStatus] = useState("");
  function changed(event: FormEvent<HTMLFormElement>) {
    if ((event.target as HTMLInputElement).name === "bank_search") return;
    generation.current += 1;
    requestId.current = crypto.randomUUID();
    setError("");
    setUploadStatus("");
    if ((event.target as HTMLInputElement).type === "file")
      uploads.remove((event.target as HTMLInputElement).name);
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const selectedGeneration = generation.current;
    const active = uploads.fence();
    const isCurrent = () => active() && selectedGeneration === generation.current;
    setBusy(true);
    setError("");
    try {
      const body: Record<string, string | boolean> = {
        client_request_id: requestId.current,
        expected_submission_id: submissionId,
      };
      if (needsAgreement) {
        if (form.get("agreement_accepted") !== "on")
          throw new Error("Read and agree to the driver agreement.");
        body.agreement_version = String(form.get("agreement_version"));
        body.agreement_accepted = true;
      }
      for (const field of [
        ...(replaceNin ? ["nin"] : []),
        ...(replaceBank ? ["account_name", "account_number", "bank_code"] : []),
      ])
        body[field] = String(form.get(field) ?? "");
      for (const kind of kinds) {
        const file = (formElement.elements.namedItem(kind) as HTMLInputElement).files?.[0];
        if (!(file instanceof File) || !file.size)
          throw new Error(`Choose a file for ${(labels[kind] ?? kind).toLowerCase()}.`);
        setUploadStatus(`Uploading ${labels[kind] ?? "file"}…`);
        body[`${kind}_file_id`] = await uploads.upload(kind, file, context, (id, progress) => {
          progress.onStatus = (message) => {
            if (isCurrent()) setUploadStatus(message);
          };
          return uploadDriverDocument(
            file,
            id,
            vehicleId ? "vehicle_evidence" : "driver_kyc",
            progress,
          );
        });
        if (!isCurrent()) return;
      }
      if (!isCurrent()) return;
      await onboardingResponseJson(
        await fetch(
          vehicleId
            ? `/api/driver/vehicles/${vehicleId}/documents`
            : "/api/driver/documents/person-payee",
          {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(body),
          },
        ),
      );
      if (!isCurrent()) return;
      await onSent();
    } catch (e) {
      if (!isCurrent()) return;
      setError(e instanceof Error ? e.message : "Couldn't send your documents. Try again.");
    } finally {
      if (active()) setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} onChange={changed} className="mt-4 flex flex-col gap-4">
      {replaceNin ? (
        <Field
          name="nin"
          label="NIN"
          inputMode="numeric"
          minLength={11}
          maxLength={11}
          required
          autoComplete="off"
        />
      ) : null}
      {replaceBank ? (
        <>
          <Field name="account_name" label="Bank account name" required />
          <Field
            name="account_number"
            label="Bank account number"
            inputMode="numeric"
            required
            autoComplete="off"
          />
          <BankPicker disabled={busy} />
          <p className="text-muted text-sm">If your bank is missing, contact Terrax to add it.</p>
        </>
      ) : null}
      {kinds.map((kind) => (
        <UploadControl key={kind} kind={kind} disabled={busy} />
      ))}
      {needsAgreement ? <DriverAgreement /> : null}
      {kinds.length ? (
        <p className="text-muted text-sm">
          Choose a PDF, JPEG, PNG or WebP.{" "}
          {vehicleId ? "Up to 20 MB per file." : "Up to 10 MB per file."}
        </p>
      ) : null}
      <p className="text-muted text-sm">
        Terrax will review your changes. Your other documents and saved details stay on file.
      </p>
      <Button type="submit" disabled={busy}>
        {busy ? uploadStatus || "Sending…" : "Send for review"}
      </Button>
      {error ? (
        <p role="alert" className="text-coral text-sm">
          {error}
        </p>
      ) : null}
    </form>
  );
}

function UploadControl({ kind, disabled }: { kind: string; disabled: boolean }) {
  const [selected, setSelected] = useState(false);
  return (
    <label className="border-edge bg-raised focus-within:border-amber relative flex cursor-pointer items-center justify-between gap-3 rounded-lg border px-3 py-3 text-sm">
      <span>{labels[kind]}</span>
      <span className="text-amber shrink-0">
        {selected ? "File selected · Change" : "Upload replacement"}
      </span>
      <input
        className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
        aria-label={`Replace ${labels[kind]}`}
        name={kind}
        type="file"
        accept="application/pdf,image/jpeg,image/png,image/webp"
        required
        disabled={disabled}
        onChange={(event) => setSelected(Boolean(event.target.files?.length))}
      />
    </label>
  );
}

function DocumentStatus({
  documents,
}: {
  documents: Record<string, components["schemas"]["DocumentReviewRead"]>;
}) {
  return (
    <ul className="mt-3 space-y-3 text-sm">
      {Object.entries(documents).map(([kind, item]) => (
        <li key={kind}>
          <span className="font-medium">{labels[kind]}: </span>
          <span
            className={
              item.status === "rejected" || item.status === "expired" ? "text-coral" : "text-muted"
            }
          >
            {item.status === "accepted"
              ? "accepted"
              : item.status === "on_file"
                ? "on file, awaiting review"
                : item.status === "expired" && item.expires_on
                  ? `expired ${new Date(item.expires_on + "T12:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "Africa/Lagos" })}, upload a current document`
                  : (reasons[item.reason_code ?? ""] ?? "upload a replacement")}
          </span>
        </li>
      ))}
    </ul>
  );
}

function replacements(documents: Record<string, components["schemas"]["DocumentReviewRead"]>) {
  return Object.keys(documents).filter((kind) =>
    ["rejected", "expired"].includes(documents[kind]?.status ?? "on_file"),
  );
}

export function DocumentRenewals({ driverId }: { driverId: string }) {
  return <OwnedDocumentRenewals key={driverId} driverId={driverId} />;
}

function OwnedDocumentRenewals({ driverId }: { driverId: string }) {
  const router = useRouter();
  const [documents, setDocuments] = useState<Documents>();
  const [error, setError] = useState("");
  const generation = useRef(0);
  const mounted = useRef(true);
  const loggedOut = useRef(false);
  async function refresh() {
    const selectedGeneration = generation.current;
    setError("");
    const data = await onboardingResponseJson<Documents>(
      await fetch("/api/driver/documents", { cache: "no-store" }),
    );
    if (!mounted.current || loggedOut.current || selectedGeneration !== generation.current) return;
    setDocuments(data);
  }
  useEffect(() => {
    mounted.current = true;
    let active = true;
    const selectedGeneration = generation.current;
    const logout = () => {
      loggedOut.current = true;
      generation.current += 1;
      setDocuments(undefined);
    };
    window.addEventListener("cardvert-driver-logout", logout);
    fetch("/api/driver/documents", { cache: "no-store" })
      .then(onboardingResponseJson<Documents>)
      .then((data) => {
        if (active && !loggedOut.current && selectedGeneration === generation.current)
          setDocuments(data);
      })
      .catch(() => {
        if (active && !loggedOut.current && selectedGeneration === generation.current)
          setError("Couldn't load your documents. Try again.");
      });
    return () => {
      active = false;
      mounted.current = false;
      generation.current += 1;
      window.removeEventListener("cardvert-driver-logout", logout);
    };
  }, [driverId]);
  const sent = async () => {
    const selectedGeneration = generation.current;
    await refresh();
    if (!mounted.current || loggedOut.current || selectedGeneration !== generation.current) return;
    router.refresh();
  };
  if (error)
    return (
      <Panel className="p-5">
        <p role="alert">{error}</p>
        <Button
          onClick={() =>
            refresh().catch(() => setError("Couldn't load your documents. Try again."))
          }
        >
          Try again
        </Button>
      </Panel>
    );
  if (!documents)
    return (
      <Panel className="p-5">
        <p role="status">Loading your documents...</p>
      </Panel>
    );
  const person = documents.person_payee;
  return (
    <Panel className="p-5">
      <h2 className="font-medium">Your documents</h2>
      <section className="mt-4">
        <h3 className="font-medium">Identity and bank details</h3>
        <DocumentStatus documents={person.documents ?? {}} />
        {person.purged_at ? (
          <p className="text-muted mt-3 text-sm">
            Your previous documents and saved details have been removed. Send a new set for Terrax
            to review.
          </p>
        ) : null}
        {person.status === "pending_review" ? (
          <p role="status" className="text-muted mt-3 text-sm">
            Terrax is reviewing your changes.
          </p>
        ) : null}
        {person.replace_bank && !person.purged_at ? (
          <p className="text-coral mt-3 text-sm">
            Bank details did not match. Choose your bank and enter the corrected account details.
          </p>
        ) : null}
        {person.replace_nin && !person.purged_at ? (
          <p className="text-coral mt-3 text-sm">
            Identity details did not match. Enter your corrected NIN.
          </p>
        ) : null}
        {person.status !== "approved" ? (
          <p className="text-muted mt-3 text-sm">
            Starting new campaign trips is paused until Terrax approves your identity and bank
            review. You can still sign in and finish a trip already in progress.
          </p>
        ) : null}
        {person.submission_id &&
        (["rejected", "expired"].includes(person.status) ||
          (person.status === "approved" &&
            (!person.agreement_accepted_at || person.agreement_version !== "1"))) ? (
          <RenewalForm
            key={`${driverId}:${person.submission_id}`}
            driverId={driverId}
            submissionId={person.submission_id}
            kinds={
              person.purged_at
                ? ["driver_license", "driver_photo"]
                : replacements(person.documents ?? {})
            }
            replaceNin={person.replace_nin}
            replaceBank={person.replace_bank}
            needsAgreement={!person.agreement_accepted_at || person.agreement_version !== "1"}
            onSent={sent}
          />
        ) : null}
      </section>
      {(documents.vehicles ?? []).map((vehicle) => (
        <section className="border-edge mt-6 border-t pt-4" key={vehicle.vehicle_id}>
          <h3 className="font-medium">Vehicle documents · {vehicle.plate_number}</h3>
          <DocumentStatus documents={vehicle.documents ?? {}} />
          {vehicle.valid_until ? (
            <p className="text-muted mt-3 text-sm">
              Vehicle approval {vehicle.status === "expired" ? "expired on" : "ends on"}{" "}
              {formatDate(vehicle.valid_until)}.
            </p>
          ) : null}
          {vehicle.status === "pending_review" ? (
            <p role="status" className="text-muted mt-3 text-sm">
              Terrax is reviewing this car’s documents.
            </p>
          ) : null}
          {vehicle.status !== "approved" ? (
            <p className="text-muted mt-3 text-sm">
              Starting new campaign trips in this car is paused until Terrax approves its review.
              You can finish a trip already in progress.
              {person.status === "approved"
                ? " If you have another approved car, you can continue with it."
                : ""}
            </p>
          ) : null}
          {vehicle.submission_id &&
          vehicle.vehicle_id &&
          ["rejected", "expired"].includes(vehicle.status ?? "") ? (
            <RenewalForm
              key={`${driverId}:${vehicle.vehicle_id}:${vehicle.submission_id}`}
              driverId={driverId}
              vehicleId={vehicle.vehicle_id}
              submissionId={vehicle.submission_id}
              kinds={
                vehicle.purged_at
                  ? ["registration", "insurance", "vehicle_photo"]
                  : replacements(vehicle.documents ?? {})
              }
              onSent={sent}
            />
          ) : null}
        </section>
      ))}
    </Panel>
  );
}
