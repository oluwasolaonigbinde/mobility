import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const resolve = vi.hoisted(() => vi.fn());
vi.mock("./operations-actions", () => ({ resolveOperation: resolve }));

import { OperationForm } from "./operation-form";

const TASK = "11111111-1111-4111-8111-111111111111";

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
    render(<OperationForm id={TASK} />);
    expect(screen.queryByRole("button", { name: "Add to trip" })).toBeNull();
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

  it("does not submit until the reason and confirmation are provided", async () => {
    const user = userEvent.setup();
    const { container } = render(<OperationForm id={TASK} />);
    expect(container.querySelector('input[name="trip"]')).toBeNull();
    await user.click(screen.getByRole("button", { name: "Record outcome" }));
    expect(resolve).not.toHaveBeenCalled();
  });
});
