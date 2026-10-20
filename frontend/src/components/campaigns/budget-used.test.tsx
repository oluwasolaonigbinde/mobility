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
it("shows an over-budget booked amount honestly while capping the visual bar", () => {
  render(<BudgetUsed value={value(15000)} />);
  expect(screen.getByRole("heading")).toHaveTextContent("Booked: ₦150.00 of your ₦100.00 budget");
  expect(screen.getByRole("progressbar", { name: "Budget booked" })).toHaveAttribute(
    "value",
    "100",
  );
  expect(screen.getByText("150%")).toBeInTheDocument();
  expect(screen.getByText(/As at/)).toHaveTextContent("Nigeria time (WAT)");
});
it.each([
  [10000, "text-green", "accent-green"],
  [10001, "text-amber", "accent-amber"],
])("styles exactly the budget as normal and only more as a warning (%i)", (booked, text, bar) => {
  render(<BudgetUsed value={value(booked)} />);
  expect(screen.getByText(/%$/)).toHaveClass(text);
  expect(screen.getByRole("progressbar")).toHaveClass(bar);
});
it.each([
  [0, "0", "0%"],
  [9999, "99.99", "99.99%"],
  [10000, "100", "100%"],
  [10001, "100", "100.01%"],
])("draws booked %i of 10000 minor units as bar %s and text %s", (booked, bar, text) => {
  render(<BudgetUsed value={value(booked)} />);
  expect(screen.getByRole("progressbar")).toHaveAttribute("value", bar);
  expect(screen.getByText(text)).toBeInTheDocument();
});
it("shows a quiet dash, with no bar or sentence, when the figure is missing", () => {
  render(<BudgetUsed value={null} />);
  expect(screen.queryByRole("progressbar")).toBeNull();
  expect(screen.getByRole("heading")).toHaveTextContent("Booked: —");
  expect(screen.queryByText(/being updated/)).toBeNull();
});
