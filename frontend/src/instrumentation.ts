import * as Sentry from "@sentry/nextjs";
import { scrubSentryEvent } from "@/lib/observability";
import { isPublicScanPath, isScanEvent } from "@/lib/qr/privacy";

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
    beforeSend: (event) => (isScanEvent(event) ? null : scrubSentryEvent(event)),
  });
}

export const onRequestError: typeof Sentry.captureRequestError = (...args) => {
  if (isPublicScanPath(args[1].path)) return;
  return Sentry.captureRequestError(...args);
};
