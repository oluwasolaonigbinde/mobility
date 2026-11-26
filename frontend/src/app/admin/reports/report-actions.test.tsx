import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { RerunReportForm } from "./report-actions";

const refresh = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  useRouter: () => ({ refresh }),
}));
const fetchMock = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("keeps the same staff rerun request after an uncertain result", async () => {
  fetchMock
    .mockRejectedValueOnce(new Error("Connection lost"))
    .mockResolvedValueOnce(Response.json({ id: "report" }, { status: 202 }));
  render(<RerunReportForm campaignId="campaign" staffId="staff" />);
  fireEvent.click(screen.getByRole("button", { name: "Re-run" }));
  fireEvent.click(await screen.findByRole("button", { name: "Check request" }));
  await screen.findByText(/Report requested/);
  expect(fetchMock.mock.calls[1]?.[1]?.body).toEqual(fetchMock.mock.calls[0]?.[1]?.body);
  expect(refresh).toHaveBeenCalledOnce();
  expect(sessionStorage.getItem("campaign-report-rerun:staff:campaign")).toBeNull();
});

it("does not restore another staff member's request", () => {
  sessionStorage.setItem("campaign-report-rerun:other:campaign", "other-request");
  render(<RerunReportForm campaignId="campaign" staffId="staff" />);
  expect(screen.getByRole("button", { name: "Re-run" })).toBeEnabled();
  expect(screen.queryByRole("button", { name: "Check request" })).not.toBeInTheDocument();
});

it("clears the request and shows the public refusal on a readable 4xx", async () => {
  fetchMock.mockResolvedValueOnce(
    Response.json(
      { error: { code: "REPORT_NOT_DUE", message: "A new report can't be prepared yet." } },
      { status: 409 },
    ),
  );
  render(<RerunReportForm campaignId="campaign" staffId="staff" />);
  fireEvent.click(screen.getByRole("button", { name: "Re-run" }));
  await screen.findByText("A new report can't be prepared yet.");
  expect(screen.getByRole("button", { name: "Re-run" })).toBeEnabled();
  expect(sessionStorage.getItem("campaign-report-rerun:staff:campaign")).toBeNull();
});

it("keeps the request after an unreadable 4xx and retries with the same body", async () => {
  fetchMock
    .mockResolvedValueOnce(new Response("not json", { status: 409 }))
    .mockResolvedValueOnce(Response.json({ id: "report" }, { status: 202 }));
  render(<RerunReportForm campaignId="campaign" staffId="staff" />);
  fireEvent.click(screen.getByRole("button", { name: "Re-run" }));
  await screen.findByText(/We couldn't confirm this request/);
  fireEvent.click(screen.getByRole("button", { name: "Check request" }));
  await screen.findByText(/Report requested/);
  expect(fetchMock.mock.calls[1]?.[1]?.body).toEqual(fetchMock.mock.calls[0]?.[1]?.body);
});

it("keeps the request after a 5xx", async () => {
  fetchMock.mockResolvedValueOnce(
    Response.json(
      { error: { code: "X", message: "That didn't work. Try again." } },
      { status: 502 },
    ),
  );
  render(<RerunReportForm campaignId="campaign" staffId="staff" />);
  fireEvent.click(screen.getByRole("button", { name: "Re-run" }));
  await screen.findByText(/We couldn't confirm this request/);
  expect(screen.getByRole("button", { name: "Check request" })).toBeEnabled();
  expect(sessionStorage.getItem("campaign-report-rerun:staff:campaign")).not.toBeNull();
});
