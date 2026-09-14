import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DriverAccountSetupForm } from "./setup-form";

const mocks = vi.hoisted(() => ({
  replaceState: vi.fn(),
}));

describe("DriverAccountSetupForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window.history, "replaceState").mockImplementation(mocks.replaceState);
  });

  it("removes the bearer token from browser history and never renders it as copy", async () => {
    render(<DriverAccountSetupForm token="private-one-use-token" />);

    await waitFor(() =>
      expect(mocks.replaceState).toHaveBeenCalledWith(null, "", "/driver-account-setup"),
    );
    expect(screen.queryByText("private-one-use-token")).not.toBeInTheDocument();
    expect(screen.getByLabelText("New password")).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getByRole("button", { name: "Set password" })).toBeInTheDocument();
  });
});
