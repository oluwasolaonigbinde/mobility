import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

const unlock = vi.hoisted(() => vi.fn());
vi.mock("./actions", () => ({ unlockFeedbackAction: unlock }));

import { UnlockForm } from "./unlock-form";

it("submits the password and shows the refusal from the server", async () => {
  unlock.mockResolvedValue({ error: "That password did not match." });
  const user = userEvent.setup({ delay: null });
  render(<UnlockForm />);
  const password = screen.getByLabelText("Password");
  expect(password).toHaveAttribute("type", "password");
  await user.type(password, "guess");
  await user.click(screen.getByRole("button", { name: "View feedback" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("That password did not match.");
  const sent = unlock.mock.calls[0]![1] as FormData;
  expect(sent.get("password")).toBe("guess");
});
