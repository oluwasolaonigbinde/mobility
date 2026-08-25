/**
 * Tracker failure modes (review findings 5–7): storage and cross-tab locking
 * fail CLOSED, and the end watermark never claims completeness the durable
 * queue cannot vouch for.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TripTracker } from "./trip-tracker";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

const actions = vi.hoisted(() => ({
  startTripAction: vi.fn(),
  getCurrentTripAction: vi.fn(),
  endTripAction: vi.fn(),
  sendPingBatchAction: vi.fn(),
  verifyDriverTripOwnershipAction: vi.fn(),
}));
vi.mock("@/app/driver/actions", () => actions);

const pingQueue = vi.hoisted(() => ({ openPingQueue: vi.fn() }));
vi.mock("@/lib/trips/ping-queue", () => pingQueue);

const TRIP_ID = "11111111-1111-4111-8111-111111111111";
const DRIVER_ID = "33333333-3333-4333-8333-333333333333";
const TRIP = {
  id: TRIP_ID,
  status: "active",
  started_at: new Date().toISOString(),
} as never;

const ASSIGNMENT = {
  id: "22222222-2222-4222-8222-222222222222",
  campaign: { name: "Test Campaign" },
  vehicle: { plate_number: "TST-001" },
} as never;

function fakeQueue(overrides: Record<string, unknown> = {}) {
  return {
    addPing: vi.fn().mockResolvedValue({ sequence_number: 0 }),
    cutBatch: vi.fn().mockResolvedValue(null),
    listBatches: vi.fn().mockResolvedValue([]),
    listDeadLetters: vi.fn().mockResolvedValue([]),
    deadLetterCount: vi.fn().mockResolvedValue(0),
    ackBatch: vi.fn().mockResolvedValue(undefined),
    dropBatch: vi.fn().mockResolvedValue(undefined),
    recordAttempt: vi.fn().mockResolvedValue(undefined),
    pendingCount: vi.fn().mockResolvedValue(0),
    unsyncedCount: vi.fn().mockResolvedValue(0),
    meta: vi
      .fn()
      .mockResolvedValue({ tripId: TRIP_ID, nextSeq: 3, batchesCut: 2, pingsRecorded: 3 }),
    tripsWithLeftovers: vi.fn().mockResolvedValue([]),
    forgetTrip: vi.fn().mockResolvedValue(undefined),
    close: vi.fn(),
    ...overrides,
  };
}

function grantWebLock() {
  Object.defineProperty(navigator, "locks", {
    configurable: true,
    value: {
      request: (_name: string, _opts: unknown, cb: (lock: object | null) => unknown) => {
        void cb({});
        return new Promise(() => undefined); // held for component lifetime
      },
    },
  });
}

function installRuntime(overrides: { fetchStatus?: number } = {}) {
  const release = vi.fn().mockResolvedValue(undefined);
  const sentinel = Object.assign(new EventTarget(), { release, released: false });
  const watchPosition = vi.fn().mockReturnValue(1);
  const clearWatch = vi.fn();
  Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi
      .fn()
      .mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
  });
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: { getRegistration: vi.fn().mockResolvedValue({ scope: "/driver/" }) },
  });
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: {
      getCurrentPosition: vi.fn((success: PositionCallback) => success({} as GeolocationPosition)),
      watchPosition,
      clearWatch,
    },
  });
  Object.defineProperty(navigator, "wakeLock", {
    configurable: true,
    value: { request: vi.fn().mockResolvedValue(sentinel) },
  });
  const manifest = document.createElement("link");
  manifest.rel = "manifest";
  manifest.href = "/driver/manifest.webmanifest";
  manifest.dataset.testManifest = "true";
  document.head.append(manifest);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: (overrides.fetchStatus ?? 200) === 200,
      status: overrides.fetchStatus ?? 200,
      type: "basic",
      json: vi.fn().mockResolvedValue({ status: "valid", driverId: DRIVER_ID }),
    }),
  );
  grantWebLock();
  return { sentinel, release, watchPosition, clearWatch };
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks(); // vi.fn call history survives restoreAllMocks
  actions.endTripAction.mockResolvedValue({ trip: undefined });
  actions.startTripAction.mockResolvedValue({ trip: TRIP, outcome: "started" });
  actions.getCurrentTripAction.mockResolvedValue({ trip: TRIP, outcome: "started" });
  actions.sendPingBatchAction.mockResolvedValue({});
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

afterEach(() => {
  // jsdom has no navigator.locks by default; remove any per-test grant.
  delete (navigator as { locks?: unknown }).locks;
  delete (navigator as { geolocation?: unknown }).geolocation;
  delete (navigator as { wakeLock?: unknown }).wakeLock;
  delete (navigator as { serviceWorker?: unknown }).serviceWorker;
  vi.unstubAllGlobals();
  document.querySelectorAll('[data-test-manifest="true"]').forEach((element) => element.remove());
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: "visible",
  });
});

describe("assignment activation authority", () => {
  it("tells the driver to wait for admin activation", () => {
    pingQueue.openPingQueue.mockResolvedValue(fakeQueue());
    render(<TripTracker assignment={null} initialTrip={null} driverId={DRIVER_ID} />);

    expect(screen.getByText(/wait for admin activation/i)).toBeInTheDocument();
    expect(screen.queryByText(/accept and activate/i)).not.toBeInTheDocument();
  });
});

describe("storage fail-closed (finding 5)", () => {
  it("blocks starting a trip when IndexedDB cannot open", async () => {
    pingQueue.openPingQueue.mockRejectedValue(new Error("idb unavailable"));
    render(<TripTracker assignment={ASSIGNMENT} initialTrip={null} driverId={DRIVER_ID} />);

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/offline storage is unavailable/i),
    );
    expect(screen.getByRole("button", { name: /Start trip/ })).toBeDisabled();
  });

  it("disables ending when storage failed with an active trip (no false completeness)", async () => {
    pingQueue.openPingQueue.mockRejectedValue(new Error("idb unavailable"));
    grantWebLock();
    render(<TripTracker assignment={null} initialTrip={TRIP} driverId={DRIVER_ID} />);

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/offline storage is unavailable/i),
    );
    // Storage never became ready -> the lock is never acquired -> fail closed.
    expect(screen.getByRole("button", { name: /End trip/ })).toBeDisabled();
    expect(actions.endTripAction).not.toHaveBeenCalled();
  });
});

describe("single-writer lock fail-closed (finding 6)", () => {
  it("never calls Start before the exclusive writer lock is acquired", async () => {
    pingQueue.openPingQueue.mockResolvedValue(fakeQueue());
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: {
        request: vi.fn(() => new Promise(() => undefined)),
      },
    });
    render(<TripTracker assignment={ASSIGNMENT} initialTrip={null} driverId={DRIVER_ID} />);

    const startButton = await screen.findByRole("button", { name: /Start trip/ });
    expect(startButton).toBeEnabled();
    await userEvent.click(startButton);

    expect(actions.startTripAction).not.toHaveBeenCalled();
  });

  it("calls Start only after the writer lock and every live prerequisite are held", async () => {
    const order: string[] = [];
    pingQueue.openPingQueue.mockResolvedValue(fakeQueue());
    installRuntime();
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: {
        request: (_name: string, _options: unknown, callback: (lock: object) => Promise<void>) => {
          order.push("lock");
          return callback({});
        },
      },
    });
    actions.startTripAction.mockImplementation(async () => {
      order.push("start");
      return { trip: TRIP, outcome: "started" };
    });
    render(<TripTracker assignment={ASSIGNMENT} initialTrip={null} driverId={DRIVER_ID} />);

    await userEvent.click(await screen.findByRole("button", { name: /Start trip/ }));
    await waitFor(() => expect(actions.startTripAction).toHaveBeenCalledTimes(1));
    expect(order.slice(0, 2)).toEqual(["lock", "start"]);
  });

  it("reconciles an unknown Start response while retaining the acquired writer", async () => {
    pingQueue.openPingQueue.mockResolvedValue(fakeQueue());
    installRuntime();
    actions.startTripAction.mockResolvedValue({ error: "response lost", outcome: "unknown" });
    actions.getCurrentTripAction.mockResolvedValue({ trip: TRIP, outcome: "started" });
    render(<TripTracker assignment={ASSIGNMENT} initialTrip={null} driverId={DRIVER_ID} />);

    await userEvent.click(await screen.findByRole("button", { name: /Start trip/ }));
    await waitFor(() => expect(actions.getCurrentTripAction).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: /Ending|End trip/ })).toBeInTheDocument();
    expect(screen.getByTestId("tracking-health")).toHaveTextContent("active");
    expect(actions.startTripAction).toHaveBeenCalledTimes(1);
  });

  it("retries only reconciliation after Start remains unknown", async () => {
    pingQueue.openPingQueue.mockResolvedValue(fakeQueue());
    installRuntime();
    actions.startTripAction.mockResolvedValue({ error: "response lost", outcome: "unknown" });
    actions.getCurrentTripAction.mockResolvedValue({
      error: "authority unavailable",
      outcome: "unknown",
    });
    render(<TripTracker assignment={ASSIGNMENT} initialTrip={null} driverId={DRIVER_ID} />);

    await userEvent.click(await screen.findByRole("button", { name: /Start trip/ }));
    const reconcile = await screen.findByRole("button", { name: /Reconcile trip/ });
    await userEvent.click(reconcile);

    await waitFor(() => expect(actions.getCurrentTripAction).toHaveBeenCalledTimes(2));
    expect(actions.startTripAction).toHaveBeenCalledTimes(1);
  });

  it("reacquires the writer before reconciling an active trip after reload", async () => {
    const order: string[] = [];
    pingQueue.openPingQueue.mockResolvedValue(fakeQueue());
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: {
        request: (_name: string, _options: unknown, callback: (lock: object) => Promise<void>) => {
          order.push("lock");
          return callback({});
        },
      },
    });
    actions.getCurrentTripAction.mockImplementation(async () => {
      order.push("reconcile");
      return { trip: TRIP, outcome: "started" };
    });

    render(<TripTracker assignment={null} initialTrip={TRIP} driverId={DRIVER_ID} />);

    await waitFor(() => expect(actions.getCurrentTripAction).toHaveBeenCalled());
    expect(order.slice(0, 2)).toEqual(["lock", "reconcile"]);
  });

  it("without Web Locks support: warns and disables End", async () => {
    pingQueue.openPingQueue.mockResolvedValue(fakeQueue());
    render(<TripTracker assignment={null} initialTrip={TRIP} driverId={DRIVER_ID} />);

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/exclusive tracking lock/),
    );
    expect(screen.getByTestId("tracking-health")).toHaveTextContent("stopped");
    expect(screen.getByRole("button", { name: /End trip/ })).toBeDisabled();
  });

  it("when another tab holds the lock: warns and disables End", async () => {
    pingQueue.openPingQueue.mockResolvedValue(fakeQueue());
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: {
        request: (_n: string, _o: unknown, cb: (lock: object | null) => unknown) =>
          Promise.resolve(cb(null)), // ifAvailable miss
      },
    });
    render(<TripTracker assignment={null} initialTrip={TRIP} driverId={DRIVER_ID} />);

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/another Cardvert tab/),
    );
    expect(screen.getByRole("button", { name: /End trip/ })).toBeDisabled();
  });
});

describe("live runtime truth", () => {
  it("does not claim active health without a currently held wake lock", async () => {
    pingQueue.openPingQueue.mockResolvedValue(fakeQueue());
    grantWebLock();
    render(<TripTracker assignment={null} initialTrip={TRIP} driverId={DRIVER_ID} />);

    await waitFor(() => expect(screen.getByTestId("tracking-health")).toHaveTextContent("stopped"));
    expect(screen.queryByText(/Tracking live/i)).not.toBeInTheDocument();
  });

  it("does not capture while the document is hidden", async () => {
    const watchPosition = vi.fn().mockReturnValue(1);
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "hidden",
    });
    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: { watchPosition, clearWatch: vi.fn() },
    });
    pingQueue.openPingQueue.mockResolvedValue(fakeQueue());
    grantWebLock();
    render(<TripTracker assignment={null} initialTrip={TRIP} driverId={DRIVER_ID} />);

    await waitFor(() => expect(screen.getByRole("button", { name: /End trip/ })).toBeEnabled());
    expect(watchPosition).not.toHaveBeenCalled();
  });

  it("stops capture synchronously when visibility is lost", async () => {
    const runtime = installRuntime();
    pingQueue.openPingQueue.mockResolvedValue(fakeQueue());
    render(<TripTracker assignment={null} initialTrip={TRIP} driverId={DRIVER_ID} />);
    await waitFor(() => expect(runtime.watchPosition).toHaveBeenCalledTimes(1));

    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    document.dispatchEvent(new Event("visibilitychange"));

    await waitFor(() => expect(runtime.clearWatch).toHaveBeenCalledWith(1));
    expect(screen.getByTestId("tracking-health")).not.toHaveTextContent("active");
  });

  it("stops capture when the held wake sentinel releases", async () => {
    const runtime = installRuntime();
    pingQueue.openPingQueue.mockResolvedValue(fakeQueue());
    render(<TripTracker assignment={null} initialTrip={TRIP} driverId={DRIVER_ID} />);
    await waitFor(() => expect(runtime.watchPosition).toHaveBeenCalledTimes(1));

    runtime.sentinel.dispatchEvent(new Event("release"));

    await waitFor(() => expect(runtime.clearWatch).toHaveBeenCalledWith(1));
    expect(screen.getByTestId("tracking-health")).toHaveTextContent("stopped");
  });

  it("closes driver-scoped storage and disables End on revoked keepalive", async () => {
    const runtime = installRuntime();
    let writerReleased = false;
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: {
        request: async (_name: string, _options: unknown, callback: (lock: object) => unknown) => {
          await callback({});
          writerReleased = true;
        },
      },
    });
    const queue = fakeQueue();
    pingQueue.openPingQueue.mockResolvedValue(queue);
    render(<TripTracker assignment={null} initialTrip={TRIP} driverId={DRIVER_ID} />);
    await waitFor(() => expect(runtime.watchPosition).toHaveBeenCalledTimes(1));
    vi.mocked(fetch).mockResolvedValue({ ok: false, status: 401, type: "basic" } as Response);

    window.dispatchEvent(new Event("online"));

    await waitFor(() => expect(queue.close).toHaveBeenCalled());
    await waitFor(() => expect(writerReleased).toBe(true));
    expect(screen.getByRole("button", { name: /End trip/ })).toBeDisabled();
  });
});

describe("end watermark honesty (finding 5)", () => {
  it("reports complete only when the queue is drained", async () => {
    pingQueue.openPingQueue.mockResolvedValue(fakeQueue());
    grantWebLock();
    render(<TripTracker assignment={null} initialTrip={TRIP} driverId={DRIVER_ID} />);

    const endButton = screen.getByRole("button", { name: /End trip/ });
    await waitFor(() => expect(endButton).toBeEnabled());
    await userEvent.click(endButton);

    await waitFor(() => expect(actions.endTripAction).toHaveBeenCalledTimes(1));
    expect(actions.endTripAction).toHaveBeenCalledWith(TRIP_ID, {
      clientBatchCount: 2,
      clientPingCount: 3,
      clientComplete: true,
    });
  });

  it("reports incomplete when unsynced data remains after the final drain", async () => {
    pingQueue.openPingQueue.mockResolvedValue(
      fakeQueue({ unsyncedCount: vi.fn().mockResolvedValue(2) }),
    );
    grantWebLock();
    render(<TripTracker assignment={null} initialTrip={TRIP} driverId={DRIVER_ID} />);

    const endButton = screen.getByRole("button", { name: /End trip/ });
    await waitFor(() => expect(endButton).toBeEnabled());
    await userEvent.click(endButton);

    await waitFor(() => expect(actions.endTripAction).toHaveBeenCalledTimes(1));
    expect(actions.endTripAction).toHaveBeenCalledWith(TRIP_ID, {
      clientBatchCount: 2,
      clientPingCount: 3,
      clientComplete: false,
    });
    expect(window.confirm).toHaveBeenCalledWith(expect.stringMatching(/unsynced/));
  });

  it("forces clientComplete false when diagnostic dead letters remain", async () => {
    pingQueue.openPingQueue.mockResolvedValue(
      fakeQueue({
        deadLetterCount: vi.fn().mockResolvedValue(1),
        listDeadLetters: vi.fn().mockResolvedValue([{ pings: [{ sequence_number: 0 }] }]),
      }),
    );
    grantWebLock();
    render(<TripTracker assignment={null} initialTrip={TRIP} driverId={DRIVER_ID} />);
    const endButton = screen.getByRole("button", { name: /End trip/ });
    await waitFor(() => expect(endButton).toBeEnabled());
    await userEvent.click(endButton);

    await waitFor(() => expect(actions.endTripAction).toHaveBeenCalledTimes(1));
    expect(actions.endTripAction).toHaveBeenCalledWith(
      TRIP_ID,
      expect.objectContaining({ clientComplete: false }),
    );
  });
});

describe("stranded-data recovery (finding 7)", () => {
  it("drains leftover trips on mount, on a timer, and on reconnect", async () => {
    vi.useFakeTimers();
    try {
      const order: string[] = [];
      const leftovers = vi.fn().mockResolvedValue(["99999999-9999-4999-8999-999999999999"]);
      const queue = fakeQueue({
        tripsWithLeftovers: leftovers,
        unsyncedCount: vi.fn().mockResolvedValue(1), // never fully drains
        listBatches: vi.fn().mockImplementation(async () => {
          order.push("recover");
          return [];
        }),
      });
      pingQueue.openPingQueue.mockResolvedValue(queue);
      Object.defineProperty(navigator, "locks", {
        configurable: true,
        value: {
          request: async (
            _name: string,
            _options: unknown,
            callback: (lock: object) => unknown,
          ) => {
            order.push("lock");
            await callback({});
          },
        },
      });
      render(<TripTracker assignment={ASSIGNMENT} initialTrip={null} driverId={DRIVER_ID} />);

      await vi.waitFor(() => expect(leftovers).toHaveBeenCalled());
      await vi.waitFor(() => expect(order.slice(0, 2)).toEqual(["lock", "recover"]));
      const afterMount = leftovers.mock.calls.length;
      await act(() => vi.advanceTimersByTimeAsync(61_000));
      expect(leftovers.mock.calls.length).toBeGreaterThan(afterMount);

      const before = leftovers.mock.calls.length;
      act(() => window.dispatchEvent(new Event("online")));
      await vi.waitFor(() => expect(leftovers.mock.calls.length).toBeGreaterThan(before));
    } finally {
      vi.useRealTimers();
    }
  });
});
