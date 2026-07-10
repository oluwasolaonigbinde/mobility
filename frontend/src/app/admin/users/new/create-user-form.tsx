"use client";

import { useActionState, useState } from "react";
import { createUserAction, type AdminActionState } from "../actions";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { cx } from "@/lib/cx";

const initialState: AdminActionState = {};

const ROLES = [
  { value: "advertiser", label: "Advertiser", hint: "Runs campaigns; gets an organization" },
  { value: "driver", label: "Driver", hint: "Drives, tracks trips, earns" },
  { value: "admin", label: "Admin / Ops", hint: "Full network control" },
] as const;

export function CreateUserForm() {
  const [state, formAction, pending] = useActionState(createUserAction, initialState);
  const [role, setRole] = useState<string>("advertiser");

  return (
    <form action={formAction} className="flex flex-col gap-5" noValidate>
      <fieldset>
        <legend className="micro text-muted mb-2">Role</legend>
        <div className="flex gap-2">
          {ROLES.map((r) => (
            <label
              key={r.value}
              className={cx(
                "flex-1 cursor-pointer rounded-lg border p-3.5 transition-colors",
                role === r.value
                  ? "border-amber/60 bg-amber/10"
                  : "border-edge bg-raised hover:border-edge-strong",
              )}
            >
              <input
                type="radio"
                name="role"
                value={r.value}
                checked={role === r.value}
                onChange={() => setRole(r.value)}
                className="sr-only"
              />
              <span className="block text-sm font-medium">{r.label}</span>
              <span className="micro text-faint mt-0.5 block">{r.hint}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Full name" name="full_name" required placeholder="e.g. Amina Yusuf" />
        <Field label="Phone" name="phone" placeholder="+234 …" autoComplete="off" />
      </div>
      <Field
        label="Email"
        name="email"
        type="email"
        required
        placeholder="them@company.com"
        autoComplete="off"
      />
      <Field
        label="Temporary password"
        name="password"
        type="text"
        required
        placeholder="min 12 characters — share it with them securely"
        autoComplete="off"
        className="font-mono"
      />

      {role === "advertiser" ? (
        <div className="border-edge flex flex-col gap-4 rounded-xl border border-dashed p-4">
          <p className="micro text-muted">
            Advertiser organization{" "}
            <span className="text-faint">(optional — created with this user as owner)</span>
          </p>
          <Field label="Organization name" name="org_name" placeholder="e.g. MTN Nigeria" />
          <Field
            label="Currency"
            name="org_currency"
            placeholder="NGN"
            maxLength={3}
            className="font-mono uppercase"
          />
        </div>
      ) : null}

      {state.error ? (
        <p
          role="alert"
          className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm"
        >
          {state.error}
        </p>
      ) : null}

      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Creating…" : "Create account"}
      </Button>
    </form>
  );
}
