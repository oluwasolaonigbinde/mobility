"use client";

import { useActionState, useState } from "react";
import { createUserAction, type AdminActionState } from "../actions";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { cx } from "@/lib/cx";

const initialState: AdminActionState = {};

const ROLES = [
  { value: "advertiser", label: "Advertiser", hint: "Runs campaigns; gets a company" },
  { value: "driver", label: "Driver", hint: "Drives, tracks trips, earns" },
  { value: "admin", label: "Terrax staff", hint: "Terrax Media operations" },
] as const;

export function CreateUserForm({ fixedRole }: { fixedRole?: "admin" | "driver" | "advertiser" }) {
  const [state, formAction, pending] = useActionState(createUserAction, initialState);
  const [role, setRole] = useState<string>(fixedRole ?? "advertiser");

  return (
    <form action={formAction} className="flex flex-col gap-5" noValidate>
      {fixedRole || state.createdUserId ? (
        <input type="hidden" name="role" value={state.createdUserId ? "advertiser" : fixedRole} />
      ) : (
        <fieldset>
          <legend className="micro text-muted mb-2">Role</legend>
          <div className="grid gap-2 sm:grid-cols-3">
            {ROLES.map((r) => (
              <label
                key={r.value}
                className={cx(
                  "min-w-0 cursor-pointer rounded-lg border p-3.5 transition-colors",
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
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          key={`name-${state.createdUserId ?? "new"}`}
          label="Full name"
          name="full_name"
          required
          placeholder="e.g. Amina Yusuf"
          defaultValue={state.createdFullName}
          readOnly={Boolean(state.createdUserId)}
        />
        <Field
          key={`phone-${state.createdUserId ?? "new"}`}
          label="Phone"
          name="phone"
          placeholder="+234 …"
          autoComplete="off"
          defaultValue={state.createdPhone ?? undefined}
          readOnly={Boolean(state.createdUserId)}
        />
      </div>
      <Field
        key={`email-${state.createdUserId ?? "new"}`}
        label="Email"
        name="email"
        type="email"
        required
        placeholder="them@company.com"
        autoComplete="off"
        defaultValue={state.createdEmail}
        readOnly={Boolean(state.createdUserId)}
      />
      <Field
        key={`password-${state.createdUserId ?? "new"}`}
        label="Temporary password"
        name="password"
        type="text"
        required={!state.createdUserId}
        disabled={Boolean(state.createdUserId)}
        placeholder="min 12 characters — share it with them securely"
        autoComplete="off"
        className="font-mono"
      />

      {role === "admin" ? (
        <Field
          label="Your current password"
          name="current_password"
          type="password"
          required
          autoComplete="current-password"
        />
      ) : null}

      {role === "advertiser" ? (
        <div className="border-edge flex flex-col gap-4 rounded-xl border border-dashed p-4">
          <p className="micro text-muted">Company and its login</p>
          <Field label="Company name" name="org_name" required placeholder="e.g. MTN Nigeria" />
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
        {pending ? "Creating…" : state.createdUserId ? "Retry company creation" : "Create account"}
      </Button>
    </form>
  );
}
