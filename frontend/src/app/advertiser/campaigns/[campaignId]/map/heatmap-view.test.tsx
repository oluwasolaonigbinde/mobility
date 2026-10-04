import { renderToString } from "react-dom/server";
import { hydrateRoot } from "react-dom/client";
import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mapConstructor = vi.hoisted(() => vi.fn());
const handlers = vi.hoisted(() => new Map<string, () => void>());

vi.mock("maplibre-gl", () => ({
  Map: mapConstructor,
  Marker: class {
    setLngLat() {
      return this;
    }
    addTo() {
      return this;
    }
  },
}));

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
    vi.stubEnv("NEXT_PUBLIC_MAP_STYLE_URL", "https://maps.example.invalid/style.json");
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
    expect(screen.getByRole("alert")).toHaveTextContent(/areas could not be drawn/i);
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

  it("uses the configured style and attribution, then fits and outlines the areas", () => {
    const map = fakeMap();
    mapConstructor.mockImplementation(function () {
      return map;
    });
    render(<GovernedZoneMap zones={[zone]} />);
    expect(mapConstructor).toHaveBeenCalledWith(
      expect.objectContaining({
        style: "https://maps.example.invalid/style.json",
        attributionControl: { compact: true },
      }),
    );
    act(() => handlers.get("load")?.());
    expect(map.fitBounds).toHaveBeenCalled();
    expect(map.addSource).toHaveBeenCalled();
    expect(map.addLayer.mock.calls.map(([layer]) => layer.type)).toEqual(["fill", "line"]);
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

it("draws and names local areas without starting a network map", () => {
  mapConstructor.mockClear();
  vi.stubEnv("NEXT_PUBLIC_MAP_STYLE_URL", "");
  render(<GovernedZoneMap zones={[zone]} />);
  expect(
    screen.getByRole("img", { name: "Campaign areas by estimated ad exposure" }),
  ).toBeInTheDocument();
  expect(document.querySelector("path")).toHaveAttribute("fill-rule", "evenodd");
  expect(document.querySelector("text")).toHaveTextContent("Central Abuja");
  expect(mapConstructor).not.toHaveBeenCalled();
});
it("rejects invalid and empty local geometry", () => {
  vi.stubEnv("NEXT_PUBLIC_MAP_STYLE_URL", "");
  const { rerender } = render(<GovernedZoneMap zones={[]} />);
  expect(screen.getByRole("status")).toHaveTextContent("Campaign areas are unavailable");
  rerender(
    <GovernedZoneMap zones={[{ ...zone, geometry: { type: "Point", coordinates: [7, 9] } }]} />,
  );
  expect(screen.queryByRole("img")).toBeNull();
});
it("renders MultiPolygon islands and inner holes", () => {
  vi.stubEnv("NEXT_PUBLIC_MAP_STYLE_URL", "");
  const ring = zone.geometry.coordinates[0]!;
  render(
    <GovernedZoneMap
      zones={[{ ...zone, geometry: { type: "MultiPolygon", coordinates: [[ring, ring], [ring]] } }]}
    />,
  );
  expect(document.querySelector("path")!.getAttribute("d")!.split(" Z")).toHaveLength(4);
  expect(document.querySelector("path")!.getAttribute("d")).not.toMatch(/NaN|Infinity/);
});

it("hydrates the server-rendered area title without regenerating the map", async () => {
  vi.stubEnv("NEXT_PUBLIC_MAP_STYLE_URL", "");
  const container = document.createElement("div");
  container.innerHTML = renderToString(<GovernedZoneMap zones={[zone]} />);
  document.body.append(container);
  const originalPath = container.querySelector("path");
  const onRecoverableError = vi.fn();
  let root: ReturnType<typeof hydrateRoot> | undefined;
  try {
    await act(async () => {
      root = hydrateRoot(container, <GovernedZoneMap zones={[zone]} />, { onRecoverableError });
    });
    expect(onRecoverableError).not.toHaveBeenCalled();
    expect(container.querySelector("path")).toBe(originalPath);
    expect(container.querySelector("title")).toHaveTextContent("1. Central Abuja");
  } finally {
    await act(async () => root?.unmount());
    container.remove();
  }
});
