"use client";

import { useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { FilePicker } from "@/components/ui/file-picker";
import { Panel } from "@/components/ui/panel";
import { onboardingResponseJson, uploadOnboardingFile } from "@/lib/files/onboarding-upload";
import { CarChooser } from "./car-chooser";
import { useUploadStates } from "./upload-states";
import { useDocumentUploads } from "@/lib/files/use-document-uploads";
import type { ApplicationCar } from "./application-journey";

type VehicleStage = {
  status: string;
  vehicle_id?: string | null;
  version?: number | null;
  plate_number?: string | null;
};

const FILES = ["registration", "insurance", "photo"] as const;

export function VehicleForm({
  accessToken,
  cars,
}: {
  accessToken: string;
  cars: ApplicationCar[];
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const [result, setResult] = useState<VehicleStage>();
  const uploads = useUploadStates(FILES);
  const submissionRequestId = useRef(crypto.randomUUID());
  const fileUploads = useDocumentUploads();
  const generation = useRef(0);

  function changed(event?: FormEvent<HTMLFormElement>) {
    if ((event?.target as HTMLInputElement | undefined)?.name === "vehicle_id") {
      fileUploads.clear();
      uploads.reset();
    }
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
      if (cars.length && !form.has("vehicle_id"))
        throw new Error("Choose the car you are updating.");
      const registration = (formElement.elements.namedItem("registration") as HTMLInputElement)
        .files?.[0];
      const insurance = (formElement.elements.namedItem("insurance") as HTMLInputElement)
        .files?.[0];
      const photo = (formElement.elements.namedItem("vehicle_photo") as HTMLInputElement)
        .files?.[0];
      if (
        !(registration instanceof File) ||
        !(insurance instanceof File) ||
        !(photo instanceof File)
      ) {
        throw new Error(
          "Add all three files: the registration papers, the insurance certificate and a photo of the car.",
        );
      }
      const context = JSON.stringify([accessToken, String(form.get("vehicle_id") ?? "")]);
      const [registrationId, insuranceId, photoId] = await Promise.all([
        track(
          "registration",
          fileUploads.upload("registration", registration, context, (id, progress) => {
            progress.onStatus = uploads.onStatus("registration", isCurrent);
            return uploadOnboardingFile(
              accessToken,
              registration,
              id,
              "vehicle_evidence",
              progress,
            );
          }),
        ),
        track(
          "insurance",
          fileUploads.upload("insurance", insurance, context, (id, progress) => {
            progress.onStatus = uploads.onStatus("insurance", isCurrent);
            return uploadOnboardingFile(accessToken, insurance, id, "vehicle_evidence", progress);
          }),
        ),
        track(
          "photo",
          fileUploads.upload("photo", photo, context, (id, progress) => {
            progress.onStatus = uploads.onStatus("photo", isCurrent);
            return uploadOnboardingFile(accessToken, photo, id, "vehicle_evidence", progress);
          }),
        ),
      ]);
      if (!isCurrent()) return;
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
      const nextResult = await onboardingResponseJson<VehicleStage>(response);
      if (!isCurrent()) return;
      setResult(nextResult);
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
        <h2 className="font-display text-2xl font-semibold">Car details sent</h2>
        <p role="status" className="text-muted mt-3 text-sm">
          Terrax Media will check your car and email you about the next step.
        </p>
      </Panel>
    );
  return (
    <Panel className="mt-5 p-6">
      <h2 className="font-display text-2xl font-semibold">Your car</h2>
      <p className="text-muted mt-2 mb-6 max-w-3xl text-sm">
        You can add your car after your ID and bank details are approved. If you change your car or
        its papers, we check it again before you can drive.
      </p>
      <form onSubmit={submit} onChange={changed} className="grid gap-4" noValidate>
        <CarChooser cars={cars} />
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Plate number" name="plate_number" required />
          <input type="hidden" name="plate_country_code" value="NG" />
          <Field label="Year (optional)" name="year" type="number" min={1980} max={2100} />
          <Field label="Make (optional)" name="make" placeholder="Toyota" />
          <Field label="Model (optional)" name="model" placeholder="Corolla" />
          <Field label="Colour (optional)" name="color" />
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <FilePicker
            label="Registration papers"
            name="registration"
            accept="application/pdf,image/jpeg,image/png,image/webp"
            required
            state={uploads.states.registration}
            onFile={() => fileChanged("registration")}
          />
          <FilePicker
            label="Insurance certificate"
            name="insurance"
            accept="application/pdf,image/jpeg,image/png,image/webp"
            required
            state={uploads.states.insurance}
            onFile={() => fileChanged("insurance")}
          />
          <FilePicker
            label="Photo of the car"
            name="vehicle_photo"
            accept="image/jpeg,image/png,image/webp"
            required
            state={uploads.states.photo}
            onFile={() => fileChanged("photo")}
          />
        </div>
        {error ? (
          <p role="alert" className="text-coral text-sm">
            {error}
          </p>
        ) : null}
        <Button type="submit" disabled={pending}>
          {pending ? "Sending…" : "Send my car"}
        </Button>
      </form>
    </Panel>
  );
}
