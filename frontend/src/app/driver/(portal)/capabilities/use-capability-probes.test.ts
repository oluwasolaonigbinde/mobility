import "fake-indexeddb/auto";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useCapabilityProbes } from "./use-capability-probes";

type Nav = Navigator & Record<string, unknown>;

function define(target: object, key: string, value: unknown) {
  Object.defineProperty(target, key, { configurable: true, value });
}

let locationCalls = 0;
let permissionListener: (() => void) | undefined;
let permissionState: PermissionState = "prompt";

beforeEach(() => {
  locationCalls = 0;
  permissionState = "prompt";
  define(window, "matchMedia", () => ({ matches: false }));
  define(navigator, "serviceWorker", { getRegistration: async () => ({}) });
  define(navigator, "permissions", {
    query: async () => ({
      get state() {
        return permissionState;
      },
      addEventListener: (_: string, listener: () => void) => (permissionListener = listener),
      removeEventListener: () => undefined,
    }),
  });
  let held = false;
  define(navigator, "locks", {
    request: async (
      _name: string,
      _options: unknown,
      callback: (lock: object | null) => unknown,
    ) => {
      if (held) return callback(null);
      held = true;
      try {
        return await callback({});
      } finally {
        held = false;
      }
    },
  });
  define(navigator, "wakeLock", { request: async () => ({ release: async () => undefined }) });
  define(navigator, "geolocation", {
    getCurrentPosition: (success: PositionCallback) => {
      locationCalls += 1;
      success({ coords: { latitude: 6.5, longitude: 3.4 } } as GeolocationPosition);
    },
  });
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response("ok", { status: 200 }) as unknown as Response,
  );
});

afterEach(() => vi.restoreAllMocks());

describe("useCapabilityProbes", () => {
  it("observes passively without asking for location, then checks everything on one press", async () => {
    const { result } = renderHook(() => useCapabilityProbes());
    await waitFor(() => expect(result.current.passiveReady).toBe(true));
    expect(result.current.snapshot.serviceWorker).toBe("registered");
    expect(result.current.snapshot.displayMode).toBe("browser");
    expect(locationCalls).toBe(0);

    await act(async () => {
      await result.current.checkAll();
    });

    expect(locationCalls).toBe(1);
    expect(result.current.notice).toBe("Phone check finished.");
    expect(result.current.snapshot).toMatchObject({
      indexedDb: "pass",
      durableQueue: "pass",
      webLocks: "pass",
      wakeLock: "pass",
      session: "valid",
      location: "granted",
    });
    // The copied report is redacted: no coordinates or synthetic trip identity.
    expect(result.current.report).not.toMatch(/6\.5|3\.4|latitude|r14-a-synthetic-probe/);
    expect(JSON.parse(result.current.report).contractVersion).toBe("r14-a-v2");
  });

  it("reports each support probe outcome, including refusals", async () => {
    define(navigator, "wakeLock", { request: async () => Promise.reject(new Error("denied")) });
    define(navigator, "geolocation", {
      getCurrentPosition: (_: PositionCallback, error: PositionErrorCallback) =>
        error({ code: 1 } as GeolocationPositionError),
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("", { status: 401 }) as unknown as Response,
    );
    const { result } = renderHook(() => useCapabilityProbes());
    await waitFor(() => expect(result.current.passiveReady).toBe(true));

    await act(async () => result.current.probeLocks());
    expect(result.current.notice).toBe("Web Locks probe passed.");
    await act(async () => result.current.probeWake());
    expect(result.current.notice).toBe("Screen Wake Lock probe returned denied.");
    await act(async () => result.current.probeSession());
    expect(result.current.notice).toBe("BFF session probe returned invalid.");
    await act(async () => result.current.probeLocation());
    expect(result.current.notice).toMatch(/returned denied; the position was discarded/);
    await act(async () => result.current.probeQueue());
    expect(result.current.notice).toMatch(/Durable queue probe passed/);
    expect(result.current.busy).toBeNull();

    // A granted location that is later revoked in settings is reconciled.
    define(navigator, "geolocation", {
      getCurrentPosition: (success: PositionCallback) =>
        success({ coords: { latitude: 0, longitude: 0 } } as GeolocationPosition),
    });
    await act(async () => result.current.probeLocation());
    permissionState = "denied";
    act(() => permissionListener?.());
    expect(result.current.snapshot.location).toBe("revoked");
  });

  it("fails closed when storage or the lock API is unavailable", async () => {
    const nav = navigator as Nav;
    const { indexedDB: realIndexedDb } = window;
    define(nav, "locks", undefined);
    // @ts-expect-error simulate a browser without IndexedDB
    delete window.indexedDB;
    try {
      const { result } = renderHook(() => useCapabilityProbes());
      await waitFor(() => expect(result.current.passiveReady).toBe(true));
      await act(async () => result.current.probeQueue());
      expect(result.current.notice).toBe("IndexedDB is unavailable.");
      expect(result.current.snapshot.durableQueue).toBe("failed");
      await act(async () => result.current.probeLocks());
      expect(result.current.snapshot.webLocks).toBe("unavailable");
    } finally {
      define(window, "indexedDB", realIndexedDb);
    }
  });
});
