import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DriverAccountSetupForm } from "./setup-form";

vi.mock("./actions", () => ({
  completeDriverAccountSetupAction: vi.fn(async () => ({ done: "Your password is set." })),
}));

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

it("shows only the confirmation and sign-in link after setup", async () => {
  const { container } = render(<DriverAccountSetupForm token="private-token" />);
  await userEvent.click(screen.getByRole("button", { name: "Set password" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Your password is set.");
  expect(screen.getByRole("link", { name: "Continue to sign in" })).toHaveAttribute(
    "href",
    "/login",
  );
  expect(container.querySelector("form")).toBeNull();
  expect(screen.queryByLabelText("New password")).toBeNull();
  expect(screen.queryByLabelText("Confirm new password")).toBeNull();
});
