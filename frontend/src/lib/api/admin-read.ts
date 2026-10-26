import "server-only";
import { redirect, unstable_rethrow } from "next/navigation";
import { ApiError } from "./errors";

/** Optional staff panels keep failed reads distinct from successful empty data. */
export function adminValueFailure(error: unknown): undefined {
  unstable_rethrow(error);
  if (error instanceof ApiError && error.status === 401) redirect("/login");
  // Fixed fields only: never include backend messages, details, URLs or account data.
  console.warn("Cardvert admin read failed", {
    status: error instanceof ApiError ? error.status : "unavailable",
  });
  return undefined;
}

export function adminReadFailure(error: unknown): { data: undefined } {
  adminValueFailure(error);
  return { data: undefined };
}
