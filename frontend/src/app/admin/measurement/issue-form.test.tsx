import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const issueMeasurement = vi.hoisted(() => vi.fn());
vi.mock("./actions", () => ({ issueMeasurement }));
vi.mock("../search-select", () => ({
  SearchSelect: ({ name, label }: { name: string; label: string }) => (
    <input
      type="hidden"
      name={name}
      value="44444444-4444-4444-8444-444444444444"
      aria-label={label}
    />
  ),
}));

import { IssueMeasurementForm } from "./issue-form";

async function fillPeriod(user: ReturnType<typeof userEvent.setup>) {
  await user.type(
    screen.getByRole("textbox", { name: "Period start (UTC)" }),
    "2026-09-01T00:00:00Z",
  );
  await user.type(
    screen.getByRole("textbox", { name: "Period end (UTC, excluded)" }),
    "2026-10-01T00:00:00Z",
  );
}

describe("IssueMeasurementForm", () => {
  beforeEach(() => issueMeasurement.mockReset());

  it("submits the selected campaign, UTC period and synthetic flag and reports the result", async () => {
    issueMeasurement.mockResolvedValue({ done: "Measurement run recorded. Open it to review." });
    const user = userEvent.setup();
    render(<IssueMeasurementForm />);
    expect(screen.getByText(/does not\s+issue downloads, confirm physical activity/)).toBeTruthy();
    await fillPeriod(user);
    await user.click(screen.getByRole("checkbox", { name: "Synthetic test data only" }));
    await user.click(screen.getByRole("button", { name: "Prepare measurement run" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Measurement run recorded");
    expect(issueMeasurement).toHaveBeenCalledTimes(1);
    const sent = Object.fromEntries((issueMeasurement.mock.calls[0]![1] as FormData).entries());
    expect(sent).toMatchObject({
      campaign_id: "44444444-4444-4444-8444-444444444444",
      period_start_at: "2026-09-01T00:00:00Z",
      period_end_at: "2026-10-01T00:00:00Z",
      test_only: "on",
    });
    expect(sent.client_request_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a refusal and retries with the same request identity", async () => {
    issueMeasurement.mockResolvedValue({
      error: "Select a campaign and enter complete UTC period timestamps.",
    });
    const user = userEvent.setup();
    render(<IssueMeasurementForm />);
    await fillPeriod(user);
    await user.click(screen.getByRole("button", { name: "Prepare measurement run" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("complete UTC period timestamps");

    await fillPeriod(user);
    await user.click(screen.getByRole("button", { name: "Prepare measurement run" }));
    await vi.waitFor(() => expect(issueMeasurement).toHaveBeenCalledTimes(2));
    const [first, second] = issueMeasurement.mock.calls.map((call) =>
      (call[1] as FormData).get("client_request_id"),
    );
    expect(second).toBe(first);
    expect((issueMeasurement.mock.calls[1]![1] as FormData).get("test_only")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });
});
