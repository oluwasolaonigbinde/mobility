"use client";

import { useState, type MouseEvent } from "react";
import { Button } from "@/components/ui/button";
import { onboardingResponseJson } from "@/lib/files/onboarding-upload";

type Car = { vehicle_id: string; plate_number: string; status: string };

const STATUS: Record<string, string> = {
  not_submitted: "documents not sent",
  pending_review: "being checked",
  approved: "approved",
  rejected: "not approved",
  expired: "approval expired",
};

/**
 * Lets an applicant pick which of their own cars they are updating, by plate,
 * instead of typing an internal ID. It reads the onboarding code from the
 * surrounding form, and the chosen car travels with that form as `vehicle_id`.
 */
export function CarChooser() {
  const [cars, setCars] = useState<Car[]>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);

  async function findCars(event: MouseEvent<HTMLButtonElement>) {
    const form = event.currentTarget.form;
    const code = String(
      form ? (new FormData(form).get("application_access_token") ?? "") : "",
    ).trim();
    if (!code) {
      setError("Enter your onboarding code first.");
      return;
    }
    setLoading(true);
    setError(undefined);
    try {
      const response = await fetch("/api/apply/onboarding/vehicles", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ application_access_token: code }),
      });
      setCars((await onboardingResponseJson<{ items: Car[] }>(response)).items);
    } catch (caught) {
      setCars(undefined);
      setError(caught instanceof Error ? caught.message : "Your cars couldn't be loaded.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <fieldset className="border-edge rounded-lg border p-4">
      <legend className="text-muted px-1 text-xs">Which car is this?</legend>
      {cars ? (
        <div className="grid gap-2 text-sm">
          {cars.map((car) => (
            <label key={car.vehicle_id} className="flex items-center gap-2">
              <input type="radio" name="vehicle_id" value={car.vehicle_id} />
              <span className="font-mono">{car.plate_number}</span>
              <span className="text-muted text-xs">({STATUS[car.status] ?? car.status})</span>
            </label>
          ))}
          <label className="flex items-center gap-2">
            <input type="radio" name="vehicle_id" value="" defaultChecked />A new car
          </label>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-muted text-sm">
            Sending a car for the first time? Leave this. Updating a car you already sent?
          </p>
          <Button type="button" variant="ghost" onClick={findCars} disabled={loading}>
            {loading ? "Finding your cars…" : "Find my cars"}
          </Button>
        </div>
      )}
      {error ? (
        <p role="alert" className="text-coral mt-2 text-sm">
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}
