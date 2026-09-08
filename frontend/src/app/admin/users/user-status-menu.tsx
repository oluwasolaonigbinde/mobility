"use client";

import { useState, useTransition } from "react";
import { updateUserStatusAction } from "./actions";
import type { components } from "@/lib/api/schema";
import { Field } from "@/components/ui/field";

type UserStatus = components["schemas"]["UserStatus"];

/** One inverse action per state: suspend active users, reactivate the rest. */
export function UserStatusMenu({
  userId,
  status,
  role,
}: {
  userId: string;
  status: UserStatus;
  role: components["schemas"]["UserRole"];
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string>();
  const [reauthenticating, setReauthenticating] = useState(false);

  const target: UserStatus = status === "active" ? "suspended" : "active";
  const label = status === "active" ? "Suspend" : "Reactivate";

  function run(currentPassword?: string) {
    if (role === "admin" && target === "active" && !currentPassword) {
      setReauthenticating(true);
      return;
    }
    if (
      target === "suspended" &&
      !window.confirm("Suspend this account? They lose access immediately.")
    ) {
      return;
    }
    setError(undefined);
    startTransition(async () => {
      const result = await updateUserStatusAction({
        userId,
        status: target,
        ...(currentPassword !== undefined ? { current_password: currentPassword } : {}),
      });
      setReauthenticating(false);
      if (result.error) setError(result.error);
    });
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={() => run()}
        disabled={pending}
        className={
          "micro transition-colors disabled:opacity-50 " +
          (target === "suspended" ? "text-muted hover:text-coral" : "text-muted hover:text-green")
        }
      >
        {pending ? "…" : label}
      </button>
      {reauthenticating ? (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const form = event.currentTarget;
            const proof = new FormData(form).get("current_password");
            if (typeof proof !== "string" || !proof) return;
            form.reset();
            run(proof);
          }}
          className="flex flex-col gap-2"
        >
          <Field
            label="Your current password"
            name="current_password"
            type="password"
            required
            autoComplete="current-password"
            disabled={pending}
          />
          <button type="submit" disabled={pending}>
            Confirm reactivation
          </button>
          <button type="button" disabled={pending} onClick={() => setReauthenticating(false)}>
            Cancel
          </button>
        </form>
      ) : null}
      {error ? (
        <p role="alert" className="text-coral text-xs">
          {error}
        </p>
      ) : null}
    </div>
  );
}
