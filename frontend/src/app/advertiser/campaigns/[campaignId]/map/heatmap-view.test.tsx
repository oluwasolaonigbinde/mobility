import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mapConstructor = vi.hoisted(() => vi.fn());
const handlers = vi.hoisted(() => new Map<string, () => void>());

vi.mock("maplibre-gl", () => ({ default: { Map: mapConstructor } }));

import { GovernedZoneMap, MAP_READY_TIMEOUT_MS } from "./heatmap-view";

const zone = {
  rank: 1,
  id: "00000000-0000-4000-8000-000000000001",
  campaign_id: "00000000-0000-4000-8000-000000000002",
  name: "Central Abuja",
  description: null,
  zone_type: "target" as const,
  area_sq_m: "1000000.00",
  geometry: {
    type: "Polygon" as const,
    coordinates: [
      [
        [7.4, 9.0],
        [7.5, 9.0],
        [7.5, 9.1],
        [7.4, 9.0],
      ],
    ],
  },
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

function fakeMap() {
  return {
    on: vi.fn((event: string, handler: () => void) => handlers.set(event, handler)),
    once: vi.fn((event: string, handler: () => void) => handlers.set(event, handler)),
    addSource: vi.fn(),
    addLayer: vi.fn(),
    fitBounds: vi.fn(),
    off: vi.fn(),
    remove: vi.fn(),
  };
}

describe("GovernedZoneMap failure boundary", () => {
  beforeEach(() => {
    handlers.clear();
    mapConstructor.mockReset();
  });

  it("fails closed when MapLibre cannot start", () => {
    mapConstructor.mockImplementation(function () {
      throw new Error("constructor failed");
    });
    render(<GovernedZoneMap zones={[zone]} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/map could not start/i);
  });

  it("fails closed on an asynchronous style error", () => {
    mapConstructor.mockImplementation(function () {
      return fakeMap();
    });
    render(<GovernedZoneMap zones={[zone]} />);
    act(() => handlers.get("error")?.());
    expect(screen.getByRole("alert")).toHaveTextContent(/configured map style failed/i);
  });

  it("fails closed when governed geometry cannot be installed after style load", () => {
    const map = fakeMap();
    map.addSource.mockImplementation(() => {
      throw new Error("invalid geometry");
    });
    mapConstructor.mockImplementation(function () {
      return map;
    });
    render(<GovernedZoneMap zones={[zone]} />);
    act(() => handlers.get("load")?.());
    expect(screen.getByRole("alert")).toHaveTextContent(/geometry could not be rendered/i);
  });

  it("hides an already-ready map if MapLibre later reports an error", () => {
    mapConstructor.mockImplementation(function () {
      return fakeMap();
    });
    render(<GovernedZoneMap zones={[zone]} />);
    act(() => handlers.get("load")?.());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    act(() => handlers.get("error")?.());
    expect(screen.getByRole("alert")).toHaveTextContent(/configured map style failed/i);
  });

  it("fails closed when the map is never ready within the latency bound", () => {
    vi.useFakeTimers();
    mapConstructor.mockImplementation(function () {
      return fakeMap();
    });
    render(<GovernedZoneMap zones={[zone]} />);
    act(() => vi.advanceTimersByTime(MAP_READY_TIMEOUT_MS));
    expect(screen.getByRole("alert")).toHaveTextContent(/within 3 seconds/i);
    vi.useRealTimers();
  });
});
