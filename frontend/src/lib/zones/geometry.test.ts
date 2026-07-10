import { describe, expect, it } from "vitest";
import { validateZoneGeometry, geometryBounds, type ZoneGeometry } from "./geometry";

const square: ZoneGeometry = {
  type: "Polygon",
  coordinates: [
    [
      [7.45, 9.03],
      [7.53, 9.03],
      [7.53, 9.09],
      [7.45, 9.09],
      [7.45, 9.03],
    ],
  ],
};

describe("validateZoneGeometry", () => {
  it("accepts a valid closed polygon", () => {
    expect(validateZoneGeometry(square)).toEqual({ ok: true });
  });

  it("accepts a MultiPolygon of valid polygons", () => {
    const multi = { type: "MultiPolygon", coordinates: [square.coordinates] };
    expect(validateZoneGeometry(multi)).toEqual({ ok: true });
  });

  it("rejects unclosed rings", () => {
    const open = {
      type: "Polygon",
      coordinates: [
        [
          [7.45, 9.03],
          [7.53, 9.03],
          [7.53, 9.09],
          [7.45, 9.09],
        ],
      ],
    };
    const result = validateZoneGeometry(open);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toMatch(/closed/i);
  });

  it("rejects rings with fewer than four positions", () => {
    const triangleOpen = {
      type: "Polygon",
      coordinates: [
        [
          [7.45, 9.03],
          [7.53, 9.03],
          [7.45, 9.03],
        ],
      ],
    };
    const result = validateZoneGeometry(triangleOpen);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toMatch(/four positions/i);
  });

  it("rejects out-of-bounds and non-finite coordinates", () => {
    const bad = (lon: number, lat: number) => ({
      type: "Polygon",
      coordinates: [
        [
          [lon, lat],
          [7.53, 9.03],
          [7.53, 9.09],
          [lon, lat],
        ],
      ],
    });
    expect(validateZoneGeometry(bad(181, 9)).ok).toBe(false);
    expect(validateZoneGeometry(bad(7, 91)).ok).toBe(false);
    expect(validateZoneGeometry(bad(Number.NaN, 9)).ok).toBe(false);
  });

  it("rejects non-polygon geometry types and garbage", () => {
    expect(validateZoneGeometry({ type: "Point", coordinates: [7.4, 9.0] }).ok).toBe(false);
    expect(validateZoneGeometry(null).ok).toBe(false);
    expect(validateZoneGeometry("polygon").ok).toBe(false);
  });
});

describe("geometryBounds", () => {
  it("computes the bounding box of a polygon", () => {
    expect(geometryBounds(square)).toEqual([7.45, 9.03, 7.53, 9.09]);
  });
});
