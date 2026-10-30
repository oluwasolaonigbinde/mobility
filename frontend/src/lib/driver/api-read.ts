import "server-only";

import { ApiError } from "@/lib/api/errors";

export type DriverApiRead<T> =
  | { state: "ready"; data: T }
  | { state: "missing" | "auth" }
  | { state: "unavailable"; message?: string };

export function driverJobConflictMessage(error: unknown): string | undefined {
  if (
    error instanceof ApiError &&
    error.status === 409 &&
    error.code === "MULTIPLE_ACTIVE_ASSIGNMENTS"
  )
    return "Two jobs are live on your account. Please contact support so we can fix it.";
}

/** Preserve the difference between successful emptiness, missing ownership and failed authority. */
export async function readDriverApi<T>(
  operation: () => Promise<{ data?: T }>,
  options: { notFoundIsMissing?: boolean } = {},
): Promise<DriverApiRead<T>> {
  try {
    const { data } = await operation();
    return data === undefined ? { state: "unavailable" } : { state: "ready", data };
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
      return { state: "auth" };
    }
    if (error instanceof ApiError && error.status === 404 && options.notFoundIsMissing) {
      return { state: "missing" };
    }
    const message = driverJobConflictMessage(error);
    if (message) return { state: "unavailable", message };
    return { state: "unavailable" };
  }
}
