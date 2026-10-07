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
// Provider codes stay inside the form; drivers choose bank names.
// Sources: paystack.com/docs/payments/direct-debit/ and globusbank.com/Files/List-of-Nigerian-Banks.pdf.
const banks = [
  ["044", "Access Bank"],
  ["023", "Citibank Nigeria"],
  ["050", "Ecobank Nigeria"],
  ["070", "Fidelity Bank"],
  ["011", "First Bank of Nigeria"],
  ["214", "First City Monument Bank"],
  ["00103", "Globus Bank"],
  ["058", "Guaranty Trust Bank"],
  ["301", "Jaiz Bank"],
  ["082", "Keystone Bank"],
  ["50211", "Kuda Bank"],
  ["100004", "OPay"],
  ["076", "Polaris Bank"],
  ["105", "PremiumTrust Bank"],
  ["101", "Providus Bank"],
  ["221", "Stanbic IBTC Bank"],
  ["068", "Standard Chartered Bank"],
  ["232", "Sterling Bank"],
  ["100", "Suntrust Bank"],
  ["102", "Titan Bank"],
  ["032", "Union Bank"],
  ["033", "United Bank for Africa"],
  ["215", "Unity Bank"],
  ["035", "Wema Bank"],
  ["057", "Zenith Bank"],
];
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
  submissionId,
  vehicleId,
  onSent,
  kinds,
  replaceNin = false,
  replaceBank = false,
}: {
  submissionId: string;
  vehicleId?: string;
  onSent: () => Promise<void>;
  kinds: string[];
  replaceNin?: boolean;
  replaceBank?: boolean;
}) {
  const requestId = useRef(crypto.randomUUID());
  const uploads = useRef(new Map<string, { requestId: string; fileId?: string }>());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(form: FormData) {
    setBusy(true);
    setError("");
    try {
      const body: Record<string, string> = {
        client_request_id: requestId.current,
        expected_submission_id: submissionId,
      };
      for (const field of [
        ...(replaceNin ? ["nin"] : []),
        ...(replaceBank ? ["account_name", "account_number", "bank_code"] : []),
      ])
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
          <label className="micro text-muted flex flex-col gap-2">
            Bank
            <select
              name="bank_code"
              required
              disabled={busy}
              className="border-edge bg-raised text-ink h-11 rounded-lg border px-3 text-sm"
            >
              <option value="">Choose your bank</option>
              {banks.map(([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <p className="text-muted text-sm">If your bank is missing, contact Terrax to add it.</p>
        </>
      ) : null}
      {kinds.map((kind) => (
        <UploadControl key={kind} kind={kind} disabled={busy} />
      ))}
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
        {busy ? "Uploading and checking files..." : "Send for review"}
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
        {person.submission_id && ["rejected", "expired"].includes(person.status) ? (
          <RenewalForm
            key={person.submission_id}
            submissionId={person.submission_id}
            kinds={
              person.purged_at
                ? ["driver_license", "driver_photo", "signed_agreement"]
                : replacements(person.documents ?? {})
            }
            replaceNin={person.replace_nin}
            replaceBank={person.replace_bank}
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
              key={vehicle.submission_id}
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
