import * as Sentry from "@sentry/nextjs";

export function register() {
  const dsn = process.env.SENTRY_DSN?.trim();
  if (!dsn) {
    return;
  }

  Sentry.init({
    dsn,
    tracesSampleRate: 0,
    sendDefaultPii: false,
  });
}

export const onRequestError = Sentry.captureRequestError;
