import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DriverAccountSetupForm } from "./setup-form";

describe("DriverAccountSetupForm", () => {
  // REQ-316 F8: the token now arrives in the fragment, which the shared capture removes from
  // history before monitoring starts (invite-link.test.ts), so the form no longer rewrites history.
  it("never renders the bearer token as copy", () => {
    render(<DriverAccountSetupForm token="private-one-use-token" />);

    expect(screen.queryByText("private-one-use-token")).not.toBeInTheDocument();
    expect(screen.getByLabelText("New password")).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getByRole("button", { name: "Set password" })).toBeInTheDocument();
  });
});
