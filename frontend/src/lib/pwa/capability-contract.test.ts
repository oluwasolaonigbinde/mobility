import { describe, expect, it, vi } from "vitest";
import {
  D15_D16_PROTOCOL,
  R14A_SESSION_PROBE_PATH,
  assessPilotPwa,
  probeBffSession,
  probeExclusiveWebLock,
  probeForegroundLocation,
  probeScreenWakeLock,
  reconcileLocationPermission,
  type CapabilitySnapshot,
  type FetchLike,
  type WebLocksLike,
} from "./capability-contract";

const ready = (): CapabilitySnapshot => ({
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
});
const changed = (patch: Partial<CapabilitySnapshot>) => assessPilotPwa({ ...ready(), ...patch });
const result = (patch: Partial<CapabilitySnapshot>, id: string) =>
  changed(patch).results.find((item) => item.id === id);

describe("R14-A capability policy", () => {
  it("allows only the proven standalone foreground contract", () => {
    expect(assessPilotPwa(ready())).toMatchObject({
      health: "active",
      actions: { start: true, capture: true, end: true },
      blockingCodes: [],
    });
  });

  it.each([
    [{ secureContext: false }, "INSECURE_CONTEXT", "stopped"],
    [{ manifestLinked: false }, "MANIFEST_MISSING", "stopped"],
    [{ serviceWorker: "unavailable" }, "SERVICE_WORKER_UNAVAILABLE", "stopped"],
    [{ serviceWorker: "unprobed" }, "SERVICE_WORKER_UNPROBED", "degraded"],
    [{ serviceWorker: "not-registered" }, "SERVICE_WORKER_NOT_REGISTERED", "degraded"],
    [{ displayMode: "browser" }, "NOT_STANDALONE", "degraded"],
  ] satisfies Array<[Partial<CapabilitySnapshot>, string, string]>) (
    "maps installability %#",
    (patch, code, health) => {
      const assessment = changed(patch);
      expect(result(patch, "installability")?.code).toBe(code);
      expect(assessment.health).toBe(health);
      expect(assessment.actions.start).toBe(false);
      expect(assessment.actions.capture).toBe(false);
    },
  );

  it.each([
    ["unprobed", "degraded", "SCREEN_ON_UNPROBED"],
    ["released", "rejected", "WAKE_LOCK_RELEASED"],
    ["denied", "rejected", "WAKE_LOCK_DENIED"],
    ["unavailable", "rejected", "WAKE_LOCK_UNAVAILABLE"],
  ] as const)("maps screen wake lock %s", (wakeLock, status, code) => {
    expect(result({ wakeLock }, "screen-on")).toMatchObject({ status, code });
    expect(changed({ wakeLock }).actions).toEqual({ start: false, capture: false, end: true });
  });

  it("pauses hidden capture and rejects unknown visibility", () => {
    expect(result({ visibility: "hidden" }, "visibility-background")).toMatchObject({
      status: "degraded",
      code: "BACKGROUND_PAUSED",
    });
    expect(changed({ visibility: "hidden" }).actions).toEqual({ start: false, capture: false, end: true });
    expect(result({ visibility: "unknown" }, "visibility-background")?.code).toBe("VISIBILITY_UNKNOWN");
  });

  it.each([
    ["prompt", "degraded", "LOCATION_UNPROBED"],
    ["denied", "rejected", "LOCATION_DENIED"],
    ["revoked", "rejected", "LOCATION_REVOKED"],
    ["unavailable", "rejected", "LOCATION_UNAVAILABLE"],
  ] as const)("maps location %s", (location, status, code) => {
    expect(result({ location }, "location")).toMatchObject({ status, code });
    expect(changed({ location }).actions).toEqual({ start: false, capture: false, end: true });
  });

  it("continues durable foreground capture offline on an active trip but blocks Start and End", () => {
    expect(changed({ online: false, session: "offline", activeTrip: true })).toMatchObject({
      health: "active",
      actions: { start: false, capture: true, end: false },
    });
  });

  it("never authorizes offline capture or active health without an active trip", () => {
    // The probe page's exact shape: capability evidence only, no trip.
    expect(changed({ online: false, session: "offline" })).toMatchObject({
      actions: { start: false, capture: false, end: false },
    });
    expect(changed({ online: false, session: "offline" }).health).not.toBe("active");
    expect(changed({ session: "unavailable" }).actions.capture).toBe(false);
  });

  it.each([
    [{ indexedDb: "failed" }, "INDEXEDDB_FAILED"],
    [{ indexedDb: "unavailable" }, "INDEXEDDB_UNAVAILABLE"],
    [{ durableQueue: "failed" }, "DURABLE_QUEUE_FAILED"],
    [{ webLocks: "contended" }, "WEB_LOCK_CONTENDED"],
    [{ webLocks: "denied" }, "WEB_LOCK_DENIED"],
    [{ webLocks: "unavailable" }, "WEB_LOCKS_UNAVAILABLE"],
    [{ session: "invalid" }, "SESSION_INVALID"],
  ] satisfies Array<[Partial<CapabilitySnapshot>, string]>)("fails closed %#", (patch, code) => {
    const assessment = changed(patch);
    expect(assessment.blockingCodes).toContain(code);
    expect(assessment.actions).toEqual({ start: false, capture: false, end: false });
  });

  it.each(["unavailable", "offline"] as const)(
    "retains durable active-trip capture but not Start/End when session is %s",
    (session) => {
      expect(changed({ session, activeTrip: true })).toMatchObject({
        health: "active",
        actions: { start: false, capture: true, end: false },
      });
      expect(result({ session }, "bff-session")?.status).toBe("degraded");
    },
  );

  it("keeps background capture explicitly rejected without blocking foreground readiness", () => {
    const assessment = assessPilotPwa(ready());
    expect(result({}, "background-capture")).toMatchObject({
      status: "rejected",
      code: "BACKGROUND_CAPTURE_OUT_OF_SCOPE",
      blocking: false,
    });
    expect(assessment.health).toBe("active");
  });

  it("freezes the complete D15/D16 protocol", () => {
    expect(D15_D16_PROTOCOL).toEqual({
      version: "d25-trip-evidence-v2",
      auth: { boundary: "next-bff-http-only-cookie", browserBearerToken: false },
      queue: {
        storage: "indexeddb",
        singleWriter: "web-locks-exclusive",
        idempotencyKey: "mint-once-at-batch-cut",
        retry: "reuse-identical-key-and-payload",
        ackDeletes: ["signed-accepted", "signed-duplicate", "signed-quarantined"],
        terminalHttpStatuses: [400, 409, 422],
        terminalAction: "dead-letter-without-rekey",
      },
      watermark: {
        sealPredicate: "exact-signed-content-manifest-verified",
        clientPingCount: "manifest-content-bound",
        clientComplete: "claim-requires-exact-reconciliation",
      },
      lifecycle: ["active", "ended", "sealed"],
      lateData: {
        endedTrip: "accept-with-end-skew-bound",
        assignmentActiveGate: "not-required-for-ended-delivery",
        graceSeal: false,
      },
      quarantine: {
        postSealBatches: "preserve-never-reject",
        resolution: "audited-admin-apply-or-discard",
        applyRequiresInitialPayout: true,
        applyAutoRecomputesMoney: false,
        preSealAnalyticsReusableForMoney: false,
      },
    });
  });
});

