import { ApiError } from "./errors";
import { unstable_rethrow } from "next/navigation";

export function publicActionError(
  error: unknown,
  messages: Readonly<Record<string, string>> = {},
  fallback = "The request could not be completed. Check the details and try again.",
): string {
  unstable_rethrow(error);
  // Never log backend text/details, submitted values, URLs or arbitrary error objects.
  console.warn("Cardvert action failed", {
    status: error instanceof ApiError ? error.status : "unavailable",
  });
  if (!(error instanceof ApiError)) return fallback;
  const message = Object.hasOwn(messages, error.code) ? messages[error.code] : undefined;
  return typeof message === "string" ? message : fallback;
}
