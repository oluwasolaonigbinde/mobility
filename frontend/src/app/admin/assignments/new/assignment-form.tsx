"use client";
import { useActionState, useState, useTransition } from "react";
import {
  createAssignmentAction,
  listAssignmentRecommendationsAction,
  type AdminActionState,
  type AssignmentRecommendation,
} from "../actions";
import { SearchSelect } from "../../search-select";
import { Field } from "@/components/ui/field";
import { Button } from "@/components/ui/button";

export function AssignmentForm() {
  const [state, action, pending] = useActionState(createAssignmentAction, {} as AdminActionState);
  const [campaign, setCampaign] = useState("");
  const [driver, setDriver] = useState("");
  const [vehicle, setVehicle] = useState("");
  const [city, setCity] = useState("");
  const [recommendations, setRecommendations] = useState<AssignmentRecommendation[]>([]);
  const [selected, setSelected] = useState<AssignmentRecommendation>();
  const [error, setError] = useState<string>();
  const [finding, start] = useTransition();
  return (
    <form action={action} className="flex flex-col gap-5">
      <SearchSelect
        kind="campaign"
        name="campaign_id"
        label="Campaign"
        value={campaign}
        onSelect={(id) => {
          setCampaign(id);
          setSelected(undefined);
          setRecommendations([]);
        }}
      />
      <SearchSelect
        kind="driver"
        name="driver_profile_id"
        label="Driver"
        value={driver}
        onSelect={(id) => {
          setDriver(id);
          setVehicle("");
          setSelected(undefined);
        }}
      />
      <SearchSelect
        key={driver}
        kind="vehicle"
        name="vehicle_id"
        label="Vehicle"
        parentId={driver || undefined}
        value={vehicle}
        onSelect={(id) => {
          setVehicle(id);
          setSelected(undefined);
        }}
      />
      <SearchSelect
        key={campaign}
        kind="creative"
        name="creative_id"
        label="Approved artwork"
        parentId={campaign || undefined}
      />
      <section className="border-edge rounded-lg border p-3" aria-label="Ranked car candidates">
        <h2>Ranked car candidates</h2>
        <label className="text-muted flex flex-col gap-1 text-sm">
          Service city
          <input
            value={city}
            onChange={(e) => setCity(e.target.value)}
            className="border-edge bg-raised rounded border p-2"
          />
        </label>
        <Button
          type="button"
          disabled={!campaign || !city.trim() || finding}
          onClick={() =>
            start(async () => {
              const next = await listAssignmentRecommendationsAction({
                campaign_id: campaign,
                service_city: city,
              });
              setRecommendations(next.candidates ?? []);
              setError(next.error);
              setSelected(undefined);
            })
          }
        >
          {finding ? "Finding…" : "Find candidates"}
        </Button>
        {error ? <p role="alert">{error}</p> : null}
        {recommendations.map((c) => (
          <div className="border-edge my-2 rounded border p-3" key={c.fingerprint}>
            <p>
              {c.driver_name} · {c.vehicle_plate_number}
            </p>
            <p className="text-muted text-xs">
              Vehicle load {c.components.vehicle_load} · driver load {c.components.driver_load}
            </p>
            <Button
              type="button"
              onClick={() => {
                setDriver(c.driver_profile_id);
                setVehicle(c.vehicle_id);
                setSelected(c);
              }}
            >
              Choose candidate
            </Button>
          </div>
        ))}
        {selected ? (
          <>
            <p className="text-green">
              Selected: {selected.driver_name} · {selected.vehicle_plate_number}
            </p>
            <input type="hidden" name="recommendation_service_city" value={selected.service_city} />
            <input
              type="hidden"
              name="recommendation_matching_version"
              value={selected.matching_version}
            />
            <input type="hidden" name="recommendation_fingerprint" value={selected.fingerprint} />
          </>
        ) : null}
      </section>
      <Field label="Offer expires" name="expires_at" type="datetime-local" required />
      <p className="text-muted text-sm">
        Expiry must be in the future and no later than campaign end. Sending an offer does not
        activate work.
      </p>
      <Field label="Notes" name="notes" />
      {state.error ? (
        <p role="alert" className="text-coral">
          {state.error}
        </p>
      ) : null}
      <Button type="submit" disabled={pending}>
        {pending ? "Offering…" : "Send offer"}
      </Button>
    </form>
  );
}
