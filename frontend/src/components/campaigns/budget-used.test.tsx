import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { BudgetUsed } from "./budget-used";
const value = (booked: number, budget: number | null = 10000) => ({
  booked: BigInt(booked),
  budget: budget === null ? null : BigInt(budget),
  currency: "NGN",
  asOf: "2026-10-18T09:00:00Z",
});
it("shows a daily-only campaign's booked amount alone, with no bar", () => {
  render(<BudgetUsed value={value(2500, null)} />);
  expect(screen.getByRole("heading")).toHaveTextContent(/^Booked: ₦25\.00$/);
  expect(screen.queryByRole("progressbar")).toBeNull();
  expect(document.body).not.toHaveTextContent(/today|daily|budget/i);
});
it.each([0, 9999, 10000, 10001, 15000])(
  "shows only the amounts for booked %i of 10000, with no bar, percent or warning colour",
  (booked) => {
    const { container } = render(<BudgetUsed value={value(booked)} />);
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(document.body).not.toHaveTextContent(/%/);
    expect(container.querySelector(".text-amber, .text-green")).toBeNull();
    expect(screen.getByText(/As at/)).toHaveTextContent("Nigeria time (WAT)");
  },
);
it("shows an over-budget booked amount honestly", () => {
  render(<BudgetUsed value={value(15000)} />);
  expect(screen.getByRole("heading")).toHaveTextContent("Booked: ₦150.00 of your ₦100.00 budget");
});
it("shows a quiet dash, with no bar or sentence, when the figure is missing", () => {
  render(<BudgetUsed value={null} />);
  expect(screen.queryByRole("progressbar")).toBeNull();
  expect(screen.getByRole("heading")).toHaveTextContent("Booked: —");
  expect(screen.queryByText(/being updated/)).toBeNull();
});
