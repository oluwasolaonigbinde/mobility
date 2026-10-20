"use client";

import { useEffect } from "react";
import { captureClientError } from "@/lib/client-monitoring";

export default function GlobalError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    void captureClientError(error);
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
            <h1>Something went wrong.</h1>
            <p>Please reload the page. If it happens again, contact Terrax Media.</p>
            <button type="button" onClick={retry}>
              Reload page
            </button>
          </section>
        </main>
      </body>
    </html>
  );
}
