import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ReportIssuancePanel } from "./report-issuance-panel";

const RUN_ID = "00000000-0000-4000-8000-000000000041";
const ISSUANCE_ID = "00000000-0000-4000-8000-000000000042";

function isCurrentRequest(input: RequestInfo | URL, init?: RequestInit) {
  return (
    String(input) === `/api/advertiser/measurement-runs/${RUN_ID}/report-issuances` &&
    (!init?.method || init.method === "GET")
  );
}

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ReportIssuancePanel measurementRunId={RUN_ID} />
    </QueryClientProvider>,
  );
}

describe("ReportIssuancePanel", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(
      "00000000-0000-4000-8000-000000000043",
    );
  });

  it("persists the request identity before sending and exposes only a ready artifact pair", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock.mockImplementation(async (input, init) => {
      if (isCurrentRequest(input, init)) return new Response("null");
      if (init?.method === "POST") {
        return new Response(
          JSON.stringify({
            id: ISSUANCE_ID,
            measurement_run_id: RUN_ID,
            version: 1,
            status: "queued",
            artifacts: [],
          }),
          { status: 202 },
        );
      }
      return new Response(
        JSON.stringify({
          id: ISSUANCE_ID,
          measurement_run_id: RUN_ID,
          version: 1,
          status: "ready",
          artifacts: [
            {
              format: "csv",
              filename: "campaign-performance-v1.csv",
              content_type: "text/csv; charset=utf-8",
              size_bytes: 128,
              checksum_sha256: "a".repeat(64),
            },
            {
              format: "pdf",
              filename: "campaign-performance-v1.pdf",
              content_type: "application/pdf",
              size_bytes: 256,
              checksum_sha256: "b".repeat(64),
            },
          ],
        }),
      );
    });

    renderPanel();
    await userEvent.click(await screen.findByRole("button", { name: "Create CSV and PDF" }));

    const stored = JSON.parse(localStorage.getItem(`report-issuance:${RUN_ID}`) ?? "null");
    expect(stored.clientRequestId).toBe("00000000-0000-4000-8000-000000000043");
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/advertiser/measurement-runs/${RUN_ID}/report-issuances`,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          client_request_id: "00000000-0000-4000-8000-000000000043",
          reissue_of_id: null,
        }),
      }),
    );

    expect(await screen.findByText("Version 1 is ready")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /download csv/i })).toHaveAttribute(
      "href",
      `/api/advertiser/report-issuances/${ISSUANCE_ID}/artifacts/csv/download`,
    );
    expect(screen.getByRole("link", { name: /download pdf/i })).toBeInTheDocument();
    expect(screen.queryByText(/return on investment|\broi\b/i)).not.toBeInTheDocument();
  });

  it("replays a persisted lost-response request with the same client identity", async () => {
    localStorage.setItem(
      `report-issuance:${RUN_ID}`,
      JSON.stringify({
        clientRequestId: "00000000-0000-4000-8000-000000000044",
        issuanceId: null,
        reissueOfId: null,
      }),
    );
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (isCurrentRequest(input, init)) return new Response("null");
      return new Response(
        JSON.stringify({
          id: ISSUANCE_ID,
          measurement_run_id: RUN_ID,
          version: 1,
          status: "queued",
          artifacts: [],
        }),
        { status: 202 },
      );
    });

    renderPanel();
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true),
    );
    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(postCall?.[1]?.body)).client_request_id).toBe(
      "00000000-0000-4000-8000-000000000044",
    );
  });

  it("does not let a delayed current lookup replace an accepted replay", async () => {
    const REISSUE_ID = "00000000-0000-4000-8000-000000000045";
    localStorage.setItem(
      `report-issuance:${RUN_ID}`,
      JSON.stringify({
        clientRequestId: "00000000-0000-4000-8000-000000000044",
        issuanceId: null,
        reissueOfId: ISSUANCE_ID,
      }),
    );
    let resolveCurrent: (response: Response) => void = () => undefined;
    const delayedCurrent = new Promise<Response>((resolve) => {
      resolveCurrent = resolve;
    });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (isCurrentRequest(input, init)) return delayedCurrent;
      if (init?.method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: REISSUE_ID,
              measurement_run_id: RUN_ID,
              version: 2,
              status: "queued",
              artifacts: [],
            }),
            { status: 202 },
          ),
        );
      }
      if (url === `/api/advertiser/report-issuances/${REISSUE_ID}`) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: REISSUE_ID,
              measurement_run_id: RUN_ID,
              version: 2,
              status: "queued",
              artifacts: [],
            }),
          ),
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            error: { code: "REPORT_ISSUANCE_NOT_FOUND", message: "Report issuance was not found" },
          }),
          { status: 404 },
        ),
      );
    });

    renderPanel();
    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem(`report-issuance:${RUN_ID}`) ?? "null");
      expect(stored.issuanceId).toBe(REISSUE_ID);
    });

    await act(async () => {
      resolveCurrent(
        new Response(
          JSON.stringify({
            id: ISSUANCE_ID,
            measurement_run_id: RUN_ID,
            version: 1,
            status: "ready",
          }),
        ),
      );
    });

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([input]) => String(input) === `/api/advertiser/report-issuances/${REISSUE_ID}`,
        ),
      ).toBe(true),
    );
    expect(
      fetchMock.mock.calls.some(
        ([input]) => String(input) === `/api/advertiser/report-issuances/${ISSUANCE_ID}`,
      ),
    ).toBe(false);
    expect(screen.getByRole("status")).toHaveTextContent("Your report is being prepared");
  });

  it("retries a lost response without replacing the accepted request identity", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    let postAttempts = 0;
    fetchMock.mockImplementation(async (input, init) => {
      if (isCurrentRequest(input, init)) return new Response("null");
      if (init?.method === "POST" && postAttempts++ === 0) {
        throw new TypeError("response lost");
      }
      return new Response(
        JSON.stringify({
          id: ISSUANCE_ID,
          measurement_run_id: RUN_ID,
          version: 1,
          status: "queued",
          artifacts: [],
        }),
        { status: 202 },
      );
    });

    renderPanel();
    await userEvent.click(await screen.findByRole("button", { name: "Create CSV and PDF" }));
    const retry = await screen.findByRole("button", { name: "Retry the same request" });
    await userEvent.click(retry);

    await waitFor(() =>
      expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(2),
    );
    const postCalls = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
    const firstBody = JSON.parse(String(postCalls[0]?.[1]?.body));
    const retryBody = JSON.parse(String(postCalls[1]?.[1]?.body));
    expect(retryBody.client_request_id).toBe(firstBody.client_request_id);
    expect(retryBody.reissue_of_id).toBe(firstBody.reissue_of_id);
  });

  it("creates an explicit append-only reissue after a ready version", async () => {
    localStorage.setItem(
      `report-issuance:${RUN_ID}`,
      JSON.stringify({
        clientRequestId: "00000000-0000-4000-8000-000000000044",
        issuanceId: ISSUANCE_ID,
        reissueOfId: null,
      }),
    );
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock.mockImplementation(async (input, init) => {
      if (isCurrentRequest(input, init)) {
        return new Response(
          JSON.stringify({
            id: ISSUANCE_ID,
            measurement_run_id: RUN_ID,
            version: 1,
            status: "ready",
          }),
        );
      }
      if (init?.method === "POST") {
        return new Response(
          JSON.stringify({
            id: "00000000-0000-4000-8000-000000000045",
            measurement_run_id: RUN_ID,
            version: 2,
            status: "queued",
            artifacts: [],
          }),
          { status: 202 },
        );
      }
      return new Response(
        JSON.stringify({
          id: ISSUANCE_ID,
          measurement_run_id: RUN_ID,
          version: 1,
          status: "ready",
          artifacts: [
            { format: "csv", filename: "v1.csv", checksum_sha256: "a".repeat(64) },
            { format: "pdf", filename: "v1.pdf", checksum_sha256: "b".repeat(64) },
          ],
        }),
      );
    });

    renderPanel();
    expect(await screen.findByText("Version 1 is ready")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Create a new version" }));

    await act(async () => undefined);
    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    const createBody = JSON.parse(String(postCall?.[1]?.body));
    expect(createBody.reissue_of_id).toBe(ISSUANCE_ID);
    expect(createBody.client_request_id).toBe("00000000-0000-4000-8000-000000000043");
  });

  it("recovers a hidden latest parent after authority or requester turnover", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (
        url === `/api/advertiser/measurement-runs/${RUN_ID}/report-issuances` &&
        (!init?.method || init.method === "GET")
      ) {
        return new Response(
          JSON.stringify({
            id: ISSUANCE_ID,
            measurement_run_id: RUN_ID,
            version: 1,
            status: "ready",
          }),
        );
      }
      if (url === `/api/advertiser/report-issuances/${ISSUANCE_ID}`) {
        return new Response(
          JSON.stringify({
            error: { code: "REPORT_ISSUANCE_NOT_FOUND", message: "Report issuance was not found" },
          }),
          { status: 404 },
        );
      }
      if (init?.method === "POST") {
        return new Response(
          JSON.stringify({
            id: "00000000-0000-4000-8000-000000000045",
            measurement_run_id: RUN_ID,
            version: 2,
            status: "queued",
            artifacts: [],
          }),
          { status: 202 },
        );
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    renderPanel();
    const reissue = await screen.findByRole("button", { name: "Create a new version" });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await userEvent.click(reissue);

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([, init]) => {
          if (init?.method !== "POST") return false;
          return JSON.parse(String(init.body)).reissue_of_id === ISSUANCE_ID;
        }),
      ).toBe(true),
    );
  });
});
