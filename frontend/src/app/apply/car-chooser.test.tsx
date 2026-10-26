import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { CarChooser } from "./car-chooser";

const cars = [
  { vehicle_id: "car-1", plate_number: "ABC-123-XY", status: "rejected" },
  { vehicle_id: "car-2", plate_number: "LND-222-ZZ", status: "approved" },
];

function renderInForm(list = cars) {
  render(
    <form aria-label="car">
      <CarChooser cars={list} />
    </form>,
  );
  return screen.getByRole("form", { name: "car" }) as HTMLFormElement;
}

it("lists the applicant's own cars by plate and sends the chosen one as vehicle_id", () => {
  const form = renderInForm();
  expect(screen.getByRole("group", { name: "Which car are you updating?" })).toBeInTheDocument();
  expect(new FormData(form).get("vehicle_id")).toBeNull();
  fireEvent.click(screen.getByRole("radio", { name: "ABC-123-XY" }));
  expect(new FormData(form).get("vehicle_id")).toBe("car-1");
  fireEvent.click(screen.getByRole("radio", { name: "A different car" }));
  expect(new FormData(form).get("vehicle_id")).toBe("");
  expect(screen.queryByText("car-1")).not.toBeInTheDocument();
});

it("preselects the only car", () => {
  const form = renderInForm([cars[0]!]);
  expect(screen.getByRole("radio", { name: "ABC-123-XY" })).toBeChecked();
  expect(new FormData(form).get("vehicle_id")).toBe("car-1");
});

it("shows nothing when the applicant has no cars yet", () => {
  renderInForm([]);
  expect(screen.queryByRole("group")).toBeNull();
  expect(screen.queryByRole("radio")).toBeNull();
});
