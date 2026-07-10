"use client";

import { useState, useTransition } from "react";
import { updateUserStatusAction } from "./actions";
import type { components } from "@/lib/api/schema";

type UserStatus = components["schemas"]["UserStatus"];

/** One inverse action per state: suspend active users, reactivate the rest. */
export function UserStatusMenu({ userId, status }: { userId: string; status: UserStatus }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string>();

  const target: UserStatus = status === "active" ? "suspended" : "active";
  const label = status === "active" ? "Suspend" : "Reactivate";

  function run() {
    if (
      target === "suspended" &&
      !window.confirm("Suspend this account? They lose access immediately.")
    ) {
      return;
    }
    setError(undefined);
    startTransition(async () => {
      const result = await updateUserStatusAction({ userId, status: target });
      if (result.error) setError(result.error);
    });
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={run}
        disabled={pending}
        className={
          "micro transition-colors disabled:opacity-50 " +
          (target === "suspended" ? "text-muted hover:text-coral" : "text-muted hover:text-green")
        }
      >
        {pending ? "…" : label}
      </button>
      {error ? (
        <p role="alert" className="text-coral text-xs">
          {error}
        </p>
      ) : null}
    </div>
  );
}
