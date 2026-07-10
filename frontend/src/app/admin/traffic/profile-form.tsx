"use client";

import { useActionState } from "react";
import { saveProfileAction, type ProfileActionState } from "./actions";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import type { components } from "@/lib/api/schema";

type Profile = components["schemas"]["TrafficDensityProfileRead"];

const initialState: ProfileActionState = {};

export function ProfileForm({ profile }: { profile: Profile | null }) {
  const [state, formAction, pending] = useActionState(saveProfileAction, initialState);
  const d = (v: string | null | undefined) => v ?? "";

  return (
    <form key={profile?.id ?? "new"} action={formAction} className="flex flex-col gap-6" noValidate>
      {profile ? <input type="hidden" name="profile_id" value={profile.id} /> : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Profile name"
          name="name"
          required
          defaultValue={profile?.name ?? ""}
          placeholder="e.g. Abuja weekday"
        />
        <Field
          label="Description"
          name="description"
          defaultValue={d(profile?.description)}
          placeholder="optional"
        />
      </div>

      <fieldset className="grid gap-4 sm:grid-cols-2">
        <legend className="micro text-muted mb-3">Core assumptions</legend>
        <Field
          label="Traffic density / km"
          name="traffic_density_per_km"
          required
          inputMode="decimal"
          defaultValue={d(profile?.traffic_density_per_km)}
          placeholder="e.g. 120"
          className="font-mono"
        />
        <Field
          label="Dwell impressions / minute"
          name="dwell_impressions_per_minute"
          required
          inputMode="decimal"
          defaultValue={d(profile?.dwell_impressions_per_minute)}
          placeholder="e.g. 3"
          className="font-mono"
        />
      </fieldset>

      <fieldset className="grid gap-4 sm:grid-cols-4">
        <legend className="micro text-muted mb-3">Time-of-day weights</legend>
        <Field
          label="Morning"
          name="morning_weight"
          inputMode="decimal"
          defaultValue={d(profile?.morning_weight)}
          placeholder="1.3"
          className="font-mono"
        />
        <Field
          label="Midday"
          name="midday_weight"
          inputMode="decimal"
          defaultValue={d(profile?.midday_weight)}
          placeholder="1.0"
          className="font-mono"
        />
        <Field
          label="Evening"
          name="evening_weight"
          inputMode="decimal"
          defaultValue={d(profile?.evening_weight)}
          placeholder="1.4"
          className="font-mono"
        />
        <Field
          label="Night"
          name="night_weight"
          inputMode="decimal"
          defaultValue={d(profile?.night_weight)}
          placeholder="0.5"
          className="font-mono"
        />
      </fieldset>

      <fieldset className="grid gap-4 sm:grid-cols-3">
        <legend className="micro text-muted mb-3">Zone weights</legend>
        <Field
          label="Target zone"
          name="target_zone_weight"
          inputMode="decimal"
          defaultValue={d(profile?.target_zone_weight)}
          placeholder="1.5"
          className="font-mono"
        />
        <Field
          label="Bonus zone"
          name="bonus_zone_weight"
          inputMode="decimal"
          defaultValue={d(profile?.bonus_zone_weight)}
          placeholder="1.2"
          className="font-mono"
        />
        <Field
          label="Exclusion zone"
          name="exclusion_zone_weight"
          inputMode="decimal"
          defaultValue={d(profile?.exclusion_zone_weight)}
          placeholder="0"
          className="font-mono"
        />
      </fieldset>

      <label className="micro text-muted flex cursor-pointer items-center gap-2">
        <input
          type="checkbox"
          name="is_default"
          defaultChecked={profile?.is_default ?? false}
          className="accent-amber"
        />
        Use as the default profile for new estimates
      </label>

      {state.error ? (
        <p
          role="alert"
          className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm"
        >
          {state.error}
        </p>
      ) : null}
      {state.saved && !state.error ? (
        <p className="border-green/40 bg-green/10 text-green rounded-lg border px-3.5 py-2.5 text-sm">
          ✓ Profile saved — future impression estimates use these assumptions.
        </p>
      ) : null}

      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Saving…" : profile ? "Update profile" : "Create profile"}
      </Button>
    </form>
  );
}
