import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { DriverApplicationState } from "./actions";

const actionState = vi.hoisted(() => ({ state: {} as DriverApplicationState, pending: false }));
vi.mock("react", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react")>()),
  useActionState: () => [actionState.state, () => undefined, actionState.pending],
}));
vi.mock("./actions", () => ({
  submitDriverApplicationAction: vi.fn(),
  requestDriverOnboardingAccessAction: vi.fn(),
}));

import { DriverApplicationForms } from "./application-forms";

it("shows the typed contact details again after a failed send", () => {
  actionState.state = {
    fieldErrors: { email: "Enter a valid email address" },
    values: {
      full_name: "Ada Driver",
      email: "ada@",
      phone: "+2348000000000",
      service_city: "Abuja",
    },
  };
  render(<DriverApplicationForms />);
  expect(screen.getByLabelText("Full name")).toHaveValue("Ada Driver");
  expect(screen.getByLabelText("Email")).toHaveValue("ada@");
  expect(screen.getByLabelText("Phone (optional)")).toHaveValue("+2348000000000");
  expect(screen.getByLabelText("City you drive in")).toHaveValue("Abuja");
  expect(screen.getByText("Enter a valid email address")).toBeInTheDocument();
});

it("hides stale field errors while sending and reveals the newest result when done", () => {
  actionState.state = { fieldErrors: { email: "Enter a valid email address" } };
  const { rerender } = render(<DriverApplicationForms />);
  expect(screen.getByText("Enter a valid email address")).toBeVisible();
  actionState.pending = true;
  rerender(<DriverApplicationForms />);
  expect(screen.queryByText("Enter a valid email address")).toBeNull();
  expect(
    screen
      .getAllByRole("button", { name: "Sending…" })
      .every((button) => button.hasAttribute("disabled")),
  ).toBe(true);
  actionState.state = { fieldErrors: { email: "Check your email" } };
  actionState.pending = false;
  rerender(<DriverApplicationForms />);
  expect(screen.getByText("Check your email")).toBeVisible();
});
