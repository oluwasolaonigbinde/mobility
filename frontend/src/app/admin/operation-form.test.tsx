import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const resolve = vi.hoisted(() => vi.fn());
vi.mock("./operations-actions", () => ({ resolveOperation: resolve }));

import { OperationForm } from "./operation-form";

const TASK = "11111111-1111-4111-8111-111111111111";
const TRIP = "22222222-2222-4222-8222-222222222222";

function submitted(call = 0) {
  return Object.fromEntries((resolve.mock.calls[call]![1] as FormData).entries());
}

describe("OperationForm", () => {
  beforeEach(() => resolve.mockReset());

  it("records a contact outcome once and then locks the task", async () => {
    resolve.mockResolvedValue({
      done: "Contact outcome recorded. This does not confirm provider delivery.",
    });
    const user = userEvent.setup();
    render(<OperationForm id={TASK} contact />);
    expect(screen.queryByRole("button", { name: "Apply evidence" })).toBeNull();
    await user.selectOptions(screen.getByRole("combobox", { name: "Recorded outcome" }), "reached");
    await user.type(screen.getByRole("textbox", { name: "Contact note" }), "Spoke to driver");
    await user.click(screen.getByRole("checkbox", { name: /exact contact purpose/ }));
    await user.click(screen.getByRole("button", { name: "Record outcome" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "does not confirm provider delivery",
    );
    expect(submitted()).toEqual({
      id: TASK,
      kind: "contact",
      outcome: "reached",
      note: "Spoke to driver",
      confirmed: "on",
    });
    expect(screen.getByRole("button", { name: "Record outcome" })).toBeDisabled();
  });

  it("submits the chosen evidence decision with its trip and keeps retry available on error", async () => {
    resolve.mockResolvedValue({ error: "No result was confirmed. Reload or retry." });
    const user = userEvent.setup();
    render(<OperationForm id={TASK} trip={TRIP} />);
    expect(screen.queryByRole("combobox")).toBeNull();
    await user.type(screen.getByRole("textbox", { name: "Review reason" }), "Duplicate upload");
    await user.click(screen.getByRole("checkbox", { name: /does not change earnings/ }));
    await user.click(screen.getByRole("button", { name: "Discard evidence" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No result was confirmed");
    expect(submitted()).toEqual({
      id: TASK,
      trip: TRIP,
      kind: "discard",
      note: "Duplicate upload",
      confirmed: "on",
    });
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByRole("button", { name: "Apply evidence" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Discard evidence" })).toBeEnabled();
  });

  it("does not submit until the reason and confirmation are provided", async () => {
    const user = userEvent.setup();
    const { container } = render(<OperationForm id={TASK} />);
    expect(container.querySelector('input[name="trip"]')).toBeNull();
    await user.click(screen.getByRole("button", { name: "Apply evidence" }));
    expect(resolve).not.toHaveBeenCalled();
  });
});
