"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";

/**
 * Root error boundary. Shown when a server component throws an unexpected
 * error (expected errors are handled at their call sites). No stack traces
 * or internals leak to the user — the digest is enough to find it in logs.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Server logs carry the full error; the client just records occurrence.
    console.error("Unhandled UI error", error.digest ?? error.message);
  }, [error]);

  return (
    <main className="bg-atmosphere flex min-h-dvh items-center justify-center p-6">
      <Panel className="w-full max-w-sm p-8 text-center">
        <p className="micro text-coral">Something broke</p>
        <h1 className="font-display mt-2 text-2xl font-semibold">
          That wasn&apos;t supposed to happen.
        </h1>
        <p className="text-muted mt-3 text-sm">
          The error has been logged{error.digest ? ` (ref ${error.digest})` : ""}. Try again — if it
          persists, contact ops with the reference.
        </p>
        <Button type="button" onClick={reset} className="mt-6 w-full">
          Try again
        </Button>
      </Panel>
    </main>
  );
}
