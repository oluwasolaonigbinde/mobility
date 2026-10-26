import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { GET } from "@/app/driver/manifest.webmanifest/route";

describe("Cardvert driver install/update contract", () => {
  it("publishes the public Cardvert standalone manifest at driver scope", async () => {
    const response = GET();
    const manifest = await response.json();
    expect(manifest).toMatchObject({
      name: "Cardvert Driver",
      id: "/driver",
      start_url: "/driver",
      scope: "/driver",
      display: "standalone",
    });
    expect(response.headers.get("content-type")).toContain("application/manifest+json");
  });

  it.each([
    ["driver-180.png", 180],
    ["driver-192.png", 192],
    ["driver-512.png", 512],
  ])("ships the declared %s icon at its real square size", (file, expectedSize) => {
    const png = readFileSync(join(process.cwd(), "public/icons", file));
    expect(png.subarray(1, 4).toString()).toBe("PNG");
    expect(png.readUInt32BE(16)).toBe(expectedSize);
    expect(png.readUInt32BE(20)).toBe(expectedSize);
  });
});
