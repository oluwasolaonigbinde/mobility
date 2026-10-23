import { expect, it } from "vitest";
import { isScanEvent } from "./privacy";
it("excludes public scans from error telemetry even with queries or framework route names", () => {
  expect(isScanEvent({ request: { url: "https://cardvert.example/q/random?email=private" } })).toBe(
    true,
  );
  expect(isScanEvent({ transaction: "GET /q/[code]/route" })).toBe(true);
  expect(isScanEvent({ request: { url: "https://cardvert.example/advertiser" } })).toBe(false);
});
