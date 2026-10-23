import { afterEach, describe, expect, it, vi } from "vitest";
const workerURL = vi.hoisted(() => vi.fn());
vi.mock("maplibre-gl", () => ({ setWorkerUrl: workerURL }));
import { activeMapStyle, basemapMode, MAP_WORKER_URL } from "./config";
import mapLibrePackage from "maplibre-gl/package.json";

describe("provider-neutral map configuration", () => {
  it("configures the installed package worker before either map is constructed", () => {
    expect(workerURL).toHaveBeenCalledWith(MAP_WORKER_URL);
    expect(MAP_WORKER_URL).toBe(`/maplibre/${mapLibrePackage.version}/maplibre-gl-worker.mjs`);
    expect(MAP_WORKER_URL).not.toMatch(/cdn|unpkg|jsdelivr/);
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("uses the configured provider style when supplied at build time", () => {
    const configuredStyle = "https://api.maptiler.com/maps/streets-v4/style.json?key=synthetic";
    vi.stubEnv("NEXT_PUBLIC_MAP_STYLE_URL", configuredStyle);

    expect(activeMapStyle()).toBe(configuredStyle);
    expect(basemapMode()).toBe("configured-provider");
  });

  it("uses a local schematic style with no tile network request by default", () => {
    vi.stubEnv("NEXT_PUBLIC_MAP_STYLE_URL", "");

    const style = activeMapStyle();
    expect(typeof style).toBe("object");
    expect(JSON.stringify(style)).not.toMatch(/https?:\/\//i);
    expect(basemapMode()).toBe("local");
  });
});
