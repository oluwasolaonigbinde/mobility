import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

const complete = vi.hoisted(() => vi.fn());
vi.mock("../reset-password/actions", () => ({
  completeAdvertiserInviteAction: complete,
  completePasswordResetAction: vi.fn(),
}));
import Page from "./page";

beforeEach(() => {
  complete.mockReset();
  window.history.replaceState(null, "", "/advertiser-invite#token=invite-secret");
});

it("uses invite wording, removes the fragment and returns to manual sign-in", async () => {
  complete.mockResolvedValue({ done: "Your login is ready. Sign in with your new password." });
  render(<Page />);
  expect(await screen.findByRole("button", { name: "Set password" })).toBeVisible();
  expect(window.location.hash).toBe("");
  expect(screen.getByRole("heading", { name: "Accept your invite" })).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "Set password" }));
  expect(
    await screen.findByText("Your login is ready. Sign in with your new password."),
  ).toBeVisible();
  expect(screen.getByRole("link", { name: "Continue to sign in" })).toHaveAttribute(
    "href",
    "/login",
  );
});

it("gives an expired or used invite a plain staff recovery message", async () => {
  complete.mockResolvedValue({
    error: "This invite link is invalid, expired, or already used. Ask Terrax for a new invite.",
  });
  render(<Page />);
  await userEvent.click(await screen.findByRole("button", { name: "Set password" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Ask Terrax for a new invite");
  expect(screen.queryByRole("link", { name: "Send a new link" })).toBeNull();
});
