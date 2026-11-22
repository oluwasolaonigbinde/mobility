import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

const initiate = vi.hoisted(() => vi.fn());
vi.mock("./actions", () => ({ initiateDriverAccountSetupAction: initiate }));

import { AccountSetupAction } from "./account-setup-action";

beforeEach(() => {
  initiate.mockReset();
  initiate.mockResolvedValue({});
});

it("uses the shared accessible dialog and returns focus after cancellation", async () => {
  const user = userEvent.setup();
  render(
    <AccountSetupAction
      applicationId="application-1"
      applicantName="Ada Applicant"
      applicantEmail="ada@example.test"
    />,
  );

  const trigger = screen.getByRole("button", { name: "Start account setup" });
  await user.click(trigger);

  expect(initiate).not.toHaveBeenCalled();
  const dialog = screen.getByRole("alertdialog", {
    name: "Email Ada Applicant a link to set their password?",
  });
  expect(dialog.tagName).toBe("DIALOG");
  expect(dialog).toHaveTextContent("A new link replaces any earlier unused setup link.");
  expect(dialog).not.toHaveTextContent(/one-use|queues delivery|Delivery is not confirmed/);
  expect(dialog).toHaveTextContent("replaces any earlier unused setup link");
  const cancel = within(dialog).getByRole("button", { name: "Cancel" });
  const confirm = within(dialog).getByRole("button", { name: "Send link" });
  expect(cancel).toHaveFocus();

  await user.keyboard("{Shift>}{Tab}{/Shift}");
  expect(confirm).toHaveFocus();
  await user.keyboard("{Tab}");
  expect(cancel).toHaveFocus();

  await user.keyboard("{Escape}");
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();

  await user.click(trigger);
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

it("keeps pending confirmation modal and shows a refusal inside it", async () => {
  let resolveAction!: (state: { error: string }) => void;
  initiate.mockImplementation(
    () =>
      new Promise((resolve) => {
        resolveAction = resolve;
      }),
  );
  const user = userEvent.setup();
  render(
    <AccountSetupAction
      applicationId="application-1"
      applicantName="Ada Applicant"
      applicantEmail="ada@example.test"
    />,
  );

  await user.click(screen.getByRole("button", { name: "Start account setup" }));
  await user.click(screen.getByRole("button", { name: "Send link" }));

  const dialog = screen.getByRole("alertdialog");
  expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeDisabled();
  expect(within(dialog).getByRole("button", { name: "Working…" })).toBeDisabled();
  await user.keyboard("{Escape}");
  expect(screen.getByRole("alertdialog")).toBeInTheDocument();

  resolveAction({ error: "Applicant approval changed elsewhere" });

  expect(await within(dialog).findByRole("alert")).toHaveTextContent(
    "Applicant approval changed elsewhere",
  );
  expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  expect(initiate).toHaveBeenCalledOnce();
  const [previousState, formData] = initiate.mock.calls[0] as [unknown, FormData];
  expect(previousState).toEqual({});
  expect(formData.get("application_id")).toBe("application-1");
  expect(formData.get("client_request_id")).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
  );
});

it("focuses the dated setup result and sends a new request for another link", async () => {
  initiate.mockImplementation(async (_previous, data: FormData) => ({
    requestedAt: "2026-11-21T08:15:00Z",
    requestId: data.get("client_request_id"),
  }));
  const user = userEvent.setup();
  render(
    <AccountSetupAction
      applicationId="application-1"
      applicantName="Ada Applicant"
      applicantEmail="ada@example.test"
    />,
  );
  await user.click(screen.getByRole("button", { name: "Start account setup" }));
  await user.click(screen.getByRole("button", { name: "Send link" }));
  const status = await screen.findByRole("status");
  expect(status).toHaveTextContent(
    "Setup email on its way to ada@example.test (requested 21 Nov 2026, 09:15)",
  );
  expect(status).toHaveFocus();
  expect(screen.queryByRole("alertdialog")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Send another link" }));
  await user.click(screen.getByRole("button", { name: "Send link" }));
  expect(initiate).toHaveBeenCalledTimes(2);
  expect(initiate.mock.calls[0]![1].get("client_request_id")).not.toBe(
    initiate.mock.calls[1]![1].get("client_request_id"),
  );
  expect(status).toHaveFocus();
});
