"use client";

import { useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import { onboardingResponseJson, uploadOnboardingFile } from "@/lib/files/onboarding-upload";

type StageResponse = {
  status: string;
  masked_nin?: string | null;
  version?: number | null;
};

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
          uploadOnboardingFile(
            accessToken,
            license,
            uploadRequestIds.current.license,
            "driver_kyc",
          ),
          uploadOnboardingFile(accessToken, photo, uploadRequestIds.current.photo, "driver_kyc"),
          uploadOnboardingFile(
            accessToken,
            agreement,
            uploadRequestIds.current.agreement,
            "driver_kyc",
          ),
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
      setResult(await onboardingResponseJson<StageResponse>(response));
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
