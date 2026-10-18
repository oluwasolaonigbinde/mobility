import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { CampaignCancellationPanel } from "./campaign-cancellation-panel";
it("prepares a reason without submitting or claiming cancellation before Phase 2", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <CampaignCancellationPanel campaignId="campaign" campaignName="Wuse lunch rush" />,
  );
  await user.type(
    screen.getByRole("textbox", { name: "Why would you like to cancel?" }),
    "Our opening date changed.",
  );
  expect(screen.getByRole("button", { name: "Ask Terrax to cancel" })).toBeDisabled();
  expect(container.querySelector("form")).toBeNull();
  expect(screen.getByRole("link", { name: "Email Terrax Media" }).getAttribute("href")).toContain(
    "Our%20opening%20date%20changed.",
  );
  expect(container).not.toHaveTextContent(
    /cancel permanently|campaign cancelled|request sent|complaint/i,
  );
});
it("requires a trimmed short reason without enabling unsupported submission", async () => {
  const user = userEvent.setup();
  render(<CampaignCancellationPanel campaignId="campaign" campaignName="Wuse lunch rush" />);
  const reason = screen.getByRole("textbox", { name: "Why would you like to cancel?" });
  expect(reason).toBeRequired();
  expect(reason).toHaveAttribute("maxlength", "2000");
  await user.type(reason, "   ");
  await user.tab();
  expect(screen.getByRole("alert")).toHaveTextContent("Please add a short reason.");
  expect(reason).toHaveAttribute("aria-invalid", "true");
  await user.type(reason, "Dates changed");
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByRole("button", { name: "Ask Terrax to cancel" })).toBeDisabled();
});
