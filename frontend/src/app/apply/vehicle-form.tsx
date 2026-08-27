"use client";

import { useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import { onboardingResponseJson, uploadOnboardingFile } from "@/lib/files/onboarding-upload";

type VehicleStage = {
  status: string;
  vehicle_id?: string | null;
  version?: number | null;
  plate_number?: string | null;
};

export function VehicleForm() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const [result, setResult] = useState<VehicleStage>();
  const submissionRequestId = useRef(crypto.randomUUID());
  const uploadRequestIds = useRef({
    registration: crypto.randomUUID(),
    insurance: crypto.randomUUID(),
    photo: crypto.randomUUID(),
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
      const registration = form.get("registration");
      const insurance = form.get("insurance");
      const photo = form.get("vehicle_photo");
      if (
        !(registration instanceof File) ||
        !(insurance instanceof File) ||
        !(photo instanceof File)
      ) {
        throw new Error("Registration, insurance and vehicle photo files are required.");
      }
      const [registrationId, insuranceId, photoId] =
        uploadedFileIds.current ??
        (await Promise.all([
          uploadOnboardingFile(
            accessToken,
            registration,
            uploadRequestIds.current.registration,
            "vehicle_evidence",
          ),
          uploadOnboardingFile(
            accessToken,
            insurance,
            uploadRequestIds.current.insurance,
            "vehicle_evidence",
          ),
          uploadOnboardingFile(
            accessToken,
            photo,
            uploadRequestIds.current.photo,
            "vehicle_evidence",
          ),
        ]));
      uploadedFileIds.current = [registrationId, insuranceId, photoId];
      const response = await fetch("/api/apply/onboarding/vehicle", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          application_access_token: accessToken,
          client_request_id: submissionRequestId.current,
          vehicle_id: String(form.get("vehicle_id") ?? "").trim() || null,
          plate_number: String(form.get("plate_number") ?? ""),
          plate_country_code: String(form.get("plate_country_code") ?? "").toUpperCase(),
          vehicle_type: "car",
          make: String(form.get("make") ?? "").trim() || null,
          model: String(form.get("model") ?? "").trim() || null,
          year: Number(form.get("year")) || null,
          color: String(form.get("color") ?? "").trim() || null,
          registration_file_id: registrationId,
          insurance_file_id: insuranceId,
          vehicle_photo_file_id: photoId,
        }),
      });
      setResult(await onboardingResponseJson<VehicleStage>(response));
      submissionRequestId.current = crypto.randomUUID();
      uploadRequestIds.current = {
        registration: crypto.randomUUID(),
        insurance: crypto.randomUUID(),
        photo: crypto.randomUUID(),
      };
      uploadedFileIds.current = null;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The vehicle request failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Panel className="mt-5 p-6">
      <p className="micro text-amber mb-2">Vehicle approval stage</p>
      <h2 className="font-display text-2xl font-semibold">Submit your pilot vehicle</h2>
      <p className="text-muted mt-2 mb-6 max-w-3xl text-sm">
        Add the car you propose to drive. Any change to its identity or evidence creates a new
        review revision and immediately closes work eligibility until an administrator approves it.
      </p>
      <form onSubmit={submit} className="grid gap-4" noValidate>
        <Field
          label="Onboarding access code"
          name="application_access_token"
          type="password"
          autoComplete="one-time-code"
          required
        />
        <Field
          label="Existing vehicle ID (only when revising)"
          name="vehicle_id"
          placeholder="Leave blank for your first submission"
        />
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Plate number" name="plate_number" required />
          <Field
            label="Plate country code"
            name="plate_country_code"
            defaultValue="NG"
            minLength={2}
            maxLength={2}
            required
          />
          <Field label="Year" name="year" type="number" min={1980} max={2100} />
          <Field label="Make" name="make" />
          <Field label="Model" name="model" />
          <Field label="Colour" name="color" />
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field
            label="Vehicle registration"
            name="registration"
            type="file"
            accept="application/pdf,image/jpeg,image/png,image/webp"
            required
          />
          <Field
            label="Current insurance"
            name="insurance"
            type="file"
            accept="application/pdf,image/jpeg,image/png,image/webp"
            required
          />
          <Field
            label="Vehicle photo"
            name="vehicle_photo"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            required
          />
        </div>
        {error ? (
          <p role="alert" className="text-coral text-sm">
            {error}
          </p>
        ) : null}
        {result ? (
          <p role="status" className="text-green text-sm">
            Vehicle evidence version {result.version} for {result.plate_number} is{" "}
            {result.status.replaceAll("_", " ")}.
            {result.vehicle_id ? (
              <span className="mt-1 block">
                Save vehicle ID <code className="font-mono">{result.vehicle_id}</code> for a later
                revision.
              </span>
            ) : null}
          </p>
        ) : null}
        <Button type="submit" disabled={pending}>
          {pending ? "Checking and submitting…" : "Submit vehicle evidence"}
        </Button>
      </form>
    </Panel>
  );
}
