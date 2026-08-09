/**
 * Tracker failure modes (review findings 5–7): storage and cross-tab locking
 * fail CLOSED, and the end watermark never claims completeness the durable
 * queue cannot vouch for.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TripTracker } from "./trip-tracker";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

const actions = vi.hoisted(() => ({
  startTripAction: vi.fn(),
  endTripAction: vi.fn(),
  sendPingBatchAction: vi.fn(),
}));
vi.mock("@/app/driver/actions", () => actions);

const pingQueue = vi.hoisted(() => ({ openPingQueue: vi.fn() }));
vi.mock("@/lib/trips/ping-queue", () => pingQueue);

const TRIP_ID = "11111111-1111-4111-8111-111111111111";
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

beforeEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks(); // vi.fn call history survives restoreAllMocks
  actions.endTripAction.mockResolvedValue({ trip: undefined });
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

afterEach(() => {
  // jsdom has no navigator.locks by default; remove any per-test grant.
  delete (navigator as { locks?: unknown }).locks;
});

describe("storage fail-closed (finding 5)", () => {
  it("blocks starting a trip when IndexedDB cannot open", async () => {
    pingQueue.openPingQueue.mockRejectedValue(new Error("idb unavailable"));
    render(<TripTracker assignment={ASSIGNMENT} initialTrip={null} />);

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/Offline storage is unavailable/),
    );
    expect(screen.getByRole("button", { name: /Start trip/ })).toBeDisabled();
  });

  it("disables ending when storage failed with an active trip (no false completeness)", async () => {
    pingQueue.openPingQueue.mockRejectedValue(new Error("idb unavailable"));
    grantWebLock();
    render(<TripTracker assignment={null} initialTrip={TRIP} />);

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/Offline storage is unavailable/),
    );
    // Storage never became ready -> the lock is never acquired -> fail closed.
    expect(screen.getByRole("button", { name: /End trip/ })).toBeDisabled();
    expect(actions.endTripAction).not.toHaveBeenCalled();
  });
});

describe("single-writer lock fail-closed (finding 6)", () => {
  it("without Web Locks support: warns and disables End", async () => {
    pingQueue.openPingQueue.mockResolvedValue(fakeQueue());
    render(<TripTracker assignment={null} initialTrip={TRIP} />);

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/can't guarantee single-tab/),
    );
    expect(screen.getByText(/tracked in another tab/)).toBeInTheDocument();
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
    render(<TripTracker assignment={null} initialTrip={TRIP} />);

    await waitFor(() =>
      expect(screen.getByText(/tracked in another tab/)).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /End trip/ })).toBeDisabled();
  });
});

describe("end watermark honesty (finding 5)", () => {
  it("reports complete only when the queue is drained", async () => {
    pingQueue.openPingQueue.mockResolvedValue(fakeQueue());
    grantWebLock();
    render(<TripTracker assignment={null} initialTrip={TRIP} />);

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
    render(<TripTracker assignment={null} initialTrip={TRIP} />);

    const endButton = screen.getByRole("button", { name: /End trip/ });
    await waitFor(() => expect(endButton).toBeEnabled());
    await userEvent.click(endButton);

    await waitFor(() => expect(actions.endTripAction).toHaveBeenCalledTimes(1));
    expect(actions.endTripAction).toHaveBeenCalledWith(TRIP_ID, {
      clientBatchCount: 2,
      clientPingCount: 3,
      clientComplete: false,
    });
    expect(window.confirm).toHaveBeenCalledWith(expect.stringMatching(/may not be synced/));
  });
});

describe("stranded-data recovery (finding 7)", () => {
  it("drains leftover trips on mount, on a timer, and on reconnect", async () => {
    vi.useFakeTimers();
    try {
      const leftovers = vi.fn().mockResolvedValue(["99999999-9999-4999-8999-999999999999"]);
      const queue = fakeQueue({
        tripsWithLeftovers: leftovers,
        unsyncedCount: vi.fn().mockResolvedValue(1), // never fully drains
        listBatches: vi.fn().mockResolvedValue([]),
      });
      pingQueue.openPingQueue.mockResolvedValue(queue);
      render(<TripTracker assignment={ASSIGNMENT} initialTrip={null} />);

      await vi.waitFor(() => expect(leftovers).toHaveBeenCalledTimes(1));
      await vi.advanceTimersByTimeAsync(61_000);
      expect(leftovers.mock.calls.length).toBeGreaterThanOrEqual(2);

      const before = leftovers.mock.calls.length;
      window.dispatchEvent(new Event("online"));
      await vi.waitFor(() => expect(leftovers.mock.calls.length).toBeGreaterThan(before));
    } finally {
      vi.useRealTimers();
    }
  });
});
