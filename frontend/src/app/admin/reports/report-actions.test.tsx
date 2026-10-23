import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { RerunReportForm } from "./report-actions";

const refresh = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
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
