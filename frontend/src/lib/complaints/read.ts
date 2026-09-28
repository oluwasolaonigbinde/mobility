import "server-only";

import { ApiError } from "@/lib/api/errors";

export type ComplaintRead<T> =
  { state: "ready"; data: T } | { state: "missing" | "auth" | "unavailable" };

/** Keep "not yours or gone", "signed out" and "couldn't load" apart for the screen. */
export async function readComplaintApi<T>(
  operation: () => Promise<{ data?: T }>,
): Promise<ComplaintRead<T>> {
  try {
    const { data } = await operation();
    return data === undefined ? { state: "unavailable" } : { state: "ready", data };
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
      return { state: "auth" };
    }
    if (error instanceof ApiError && error.status === 404) return { state: "missing" };
    return { state: "unavailable" };
  }
}
