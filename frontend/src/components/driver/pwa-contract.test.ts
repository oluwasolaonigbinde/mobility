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

  it("keeps authenticated traffic network-only and deletes only Cardvert-prefixed caches", () => {
    const source = readFileSync(join(process.cwd(), "public/driver-sw.js"), "utf8");
    expect(source).toContain('const CACHE_PREFIX = "cardvert-driver-"');
    expect(source).toContain("key.startsWith(CACHE_PREFIX)");
    expect(source).not.toMatch(/filter\(\(k\) => k !== STATIC_CACHE/);
    expect(source).toContain('event.request.mode === "navigate"');
    expect(source).not.toMatch(/caches\.open\([^)]*\).*\/api\//s);
    expect(source).toContain("This offline page is not tracking your location");
  });
});
