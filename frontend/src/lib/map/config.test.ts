import { afterEach, describe, expect, it, vi } from "vitest";
import { activeMapStyle, basemapMode } from "./config";

describe("provider-neutral map configuration", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("uses the configured provider style when supplied at build time", () => {
    const configuredStyle = "https://maps.example.test/styles/release.json";
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
