"use client";

import { useState, useSyncExternalStore } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Panel } from "@/components/ui/panel";
import type { components } from "@/lib/api/schema";

type ReportList = components["schemas"]["CampaignReportList"];
type RequestBody = components["schemas"]["CampaignReportCreate"];
type Campaign = { id: string; name: string };

function subscribeToStorage(callback: () => void) {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}

async function readReports(url: string): Promise<ReportList> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error("Reports could not be loaded");
  return response.json() as Promise<ReportList>;
}

export function Reports({
  campaigns,
  today,
  campaignId,
  sessionScope,
}: {
  campaigns: Campaign[];
  today: string;
  campaignId?: string;
  sessionScope: string;
}) {
  const queryClient = useQueryClient();
  const [offset, setOffset] = useState(0);
  const [selection, setSelection] = useState(campaignId || "all");
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(today);
  const [pendingRequest, setPending] = useState<RequestBody | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const storageKey = `campaign-report-request:${sessionScope}:${campaignId || "all"}`;
  const queryKey = ["campaign-reports", sessionScope, campaignId, offset];
  const url = `/api/advertiser/reports?${new URLSearchParams({
    offset: String(offset),
    ...(campaignId ? { campaign_id: campaignId } : {}),
  })}`;
  const reports = useQuery({
    queryKey,
    queryFn: () => readReports(url),
    refetchInterval: (query) =>
      query.state.data?.items.some((item) => item.status === "queued") ? 3000 : false,
  });

  const saved = useSyncExternalStore(
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
  let restored: RequestBody | null = null;
  if (saved) {
    try {
      const value = JSON.parse(saved) as RequestBody;
      if (value.client_request_id && value.start_date && value.end_date) {
        restored = value;
      }
    } catch {
      /* An unavailable browser store does not block reports. */
    }
  }
  const pending = pendingRequest || restored;

  async function requestReport() {
    const payload = pending || {
      client_request_id: crypto.randomUUID(),
      start_date: start,
      end_date: end,
      campaign_id: selection === "all" ? null : selection,
    };
    setPending(payload);
    setBusy(true);
    setMessage("");
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(payload));
    } catch {
      /* retry uses state */
    }
    try {
      const response = await fetch("/api/advertiser/reports", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = (await response.json()) as { error?: { message?: string } };
      if (!response.ok) {
        if (response.status >= 400 && response.status < 500) {
          setPending(null);
          try {
            sessionStorage.removeItem(storageKey);
          } catch {
            /* optional */
          }
        }
        throw new Error(body.error?.message || "Report could not be requested");
      }
      setPending(null);
      try {
        sessionStorage.removeItem(storageKey);
      } catch {
        /* optional */
      }
      setMessage("Report requested. Its downloads will appear when it is ready.");
      setOffset(0);
      await queryClient.invalidateQueries({ queryKey: ["campaign-reports", sessionScope] });
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "The result is uncertain. Check this request again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <Panel>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void requestReport();
          }}
          className="space-y-4"
        >
          <h2>Download a report</h2>
          <p>Choose Nigeria calendar dates (WAT). Today includes results verified so far.</p>
          <label className="block">
            Campaign
            <select
              aria-label="Campaign"
              value={pending ? pending.campaign_id || "all" : selection}
              disabled={busy || !!pending || !!campaignId}
              onChange={(event) => setSelection(event.target.value)}
            >
              {!campaignId ? <option value="all">All my campaigns</option> : null}
              {campaigns.map((campaign) => (
                <option key={campaign.id} value={campaign.id}>
                  {campaign.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            From
            <input
              aria-label="From"
              type="date"
              required
              value={pending?.start_date || start}
              max={end || today}
              disabled={busy || !!pending}
              onChange={(event) => setStart(event.target.value)}
            />
          </label>
          <label className="block">
            To
            <input
              aria-label="To"
              type="date"
              required
              value={pending?.end_date || end}
              min={start}
              max={today}
              disabled={busy || !!pending}
              onChange={(event) => setEnd(event.target.value)}
            />
          </label>
          <button type="submit" disabled={busy || !campaigns.length}>
            {busy ? "Checking…" : pending ? "Check request" : "Create report"}
          </button>
          <p role="status">
            {message ||
              (restored
                ? "A previous request needs checking. Check it before creating another report."
                : "")}
          </p>
          <p>
            PDF includes charts and creative previews; PDF artwork uses a file tile. CSV contains
            the results, chart data and artwork references. Measured driving is separate from
            estimated views. Results need at least three cars in each campaign, day or area; a
            withheld result is unavailable, not zero.
          </p>
        </form>
      </Panel>
      <section aria-label="Reports">
        <h2>Reports</h2>
        {reports.isPending ? (
          <p role="status">Loading reports…</p>
        ) : reports.isError ? (
          <div role="alert">
            <p>Reports could not be loaded.</p>
            <button onClick={() => void reports.refetch()}>Try again</button>
          </div>
        ) : (
          <>
            {!reports.data.items.length ? (
              <p>No reports yet.</p>
            ) : (
              reports.data.items.map((report) => (
                <Panel key={report.id}>
                  <h3>{report.campaigns.map((campaign) => campaign.name).join(", ")}</h3>
                  <p>
                    {report.start_date} to {report.end_date} · WAT ·{" "}
                    {report.kind === "issued" ? "Issued" : report.kind} · Version {report.version}
                  </p>
                  {report.status === "ready" ? (
                    <div className="flex gap-4">
                      {["csv", "pdf"].map((format) => (
                        <a
                          key={format}
                          href={`/api/advertiser/reports/${report.id}/download?format=${format}&legacy=${report.legacy}`}
                        >
                          Download {format.toUpperCase()}
                        </a>
                      ))}
                    </div>
                  ) : (
                    <p role="status">
                      {report.status === "queued" ? "Preparing report…" : report.error}
                    </p>
                  )}
                </Panel>
              ))
            )}
            <div className="flex gap-4">
              <button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 25))}>
                Previous
              </button>
              <button
                disabled={offset + 25 >= reports.data.total}
                onClick={() => setOffset(offset + 25)}
              >
                Next
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
