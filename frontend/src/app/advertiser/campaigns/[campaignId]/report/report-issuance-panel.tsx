"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import { Panel } from "@/components/ui/panel";

type ArtifactFormat = "csv" | "pdf";
type Artifact = {
  format: ArtifactFormat;
  filename: string;
  content_type?: string;
  size_bytes?: number;
  checksum_sha256: string;
};
type Issuance = {
  id: string;
  measurement_run_id: string;
  version: number;
  status: "queued" | "processing" | "ready" | "failed";
  error_code?: string | null;
  artifacts: Artifact[];
};
type PersistedRequest = {
  clientRequestId: string;
  issuanceId: string | null;
  reissueOfId: string | null;
};

class IssuanceRequestError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

const storageListeners = new Set<() => void>();

function subscribeToStorage(listener: () => void) {
  storageListeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    storageListeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function persistRequest(key: string, value: PersistedRequest) {
  localStorage.setItem(key, JSON.stringify(value));
  storageListeners.forEach((listener) => listener());
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  const body = (await response.json()) as
    | T
    | {
        error?: { code?: string; message?: string };
      };
  if (!response.ok) {
    const envelope = body as { error?: { code?: string; message?: string } };
    throw new IssuanceRequestError(
      response.status,
      envelope.error?.code ?? "REPORT_ISSUANCE_UNAVAILABLE",
      envelope.error?.message ?? "The report issuance request could not be completed",
    );
  }
  return body as T;
}

export function ReportIssuancePanel({ measurementRunId }: { measurementRunId: string }) {
  const storageKey = `report-issuance:${measurementRunId}`;
  const storedRequest = useSyncExternalStore(
    subscribeToStorage,
    () => localStorage.getItem(storageKey),
    () => null,
  );
  const request = useMemo(() => {
    if (!storedRequest) return null;
    try {
      const restored = JSON.parse(storedRequest) as PersistedRequest;
      return restored.clientRequestId ? restored : null;
    } catch {
      return null;
    }
  }, [storedRequest]);
  const replayedRequest = useRef<string | null>(null);

  const create = useMutation({
    mutationFn: (pending: PersistedRequest) =>
      requestJson<Issuance>(
        `/api/advertiser/measurement-runs/${measurementRunId}/report-issuances`,
        {
          method: "POST",
          body: JSON.stringify({
            client_request_id: pending.clientRequestId,
            reissue_of_id: pending.reissueOfId,
          }),
        },
      ),
    onSuccess: (issuance, pending) => {
      const settled = { ...pending, issuanceId: issuance.id };
      persistRequest(storageKey, settled);
    },
  });

  useEffect(() => {
    if (
      request &&
      !request.issuanceId &&
      replayedRequest.current !== request.clientRequestId &&
      !create.isPending
    ) {
      replayedRequest.current = request.clientRequestId;
      create.mutate(request);
    }
  }, [create, request]);

  const status = useQuery({
    queryKey: ["report-issuance", measurementRunId, request?.issuanceId],
    queryFn: () => requestJson<Issuance>(`/api/advertiser/report-issuances/${request?.issuanceId}`),
    enabled: Boolean(request?.issuanceId),
    refetchInterval: (query) => {
      const current = query.state.data;
      return current?.status === "queued" || current?.status === "processing" ? 3_000 : false;
    },
    refetchIntervalInBackground: false,
    retry: (failureCount, error) =>
      !(error instanceof IssuanceRequestError && [401, 403, 404, 409].includes(error.status)) &&
      failureCount < 1,
  });

  const readyArtifacts = useMemo(() => {
    if (status.data?.status !== "ready") return null;
    const byFormat = new Map(status.data.artifacts.map((artifact) => [artifact.format, artifact]));
    const csv = byFormat.get("csv");
    const pdf = byFormat.get("pdf");
    return csv && pdf && byFormat.size === 2 ? { csv, pdf } : null;
  }, [status.data]);
  const failedIssuanceId = status.data?.status === "failed" ? status.data.id : null;

  function submit(reissueOfId: string | null) {
    const pending: PersistedRequest = {
      clientRequestId: crypto.randomUUID(),
      issuanceId: null,
      reissueOfId,
    };
    replayedRequest.current = pending.clientRequestId;
    persistRequest(storageKey, pending);
    create.mutate(pending);
  }

  function retryPendingRequest() {
    if (!request || request.issuanceId) return;
    replayedRequest.current = request.clientRequestId;
    create.mutate(request);
  }

  const error = create.error ?? status.error;

  return (
    <Panel className="mt-6 p-6" aria-label="Downloadable report artifacts">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-lg font-semibold">CSV and PDF report</h2>
          <p className="text-muted mt-1 max-w-2xl text-sm">
            Create an immutable, privacy-cleared copy of this frozen analysis. Both formats use the
            same metrics, disclosure rules and conditional-measure decision.
          </p>
        </div>
        {!request && !create.isPending ? (
          <button
            type="button"
            className="bg-amber text-bg rounded-md px-4 py-2 text-sm font-semibold disabled:opacity-50"
            onClick={() => submit(null)}
          >
            Create CSV and PDF
          </button>
        ) : null}
        {request && !request.issuanceId && create.isError ? (
          <button
            type="button"
            className="bg-amber text-bg rounded-md px-4 py-2 text-sm font-semibold"
            onClick={retryPendingRequest}
          >
            Retry the same request
          </button>
        ) : null}
      </div>

      {create.isPending ||
      status.data?.status === "queued" ||
      status.data?.status === "processing" ? (
        <p className="text-muted mt-4 text-sm" role="status">
          Your report is being prepared. This page will update when both files are ready.
        </p>
      ) : null}

      {readyArtifacts && status.data ? (
        <div className="mt-5">
          <p className="text-green text-sm font-semibold">Version {status.data.version} is ready</p>
          <div className="mt-3 flex flex-wrap gap-3">
            {(["csv", "pdf"] as const).map((format) => {
              const artifact = readyArtifacts[format];
              return (
                <a
                  key={format}
                  href={`/api/advertiser/report-issuances/${status.data.id}/artifacts/${format}/download`}
                  className="border-edge hover:border-muted rounded-md border px-4 py-2 text-sm font-semibold uppercase"
                >
                  Download {format}
                  <span className="text-faint ml-2 font-mono text-[10px] normal-case">
                    {artifact.checksum_sha256.slice(0, 12)}…
                  </span>
                </a>
              );
            })}
          </div>
          <button
            type="button"
            className="text-muted hover:text-fg mt-4 text-sm underline underline-offset-4"
            disabled={create.isPending}
            onClick={() => submit(status.data.id)}
          >
            Create a new version
          </button>
        </div>
      ) : null}

      {status.data?.status === "ready" && !readyArtifacts ? (
        <p className="text-coral mt-4 text-sm" role="alert">
          The complete artifact pair could not be verified. No download is available.
        </p>
      ) : null}

      {status.data?.status === "failed" || error ? (
        <div className="mt-4">
          <p className="text-coral text-sm" role="alert">
            This report is unavailable. Create a new version or contact support with the report
            status code.
          </p>
          {failedIssuanceId ? (
            <button
              type="button"
              className="text-muted hover:text-fg mt-3 text-sm underline underline-offset-4"
              disabled={create.isPending}
              onClick={() => submit(failedIssuanceId)}
            >
              Create a new version
            </button>
          ) : null}
        </div>
      ) : null}
    </Panel>
  );
}
