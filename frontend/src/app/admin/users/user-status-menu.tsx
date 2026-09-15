"use client";

import { useRef, useState, useTransition } from "react";
import { updateUserStatusAction } from "./actions";
import type { components } from "@/lib/api/schema";
import { Field } from "@/components/ui/field";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";

type UserStatus = components["schemas"]["UserStatus"];

/** One inverse action per state: suspend active users, reactivate the rest. */
export function UserStatusMenu({
  userId,
  userLabel,
  status,
  role,
}: {
  userId: string;
  userLabel: string;
  status: UserStatus;
  role: components["schemas"]["UserRole"];
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string>();
  const [reauthenticating, setReauthenticating] = useState(false);
  const [confirmingSuspension, setConfirmingSuspension] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const target: UserStatus = status === "active" ? "suspended" : "active";
  const label = status === "active" ? "Suspend" : "Reactivate";

  function run(currentPassword?: string, confirmed = false) {
    if (role === "admin" && target === "active" && !currentPassword) {
      setReauthenticating(true);
      return;
    }
    if (target === "suspended" && !confirmed) {
      setConfirmingSuspension(true);
      return;
    }
    setConfirmingSuspension(false);
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
        ref={triggerRef}
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
      <ConfirmationDialog
        open={confirmingSuspension}
        onOpenChange={setConfirmingSuspension}
        title={`Suspend ${userLabel}?`}
        description="This account will lose access immediately."
        cancelLabel="Keep account active"
        confirmLabel="Confirm suspension"
        onConfirm={() => run(undefined, true)}
        returnFocusRef={triggerRef}
        pending={pending}
      />
    </div>
  );
}
