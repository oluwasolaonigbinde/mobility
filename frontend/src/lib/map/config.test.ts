import { describe, expect, it } from "vitest";
import { activeMapStyle, basemapMode } from "./config";

describe("provider-neutral map configuration", () => {
  it("uses a local schematic style with no tile network request by default", () => {
    const style = activeMapStyle();
    expect(typeof style).toBe("object");
    expect(JSON.stringify(style)).not.toMatch(/https?:\/\//i);
    expect(basemapMode()).toBe("local");
  });
});
