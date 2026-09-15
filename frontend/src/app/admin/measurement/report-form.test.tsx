import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReportState } from "./actions";

const manageReport = vi.hoisted(() => vi.fn());
vi.mock("./actions", () => ({ manageReport }));

import { ReportForm } from "./report-form";

type Report = NonNullable<ReportState["report"]>;
const RUN = "11111111-1111-4111-8111-111111111111";
const report = (overrides: Partial<Report> = {}) =>
  ({
    id: "33333333-3333-4333-8333-333333333333",
    measurement_run_id: RUN,
    version: 2,
    status: "ready",
    created_at: "2026-09-10T10:00:00Z",
    error_code: null,
    artifacts: [{ format: "pdf" }, { format: "csv" }],
    ...overrides,
  }) as unknown as Report;

function lastForm() {
  return Object.fromEntries((manageReport.mock.lastCall![1] as FormData).entries());
}

describe("ReportForm", () => {
  beforeEach(() => manageReport.mockReset());
  afterEach(() => vi.useRealTimers());

  it("does not allow preparing files for a snapshot that cannot be reproduced", () => {
    render(<ReportForm runId={RUN} canIssue={false} />);
    expect(screen.getByText(/No report selected/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Prepare report files" })).toBeDisabled();
    expect(screen.queryByRole("textbox", { name: "Reason for report access" })).toBeNull();
  });

  it("prepares files with a stable request identity and shows the queued report", async () => {
    const user = userEvent.setup();
    manageReport.mockResolvedValue({ report: report({ status: "queued", artifacts: [] }) });
    render(<ReportForm runId={RUN} canIssue />);
    await user.click(screen.getByRole("button", { name: "Prepare report files" }));
    expect(await screen.findByRole("button", { name: "Refresh report status" })).toBeEnabled();
    const first = lastForm();
    expect(first).toMatchObject({ run: RUN, issuance: "", command: "issue" });
    expect(first.request).toMatch(/^[0-9a-f-]{36}$/);
    expect(screen.getByText(/Version 2 · queued · Requested/)).toBeVisible();
    expect(screen.queryByRole("button", { name: /Authorize/ })).toBeNull();

    manageReport.mockResolvedValue({ report: report({ status: "queued", artifacts: [] }) });
    await user.click(screen.getByRole("button", { name: "Refresh report status" }));
    await vi.waitFor(() => expect(manageReport).toHaveBeenCalledTimes(2));
    expect(lastForm()).toMatchObject({
      request: first.request,
      issuance: "33333333-3333-4333-8333-333333333333",
      command: "refresh",
    });
  });

  it("surfaces a failed preparation without offering downloads", () => {
    render(
      <ReportForm
        runId={RUN}
        canIssue
        initialReport={report({ status: "failed", error_code: "RENDER_TIMEOUT", artifacts: [] })}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Report preparation failed: RENDER_TIMEOUT. No ready download is confirmed.",
    );
    expect(screen.queryByRole("button", { name: "Prepare report files" })).toBeNull();
  });

  it("authorizes one artifact format with the stated reason and shows the action error", async () => {
    const user = userEvent.setup();
    manageReport.mockResolvedValue({ report: report(), error: "No download was authorized." });
    render(<ReportForm runId={RUN} canIssue initialReport={report()} />);
    await user.type(
      screen.getByRole("textbox", { name: "Reason for report access" }),
      "Advertiser results review",
    );
    await user.click(screen.getByRole("button", { name: "Authorize CSV download" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No download was authorized.");
    expect(lastForm()).toMatchObject({ command: "csv", reason: "Advertiser results review" });
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("removes the temporary download link after one minute", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    manageReport.mockResolvedValue({
      report: report(),
      download: { url: "https://files.example.test/report.pdf", filename: "report.pdf" },
    });
    render(<ReportForm runId={RUN} canIssue initialReport={report()} />);
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "Authorize PDF download" })),
    );
    expect(screen.getByRole("link", { name: "Download report.pdf" })).toHaveAttribute(
      "href",
      "https://files.example.test/report.pdf",
    );
    act(() => vi.advanceTimersByTime(59_999));
    expect(screen.getByRole("link", { name: "Download report.pdf" })).toBeVisible();
    act(() => vi.advanceTimersByTime(1));
    expect(screen.queryByRole("link", { name: "Download report.pdf" })).toBeNull();
  });

  it("removes the download link once it has been used", async () => {
    const user = userEvent.setup();
    manageReport.mockResolvedValue({
      report: report(),
      download: { url: "#report", filename: "report.csv" },
    });
    render(<ReportForm runId={RUN} canIssue initialReport={report()} />);
    await user.click(screen.getByRole("button", { name: "Authorize CSV download" }));
    await user.click(await screen.findByRole("link", { name: "Download report.csv" }));
    expect(screen.queryByRole("link", { name: "Download report.csv" })).toBeNull();
  });
});
