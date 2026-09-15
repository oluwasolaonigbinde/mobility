import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

const initiate = vi.hoisted(() => vi.fn());
vi.mock("./actions", () => ({ initiateDriverAccountSetupAction: initiate }));

import { AccountSetupAction } from "./account-setup-action";

beforeEach(() => {
  initiate.mockReset();
  initiate.mockResolvedValue({});
});

it("names the applicant and explains link supersession before starting setup", async () => {
  const user = userEvent.setup();
  render(<AccountSetupAction applicationId="application-1" applicantName="Ada Applicant" />);

  await user.click(screen.getByRole("button", { name: "Start account setup" }));

  expect(initiate).not.toHaveBeenCalled();
  const dialog = screen.getByRole("alertdialog", {
    name: "Start account setup for Ada Applicant?",
  });
  expect(dialog).toHaveTextContent("replaces any earlier unused setup link");
  expect(screen.getByRole("button", { name: "Keep current setup state" })).toHaveFocus();
});
