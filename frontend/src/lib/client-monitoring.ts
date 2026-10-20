import { scrubSentryEvent } from "./observability";

let sdk: Promise<typeof import("@sentry/nextjs") | null> | undefined;

/** No DSN means no SDK download and no reporting request. */
export function initializeClientMonitoring() {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN?.trim();
  if (!dsn) return Promise.resolve(null);
  sdk ??= import("@sentry/nextjs")
    .then((sentry) => {
      sentry.init({
        dsn,
        release: process.env.NEXT_PUBLIC_RELEASE_REVISION?.trim() || undefined,
        tracesSampleRate: 0,
        sendDefaultPii: false,
        beforeSend: scrubSentryEvent,
      });
      return sentry;
    })
    .catch(() => null);
  return sdk;
}

export async function captureClientError(error: Error) {
  try {
    const sentry = await initializeClientMonitoring();
    sentry?.captureException(error);
  } catch {
    /* Monitoring must not break the recovery screen. */
  }
}
