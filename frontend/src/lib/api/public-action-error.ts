import { ApiError } from "./errors";

export function publicActionError(
  error: unknown,
  messages: Readonly<Record<string, string>>,
  fallback: string,
): string {
  if (!(error instanceof ApiError)) return fallback;
  return messages[error.code] ?? fallback;
}
