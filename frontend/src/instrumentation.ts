import * as Sentry from "@sentry/nextjs";
import { scrubSentryEvent } from "@/lib/observability";

export function register() {
  const dsn = process.env.SENTRY_DSN?.trim();
  if (!dsn) {
    return;
  }

  Sentry.init({
    dsn,
    release: process.env.RELEASE_REVISION?.trim() || undefined,
    tracesSampleRate: 0,
    sendDefaultPii: false,
    beforeSend: scrubSentryEvent,
  });
}

export const onRequestError = Sentry.captureRequestError;
