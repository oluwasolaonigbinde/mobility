"use client";

import { useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";

type UploadResponse = {
  upload_id: string;
  upload: { url: string; fields: Record<string, string> };
};

type StoredFileResponse = { id: string; scan_status: string };

type StageResponse = {
  status: string;
  masked_nin?: string | null;
  version?: number | null;
};

async function responseJson<T>(response: Response): Promise<T> {
  const body = (await response.json().catch(() => null)) as
    T | { error?: { message?: string } } | null;
  if (!response.ok) {
    const message =
      body && typeof body === "object" && "error" in body ? body.error?.message : undefined;
    throw new Error(message || "The onboarding request could not be completed.");
  }
  return body as T;
}

async function sha256(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function waitForClean(accessToken: string, fileId: string): Promise<void> {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const response = await fetch(`/api/apply/onboarding/files/${fileId}/status`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ application_access_token: accessToken }),
    });
    const file = await responseJson<StoredFileResponse>(response);
    if (file.scan_status === "clean") return;
    if (["infected", "rejected"].includes(file.scan_status)) {
      throw new Error("A document did not pass the required security checks.");
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
  }
  throw new Error("Document security checks are still pending. Try again shortly.");
}

async function uploadFile(
  accessToken: string,
  file: File,
  clientRequestId: string,
): Promise<string> {
  const response = await fetch("/api/apply/onboarding/uploads", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      application_access_token: accessToken,
      upload: {
        client_request_id: clientRequestId,
        purpose: "driver_kyc",
        filename: file.name,
        content_type: file.type,
        size_bytes: file.size,
        sha256: await sha256(file),
      },
    }),
  });
  const intent = await responseJson<UploadResponse>(response);
  const form = new FormData();
  for (const [name, value] of Object.entries(intent.upload.fields)) form.append(name, value);
  form.append("file", file);
  const uploaded = await fetch(intent.upload.url, { method: "POST", body: form });
  if (!uploaded.ok) throw new Error("A private document upload failed. Please try again.");
  const confirmed = await responseJson<StoredFileResponse>(
    await fetch(`/api/apply/onboarding/uploads/${intent.upload_id}/confirm`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ application_access_token: accessToken }),
    }),
  );
  await waitForClean(accessToken, confirmed.id);
  return confirmed.id;
}

export function PersonPayeeForm() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const [result, setResult] = useState<StageResponse>();
  const submissionRequestId = useRef(crypto.randomUUID());
  const uploadRequestIds = useRef({
    license: crypto.randomUUID(),
    photo: crypto.randomUUID(),
    agreement: crypto.randomUUID(),
  });
  const uploadedFileIds = useRef<[string, string, string] | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(undefined);
    setResult(undefined);
    const form = new FormData(event.currentTarget);
    try {
      const accessToken = String(form.get("application_access_token") ?? "").trim();
      const license = form.get("driver_license");
      const photo = form.get("driver_photo");
      const agreement = form.get("signed_agreement");
      if (!(license instanceof File) || !(photo instanceof File) || !(agreement instanceof File)) {
        throw new Error("Licence, driver photo and signed agreement files are required.");
      }
      const [licenseId, photoId, agreementId] =
        uploadedFileIds.current ??
        (await Promise.all([
          uploadFile(accessToken, license, uploadRequestIds.current.license),
          uploadFile(accessToken, photo, uploadRequestIds.current.photo),
          uploadFile(accessToken, agreement, uploadRequestIds.current.agreement),
        ]));
      uploadedFileIds.current = [licenseId, photoId, agreementId];
      const response = await fetch("/api/apply/onboarding/person-payee", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          application_access_token: accessToken,
          client_request_id: submissionRequestId.current,
          nin: String(form.get("nin") ?? ""),
          account_name: String(form.get("account_name") ?? ""),
          account_number: String(form.get("account_number") ?? ""),
          bank_code: String(form.get("bank_code") ?? ""),
          driver_license_file_id: licenseId,
          driver_photo_file_id: photoId,
          signed_agreement_file_id: agreementId,
        }),
      });
      setResult(await responseJson<StageResponse>(response));
      event.currentTarget.reset();
      submissionRequestId.current = crypto.randomUUID();
      uploadRequestIds.current = {
        license: crypto.randomUUID(),
        photo: crypto.randomUUID(),
        agreement: crypto.randomUUID(),
      };
      uploadedFileIds.current = null;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The onboarding request failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Panel className="mt-5 p-6">
      <p className="micro text-cyan mb-2">Person &amp; payee stage</p>
      <h2 className="font-display text-2xl font-semibold">Submit protected onboarding evidence</h2>
      <p className="text-muted mt-2 mb-6 max-w-3xl text-sm">
        Documents are privately uploaded and malware-scanned. Identity and account values are
        encrypted; reviewers receive only masked details unless an authorized, audited review
        requires a sensitive read.
      </p>
      <form onSubmit={submit} className="grid gap-4" noValidate>
        <Field
          label="Onboarding access code"
          name="application_access_token"
          type="password"
          autoComplete="one-time-code"
          required
        />
        <p className="text-faint -mt-2 text-xs">
          Use the expiring access code sent to the application email. The status reference cannot
          change an application.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="NIN"
            name="nin"
            type="password"
            inputMode="numeric"
            minLength={11}
            maxLength={11}
            required
          />
          <Field label="Verified account name" name="account_name" autoComplete="name" required />
          <Field
            label="Bank account number"
            name="account_number"
            type="password"
            inputMode="numeric"
            minLength={10}
            maxLength={10}
            required
          />
          <Field
            label="Bank code"
            name="bank_code"
            inputMode="numeric"
            minLength={3}
            maxLength={3}
            required
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field
            label="Driver licence"
            name="driver_license"
            type="file"
            accept="application/pdf,image/jpeg,image/png,image/webp"
            required
          />
          <Field
            label="Driver photo"
            name="driver_photo"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            required
          />
          <Field
            label="Signed agreement"
            name="signed_agreement"
            type="file"
            accept="application/pdf,image/jpeg,image/png"
            required
          />
        </div>
        <p className="text-faint text-xs">
          Live onboarding remains unavailable until Terrax Media supplies approved legal/privacy
          wording and adopts the production storage, scanner, key-custody and bank-provider gates.
        </p>
        {error ? (
          <p role="alert" className="text-coral text-sm">
            {error}
          </p>
        ) : null}
        {result ? (
          <p role="status" className="text-green text-sm">
            Person/payee evidence version {result.version} is pending review. NIN projection:{" "}
            {result.masked_nin}.
          </p>
        ) : null}
        <Button type="submit" disabled={pending}>
          {pending ? "Protecting and submitting…" : "Submit person & payee evidence"}
        </Button>
      </form>
    </Panel>
  );
}
