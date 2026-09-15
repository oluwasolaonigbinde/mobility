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
  render(<AccountSetupAction applicationId="application-1" applicantName="Ada Applicant" />);

  const trigger = screen.getByRole("button", { name: "Start account setup" });
  await user.click(trigger);

  expect(initiate).not.toHaveBeenCalled();
  const dialog = screen.getByRole("alertdialog", {
    name: "Start account setup for Ada Applicant?",
  });
  expect(dialog.tagName).toBe("DIALOG");
  expect(dialog).toHaveTextContent(
    "creates a one-use setup link and queues delivery to the applicant's stored email",
  );
  expect(dialog).toHaveTextContent("Delivery is not confirmed");
  expect(dialog).toHaveTextContent("replaces any earlier unused setup link");
  const cancel = within(dialog).getByRole("button", { name: "Keep current setup state" });
  const confirm = within(dialog).getByRole("button", { name: "Create one-use setup link" });
  expect(cancel).toHaveFocus();

  await user.keyboard("{Shift>}{Tab}{/Shift}");
  expect(confirm).toHaveFocus();
  await user.keyboard("{Tab}");
  expect(cancel).toHaveFocus();

  await user.keyboard("{Escape}");
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();

  await user.click(trigger);
  await user.click(screen.getByRole("button", { name: "Keep current setup state" }));
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
  render(<AccountSetupAction applicationId="application-1" applicantName="Ada Applicant" />);

  await user.click(screen.getByRole("button", { name: "Start account setup" }));
  await user.click(screen.getByRole("button", { name: "Create one-use setup link" }));

  const dialog = screen.getByRole("alertdialog");
  expect(within(dialog).getByRole("button", { name: "Keep current setup state" })).toBeDisabled();
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

it("focuses the provider-neutral terminal status after successful confirmation", async () => {
  initiate.mockResolvedValue({
    done: "A one-use setup link was created and queued for delivery to the applicant's stored email. Delivery is not confirmed.",
  });
  const user = userEvent.setup();
  render(<AccountSetupAction applicationId="application-1" applicantName="Ada Applicant" />);

  await user.click(screen.getByRole("button", { name: "Start account setup" }));
  await user.click(screen.getByRole("button", { name: "Create one-use setup link" }));

  const status = await screen.findByRole("status");
  expect(status).toHaveTextContent("created and queued for delivery");
  expect(status).toHaveTextContent("Delivery is not confirmed");
  expect(status).toHaveFocus();
  expect(screen.queryByRole("button", { name: "Start account setup" })).not.toBeInTheDocument();
});
