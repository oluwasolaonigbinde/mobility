"use client";

import { useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";

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
      const response = await fetch(`/api/admin/campaigns/${campaignId}/reports/re-run`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ client_request_id: identity }),
      });
      const body = (await response.json()) as { error?: { message?: string } };
      if (!response.ok) {
        if (response.status >= 400 && response.status < 500) {
          setRequestId(null);
          try {
            sessionStorage.removeItem(storageKey);
          } catch {
            /* optional */
          }
        }
        throw new Error(body.error?.message || "Report request could not be confirmed");
      }
      setRequestId(null);
      try {
        sessionStorage.removeItem(storageKey);
      } catch {
        /* optional */
      }
      setMessage("Report requested. Refresh the list when it is ready.");
      router.refresh();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "The result is uncertain. Check the request again.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="border-edge bg-raised mb-6 space-y-3 rounded-xl border p-5">
      <h2 className="font-display text-lg font-semibold">Campaign reports</h2>
      <p className="text-muted max-w-3xl text-sm leading-relaxed">
        One report each week and a final report when the campaign ends. Re-run prepares a new
        version for the latest due period. Issued files stay unchanged.
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
