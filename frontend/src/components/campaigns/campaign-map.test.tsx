import { act, cleanup, render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CampaignMap } from "./campaign-map";

const map = vi.hoisted(() => ({
  on: vi.fn(),
  resize: vi.fn(),
  addSource: vi.fn(),
  addLayer: vi.fn(),
  fitBounds: vi.fn(),
  remove: vi.fn(),
}));
vi.mock("maplibre-gl", () => ({
  Map: class {
    constructor() {
      return map;
    }
  },
}));
vi.mock("@/lib/map/config", () => ({
  activeMapStyle: () => ({}),
  DEFAULT_CENTER: [7, 9],
  zoneColors: () => ({ target: "green", exclusion: "red" }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

it("refits the complete real area with padding when the panel reaches a new size", () => {
  let resized: ResizeObserverCallback;
  const disconnect = vi.fn();
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(callback: ResizeObserverCallback) {
        resized = callback;
      }
      observe = vi.fn();
      disconnect = disconnect;
    },
  );
  const view = render(
    <CampaignMap
      areas={[
        {
          id: "area",
          name: "Real target",
          geometry: {
            type: "Polygon",
            coordinates: [
              [
                [7, 9],
                [7.1, 9],
                [7.1, 9.1],
                [7, 9.1],
                [7, 9],
              ],
            ],
          },
        },
      ]}
    />,
  );
  const loaded = map.on.mock.calls.find(([event]) => event === "load")?.[1];
  act(() => loaded());
  expect(map.fitBounds).toHaveBeenLastCalledWith(
    [
      [7, 9],
      [7.1, 9.1],
    ],
    { padding: 24, maxZoom: 14, duration: 0 },
  );
  map.fitBounds.mockClear();
  act(() => resized!([], {} as ResizeObserver));
  expect(map.fitBounds).toHaveBeenCalledOnce();
  view.unmount();
  expect(disconnect).toHaveBeenCalledOnce();
  expect(map.remove).toHaveBeenCalledOnce();
});
