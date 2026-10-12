"use client";

import { useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { FilePicker } from "@/components/ui/file-picker";
import { Panel } from "@/components/ui/panel";
import { onboardingResponseJson, uploadOnboardingFile } from "@/lib/files/onboarding-upload";
import { useUploadStates } from "./upload-states";

type StageResponse = {
  status: string;
  masked_nin?: string | null;
  version?: number | null;
};

const FILES = ["license", "photo", "agreement"] as const;

export function PersonPayeeForm() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const [result, setResult] = useState<StageResponse>();
  const uploads = useUploadStates(FILES);
  const submissionRequestId = useRef(crypto.randomUUID());
  const uploadRequestIds = useRef({
    license: crypto.randomUUID(),
    photo: crypto.randomUUID(),
    agreement: crypto.randomUUID(),
  });
  const uploadedFileIds = useRef<[string, string, string] | null>(null);
  const uploadContext = useRef<{ token: string; files: File[] } | null>(null);
  const generation = useRef(0);

  function changed(event?: FormEvent<HTMLFormElement>) {
    if ((event?.target as HTMLInputElement | undefined)?.name === "application_access_token") {
      uploads.reset();
    }
    generation.current += 1;
    submissionRequestId.current = crypto.randomUUID();
    setResult(undefined);
  }

  function fileChanged(key: (typeof FILES)[number]) {
    uploads.set(key, "idle");
    changed();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const selectedGeneration = generation.current;
    const formElement = event.currentTarget;
    setPending(true);
    setError(undefined);
    setResult(undefined);
    const form = new FormData(formElement);
    const track = uploads.tracker(() => selectedGeneration === generation.current);
    try {
      const accessToken = String(form.get("application_access_token") ?? "").trim();
      const license = (formElement.elements.namedItem("driver_license") as HTMLInputElement)
        .files?.[0];
      const photo = (formElement.elements.namedItem("driver_photo") as HTMLInputElement).files?.[0];
      const agreement = (formElement.elements.namedItem("signed_agreement") as HTMLInputElement)
        .files?.[0];
      if (!(license instanceof File) || !(photo instanceof File) || !(agreement instanceof File)) {
        throw new Error(
          "Add all three files: your driver's licence, a photo of you and the signed agreement.",
        );
      }
      const files = [license, photo, agreement];
      if (
        uploadContext.current?.token !== accessToken ||
        files.some((file, index) => file !== uploadContext.current?.files[index])
      ) {
        uploadedFileIds.current = null;
        uploadRequestIds.current = {
          license: crypto.randomUUID(),
          photo: crypto.randomUUID(),
          agreement: crypto.randomUUID(),
        };
        uploadContext.current = { token: accessToken, files };
      }
      const [licenseId, photoId, agreementId] =
        uploadedFileIds.current ??
        (await Promise.all([
          track(
            "license",
            uploadOnboardingFile(
              accessToken,
              license,
              uploadRequestIds.current.license,
              "driver_kyc",
            ),
          ),
          track(
            "photo",
            uploadOnboardingFile(accessToken, photo, uploadRequestIds.current.photo, "driver_kyc"),
          ),
          track(
            "agreement",
            uploadOnboardingFile(
              accessToken,
              agreement,
              uploadRequestIds.current.agreement,
              "driver_kyc",
            ),
          ),
        ]));
      if (selectedGeneration !== generation.current) return;
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
      const nextResult = await onboardingResponseJson<StageResponse>(response);
      if (selectedGeneration !== generation.current) return;
      setResult(nextResult);
      formElement.reset();
      uploads.reset();
      submissionRequestId.current = crypto.randomUUID();
      uploadRequestIds.current = {
        license: crypto.randomUUID(),
        photo: crypto.randomUUID(),
        agreement: crypto.randomUUID(),
      };
      uploadedFileIds.current = null;
    } catch (caught) {
      if (selectedGeneration !== generation.current) return;
      setError(
        caught instanceof Error ? caught.message : "Something went wrong. Please try again.",
      );
    } finally {
      if (selectedGeneration !== generation.current) uploads.clearUploading();
      setPending(false);
    }
  }

  return (
    <Panel className="mt-5 p-6">
      <h2 className="font-display text-2xl font-semibold">Your ID and bank details</h2>
      <p className="text-muted mt-2 mb-6 max-w-3xl text-sm">
        Fill in every box and add the three files. We keep your details private.
      </p>
      <form onSubmit={submit} onChange={changed} className="grid gap-4" noValidate>
        <Field
          label="Code from your email"
          name="application_access_token"
          type="password"
          autoComplete="one-time-code"
          aria-describedby="person-payee-code-hint"
          required
        />
        <p id="person-payee-code-hint" className="text-muted -mt-2 text-xs">
          Check your email for the code we sent you.
        </p>
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
          <Field label="Name on bank account" name="account_name" autoComplete="name" required />
          <Field
            label="Account number (10 digits)"
            name="account_number"
            type="password"
            inputMode="numeric"
            minLength={10}
            maxLength={10}
            required
          />
          <div className="flex flex-col gap-1.5">
            <Field
              label="Bank code (3 digits)"
              name="bank_code"
              inputMode="numeric"
              minLength={3}
              maxLength={3}
              aria-describedby="person-payee-bank-code-hint"
              required
            />
            <p id="person-payee-bank-code-hint" className="text-muted text-xs">
              Ask your bank if you&apos;re not sure.
            </p>
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
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
          <FilePicker
            label="Signed agreement"
            hint="The driver agreement Terrax Media sent you, signed."
            name="signed_agreement"
            accept="application/pdf,image/jpeg,image/png"
            required
            state={uploads.states.agreement}
            onFile={() => fileChanged("agreement")}
          />
        </div>
        {error ? (
          <p role="alert" className="text-coral text-sm">
            {error}
          </p>
        ) : null}
        {result ? (
          <p role="status" className="text-green text-sm">
            Sent. We&apos;ll check your details. Check your status with your application reference.
          </p>
        ) : null}
        <Button type="submit" disabled={pending}>
          {pending ? "Sending…" : "Send my details"}
        </Button>
      </form>
    </Panel>
  );
}
