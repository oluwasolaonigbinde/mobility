"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { unlockFeedbackAction, type UnlockState } from "./actions";

const initialState: UnlockState = {};

export function UnlockForm() {
  const [state, action, pending] = useActionState(unlockFeedbackAction, initialState);
  return (
    <form action={action} className="grid gap-4">
      <Field
        label="Password"
        name="password"
        type="password"
        autoComplete="current-password"
        required
        error={state.error}
      />
      <Button type="submit" disabled={pending}>
        {pending ? "Checking…" : "View feedback"}
      </Button>
    </form>
  );
}
