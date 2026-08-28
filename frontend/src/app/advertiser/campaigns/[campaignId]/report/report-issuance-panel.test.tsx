import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ReportIssuancePanel } from "./report-issuance-panel";

const RUN_ID = "00000000-0000-4000-8000-000000000041";
const ISSUANCE_ID = "00000000-0000-4000-8000-000000000042";

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
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: ISSUANCE_ID,
            measurement_run_id: RUN_ID,
            version: 1,
            status: "queued",
            artifacts: [],
          }),
          { status: 202 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
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
          { status: 200 },
        ),
      );

    renderPanel();
    await userEvent.click(screen.getByRole("button", { name: "Create CSV and PDF" }));

    const stored = JSON.parse(localStorage.getItem(`report-issuance:${RUN_ID}`) ?? "null");
    expect(stored.clientRequestId).toBe("00000000-0000-4000-8000-000000000043");
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
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
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
      async () =>
        new Response(
          JSON.stringify({
            id: ISSUANCE_ID,
            measurement_run_id: RUN_ID,
            version: 1,
            status: "queued",
            artifacts: [],
          }),
          { status: 202 },
        ),
    );

    renderPanel();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body)).client_request_id).toBe(
      "00000000-0000-4000-8000-000000000044",
    );
  });

  it("retries a lost response without replacing the accepted request identity", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock
      .mockRejectedValueOnce(new TypeError("response lost"))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: ISSUANCE_ID,
            measurement_run_id: RUN_ID,
            version: 1,
            status: "queued",
            artifacts: [],
          }),
          { status: 202 },
        ),
      )
      .mockImplementation(
        async () =>
          new Response(
            JSON.stringify({
              id: ISSUANCE_ID,
              measurement_run_id: RUN_ID,
              version: 1,
              status: "queued",
              artifacts: [],
            }),
          ),
      );

    renderPanel();
    await userEvent.click(screen.getByRole("button", { name: "Create CSV and PDF" }));
    const retry = await screen.findByRole("button", { name: "Retry the same request" });
    await userEvent.click(retry);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const firstBody = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
    const retryBody = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
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
    fetchMock.mockResolvedValueOnce(
      new Response(
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
      ),
    );
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          id: "00000000-0000-4000-8000-000000000045",
          measurement_run_id: RUN_ID,
          version: 2,
          status: "queued",
          artifacts: [],
        }),
        { status: 202 },
      ),
    );

    renderPanel();
    expect(await screen.findByText("Version 1 is ready")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Create a new version" }));

    await act(async () => undefined);
    const createBody = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
    expect(createBody.reissue_of_id).toBe(ISSUANCE_ID);
    expect(createBody.client_request_id).toBe("00000000-0000-4000-8000-000000000043");
  });
});
