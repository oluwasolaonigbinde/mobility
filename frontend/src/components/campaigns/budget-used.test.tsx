import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { BudgetUsed } from "./budget-used";
it("shows an over-budget amount honestly while capping the visual bar", () => {
  render(
    <BudgetUsed
      value={{
        spent: BigInt(15000),
        budget: BigInt(10000),
        currency: "NGN",
        evaluatedAt: "2026-10-18T09:00:00Z",
      }}
    />,
  );
  expect(screen.getByRole("progressbar", { name: "Budget used" })).toHaveAttribute("value", "100");
  expect(screen.getByText("150% used")).toBeInTheDocument();
  expect(screen.getByText(/As at/)).toHaveTextContent("Nigeria time (WAT)");
});
it("never draws a zero progress bar when spending is unavailable", () => {
  render(<BudgetUsed value={null} />);
  expect(screen.queryByRole("progressbar")).toBeNull();
  expect(screen.getByText("Spending is being updated.")).toBeInTheDocument();
});
