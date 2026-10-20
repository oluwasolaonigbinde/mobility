import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
const rerun = vi.hoisted(() => vi.fn());
vi.mock("./actions", () => ({ rerunReportAction: rerun }));
vi.mock("./report-form", () => ({ ReportForm: () => <p>Saved report</p> }));
import { RerunReportForm } from "./issue-form";
beforeEach(() => {
  vi.resetAllMocks();
});
it("uses the current campaign without exposing timestamps or a second campaign picker", async () => {
  rerun.mockResolvedValue({
    report: { id: "report", measurement_run_id: "run", status: "queued" },
  });
  const user = userEvent.setup();
  const { container } = render(<RerunReportForm campaignId="campaign" />);
  expect(container.querySelector("input")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Create results report" }));
  expect(rerun).toHaveBeenCalledWith("campaign", {});
  expect(await screen.findByRole("status")).toHaveTextContent("Report requested.");
  expect(screen.getByText("Saved report")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Create another results report" })).toBeInTheDocument();
});
it("offers inspection after an unknown result without automatically retrying", async () => {
  rerun.mockResolvedValue({ unknownOutcome: true });
  const user = userEvent.setup();
  render(<RerunReportForm campaignId="campaign" />);
  await user.click(screen.getByRole("button", { name: "Create results report" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "couldn’t confirm whether the report was requested",
  );
  expect(screen.getByRole("link", { name: "Check the campaign’s results" })).toHaveAttribute(
    "href",
    "/admin/campaigns/campaign#results",
  );
  expect(rerun).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("status")).toBeNull();
  expect(screen.queryByRole("button", { name: /^Retry/ })).toBeNull();
});
it("suppresses repeated clicks while the report request is pending", async () => {
  let finish!: (state: { error: string }) => void;
  rerun.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const { container } = render(<RerunReportForm campaignId="campaign" />);
  fireEvent.submit(container.querySelector("form")!);
  fireEvent.submit(container.querySelector("form")!);
  expect(rerun).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "Requesting report…" })).toBeDisabled();
  await act(async () => finish({ error: "No completed reporting period" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("No completed reporting period");
});
