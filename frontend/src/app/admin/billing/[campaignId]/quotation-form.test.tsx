import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { QuotationForm } from "./quotation-form";

it("keeps all entered quotation values after a conflict", async () => {
  const action = vi.fn(async () => ({ error: "This quote reference is already used." }));
  render(
    <QuotationForm action={action}>
      <label>
        Reference
        <input name="quote_reference" />
      </label>
      <label>
        VAT (%)
        <input name="tax_percentage" defaultValue="7.5" />
      </label>
      <button>Save</button>
    </QuotationForm>,
  );
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Reference"), "Q-duplicate");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "This quote reference is already used.",
  );
  expect(screen.getByLabelText("Reference")).toHaveValue("Q-duplicate");
});

afterEach(() => vi.restoreAllMocks());

it.each([true, false])(
  "confirms a small percentage once before saving (accepted: %s)",
  async (accepted) => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(accepted);
    const action = vi.fn(async () => ({ error: "Save response" }));
    render(
      <QuotationForm action={action}>
        <label>
          VAT (%)
          <input name="tax_percentage" defaultValue="0.075" />
        </label>
        <button>Save</button>
      </QuotationForm>,
    );
    await userEvent.setup().click(screen.getByRole("button", { name: "Save" }));
    expect(confirm).toHaveBeenCalledExactlyOnceWith(
      "VAT is 0.075%. Did you mean 7.5%? Save using 0.075%?",
    );
    expect(action).toHaveBeenCalledTimes(accepted ? 1 : 0);
    expect(screen.getByLabelText("VAT (%)")).toHaveValue("0.075");
  },
);

it.each(["0", "1", "7.5", "100"])(
  "saves %s without small-percentage confirmation",
  async (percentage) => {
    const confirm = vi.spyOn(window, "confirm");
    const action = vi.fn(async () => ({ error: "Save response" }));
    render(
      <QuotationForm action={action}>
        <input name="tax_percentage" defaultValue={percentage} />
        <button>Save</button>
      </QuotationForm>,
    );
    await userEvent.setup().click(screen.getByRole("button", { name: "Save" }));
    expect(action).toHaveBeenCalledOnce();
    expect(confirm).not.toHaveBeenCalled();
  },
);

it.each(["101", "0.00001"])("rejects %s before confirmation or saving", async (percentage) => {
  const confirm = vi.spyOn(window, "confirm");
  const action = vi.fn();
  render(
    <QuotationForm action={action}>
      <input name="tax_percentage" defaultValue={percentage} />
      <button>Save</button>
    </QuotationForm>,
  );
  await userEvent.setup().click(screen.getByRole("button", { name: "Save" }));
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Enter VAT from 0 to 100%, with up to 4 decimal places.",
  );
  expect(action).not.toHaveBeenCalled();
  expect(confirm).not.toHaveBeenCalled();
});
