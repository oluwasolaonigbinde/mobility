"use client";

import { DriverAgreement } from "@/components/driver/driver-agreement";
import { ApplicationBankDetails } from "@/components/driver/application-bank-details";
import { useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { FilePicker } from "@/components/ui/file-picker";
import { Panel } from "@/components/ui/panel";
import { onboardingResponseJson, uploadOnboardingFile } from "@/lib/files/onboarding-upload";
import { useUploadStates } from "./upload-states";
import { useDocumentUploads } from "@/lib/files/use-document-uploads";

type StageResponse = {
  status: string;
  masked_nin?: string | null;
  version?: number | null;
};

const FILES = ["license", "photo"] as const;

export function PersonPayeeForm({ accessToken }: { accessToken: string }) {
  const [bankReset, setBankReset] = useState(0);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const [result, setResult] = useState<StageResponse>();
  const uploads = useUploadStates(FILES);
  const submissionRequestId = useRef(crypto.randomUUID());
  const fileUploads = useDocumentUploads();
  const generation = useRef(0);

  function changed(event?: FormEvent<HTMLFormElement>) {
    if ((event?.target as HTMLInputElement | undefined)?.name === "bank_search") return;
    generation.current += 1;
    submissionRequestId.current = crypto.randomUUID();
    setResult(undefined);
  }

  function fileChanged(key: (typeof FILES)[number]) {
    fileUploads.remove(key);
    uploads.set(key, "idle");
    changed();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const selectedGeneration = generation.current;
    const active = fileUploads.fence();
    const isCurrent = () => active() && selectedGeneration === generation.current;
    const formElement = event.currentTarget;
    setPending(true);
    setError(undefined);
    setResult(undefined);
    const form = new FormData(formElement);
    const track = uploads.tracker(isCurrent);
    try {
      const license = (formElement.elements.namedItem("driver_license") as HTMLInputElement)
        .files?.[0];
      const photo = (formElement.elements.namedItem("driver_photo") as HTMLInputElement).files?.[0];
      if (!(license instanceof File) || !(photo instanceof File)) {
        throw new Error("Add your driver's licence and a photo of you.");
      }
      if (form.get("agreement_accepted") !== "on")
        throw new Error("Read and agree to the driver agreement.");
      if (!form.get("bank_check_receipt") || !form.get("account_name"))
        throw new Error("Check your bank account name first.");
      if (
        form.get("bank_check_outcome") === "resolved" &&
        form.get("account_name_confirmed") !== "true"
      )
        throw new Error("Confirm that the account name is yours.");
      const [licenseId, photoId] = await Promise.all([
        track(
          "license",
          fileUploads.upload("license", license, accessToken, (id, progress) => {
            progress.onStatus = uploads.onStatus("license", isCurrent);
            return uploadOnboardingFile(accessToken, license, id, "driver_kyc", progress);
          }),
        ),
        track(
          "photo",
          fileUploads.upload("photo", photo, accessToken, (id, progress) => {
            progress.onStatus = uploads.onStatus("photo", isCurrent);
            return uploadOnboardingFile(accessToken, photo, id, "driver_kyc", progress);
          }),
        ),
      ]);
      if (!isCurrent()) return;
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
          agreement_version: String(form.get("agreement_version")),
          agreement_accepted: form.get("agreement_accepted") === "on",
          bank_check_receipt: String(form.get("bank_check_receipt")),
          account_name_confirmed: form.get("account_name_confirmed") === "true",
        }),
      });
      const nextResult = await onboardingResponseJson<StageResponse>(response);
      if (!isCurrent()) return;
      setResult(nextResult);
      formElement.reset();
      setBankReset((value) => value + 1);
      uploads.reset();
      submissionRequestId.current = crypto.randomUUID();
      setPending(false);
      fileUploads.clear();
    } catch (caught) {
      if (!isCurrent()) return;
      setError(
        caught instanceof Error ? caught.message : "Something went wrong. Please try again.",
      );
    } finally {
      if (fileUploads.alive()) {
        if (!isCurrent()) uploads.clearUploading();
        setPending(false);
      }
    }
  }

  if (result)
    return (
      <Panel className="mt-5 p-6">
        <h2 className="font-display text-2xl font-semibold">Details sent</h2>
        <p role="status" className="text-muted mt-3 text-sm">
          Terrax Media will check your details. We’ll email you when it’s time to add your car.
        </p>
      </Panel>
    );
  return (
    <Panel className="mt-5 p-6">
      <h2 className="font-display text-2xl font-semibold">Your ID and bank details</h2>
      <p className="text-muted mt-2 mb-6 max-w-3xl text-sm">
        Add your ID, bank details and two files. Read the agreement below. We keep your details
        private.
      </p>
      <form onSubmit={submit} onChange={changed} className="grid gap-4" noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="NIN (11 digits)"
            name="nin"
            type="password"
            inputMode="numeric"
            minLength={11}
            maxLength={11}
            required
          />
        </div>
        <ApplicationBankDetails key={bankReset} accessToken={accessToken} />
        <div className="grid gap-4 sm:grid-cols-2">
          <FilePicker
            label="Driver's licence"
            name="driver_license"
            accept="application/pdf,image/jpeg,image/png,image/webp"
            required
            state={uploads.states.license}
            onFile={() => fileChanged("license")}
          />
          <FilePicker
            label="Photo of you"
            name="driver_photo"
            accept="image/jpeg,image/png,image/webp"
            required
            state={uploads.states.photo}
            onFile={() => fileChanged("photo")}
          />
        </div>
        <DriverAgreement />
        {error ? (
          <p role="alert" className="text-coral text-sm">
            {error}
          </p>
        ) : null}
        <Button type="submit" disabled={pending}>
          {pending ? "Sending…" : "Send my details"}
        </Button>
      </form>
    </Panel>
  );
}
