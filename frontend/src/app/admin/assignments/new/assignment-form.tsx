"use client";
import { useActionState, useRef, useState, useTransition } from "react";
import {
  createAssignmentAction,
  listAssignmentRecommendationsAction,
  type AdminActionState,
  type AssignmentRecommendation,
} from "../actions";
import { SearchSelect } from "../../search-select";
import { Field } from "@/components/ui/field";
import { Button } from "@/components/ui/button";
import Link from "next/link";

export function AssignmentForm({
  campaignId,
  driverId,
}: {
  campaignId?: string;
  driverId?: string;
}) {
  const [state, action, pending] = useActionState(createAssignmentAction, {} as AdminActionState);
  const [campaign, setCampaign] = useState(campaignId ?? "");
  const [driver, setDriver] = useState(driverId ?? "");
  const [vehicle, setVehicle] = useState("");
  const [city, setCity] = useState("");
  // Results, errors and a chosen recommendation belong to the criteria they were found
  // with (campaign, city and the driver this form is scoped to); any other inputs hide them.
  const criteriaKey = JSON.stringify([campaign, city.trim(), driverId ?? ""]);
  const [search, setSearch] = useState<{
    key: string;
    city: string;
    candidates: AssignmentRecommendation[];
    error?: string;
  } | null>(null);
  const latestToken = useRef(0);
  const [chosen, setChosen] = useState<{ key: string; recommendation: AssignmentRecommendation }>();
  const [finding, start] = useTransition();
  const current = !finding && search?.key === criteriaKey ? search : undefined;
  const recommendations = current?.candidates ?? [];
  const error = current?.error;
  const showEmpty = !!current && !current.error && !current.candidates.length;
  const selected = chosen?.key === criteriaKey ? chosen.recommendation : undefined;
  const setSelected = (recommendation?: AssignmentRecommendation) =>
    setChosen(recommendation ? { key: criteriaKey, recommendation } : undefined);
  function invalidateSearch() {
    latestToken.current += 1;
    setSearch(null);
    setChosen(undefined);
  }
  return (
    <form action={action} className="flex flex-col gap-5">
      {campaignId ? (
        <input type="hidden" name="campaign_id" value={campaignId} />
      ) : (
        <SearchSelect
          kind="campaign"
          name="campaign_id"
          label="Campaign"
          value={campaign}
          onSelect={(id) => {
            setCampaign(id);
            invalidateSearch();
          }}
        />
      )}
      {driverId ? (
        <input type="hidden" name="driver_profile_id" value={driverId} />
      ) : (
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
      )}
      <SearchSelect
        key={`vehicle-${driver}`}
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
        key={`creative-${campaign}`}
        kind="creative"
        name="creative_id"
        label="Approved artwork"
        parentId={campaign || undefined}
      />
      <section className="border-edge rounded-lg border p-3" aria-label="Drivers and cars">
        <h2>Drivers and cars</h2>
        <label className="text-muted flex flex-col gap-1 text-sm">
          City
          <input
            value={city}
            onChange={(e) => {
              setCity(e.target.value);
              invalidateSearch();
            }}
            className="border-edge bg-raised rounded border p-2"
          />
        </label>
        <Button
          type="button"
          disabled={!campaign || !city.trim() || finding}
          onClick={() =>
            start(async () => {
              const token = ++latestToken.current;
              const key = criteriaKey;
              const next = await listAssignmentRecommendationsAction({
                campaign_id: campaign,
                service_city: city,
              });
              if (token !== latestToken.current) return;
              setSearch({
                key,
                city: city.trim(),
                candidates: (next.candidates ?? []).filter(
                  (candidate) => !driverId || candidate.driver_profile_id === driverId,
                ),
                error: next.error,
              });
              setSelected(undefined);
            })
          }
        >
          {finding ? "Finding…" : "Find drivers"}
        </Button>
        {error ? <p role="alert">{error}</p> : null}
        {showEmpty ? (
          <p role="status" className="text-muted text-sm">
            {driverId
              ? `This driver has no match for this campaign in ${current.city}.`
              : `No drivers found for this campaign in ${current.city}.`}
          </p>
        ) : null}
        {recommendations.map((c) => (
          <div className="border-edge my-2 rounded border p-3" key={c.fingerprint}>
            <p>
              {c.driver_name} · {c.vehicle_plate_number}
            </p>
            <p className="text-muted text-xs">
              Car jobs: {c.components.vehicle_load} · Driver jobs: {c.components.driver_load}
            </p>
            <Button
              type="button"
              onClick={() => {
                setDriver(c.driver_profile_id);
                setVehicle(c.vehicle_id);
                setSelected(c);
              }}
            >
              Choose
            </Button>
          </div>
        ))}
        {selected ? (
          <>
            <p className="text-green">
              Selected: {selected.driver_name} · {selected.vehicle_plate_number}
            </p>
            <input type="hidden" name="recommendation_vehicle_type" value={selected.vehicle_type} />
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
      <Field
        label="Offer expires (Nigeria time, WAT)"
        name="expires_at"
        type="datetime-local"
        required
      />
      <p className="text-muted text-sm">
        Expiry must be in the future and before the campaign ends.
      </p>
      <Field label="Notes" name="notes" />
      {state.error ? (
        <p role="alert" className="text-coral">
          {state.error}
        </p>
      ) : null}
      {state.cityRequiredForDriver ? (
        <Link
          className="text-green underline"
          href={`/admin/drivers/${state.cityRequiredForDriver}#details`}
        >
          Add the driver’s city
        </Link>
      ) : null}
      <Button type="submit" disabled={pending}>
        {pending ? "Offering…" : "Send offer"}
      </Button>
    </form>
  );
}
