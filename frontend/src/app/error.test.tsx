import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import RootError from "./error";

const { captureException } = vi.hoisted(() => ({ captureException: vi.fn() }));

vi.mock("@sentry/nextjs", () => ({
  captureException,
}));

describe("root error boundary", () => {
  afterEach(() => {
    captureException.mockReset();
    vi.restoreAllMocks();
  });

  it("captures unexpected UI errors", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const error = Object.assign(new Error("render failed"), { digest: "digest-123" });

    render(<RootError error={error} reset={vi.fn()} />);

    await waitFor(() => expect(captureException).toHaveBeenCalledWith(error));
  });
});
