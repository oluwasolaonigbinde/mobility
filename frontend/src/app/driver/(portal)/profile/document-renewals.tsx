"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { formatDate } from "@/lib/format";
import { onboardingResponseJson, uploadDriverDocument } from "@/lib/files/onboarding-upload";
import type { components } from "@/lib/api/schema";

type Documents = components["schemas"]["DriverDocumentsRead"];
const labels: Record<string, string> = {
  driver_license: "Driving licence",
  driver_photo: "Your photo",
  signed_agreement: "Signed driver agreement",
  registration: "Vehicle registration",
  insurance: "Insurance",
  vehicle_photo: "Vehicle photo",
};
const reasons: Record<string, string> = {
  missing_evidence: "A document is missing. Send the complete set of documents.",
  rejected_evidence: "Your documents were not approved. Upload current, clear documents.",
  expired_evidence: "Your documents have expired. Upload current documents.",
  unsafe_evidence: "A document failed the file checks. Choose another file.",
  identity_mismatch:
    "Your identity details did not match. Check your NIN and licence before sending again.",
  bank_account_mismatch:
    "Your bank details did not match. Check the account name, number and bank before sending again.",
  unreadable_evidence: "A document was hard to read. Upload a clear photo or scan.",
  owner_mismatch:
    "The vehicle owner details did not match. Check the registration before sending again.",
  vehicle_identity_mismatch:
    "The vehicle details did not match. Upload documents for this vehicle.",
  not_roadworthy:
    "The vehicle was not approved as roadworthy. Contact Terrax before sending new documents.",
  not_pilot_eligible:
    "This vehicle was not approved for the pilot. Contact Terrax before sending new documents.",
};

