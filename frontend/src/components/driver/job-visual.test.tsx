import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { JobVisual } from "./job-visual";

it("shows paying areas and explicitly named exclusions", () => {
  render(
    <JobVisual
      terms={{
        zones: { target: [{ name: "Wuse II" }], exclusion: [{ name: "Airport restricted area" }] },
      }}
    />,
  );
  expect(screen.getByText("Wuse II")).toBeInTheDocument();
  expect(screen.getByText("Avoid: Airport restricted area")).toBeInTheDocument();
  expect(screen.getByRole("img")).toHaveAttribute(
    "src",
    expect.stringContaining("hero-vehicle-placeholder.svg"),
  );
});

it("warns when exclusions are unreadable even if paying areas are available", () => {
  render(<JobVisual terms={{ zones: { target: [{ name: "Wuse II" }], exclusion: [{}] } }} />);
  expect(screen.getByText("Wuse II")).toBeInTheDocument();
  expect(screen.getByText(/Areas to avoid couldn't be loaded/)).toBeInTheDocument();
});

it("does not imply restrictions are unavailable when the frozen list is explicitly empty", () => {
  render(<JobVisual terms={{ zones: { target: [{ name: "Wuse II" }], exclusion: [] } }} />);
  expect(screen.queryByText(/Areas to avoid|Avoid:/)).not.toBeInTheDocument();
});
