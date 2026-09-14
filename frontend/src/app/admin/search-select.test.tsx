import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { SearchSelect } from "./search-select";
const search = vi.hoisted(() => vi.fn());
vi.mock("./queue-options", () => ({ searchOperatorOptions: search }));
it("reaches options beyond one hundred and requires explicit available selection", async () => {
  const user = userEvent.setup();
  search.mockImplementation(async ({ offset }) => ({
    total: 101,
    items: [
      { id: `item-${offset}`, label: `Person ${offset}`, detail: "email@example.test" },
      {
        id: "blocked",
        label: "Suspended person",
        detail: "Unavailable",
        unavailable: "Approval required",
      },
    ],
  }));
  const { container } = render(
    <SearchSelect kind="driver" name="driver_profile_id" label="Driver" />,
  );
  await user.click(screen.getByRole("button", { name: "Find driver" }));
  expect(container.querySelector('input[type="hidden"]')).toHaveValue("");
  expect(await screen.findByRole("button", { name: /Suspended person/ })).toBeDisabled();
  for (let i = 0; i < 4; i++) await user.click(screen.getByRole("button", { name: "Next" }));
  expect(search).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 100 }));
  await user.click(await screen.findByRole("button", { name: /Person 100/ }));
  expect(container.querySelector('input[type="hidden"]')).toHaveValue("item-100");
});
