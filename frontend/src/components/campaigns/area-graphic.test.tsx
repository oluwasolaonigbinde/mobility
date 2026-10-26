import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { AreaGraphic } from "./area-graphic";
it("draws actual boundaries with named areas and no network image", () => {
  const { container } = render(
    <AreaGraphic
      areas={[
        {
          id: "wuse",
          name: "Wuse II",
          geometry: {
            type: "Polygon",
            coordinates: [
              [
                [7.4, 9],
                [7.5, 9],
                [7.5, 9.1],
                [7.4, 9.1],
                [7.4, 9],
              ],
            ],
          },
        },
      ]}
    />,
  );
  expect(screen.getByRole("img", { name: "Campaign areas: Wuse II" })).toBeInTheDocument();
  expect(container.innerHTML).not.toMatch(/NaN|Infinity|https?:|<image/);
});
it("does not draw malformed geometry as a real area", () => {
  render(
    <AreaGraphic
      areas={[{ id: "bad", name: "Bad", geometry: { type: "Polygon", coordinates: [] } }]}
    />,
  );
  expect(screen.getByText("The area picture is unavailable.")).toBeInTheDocument();
  expect(screen.queryByRole("img")).toBeNull();
});
it("distinguishes actual Avoid geometry with a hatch instead of drawing invented landmarks", () => {
  const { container } = render(
    <AreaGraphic
      areas={[
        {
          id: "avoid",
          name: "Restricted",
          zone_type: "exclusion",
          geometry: {
            type: "Polygon",
            coordinates: [
              [
                [7, 9],
                [7.5, 9],
                [7.5, 9.5],
                [7, 9],
              ],
            ],
          },
        },
      ]}
    />,
  );
  expect(container.querySelector('path[fill^="url(#"]')).not.toBeNull();
  expect(screen.getByRole("img", { name: "Campaign areas: Restricted" })).toBeInTheDocument();
});
