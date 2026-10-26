import type { ApplicationContinuation } from "@/lib/api/audit-batch2";

const states: Record<ApplicationContinuation["state"], ApplicationContinuation["step"]> = {
  details_needed: "details",
  details_in_review: "details",
  details_changes_needed: "details",
  car_needed: "car",
  car_in_review: "car",
  car_changes_needed: "car",
};

/**
 * The continuation answer, or null (shown as an unavailable link) when it is
 * expired or inconsistent. A reason is kept only for a changes-needed state.
 */
export function validContinuation(value: unknown): ApplicationContinuation | null {
  if (!value || typeof value !== "object") return null;
  const {
    step,
    state,
    changes_reason: reason,
    expires_at: expiresAt,
  } = value as Record<string, unknown>;
  if (
    typeof state !== "string" ||
    !Object.hasOwn(states, state) ||
    states[state as ApplicationContinuation["state"]] !== step ||
    typeof expiresAt !== "string" ||
    !(Date.parse(expiresAt) > Date.now())
  )
    return null;
  const changes = state.endsWith("_changes_needed");
  if (changes ? typeof reason !== "string" || !reason.trim() : reason != null) return null;
  return {
    step: step as ApplicationContinuation["step"],
    state: state as ApplicationContinuation["state"],
    changes_reason: changes ? (reason as string) : null,
    expires_at: expiresAt,
  };
}
