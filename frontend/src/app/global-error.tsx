"use client";

import { useEffect } from "react";
import * as Sentry from "@sentry/nextjs";

export default function GlobalError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body>
        <main
          style={{
            alignItems: "center",
            display: "flex",
            fontFamily: "system-ui, sans-serif",
            justifyContent: "center",
            minHeight: "100vh",
            padding: "1.5rem",
          }}
        >
          <section style={{ maxWidth: "24rem", textAlign: "center" }}>
            <title>Something went wrong · Cardvert</title>
            <h1>That wasn&apos;t supposed to happen.</h1>
            <p>
              The error has been logged
              {error.digest ? ` (ref ${error.digest})` : ""}. Try again, or contact ops if it
              persists.
            </p>
            <button type="button" onClick={unstable_retry}>
              Try again
            </button>
          </section>
        </main>
      </body>
    </html>
  );
}
