import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { NegativeAdjustmentForm } from "./negative-adjustment-form";

const record = vi.hoisted(() => vi.fn());
vi.mock("./actions", () => ({ negativeAdjustmentAction: record }));

it("retains one adjustment reference through uncertainty and locks a confirmed result", async () => {
  const references: string[] = [];
  record.mockImplementation(async (_previous, form: FormData) => {
    references.push(String(form.get("request_id")));
    return references.length === 1 ? { error: "Retry the same adjustment" } : { done: "Recorded" };
  });
  render(<NegativeAdjustmentForm entryId="credit" currency="NGN" />);
  const user = userEvent.setup();
  await user.click(screen.getByText("Record a negative adjustment"));
  await user.type(screen.getByRole("textbox", { name: "Amount to subtract" }), "20.25");
  await user.type(
    screen.getByRole("textbox", { name: "Adjustment reason" }),
    "Correct overpayment",
  );
  await user.click(screen.getByRole("button", { name: "Record negative adjustment" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Retry the same adjustment");
  await user.click(screen.getByRole("button", { name: "Record negative adjustment" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Recorded");
  expect(references[0]).toMatch(/^[0-9a-f-]{36}$/);
  expect(references[1]).toBe(references[0]);
  expect(screen.getByRole("button", { name: "Record negative adjustment" })).toBeDisabled();
});
