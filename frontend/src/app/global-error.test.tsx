import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import GlobalError from "./global-error";

const { captureException } = vi.hoisted(() => ({ captureException: vi.fn() }));

vi.mock("@sentry/nextjs", () => ({ captureException }));

describe("global error boundary", () => {
  afterEach(() => captureException.mockReset());

  it("captures the error, hides its digest and uses the supported retry action", async () => {
    const retry = vi.fn();
    const error = Object.assign(new Error("render failed"), { digest: "digest-456" });

    render(<GlobalError error={error} retry={retry} />);

    await waitFor(() => expect(captureException).toHaveBeenCalledWith(error));
    expect(screen.queryByText(/digest-456/)).not.toBeInTheDocument();
    expect(screen.getByText(/contact Cardvert support/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
