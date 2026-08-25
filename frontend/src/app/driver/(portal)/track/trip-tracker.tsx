"use client";

import { useCallback, useEffect, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import type { components } from "@/lib/api/schema";
import { startTripAction, endTripAction, sendPingBatchAction } from "@/app/driver/actions";
import { openPingQueue, type PingQueue } from "@/lib/trips/ping-queue";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";

type Assignment = components["schemas"]["CampaignAssignmentRead"];
type Trip = components["schemas"]["TripRead"];

const FLUSH_INTERVAL_MS = 15_000;
const FLUSH_AT_COUNT = 20;
const MAX_BATCH_PINGS = 40;
const KEEPALIVE_INTERVAL_MS = 10 * 60_000;
/** How often stranded (previous-session) data is re-attempted. */
const RECOVERY_INTERVAL_MS = 60_000;
/** Web Locks single-writer guard: two tabs must never both cut batches. */
const TRACKING_LOCK = "vantage-trip-tracking";

type GpsState = "idle" | "granted" | "denied" | "unavailable";

/**
 * Foreground trip tracking via the Geolocation API.
 *
 * Honest limitation, documented for the client: a web app (even installed
 * as a PWA) can only track while it is open and on-screen. Background GPS
 * is the future native app's job — the backend contract is identical.
 *
 * Durability (RM4/RM5): every GPS fix is persisted to IndexedDB the moment
 * it is recorded, batches carry an idempotency key minted once at cut time
 * and reused across every retry, and unsent data survives reloads — it
 * drains on the next mount, into the trip's post-end recovery window if the
 * trip has meanwhile ended (or to server-side quarantine after sealing).
 */
export function TripTracker({
  assignment,
  initialTrip,
}: {
  assignment: Assignment | null;
  initialTrip: Trip | null;
}) {
  const router = useRouter();
  const [trip, setTrip] = useState<Trip | null>(initialTrip);
  const [gps, setGps] = useState<GpsState>("idle");
  const [syncedCount, setSyncedCount] = useState(0);
  const [bufferedCount, setBufferedCount] = useState(0);
  const [lastFix, setLastFix] = useState<GeolocationPosition | null>(null);
  const [error, setError] = useState<string | undefined>();
  // null = still acquiring; false = fail closed (no tracking, no ending).
  const [lockHeld, setLockHeld] = useState<boolean | null>(null);
  // Storage is a precondition for tracking (RM5): null = still opening,
  // false = unavailable/broken — tracking must not start or claim complete.
  const [storageReady, setStorageReady] = useState<boolean | null>(null);
  const [busy, startTransition] = useTransition();

  const queueRef = useRef<PingQueue | null>(null);
  const watchRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const keepaliveRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const recoveryRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const flushingRef = useRef(false);
  const releaseLockRef = useRef<(() => void) | null>(null);
  const storageBrokenRef = useRef(false);

  const refreshCounts = useCallback(async (tripId: string) => {
    const queue = queueRef.current;
    if (!queue) return;
    const [meta, unsynced] = await Promise.all([queue.meta(tripId), queue.unsyncedCount(tripId)]);
    setSyncedCount(Math.max(0, meta.pingsRecorded - unsynced));
    setBufferedCount(unsynced);
  }, []);

  /**
   * Drain: retry previously cut batches (stable keys) in cut order, then cut
   * remaining pending pings into new batches. Terminal rejections drop the
   * batch (dead letter) so one bad batch can never jam the queue.
   */
  const flush = useCallback(
    async (tripId: string) => {
      const queue = queueRef.current;
      if (flushingRef.current || !queue) return;
      flushingRef.current = true;
      try {
        const backlog = await queue.listBatches(tripId);
        for (;;) {
          const batch = backlog.shift() ?? (await queue.cutBatch(tripId, MAX_BATCH_PINGS));
          if (!batch) break;
          await queue.recordAttempt(batch.key);
          const result = await sendPingBatchAction({
            tripId: batch.tripId,
            idempotencyKey: batch.key,
            pings: batch.pings,
          });
          if (result.error) {
            if (result.retryable === false) {
              // The server will never accept this exact batch — keep going.
              await queue.dropBatch(batch.key);
              setError(`Some GPS points were rejected: ${result.error}`);
              continue;
            }
            setError(result.error);
            break; // network/server trouble: retry the same key next flush
          }
          await queue.ackBatch(batch.key);
          setError(undefined);
        }
      } finally {
        flushingRef.current = false;
      }
      await refreshCounts(tripId);
    },
    [refreshCounts],
  );

  const stopTracking = useCallback(() => {
    if (watchRef.current !== null) {
      navigator.geolocation?.clearWatch(watchRef.current);
      watchRef.current = null;
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (keepaliveRef.current) {
      clearInterval(keepaliveRef.current);
      keepaliveRef.current = null;
    }
  }, []);

  const beginTracking = useCallback(
    (tripId: string) => {
      if (!("geolocation" in navigator)) {
        setGps("unavailable");
        return;
      }
      watchRef.current = navigator.geolocation.watchPosition(
        (pos) => {
          setGps("granted");
          setLastFix(pos);
          const queue = queueRef.current;
          if (!queue) return;
          void queue
            .addPing(tripId, {
              recorded_at: new Date(pos.timestamp).toISOString(),
              lat: pos.coords.latitude,
              lon: pos.coords.longitude,
              accuracy_m: pos.coords.accuracy ?? null,
              speed_mps: pos.coords.speed ?? null,
              heading_degrees:
                pos.coords.heading !== null && !Number.isNaN(pos.coords.heading)
                  ? pos.coords.heading
                  : null,
            })
            .then(async () => {
              const pending = await queue.pendingCount(tripId);
              setBufferedCount((count) => Math.max(count, pending));
              if (pending >= FLUSH_AT_COUNT) void flush(tripId);
              else void refreshCounts(tripId);
            })
            .catch(() => {
              // Fail closed: a queue that cannot persist means points would
              // silently vanish — stop tracking and record incompleteness so
              // the end watermark never claims a complete trip.
              storageBrokenRef.current = true;
              setStorageReady(false);
              stopTracking();
              setError(
                "This device stopped storing GPS points — tracking paused. " +
                  "Free up storage or restart the app; the trip stays open.",
              );
            });
        },
        (err) => setGps(err.code === err.PERMISSION_DENIED ? "denied" : "unavailable"),
        { enableHighAccuracy: true, maximumAge: 5_000, timeout: 20_000 },
      );
      timerRef.current = setInterval(() => void flush(tripId), FLUSH_INTERVAL_MS);
      keepaliveRef.current = setInterval(() => {
        void fetch("/driver/keepalive", {
          cache: "no-store",
          credentials: "same-origin",
        }).catch(() => undefined);
      }, KEEPALIVE_INTERVAL_MS);
    },

    [flush, refreshCounts, stopTracking],
  );

  /** Drain leftovers from earlier sessions/trips until ACKed or terminal. */
  const drainLeftovers = useCallback(
    async (currentTripId: string | null) => {
      const queue = queueRef.current;
      if (!queue) return;
      for (const tripId of await queue.tripsWithLeftovers()) {
        if (tripId === currentTripId) continue;
        await flush(tripId);
        if ((await queue.unsyncedCount(tripId)) === 0) await queue.forgetTrip(tripId);
      }
    },
    [flush],
  );

  // Open the durable queue once; drain leftovers from previous sessions
  // (their trips are in the post-end recovery window, or quarantine ACKs
  // them). Recovery keeps retrying — on a timer and on reconnect — so
  // stranded data gets more than one chance per mount (review finding 7).
  useEffect(() => {
    let cancelled = false;
    const currentTripId = initialTrip?.id ?? null;
    const recover = () => void drainLeftovers(currentTripId);
    void openPingQueue()
      .then(async (queue) => {
        if (cancelled) {
          queue.close();
          return;
        }
        queueRef.current = queue;
        setStorageReady(true);
        if (currentTripId) await refreshCounts(currentTripId);
        await drainLeftovers(currentTripId);
        recoveryRef.current = setInterval(recover, RECOVERY_INTERVAL_MS);
        window.addEventListener("online", recover);
      })
      .catch(() => {
        // Fail closed (RM5): without durable storage, tracking would lose
        // points on the first reload — refuse to start rather than pretend.
        setStorageReady(false);
        setError(
          "Offline storage is unavailable on this device — tracking can't " +
            "start. Check private-browsing mode or free up storage.",
        );
      });
    return () => {
      cancelled = true;
      if (recoveryRef.current) clearInterval(recoveryRef.current);
      recoveryRef.current = null;
      window.removeEventListener("online", recover);
      queueRef.current?.close();
      queueRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Resume tracking if the app reopens onto an already-active trip; hold the
  // cross-tab lock for the tracking lifetime (single writer, RM review #6).
  // Fail closed: no Web Locks support, a rejected request, or a lock held
  // elsewhere all mean this tab must not track OR end the trip — two writers
  // would double-cut the same pings into differently-keyed batches.
  useEffect(() => {
    if (!trip || storageReady !== true) return stopTracking;
    const tripId = trip.id;
    let cancelled = false;
    const acquire = async () => {
      if (typeof navigator === "undefined" || !("locks" in navigator)) {
        setLockHeld(false);
        setError(
          "This browser can't guarantee single-tab tracking — please update " +
            "your browser to track trips.",
        );
        return;
      }
      const held = await new Promise<boolean>((resolve) => {
        void navigator.locks
          .request(TRACKING_LOCK, { ifAvailable: true }, (lock) => {
            if (!lock) {
              resolve(false);
              return;
            }
            resolve(true);
            return new Promise<void>((release) => {
              releaseLockRef.current = release;
            });
          })
          .catch(() => resolve(false));
      });
      if (!held || cancelled) {
        setLockHeld(false);
        return;
      }
      setLockHeld(true);
      if (watchRef.current === null) beginTracking(tripId);
    };
    void acquire();
    return () => {
      cancelled = true;
      stopTracking();
      releaseLockRef.current?.();
      releaseLockRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trip?.id, storageReady]);

  function start() {
    if (!assignment) return;
    if (storageReady !== true) {
      setError(
        "Offline storage isn't ready — tracking can't start until this " +
          "device can durably store GPS points.",
      );
      return;
    }
    setError(undefined);
    startTransition(async () => {
      const result = await startTripAction(assignment.id);
      if (result.error || !result.trip) {
        setError(result.error ?? "Could not start the trip.");
        return;
      }
      setSyncedCount(0);
      setBufferedCount(0);
      setTrip(result.trip);
    });
  }

  function end() {
    if (!trip) return;
    // A tab that doesn't own the tracking lock must not end the trip: the
    // owning tab may still hold undelivered batches this tab can't see.
    if (lockHeld !== true) return;
    const tripId = trip.id;
    setError(undefined);
    startTransition(async () => {
      stopTracking();
      const queue = queueRef.current;
      await flush(tripId); // cut everything pending, drain what we can
      const unsynced = queue ? await queue.unsyncedCount(tripId) : 0;
      // Never claim completeness without a healthy queue: a missing or broken
      // store means we cannot know what was lost (review finding 5).
      const complete = queue !== null && !storageBrokenRef.current && unsynced === 0;
      const message = complete
        ? "End this trip? Tracking stops and the trip is sent for analysis."
        : `${unsynced || "Some"} GPS point${unsynced === 1 ? "" : "s"} may not be synced. ` +
          "End anyway? Anything stored on your phone keeps retrying — the trip " +
          "is finalized after a short grace period.";
      if (!window.confirm(message)) {
        beginTracking(tripId); // driver chose to keep tracking
        return;
      }
      const meta = queue ? await queue.meta(tripId) : null;
      const result = await endTripAction(
        tripId,
        meta
          ? {
              clientBatchCount: meta.batchesCut,
              clientPingCount: meta.pingsRecorded,
              clientComplete: complete,
            }
          : undefined,
      );
      if (result.error) {
        setError(result.error);
        beginTracking(tripId); // trip is still open — resume
        return;
      }
      if (complete && queue) await queue.forgetTrip(tripId);
      setTrip(null);
      setGps("idle");
      router.refresh();
    });
  }

  // --- render ---------------------------------------------------------------

  if (!assignment && !trip) {
    return (
      <Panel className="p-6 text-center">
        <p className="text-sm font-medium">No active campaign</p>
        <p className="text-muted mt-1 text-xs">
          Accept an offer and wait for admin activation — then your trips earn.
        </p>
      </Panel>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {trip ? (
        <>
          {lockHeld === false ? (
            <p className="border-amber/40 bg-amber/10 text-amber-soft rounded-lg border px-3.5 py-2.5 text-xs">
              This trip is being tracked in another tab or window. Close it or switch there —
              tracking in two places would double-count, so this tab can neither track nor end the
              trip.
            </p>
          ) : null}
          <Panel className="border-green/40 p-5">
            <p className="micro text-green flex items-center gap-1.5">
              <span className="animate-pulse-dot bg-green inline-block size-1.5 rounded-full" />
              Tracking live
            </p>
            <div className="mt-4 grid grid-cols-2 gap-4">
              <div>
                <p className="micro text-faint">Pings synced</p>
                <p className="font-display text-2xl font-semibold" data-testid="pings-sent">
                  {syncedCount}
                </p>
              </div>
              <div>
                <p className="micro text-faint">Buffered</p>
                <p className="font-display text-2xl font-semibold">{bufferedCount}</p>
              </div>
              <div>
                <p className="micro text-faint">GPS</p>
                <p className="text-sm">
                  {gps === "granted" && lastFix
                    ? `±${Math.round(lastFix.coords.accuracy)}m fix`
                    : gps === "denied"
                      ? "Permission denied"
                      : gps === "unavailable"
                        ? "Unavailable"
                        : "Waiting…"}
                </p>
              </div>
              <div>
                <p className="micro text-faint">Started</p>
                <p className="text-sm">
                  {new Date(trip.started_at).toLocaleTimeString("en-NG", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </p>
              </div>
            </div>
          </Panel>

          {gps === "denied" ? (
            <p className="border-amber/40 bg-amber/10 text-amber-soft rounded-lg border px-3.5 py-2.5 text-xs">
              Location permission is blocked. Enable it in your browser/app settings — without it
              this trip records no movement and won&apos;t earn.
            </p>
          ) : null}

          <Button
            type="button"
            variant="danger"
            onClick={end}
            disabled={busy || lockHeld !== true}
            className="h-14 w-full text-base"
          >
            {busy ? "Ending…" : "■ End trip"}
          </Button>
        </>
      ) : (
        <>
          <Panel className="p-5">
            <p className="micro text-muted">Ready to drive</p>
            <p className="mt-2 text-base font-medium">{assignment?.campaign?.name}</p>
            <p className="micro text-faint mt-1">
              {assignment?.vehicle?.plate_number} · earnings accrue from verified driving time
            </p>
          </Panel>
          <Button
            type="button"
            onClick={start}
            disabled={busy || storageReady !== true}
            className="h-14 w-full text-base"
          >
            {busy ? "Starting…" : storageReady === null ? "Preparing…" : "▶ Start trip"}
          </Button>
          <p className="text-faint text-center text-xs">
            Keep the app open while driving — tracking runs while Cardvert Driver is on screen.
            Unsent points are stored on your phone and retried automatically.
          </p>
        </>
      )}

      {error ? (
        <p
          role="alert"
          className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
