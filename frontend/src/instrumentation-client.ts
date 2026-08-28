import * as Sentry from "@sentry/nextjs";
import { scrubSentryEvent } from "@/lib/observability";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN?.trim();

if (dsn) {
  Sentry.init({
    dsn,
    release: process.env.NEXT_PUBLIC_RELEASE_REVISION?.trim() || undefined,
    tracesSampleRate: 0,
    sendDefaultPii: false,
    beforeSend: scrubSentryEvent,
  });
}
