"use client";

import { useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { FilePicker } from "@/components/ui/file-picker";
import { Panel } from "@/components/ui/panel";
import { onboardingResponseJson, uploadOnboardingFile } from "@/lib/files/onboarding-upload";
import { CarChooser } from "./car-chooser";
import { useUploadStates } from "./upload-states";

type VehicleStage = {
  status: string;
  vehicle_id?: string | null;
  version?: number | null;
  plate_number?: string | null;
};

const FILES = ["registration", "insurance", "photo"] as const;

export function VehicleForm() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const [result, setResult] = useState<VehicleStage>();
  const [chooserKey, setChooserKey] = useState(0);
  const uploads = useUploadStates(FILES);
  const submissionRequestId = useRef(crypto.randomUUID());
  const uploadRequestIds = useRef({
    registration: crypto.randomUUID(),
    insurance: crypto.randomUUID(),
    photo: crypto.randomUUID(),
  });
  const uploadedFileIds = useRef<[string, string, string] | null>(null);
  const uploadContext = useRef<{ token: string; files: File[] } | null>(null);
  const generation = useRef(0);

  function changed(event?: FormEvent<HTMLFormElement>) {
    // A different code may own different cars, so the looked-up list starts over.
    if ((event?.target as HTMLInputElement | undefined)?.name === "application_access_token") {
      setChooserKey((key) => key + 1);
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
      const files = [registration, insurance, photo];
      if (
        uploadContext.current?.token !== accessToken ||
        files.some((file, index) => file !== uploadContext.current?.files[index])
      ) {
        uploadedFileIds.current = null;
        uploadRequestIds.current = {
          registration: crypto.randomUUID(),
          insurance: crypto.randomUUID(),
          photo: crypto.randomUUID(),
        };
        uploadContext.current = { token: accessToken, files };
      }
      const [registrationId, insuranceId, photoId] =
        uploadedFileIds.current ??
        (await Promise.all([
          track(
            "registration",
            uploadOnboardingFile(
              accessToken,
              registration,
              uploadRequestIds.current.registration,
              "vehicle_evidence",
            ),
          ),
          track(
            "insurance",
            uploadOnboardingFile(
              accessToken,
              insurance,
              uploadRequestIds.current.insurance,
              "vehicle_evidence",
            ),
          ),
          track(
            "photo",
            uploadOnboardingFile(
              accessToken,
              photo,
              uploadRequestIds.current.photo,
              "vehicle_evidence",
            ),
          ),
        ]));
      if (selectedGeneration !== generation.current) return;
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
      const nextResult = await onboardingResponseJson<VehicleStage>(response);
      if (selectedGeneration !== generation.current) return;
      setResult(nextResult);
      submissionRequestId.current = crypto.randomUUID();
      uploadRequestIds.current = {
        registration: crypto.randomUUID(),
        insurance: crypto.randomUUID(),
        photo: crypto.randomUUID(),
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
      <h2 className="font-display text-2xl font-semibold">Your car</h2>
      <p className="text-muted mt-2 mb-6 max-w-3xl text-sm">
        You can add your car after your ID and bank details are approved. If you change your car or
        its papers, we check it again before you can drive.
      </p>
      <form onSubmit={submit} onChange={changed} className="grid gap-4" noValidate>
        <Field
          label="Code from your email"
          name="application_access_token"
          type="password"
          autoComplete="one-time-code"
          aria-describedby="vehicle-code-hint"
          required
        />
        <p id="vehicle-code-hint" className="text-muted -mt-2 text-xs">
          Check your email for the code we sent you.
        </p>
        <CarChooser key={chooserKey} />
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Plate number" name="plate_number" required />
          <Field
            label="Plate country (2 letters)"
            name="plate_country_code"
            defaultValue="NG"
            minLength={2}
            maxLength={2}
            required
          />
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
        {result ? (
          <p role="status" className="text-green text-sm">
            Sent. We&apos;ll check your car
            {result.plate_number ? ` (${result.plate_number})` : ""}. Check your status with your
            application reference.
          </p>
        ) : null}
        <Button type="submit" disabled={pending}>
          {pending ? "Sending…" : "Send my car"}
        </Button>
      </form>
    </Panel>
  );
}
