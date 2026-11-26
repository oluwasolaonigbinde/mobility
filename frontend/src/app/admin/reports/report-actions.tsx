"use client";

import { useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";

const UNCERTAIN_REQUEST = "We couldn't confirm this request. Check the list before trying again.";

/** The route has already replaced backend text with fixed public copy. */
function publicRefusal(body: unknown): string | undefined {
  const message = (body as { error?: { message?: unknown } } | null)?.error?.message;
  return typeof message === "string" && message.trim() ? message : undefined;
}

function subscribeToStorage(callback: () => void) {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}

export function RerunReportForm({ campaignId, staffId }: { campaignId: string; staffId: string }) {
  const router = useRouter();
  const [pendingId, setRequestId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const storageKey = `campaign-report-rerun:${staffId}:${campaignId}`;
  const previous = useSyncExternalStore(
    subscribeToStorage,
    () => {
      try {
        return sessionStorage.getItem(storageKey);
      } catch {
        return null;
      }
    },
    () => null,
  );
  const requestId = pendingId || previous;
  function clearRequest() {
    setRequestId(null);
    try {
      sessionStorage.removeItem(storageKey);
    } catch {
      /* optional */
    }
  }
  async function rerun() {
    const identity = requestId || crypto.randomUUID();
    setRequestId(identity);
    setBusy(true);
    try {
      sessionStorage.setItem(storageKey, identity);
    } catch {
      /* State retains it. */
    }
    try {
      let response: Response;
      try {
        response = await fetch(`/api/admin/campaigns/${campaignId}/reports/re-run`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ client_request_id: identity }),
        });
      } catch {
        // Network failure: the request may have arrived, so keep the same request ID.
        setMessage(UNCERTAIN_REQUEST);
        return;
      }
      let body: unknown;
      try {
        body = await response.json();
      } catch {
        // An unreadable reply decides nothing, whatever its status: keep the request ID.
        setMessage(UNCERTAIN_REQUEST);
        return;
      }
      if (response.status >= 400 && response.status < 500) {
        clearRequest();
        setMessage(publicRefusal(body) ?? "This report couldn't be requested. Try again.");
        return;
      }
      if (!response.ok) {
        setMessage(UNCERTAIN_REQUEST);
        return;
      }
      clearRequest();
      setMessage("Report requested. Refresh the list when it is ready.");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="border-edge bg-raised mb-6 space-y-3 rounded-xl border p-5">
      <h2 className="font-display text-lg font-semibold">Campaign reports</h2>
      <p className="text-muted max-w-3xl text-sm leading-relaxed">
        Re-run prepares a report for the latest due period. Issued files stay unchanged.
      </p>
      <Button variant="ghost" type="button" disabled={busy} onClick={() => void rerun()}>
        {busy ? "Checking…" : requestId ? "Check request" : "Re-run"}
      </Button>
      <p role="status" className="text-muted text-sm">
        {message || (previous ? "Check the previous request before re-running again." : "")}
      </p>
    </section>
  );
}

export function ReportDownloads({ reportId, legacy }: { reportId: string; legacy: boolean }) {
  return (
    <div className="flex flex-wrap gap-3">
      {["csv", "pdf"].map((format) => (
        <a
          key={format}
          className="border-edge bg-raised text-ink hover:border-edge-strong inline-flex h-11 items-center justify-center rounded-lg border px-5 text-sm font-medium transition-colors"
          href={`/api/admin/reports/${reportId}/download?format=${format}&legacy=${legacy}`}
        >
          Download {format.toUpperCase()}
        </a>
      ))}
    </div>
  );
}
