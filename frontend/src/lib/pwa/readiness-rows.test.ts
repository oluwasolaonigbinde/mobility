import { describe, expect, it } from "vitest";
import { assessPilotPwa, type CapabilitySnapshot } from "./capability-contract";
import { readinessRows } from "./readiness-rows";

const ready: CapabilitySnapshot = {
  secureContext: true,
  manifestLinked: true,
  serviceWorker: "registered",
  displayMode: "standalone",
  visibility: "visible",
  online: true,
  location: "granted",
  indexedDb: "pass",
  durableQueue: "pass",
  webLocks: "pass",
  wakeLock: "pass",
  session: "valid",
  activeTrip: false,
};

const variants: { [K in keyof CapabilitySnapshot]: CapabilitySnapshot[K][] } = {
  secureContext: [true, false],
  manifestLinked: [true, false],
  serviceWorker: ["registered", "not-registered", "unavailable", "unprobed"],
  displayMode: ["standalone", "browser", "unknown"],
  visibility: ["visible", "hidden", "unknown"],
  online: [true, false],
  location: ["granted", "prompt", "denied", "revoked", "unavailable", "unprobed"],
  indexedDb: ["pass", "failed", "unavailable", "unprobed"],
  durableQueue: ["pass", "failed", "unprobed"],
  webLocks: ["pass", "contended", "denied", "unavailable", "unprobed"],
  wakeLock: ["pass", "released", "denied", "unavailable", "unprobed"],
  session: ["valid", "invalid", "unavailable", "offline", "unprobed"],
  activeTrip: [false, true],
};

describe("readinessRows", () => {
  it("reports every row ok when Start is allowed", () => {
    expect(assessPilotPwa(ready).actions.start).toBe(true);
    expect(readinessRows(ready).every((row) => row.ok)).toBe(true);
  });

  it("names at least one failing row for every single-field reason Start is blocked", () => {
    for (const key of Object.keys(variants) as (keyof CapabilitySnapshot)[]) {
      for (const value of variants[key]) {
        const snapshot = { ...ready, [key]: value } as CapabilitySnapshot;
        const start = assessPilotPwa(snapshot).actions.start;
        const failing = readinessRows(snapshot).filter((row) => !row.ok);
        expect(failing.length === 0, `${key}=${String(value)}`).toBe(start);
      }
    }
  });

  it("identifies the missing requirements and remedies when several checks fail", () => {
    const snapshot: CapabilitySnapshot = {
      ...ready,
      online: false,
      location: "denied",
      webLocks: "contended",
    };
    expect(assessPilotPwa(snapshot).actions.start).toBe(false);
    const failures = readinessRows(snapshot).filter((row) => !row.ok);
    expect(failures.map((row) => row.label)).toEqual([
      "Location is allowed",
      "Trips can be saved on this phone",
      "You're online",
    ]);
    expect(failures[0]?.fix).toMatch(/Allow location/);
    expect(failures[1]?.fix).toMatch(/Close other Cardvert tabs/);
    expect(failures[2]?.fix).toMatch(/mobile data or Wi-Fi/);
  });
});
