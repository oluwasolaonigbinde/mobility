import { fireEvent, render, screen } from "@testing-library/react";
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

  await user.click(screen.getByRole("button", { name: "Keep current setup state" }));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Start account setup" }));
  fireEvent.keyDown(screen.getByRole("alertdialog"), { key: "Escape" });
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
});

it("submits the bound application once and surfaces a setup refusal", async () => {
  initiate.mockResolvedValue({ error: "Applicant approval changed elsewhere" });
  const user = userEvent.setup();
  render(<AccountSetupAction applicationId="application-1" applicantName="Ada Applicant" />);

  await user.click(screen.getByRole("button", { name: "Start account setup" }));
  await user.click(screen.getByRole("button", { name: "Issue one-use setup link" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Applicant approval changed elsewhere",
  );
  expect(initiate).toHaveBeenCalledOnce();
  const [previousState, formData] = initiate.mock.calls[0] as [unknown, FormData];
  expect(previousState).toEqual({});
  expect(formData.get("application_id")).toBe("application-1");
  expect(formData.get("client_request_id")).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
  );
});
