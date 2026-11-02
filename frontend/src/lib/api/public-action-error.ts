import { ApiError } from "./errors";
import { unstable_rethrow } from "next/navigation";

const sharedMessages: Readonly<Record<string, string>> = {
  TRY_AGAIN_SOON: "This page is busy. Try again in a moment.",
};

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
  const shared = Object.hasOwn(sharedMessages, error.code) ? sharedMessages[error.code] : undefined;
  return typeof message === "string" ? message : (shared ?? fallback);
}
