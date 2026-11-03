import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { QuotationForm } from "./quotation-form";

it("keeps all entered quotation values after a conflict", async () => {
  const action = vi.fn(async () => ({ error: "This quote reference is already used." }));
  render(
    <QuotationForm action={action}>
      <label>
        Reference
        <input name="quote_reference" />
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
