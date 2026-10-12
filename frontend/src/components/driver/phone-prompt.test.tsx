import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";
import { PhonePrompt } from "./phone-prompt";
beforeEach(() => localStorage.clear());
it("shows once per driver and keeps phone help reachable", () => {
  const view = render(<PhonePrompt driverId="one" />);
  expect(screen.getByRole("link", { name: "Check this phone" })).toHaveAttribute(
    "href",
    "/driver/capabilities",
  );
  fireEvent.click(screen.getByRole("button", { name: "Got it" }));
  view.unmount();
  render(<PhonePrompt driverId="one" />);
  expect(screen.queryByLabelText("Phone setup")).not.toBeInTheDocument();
});
