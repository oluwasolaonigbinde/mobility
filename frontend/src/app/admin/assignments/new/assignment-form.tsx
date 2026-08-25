"use client";

import { useActionState, useState, useTransition } from "react";
import {
  createAssignmentAction,
  listAssignmentRecommendationsAction,
  type AdminActionState,
  type AssignmentRecommendation,
} from "../actions";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";

const initialState: AdminActionState = {};

interface Option {
  id: string;
  label: string;
  driverProfileId?: string;
}

export function AssignmentForm({
  campaigns,
  drivers,
  vehicles,
}: {
  campaigns: Option[];
  drivers: Option[];
  vehicles: Option[];
}) {
  const [state, formAction, pending] = useActionState(createAssignmentAction, initialState);
  const [campaignId, setCampaignId] = useState("");
  const [driverId, setDriverId] = useState("");
  const [vehicleId, setVehicleId] = useState("");
  const [serviceCity, setServiceCity] = useState("");
  const [recommendationState, setRecommendationState] = useState<{
    candidates: AssignmentRecommendation[];
    error?: string;
  }>({ candidates: [] });
  const [selectedRecommendation, setSelectedRecommendation] =
    useState<AssignmentRecommendation | null>(null);
  const [recommendationsPending, startRecommendationsTransition] = useTransition();

  // Only offer vehicles that belong to the selected driver — the backend
  // enforces this pairing; the UI just avoids the dead end.
  const driverVehicles = driverId
    ? vehicles.filter((v) => v.driverProfileId === driverId)
    : vehicles;
  const selectedDriverMissing =
    selectedRecommendation &&
    !drivers.some((driver) => driver.id === selectedRecommendation.driver_profile_id);
  const selectedVehicleMissing =
    selectedRecommendation &&
    !vehicles.some((vehicle) => vehicle.id === selectedRecommendation.vehicle_id);

  const selectClass =
    "h-11 rounded-lg border border-edge bg-raised px-3.5 text-sm text-ink transition-colors focus:border-amber focus:outline-none";

  function clearRecommendation() {
    setSelectedRecommendation(null);
  }

  function findRecommendations() {
    startRecommendationsTransition(async () => {
      const next = await listAssignmentRecommendationsAction({
        campaign_id: campaignId,
        service_city: serviceCity,
      });
      setRecommendationState({ candidates: next.candidates ?? [], error: next.error });
      setSelectedRecommendation(null);
    });
  }

  function chooseRecommendation(candidate: AssignmentRecommendation) {
    setDriverId(candidate.driver_profile_id);
    setVehicleId(candidate.vehicle_id);
    setSelectedRecommendation(candidate);
  }

  return (
    <form action={formAction} className="flex flex-col gap-5" noValidate>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="a-campaign" className="micro text-muted">
          Campaign
        </label>
        <select
          id="a-campaign"
          name="campaign_id"
          required
          value={campaignId}
          onChange={(event) => {
            setCampaignId(event.target.value);
            clearRecommendation();
          }}
          className={selectClass}
        >
          <option value="" disabled>
            Select a campaign…
          </option>
          {campaigns.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="a-driver" className="micro text-muted">
          Driver
        </label>
        <select
          id="a-driver"
          name="driver_profile_id"
          required
          value={driverId}
          onChange={(e) => {
            setDriverId(e.target.value);
            setVehicleId("");
            clearRecommendation();
          }}
          className={selectClass}
        >
          <option value="" disabled>
            Select a driver…
          </option>
          {selectedDriverMissing ? (
            <option value={selectedRecommendation.driver_profile_id}>
              {selectedRecommendation.driver_name}
            </option>
          ) : null}
          {drivers.map((d) => (
            <option key={d.id} value={d.id}>
              {d.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="a-vehicle" className="micro text-muted">
          Vehicle {driverId ? `(${driverVehicles.length} for this driver)` : ""}
        </label>
        <select
          id="a-vehicle"
          name="vehicle_id"
          required
          value={vehicleId}
          onChange={(event) => {
            setVehicleId(event.target.value);
            clearRecommendation();
          }}
          className={selectClass}
        >
          <option value="" disabled>
            Select a vehicle…
          </option>
          {selectedVehicleMissing ? (
            <option value={selectedRecommendation.vehicle_id}>
              {selectedRecommendation.vehicle_plate_number}
            </option>
          ) : null}
          {driverVehicles.map((v) => (
            <option key={v.id} value={v.id}>
              {v.label}
            </option>
          ))}
        </select>
      </div>

      <section
        aria-label="Ranked car candidates"
        className="border-edge flex flex-col gap-3 rounded-lg border p-4"
      >
        <div>
          <h2 className="text-ink text-sm font-medium">Ranked car candidates</h2>
          <p className="text-muted mt-1 text-sm">
            Find current matches by service city, then explicitly choose a candidate.
          </p>
        </div>
        <label htmlFor="a-service-city" className="micro text-muted">
          Service city
        </label>
        <div className="flex gap-2">
          <input
            id="a-service-city"
            value={serviceCity}
            onChange={(event) => setServiceCity(event.target.value)}
            placeholder="Lagos"
            className={`${selectClass} min-w-0 flex-1`}
          />
          <Button
            type="button"
            disabled={!campaignId || !serviceCity.trim() || recommendationsPending}
            onClick={findRecommendations}
          >
            {recommendationsPending ? "Finding…" : "Find candidates"}
          </Button>
        </div>
        {recommendationState.error ? <p role="alert">{recommendationState.error}</p> : null}
        {recommendationState.candidates.map((candidate) => {
          const selected = selectedRecommendation?.fingerprint === candidate.fingerprint;
          const vehicleDescription = [candidate.vehicle_make, candidate.vehicle_model]
            .filter(Boolean)
            .join(" ");
          return (
            <div key={candidate.fingerprint} className="border-edge rounded-lg border p-3">
              <p className="text-ink text-sm">
                #{candidate.rank} · {candidate.driver_name} · {candidate.vehicle_plate_number}
                {vehicleDescription ? ` — ${vehicleDescription}` : ""}
              </p>
              <p className="text-muted mt-1 text-xs">
                Vehicle load {candidate.components.vehicle_load}, driver load{" "}
                {candidate.components.driver_load}, activity{" "}
                {candidate.components.active_tracking_seconds}s
              </p>
              <Button
                type="button"
                className="mt-3"
                onClick={() => chooseRecommendation(candidate)}
              >
                {selected ? "Candidate selected" : "Choose candidate"}
              </Button>
            </div>
          );
        })}
        {recommendationState.candidates.length === 0 && !recommendationState.error ? (
          <p className="text-muted text-sm">No candidates loaded yet.</p>
        ) : null}
      </section>

      {selectedRecommendation ? (
        <>
          <input
            type="hidden"
            name="recommendation_service_city"
            value={selectedRecommendation.service_city}
          />
          <input
            type="hidden"
            name="recommendation_vehicle_type"
            value={selectedRecommendation.vehicle_type}
          />
          <input
            type="hidden"
            name="recommendation_matching_version"
            value={selectedRecommendation.matching_version}
          />
          <input
            type="hidden"
            name="recommendation_fingerprint"
            value={selectedRecommendation.fingerprint}
          />
        </>
      ) : null}

      <Field
        label="Ready creative ID"
        name="creative_id"
        placeholder="UUID of the ready campaign creative"
        required
      />
      <Field label="Offer expires" name="expires_at" type="datetime-local" required />
      <p className="text-muted -mt-3 text-xs">
        Choose the exact ready creative and expiry shown to the driver. Expiry must be in the future
        and no later than the campaign end.
      </p>
      <Field label="Notes" name="notes" placeholder="Optional context for the driver" />

      {state.error ? (
        <p
          role="alert"
          className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm"
        >
          {state.error}
        </p>
      ) : null}

      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Offering…" : "Send offer"}
      </Button>
    </form>
  );
}
