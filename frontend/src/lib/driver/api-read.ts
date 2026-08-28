import "server-only";

import { ApiError } from "@/lib/api/errors";

export type DriverApiRead<T> =
  { state: "ready"; data: T } | { state: "missing" | "auth" | "unavailable" };

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
    return { state: "unavailable" };
  }
}