describe("deterministic probes", () => {
  it("does not infer a usable fix from Permissions API grant", () => {
    expect(reconcileLocationPermission("unprobed", "granted")).toBe("unprobed");
    expect(reconcileLocationPermission("granted", "prompt")).toBe("revoked");
    expect(reconcileLocationPermission("granted", "denied")).toBe("revoked");
  });

  it("proves Web Locks exclusivity and classifies contention/denial/absence", async () => {
    let held = false;
    const locks: WebLocksLike = {
      request: async (_name, _options, callback) => {
        if (held) return callback(null);
        held = true;
        try {
          return await callback({});
        } finally {
          held = false;
        }
      },
    };
    expect(await probeExclusiveWebLock(locks)).toBe("pass");
    expect(await probeExclusiveWebLock({ request: async (_n, _o, cb) => cb(null) })).toBe("contended");
    expect(await probeExclusiveWebLock({ request: vi.fn().mockRejectedValue(new Error("no")) })).toBe("denied");
    expect(await probeExclusiveWebLock()).toBe("unavailable");
  });

  it("classifies wake-lock and foreground-location outcomes", async () => {
    const release = vi.fn().mockResolvedValue(undefined);
    expect(await probeScreenWakeLock({ request: vi.fn().mockResolvedValue({ release }) })).toBe("pass");
    expect(release).toHaveBeenCalledOnce();
    expect(await probeScreenWakeLock({ request: vi.fn().mockRejectedValue(new Error("no")) })).toBe("denied");
    expect(await probeScreenWakeLock()).toBe("unavailable");

    expect(await probeForegroundLocation({ getCurrentPosition: (ok) => ok({} as GeolocationPosition) })).toBe("granted");
    expect(await probeForegroundLocation({ getCurrentPosition: (_ok, fail) => fail({ code: 1 } as GeolocationPositionError) })).toBe("denied");
    expect(await probeForegroundLocation()).toBe("unavailable");
  });

  it.each([
    [true, { ok: true, status: 200, type: "basic" }, "valid"],
    [true, { ok: false, status: 401, type: "basic" }, "invalid"],
    [true, { ok: false, status: 307, type: "basic" }, "invalid"],
    [true, { ok: false, status: 0, type: "opaqueredirect" }, "invalid"],
    [true, { ok: false, status: 503, type: "basic" }, "unavailable"],
    [false, { ok: true, status: 200, type: "basic" }, "offline"],
  ] as const)("maps BFF session %#", async (online, response, expected) => {
    const fetcher = vi.fn().mockResolvedValue(response) as FetchLike;
    expect(await probeBffSession(fetcher, online)).toBe(expected);
    if (online) expect(fetcher).toHaveBeenCalledWith(R14A_SESSION_PROBE_PATH, expect.any(Object));
    else expect(fetcher).not.toHaveBeenCalled();
  });
});
