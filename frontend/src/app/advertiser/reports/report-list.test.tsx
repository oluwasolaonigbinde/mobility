import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Reports } from "./report-list";

const fetchMock = vi.fn();
const campaigns = [{ id: "campaign", name: "Lagos launch" }];
const empty = { items: [], total: 0, offset: 0, limit: 25 };
let client: QueryClient;

function show() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Reports campaigns={campaigns} today="2026-10-21" sessionScope="owner:company" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockResolvedValue(new Response(JSON.stringify(empty)));
});
afterEach(() => {
  cleanup();
  client?.clear();
  vi.unstubAllGlobals();
});

it("shows the empty state and clearly explains charts, estimates and withheld results", async () => {
  fetchMock.mockImplementation(async () => Response.json(empty));
  show();
  expect(await screen.findByText("No reports yet.")).toBeInTheDocument();
  expect(screen.getByText(/PDF includes charts and creative previews/)).toBeInTheDocument();
  expect(screen.getByText(/withheld result is unavailable, not zero/)).toBeInTheDocument();
  expect(screen.queryByText(/ROI|CTR|budget figures|money figures/)).not.toBeInTheDocument();
});

it("sends the selected Nigeria dates and one campaign", async () => {
  const sent: Record<string, unknown>[] = [];
  fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      sent.push(JSON.parse(String(init.body)));
      return Response.json({ id: "report" }, { status: 202 });
    }
    return Response.json(empty);
  });
  show();
  await screen.findByText("No reports yet.");
  fireEvent.change(screen.getByLabelText("Campaign"), { target: { value: "campaign" } });
  fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-10-19" } });
  fireEvent.click(screen.getByRole("button", { name: "Create report" }));
  await screen.findByText(/Report requested/);
  expect(sent).toHaveLength(1);
  expect(sent[0]).toMatchObject({
    start_date: "2026-10-19",
    end_date: "2026-10-21",
    campaign_id: "campaign",
  });
  expect(sent[0]?.client_request_id).toMatch(/^[\da-f-]{36}$/);
});

it("checks an uncertain response with the identical request instead of making a second report", async () => {
  const sent: unknown[] = [];
  fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      sent.push(JSON.parse(String(init.body)));
      if (sent.length === 1) throw new Error("Connection lost; check the request");
      return Response.json({ id: "report" }, { status: 202 });
    }
    return Response.json(empty);
  });
  show();
  await screen.findByText("No reports yet.");
  fireEvent.click(screen.getByRole("button", { name: "Create report" }));
  await screen.findByRole("button", { name: "Check request" });
  expect(screen.getByLabelText("From")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Check request" }));
  await screen.findByText(/Report requested/);
  expect(sent).toHaveLength(2);
  expect(sent[1]).toEqual(sent[0]);
});

it("offers both immutable downloads when ready and retains the old-issued identity", async () => {
  fetchMock.mockImplementation(async () =>
    Response.json({
      ...empty,
      total: 1,
      items: [
        {
          id: "issued",
          kind: "issued",
          status: "ready",
          start_date: "2026-10-01",
          end_date: "2026-10-07",
          timezone: "Africa/Lagos",
          campaigns,
          version: 1,
          legacy: true,
          created_at: "2026-10-08T00:00:00Z",
          ready_at: "2026-10-08T00:00:00Z",
          error: null,
        },
      ],
    }),
  );
  show();
  expect(await screen.findByRole("link", { name: "Download CSV" })).toHaveAttribute(
    "href",
    "/api/advertiser/reports/issued/download?format=csv&legacy=true",
  );
  expect(screen.getByRole("link", { name: "Download PDF" })).toHaveAttribute(
    "href",
    "/api/advertiser/reports/issued/download?format=pdf&legacy=true",
  );
});

it("has a retry state when the report list is unavailable", async () => {
  fetchMock.mockImplementation(async () => new Response("Unavailable", { status: 503 }));
  show();
  await screen.findByText("Reports could not be loaded.");
  fetchMock.mockImplementation(async () => Response.json(empty));
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await waitFor(() => expect(screen.getByText("No reports yet.")).toBeInTheDocument());
});

it("restores only this login and company's uncertain request after a reload", async () => {
  const pending = {
    client_request_id: "8a9c3e00-6c6e-4000-9000-8b5793500001",
    start_date: "2026-10-12",
    end_date: "2026-10-18",
    campaign_id: "campaign",
  };
  sessionStorage.setItem("campaign-report-request:owner:company:all", JSON.stringify(pending));
  sessionStorage.setItem(
    "campaign-report-request:other:company:all",
    JSON.stringify({
      ...pending,
      client_request_id: "another-user-request",
    }),
  );
  fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
    if (init?.method === "POST") return Response.json({ id: "report" }, { status: 202 });
    return Response.json(empty);
  });
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Check request" }));
  await screen.findByText(/Report requested/);
  const post = fetchMock.mock.calls.find((call) => call[1]?.method === "POST");
  expect(JSON.parse(String(post?.[1]?.body))).toEqual(pending);
  expect(sessionStorage.getItem("campaign-report-request:owner:company:all")).toBeNull();
  expect(sessionStorage.getItem("campaign-report-request:other:company:all")).toContain(
    "another-user-request",
  );
});
