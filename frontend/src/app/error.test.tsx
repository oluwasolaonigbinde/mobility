import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import RootError from "./error";

const { captureException } = vi.hoisted(() => ({ captureException: vi.fn() }));

vi.mock("@/lib/client-monitoring", () => ({
  captureClientError: captureException,
}));

describe("root error boundary", () => {
  afterEach(() => {
    captureException.mockReset();
    vi.restoreAllMocks();
  });

  it("captures unexpected UI errors", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const error = Object.assign(new Error("render failed"), { digest: "digest-123" });

    render(<RootError error={error} retry={vi.fn()} />);

    await waitFor(() => expect(captureException).toHaveBeenCalledWith(error));
    expect(screen.queryByText(/digest-123/)).not.toBeInTheDocument();
    expect(screen.getByText(/contact Terrax Media/i)).toBeInTheDocument();
  });

  it("retries from the recovery action", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const retry = vi.fn();
    render(<RootError error={new Error("render failed")} retry={retry} />);

    await userEvent.click(screen.getByRole("button", { name: "Reload page" }));

    expect(retry).toHaveBeenCalledOnce();
  });
});
