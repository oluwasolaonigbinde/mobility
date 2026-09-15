import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mapConstructor = vi.hoisted(() => vi.fn());
const navigationControl = vi.hoisted(() => vi.fn());
const drawConstructor = vi.hoisted(() => vi.fn());
const adapterConstructor = vi.hoisted(() => vi.fn());
const mapHandlers = vi.hoisted(() => new Map<string, () => void>());
const deleteZoneAction = vi.hoisted(() => vi.fn());

vi.mock("maplibre-gl", () => ({
  Map: mapConstructor,
  NavigationControl: navigationControl,
}));
vi.mock("terra-draw", () => ({
  TerraDraw: drawConstructor,
  TerraDrawPolygonMode: vi.fn(),
}));
vi.mock("terra-draw-maplibre-gl-adapter", () => ({
  TerraDrawMapLibreGLAdapter: adapterConstructor,
}));
vi.mock("@/lib/map/config", () => ({
  activeMapStyleUrl: () => ({ version: 8, sources: {}, layers: [] }),
  applyThemeMapTint: vi.fn(),
  DEFAULT_CENTER: [7.49, 9.07],
  DEFAULT_ZOOM: 11,
  ZONE_COLOR_VARS: {
    target: "var(--color-amber)",
    bonus: "var(--color-cyan)",
    exclusion: "var(--color-coral)",
  },
  zoneColors: () => ({
    target: "#f90",
    bonus: "#0cf",
    exclusion: "#f66",
    neutral: "#999",
  }),
}));
vi.mock("./actions", () => ({
  createZoneAction: vi.fn(),
  updateZoneAction: vi.fn(),
  deleteZoneAction,
}));

import { ZonesEditor } from "./zones-editor";

const zone = {
  id: "00000000-0000-4000-8000-000000000001",
  campaign_id: "00000000-0000-4000-8000-000000000002",
  name: "Central Abuja",
  description: null,
  zone_type: "target" as const,
  area_sq_m: "1000000.00",
  geometry: {
    type: "Polygon",
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

function fakeMap(source?: { setData: ReturnType<typeof vi.fn> }) {
  return {
    addControl: vi.fn(),
    addLayer: vi.fn(),
    addSource: vi.fn(),
    fitBounds: vi.fn(),
    getCanvas: vi.fn(() => ({ style: { cursor: "" } })),
    getSource: vi.fn(() => source),
    on: vi.fn((event: string, layerOrHandler: string | (() => void), handler?: () => void) => {
      mapHandlers.set(event, typeof layerOrHandler === "function" ? layerOrHandler : handler!);
    }),
    remove: vi.fn(),
  };
}

function fakeDraw() {
  return {
    clear: vi.fn(),
    getSnapshot: vi.fn(() => []),
    on: vi.fn(),
    setMode: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
  };
}

describe("ZonesEditor MapLibre compatibility", () => {
  beforeEach(() => {
    mapHandlers.clear();
    mapConstructor.mockReset();
    navigationControl.mockReset();
    drawConstructor.mockReset();
    adapterConstructor.mockReset();
    deleteZoneAction.mockReset();
    deleteZoneAction.mockResolvedValue({});
  });

  it("initializes the v6 named exports and attaches TerraDraw after map load", () => {
    const map = fakeMap();
    const draw = fakeDraw();
    mapConstructor.mockImplementation(function () {
      return map;
    });
    drawConstructor.mockImplementation(function () {
      return draw;
    });

    render(<ZonesEditor campaignId={zone.campaign_id} zones={[zone]} />);

    expect(mapConstructor).toHaveBeenCalledOnce();
    expect(navigationControl).toHaveBeenCalledWith({ showCompass: false });
    expect(map.addControl).toHaveBeenCalledWith(navigationControl.mock.instances[0], "top-right");

    act(() => mapHandlers.get("load")?.());

    expect(adapterConstructor).toHaveBeenCalledWith({ map });
    expect(draw.start).toHaveBeenCalledOnce();
    expect(map.addSource).toHaveBeenCalledOnce();
    expect(map.addLayer).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId("zones-map")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Delete Central Abuja" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Delete Central Abuja?");
    fireEvent.click(screen.getByRole("button", { name: "Keep zone" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("updates an existing v6 GeoJSON source instead of replacing it", () => {
    const source = { setData: vi.fn() };
    const map = fakeMap(source);
    mapConstructor.mockImplementation(function () {
      return map;
    });
    drawConstructor.mockImplementation(function () {
      return fakeDraw();
    });

    render(<ZonesEditor campaignId={zone.campaign_id} zones={[zone]} />);
    act(() => mapHandlers.get("load")?.());

    expect(source.setData).toHaveBeenCalledOnce();
    expect(map.addSource).not.toHaveBeenCalled();
  });

  it("confirms deletion once and surfaces a refusal", async () => {
    deleteZoneAction.mockResolvedValue({ error: "Zone changed elsewhere" });
    const map = fakeMap();
    mapConstructor.mockImplementation(function () {
      return map;
    });
    drawConstructor.mockImplementation(function () {
      return fakeDraw();
    });

    render(<ZonesEditor campaignId={zone.campaign_id} zones={[zone]} />);
    act(() => mapHandlers.get("load")?.());

    fireEvent.click(screen.getByRole("button", { name: "Delete Central Abuja" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm deletion" }));

    await waitFor(() =>
      expect(deleteZoneAction).toHaveBeenCalledWith({
        campaignId: zone.campaign_id,
        zoneId: zone.id,
      }),
    );
    expect(deleteZoneAction).toHaveBeenCalledOnce();
    expect(await screen.findByRole("alert")).toHaveTextContent("Zone changed elsewhere");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });
});
