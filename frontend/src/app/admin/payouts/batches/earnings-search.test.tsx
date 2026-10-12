import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { EarningsSearch } from "./earnings-search";

it("keeps search off until something is typed", () => {
  render(<EarningsSearch query={{ tab: "payouts", runs: "1" }} />);
  const search = screen.getByRole("button", { name: "Search earnings" });
  expect(search).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Search driver or campaign"), {
    target: { value: "Ada" },
  });
  expect(search).toBeEnabled();
  fireEvent.change(screen.getByLabelText("Search driver or campaign"), {
    target: { value: "   " },
  });
  expect(search).toBeDisabled();
});

it("lets staff clear an applied search and keeps the other list filters", () => {
  const { container } = render(
    <EarningsSearch query={{ tab: "payouts", q: "Ada", runs: "1", credits: "2" }} />,
  );
  fireEvent.change(screen.getByLabelText("Search driver or campaign"), {
    target: { value: "" },
  });
  expect(screen.getByRole("button", { name: "Show all earnings" })).toBeEnabled();
  const hidden = [...container.querySelectorAll<HTMLInputElement>("input[type=hidden]")].map(
    (input) => [input.name, input.value],
  );
  expect(hidden).toEqual([
    ["tab", "payouts"],
    ["runs", "1"],
  ]);
});
