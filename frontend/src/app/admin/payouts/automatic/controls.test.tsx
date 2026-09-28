import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  switchAction: vi.fn(),
  release: vi.fn(),
  resolve: vi.fn(),
}));
vi.mock("./actions", () => ({
  switchAutomaticPayoutsAction: mocks.switchAction,
  releaseUnsentAction: mocks.release,
  resolveAlertAction: mocks.resolve,
}));

import { PauseSwitchForm, ReleaseUnsentForm, ResolveAlertForm } from "./controls";

describe("automatic payout controls", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends the pause intent with the reason and shows the result", async () => {
    mocks.switchAction.mockResolvedValue({ done: "Automatic payouts are paused." });
    render(<PauseSwitchForm paused={false} />);
    fireEvent.change(screen.getByLabelText("Why are you pausing them?"), {
      target: { value: "Bank check" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Pause automatic payouts" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Automatic payouts are paused.");
    const sent = mocks.switchAction.mock.calls[0]![1] as FormData;
    expect(sent.get("intent")).toBe("pause");
    expect(sent.get("reason")).toBe("Bank check");
  });

  it("shows the server's refusal when resuming fails", async () => {
    mocks.switchAction.mockResolvedValue({ error: "Automatic payouts are not paused" });
    render(<PauseSwitchForm paused />);
    fireEvent.change(screen.getByLabelText("Why are you resuming automatic payouts?"), {
      target: { value: "Done" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Resume automatic payouts" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Automatic payouts are not paused");
    expect((mocks.switchAction.mock.calls[0]![1] as FormData).get("intent")).toBe("resume");
  });

  it("moves unsent payments only after confirmation", async () => {
    mocks.release.mockResolvedValue({ done: "1 unsent payment moved to manual review." });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<ReleaseUnsentForm count={1} />);
    fireEvent.change(screen.getByLabelText("Why move the 1 unsent payment to manual review?"), {
      target: { value: "Month end" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Move unsent payments to manual review" }));
    expect(await screen.findByRole("status")).toHaveTextContent("1 unsent payment moved");
    confirm.mockRestore();
  });

  it("records how an alert was followed up", async () => {
    mocks.resolve.mockResolvedValue({ done: "Marked as followed up." });
    render(<ResolveAlertForm alertId="alert-1" />);
    fireEvent.change(screen.getByLabelText("What did you do about it?"), {
      target: { value: "Called the driver" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Mark as followed up" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Marked as followed up.");
    const sent = mocks.resolve.mock.calls[0]![1] as FormData;
    expect(sent.get("alert_id")).toBe("alert-1");
    expect(sent.get("note")).toBe("Called the driver");
  });
});
