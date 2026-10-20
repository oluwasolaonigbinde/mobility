"use client";

import { useEffect } from "react";
import { captureClientError } from "@/lib/client-monitoring";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";

/**
 * Root error boundary. Shown when a server component throws an unexpected
 * error (expected errors are handled at their call sites). No stack traces
 * or internals leak to the user. The captured exception remains available to operators.
 */
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
    <main className="bg-atmosphere flex min-h-dvh items-center justify-center p-6">
      <Panel className="w-full max-w-sm p-8 text-center">
        <h1 className="font-display mt-2 text-2xl font-semibold">Something went wrong.</h1>
        <p className="text-muted mt-3 text-sm">
          Please reload the page. If it happens again, contact Terrax Media.
        </p>
        <Button type="button" onClick={retry} className="mt-6 w-full">
          Reload page
        </Button>
      </Panel>
    </main>
  );
}
