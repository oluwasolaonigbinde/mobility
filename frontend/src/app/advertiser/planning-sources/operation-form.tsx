"use client";

import { useActionState, type FormEvent } from "react";
import { deactivateSourceAction, removeSourceLinkAction, type SourceActionState } from "./actions";

const initialState: SourceActionState = {};

export function stableOperationKey(state: SourceActionState) {
  const completed = Boolean(state.success);

  return {
    inputKey: `${completed ? "new" : "retry"}:${state.operationKey ?? ""}`,
    defaultValue: completed ? "" : (state.operationKey ?? ""),
  };
}

export function ensureOperationKey(event: FormEvent<HTMLFormElement>) {
  const input = event.currentTarget.elements.namedItem("operation_key");
  if (input instanceof HTMLInputElement && !input.value) {
    input.value = crypto.randomUUID();
  }
}

export function TerminalPlanningActionForm({
  kind,
  resourceId,
  label,
}: {
  kind: "deactivate-source" | "remove-link";
  resourceId: string;
  label: string;
}) {
  const serverAction =
    kind === "deactivate-source"
      ? deactivateSourceAction.bind(null, resourceId)
      : removeSourceLinkAction.bind(null, resourceId);
  const [state, action, pending] = useActionState(serverAction, initialState);
  const operation = stableOperationKey(state);

  return (
    <form action={action} onSubmit={ensureOperationKey}>
      <input
        key={operation.inputKey}
        type="hidden"
        name="operation_key"
        defaultValue={operation.defaultValue}
      />
      {state.error ? (
        <p className="text-coral mb-2 text-sm" role="alert">
          {state.error}
        </p>
      ) : null}
      <button
        disabled={pending}
        className="border-edge hover:border-coral rounded-lg border px-3 py-2 text-sm disabled:opacity-50"
      >
        {pending ? "Working…" : label}
      </button>
    </form>
  );
}
