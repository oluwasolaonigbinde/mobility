import { expect, it } from "vitest";
import { smallVatConfirmation, vatPercentageToRate, vatRateToPercentage } from "./vat-percentage";

it.each([
  ["7.5", "0.075"],
  ["0", "0"],
  ["100", "1"],
  ["0.0001", "0.000001"],
  ["0.075", "0.00075"],
])("converts %s percent to %s rate and back exactly", (percentage, rate) => {
  expect(vatPercentageToRate(percentage)).toBe(rate);
  expect(vatRateToPercentage(rate)).toBe(percentage);
});

it("displays a saved six-place rate without floating-point rounding", () => {
  expect(vatRateToPercentage("0.075000")).toBe("7.5");
  expect(vatPercentageToRate(" 007.5000 ")).toBe("0.075");
});

it.each(["7.50000", "0.00001", "100.0001", "101", "-1", "1e1", "", "NaN"])(
  "refuses invalid or over-precise percentage %s",
  (value) => expect(vatPercentageToRate(value)).toBeNull(),
);

it.each(["0.0750000", "1.000001", "-0.1", ""])("refuses invalid saved rate %s", (value) => {
  expect(vatRateToPercentage(value)).toBeNull();
});

it("asks about the actual small percentage with an exact suggested value", () => {
  expect(smallVatConfirmation("0.075")).toBe(
    "VAT is 0.075%. Did you mean 7.5%? Save using 0.075%?",
  );
  expect(smallVatConfirmation("0.0001")).toContain("VAT is 0.0001%.");
  for (const value of ["0", "1", "7.5", "100", "invalid"]) {
    expect(smallVatConfirmation(value)).toBeNull();
  }
});
