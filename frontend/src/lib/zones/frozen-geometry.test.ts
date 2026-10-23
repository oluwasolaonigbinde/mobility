import { expect, it } from "vitest";
import { frozenGeometry } from "./frozen-geometry";

it("reads actual frozen target and exclusion shapes, including holes and multipolygons", () => {
  expect(frozenGeometry("POLYGON((7 9,7.5 9,7.5 9.5,7 9))")).toEqual({
    type: "Polygon",
    coordinates: [
      [
        [7, 9],
        [7.5, 9],
        [7.5, 9.5],
        [7, 9],
      ],
    ],
  });
  expect(
    frozenGeometry("MULTIPOLYGON(((7 9,7.5 9,7.5 9.5,7 9),(7.1 9.1,7.2 9.1,7.2 9.2,7.1 9.1)))")
      ?.coordinates,
  ).toHaveLength(1);
  expect(frozenGeometry("POLYGON((+7e0 9,7.5 9,7.5 9.5,+7e0 9))")?.type).toBe("Polygon");
});
it.each([
  null,
  "POLYGON EMPTY",
  "POINT(7 9)",
  "POLYGON((7 9,8 9,8 10))",
  "POLYGON((999 9,8 9,8 10,999 9))",
  "POLYGON((7 9 0,8 9 0,8 10 0,7 9 0))",
  "POLYGON((garbage))",
])("does not invent a map for invalid or unsupported frozen geometry %s", (value) => {
  expect(frozenGeometry(value)).toBeNull();
});