function RenewalForm({
  submissionId,
  vehicleId,
  onSent,
}: {
  submissionId: string;
  vehicleId?: string;
  onSent: () => Promise<void>;
}) {
  const requestId = useRef(crypto.randomUUID());
  const uploads = useRef(new Map<string, { requestId: string; fileId?: string }>());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const kinds = vehicleId
    ? ["registration", "insurance", "vehicle_photo"]
    : ["driver_license", "driver_photo", "signed_agreement"];
  async function submit(form: FormData) {
    setBusy(true);
    setError("");
    try {
      const body: Record<string, string> = {
        client_request_id: requestId.current,
        expected_submission_id: submissionId,
      };
      if (!vehicleId)
        for (const field of ["nin", "account_name", "account_number", "bank_code"])
          body[field] = String(form.get(field) ?? "");
      for (const kind of kinds) {
        const file = form.get(kind);
        if (!(file instanceof File) || !file.size)
          throw new Error(`Choose a file for ${(labels[kind] ?? kind).toLowerCase()}.`);
        const digest = Array.from(
          new Uint8Array(await crypto.subtle.digest("SHA-256", await file.arrayBuffer())),
          (byte) => byte.toString(16).padStart(2, "0"),
        ).join("");
        const uploadKey = `${kind}:${file.name}:${digest}`;
        let upload = uploads.current.get(uploadKey);
        if (!upload) {
          upload = { requestId: crypto.randomUUID() };
          uploads.current.set(uploadKey, upload);
        }
        if (!upload.fileId)
          upload.fileId = await uploadDriverDocument(
            file,
            upload.requestId,
            vehicleId ? "vehicle_evidence" : "driver_kyc",
          );
        body[`${kind}_file_id`] = upload.fileId;
      }
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
      await onSent();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send your documents. Try again.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form action={submit} className="mt-4 flex flex-col gap-4">
      {!vehicleId ? (
        <>
          <Field
            name="nin"
            label="NIN"
            inputMode="numeric"
            minLength={11}
            maxLength={11}
            required
            autoComplete="off"
          />
          <Field name="account_name" label="Bank account name" required />
          <Field
            name="account_number"
            label="Bank account number"
            inputMode="numeric"
            required
            autoComplete="off"
          />
          <Field name="bank_code" label="Bank code" required />
        </>
      ) : null}
      {kinds.map((kind) => (
        <label key={kind} className="text-sm">
          {labels[kind]}
          <input
            className="border-edge mt-2 block w-full rounded-lg border p-2"
            name={kind}
            type="file"
            accept="application/pdf,image/jpeg,image/png,image/webp"
            required
            disabled={busy}
          />
        </label>
      ))}
      <p className="text-muted text-sm">
        Choose a PDF, JPEG, PNG or WebP.{" "}
        {vehicleId ? "Up to 20 MB per file." : "Up to 10 MB per file."} Terrax will review your new
        documents before you can drive.
      </p>
      <Button type="submit" disabled={busy}>
        {busy ? "Uploading and checking files…" : "Send new documents"}
      </Button>
      {error ? (
        <p role="alert" className="text-coral text-sm">
          {error}
        </p>
      ) : null}
    </form>
  );
}

function DocumentStatus({
  status,
  names,
  reason,
  validUntil,
}: {
  status: string;
  names: Record<string, string>;
  reason?: string | null;
  validUntil?: string | null;
}) {
  return (
    <>
      <p className="mt-2 text-sm">
        {status === "pending_review"
          ? "Your documents have been sent and are waiting for Terrax to review."
          : status === "approved"
            ? "Your documents are approved."
            : status === "not_submitted"
              ? "No documents are recorded yet. Contact Terrax for help."
              : (reasons[reason ?? ""] ?? "Upload current documents for Terrax to review.")}
      </p>
      {validUntil ? (
        <p className="mt-2 text-sm">
          Vehicle approval {status === "expired" ? "expired on" : "ends on"}{" "}
          {formatDate(validUntil)}.
        </p>
      ) : null}
      {Object.entries(names).length ? (
        <ul className="text-muted mt-3 space-y-1 text-sm">
          {Object.entries(names).map(([kind, name]) => (
            <li key={kind} className="break-all">
              {labels[kind]}: {name}
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}

export function DocumentRenewals() {
  const router = useRouter();
  const [documents, setDocuments] = useState<Documents>();
  const [error, setError] = useState("");
  async function refresh() {
    setError("");
    const data = await onboardingResponseJson<Documents>(
      await fetch("/api/driver/documents", { cache: "no-store" }),
    );
    setDocuments(data);
  }
  useEffect(() => {
    let active = true;
    fetch("/api/driver/documents", { cache: "no-store" })
      .then(onboardingResponseJson<Documents>)
      .then((data) => {
        if (active) setDocuments(data);
      })
      .catch(() => {
        if (active) setError("Couldn't load your documents. Try again.");
      });
    return () => {
      active = false;
    };
  }, []);
  const sent = async () => {
    await refresh();
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
        <p role="status">Loading your documents…</p>
      </Panel>
    );
  const person = documents.person_payee;
  return (
    <Panel className="p-5">
      <h2 className="font-medium">Your documents</h2>
      <section className="mt-4">
        <h3 className="font-medium">Identity and bank details</h3>
        <DocumentStatus
          status={person.status}
          names={documents.person_document_names ?? {}}
          reason={person.reason_code}
        />
        {person.submission_id && ["rejected", "expired"].includes(person.status) ? (
          <RenewalForm
            key={person.submission_id}
            submissionId={person.submission_id}
            onSent={sent}
          />
        ) : null}
      </section>
      {(documents.vehicles ?? []).map((vehicle) => (
        <section className="border-edge mt-6 border-t pt-4" key={vehicle.vehicle_id}>
          <h3 className="font-medium">Vehicle documents · {vehicle.plate_number}</h3>
          <DocumentStatus
            status={vehicle.status ?? "not_submitted"}
            names={(documents.vehicle_document_names ?? {})[vehicle.vehicle_id ?? ""] ?? {}}
            reason={vehicle.reason_code}
            validUntil={vehicle.valid_until}
          />
          {vehicle.submission_id &&
          vehicle.vehicle_id &&
          ["rejected", "expired"].includes(vehicle.status ?? "") ? (
            <RenewalForm
              key={vehicle.submission_id}
              vehicleId={vehicle.vehicle_id}
              submissionId={vehicle.submission_id}
              onSent={sent}
            />
          ) : null}
        </section>
      ))}
    </Panel>
  );
}
