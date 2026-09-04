"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { DriverTrackerAssignment, DriverTrackerTrip } from "@/lib/driver/campaign-journey";
import {
  endTripAction,
  endLegacyTripAction,
  getCurrentTripAction,
  getTripEvidenceAuthorityAction,
  reconcileTripEvidenceAction,
  sendPingBatchAction,
  startTripAction,
  verifyDriverTripOwnershipAction,
} from "@/app/driver/actions";
import { UNREADABLE_EVIDENCE_CODE, openPingQueue, type PingQueue } from "@/lib/trips/ping-queue";
import {
  EMPTY_CAPABILITY_SNAPSHOT,
  assessPilotPwa,
  type CapabilitySnapshot,
} from "@/lib/pwa/capability-contract";
import { DRIVER_SESSION_CHANNEL } from "@/components/driver/logout-button";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";

type GpsState = "idle" | "granted" | "denied" | "unavailable";
type WakeSentinel = EventTarget & { release(): Promise<void>; released?: boolean };
type NavigatorWithRuntime = Navigator & {
  wakeLock?: { request(type: "screen"): Promise<WakeSentinel> };
};

const FLUSH_INTERVAL_MS = 15_000;
const FLUSH_AT_COUNT = 20;
const MAX_BATCH_PINGS = 40;
const KEEPALIVE_INTERVAL_MS = 10 * 60_000;
const RECOVERY_INTERVAL_MS = 60_000;
const TRACKING_LOCK = "cardvert-driver-trip-writer-v2";

function passiveSnapshot(activeTrip: boolean): CapabilitySnapshot {
  if (typeof window === "undefined") return { ...EMPTY_CAPABILITY_SNAPSHOT, activeTrip };
  const visibility =
    document.visibilityState === "visible"
      ? "visible"
      : document.visibilityState === "hidden"
        ? "hidden"
        : "unknown";
  return {
    ...EMPTY_CAPABILITY_SNAPSHOT,
    secureContext: window.isSecureContext,
    manifestLinked: [...document.querySelectorAll<HTMLLinkElement>('link[rel="manifest"]')].some(
      (link) => new URL(link.href, location.href).pathname === "/driver/manifest.webmanifest",
    ),
    displayMode: window.matchMedia?.("(display-mode: standalone)").matches
      ? "standalone"
      : "browser",
    visibility,
    online: navigator.onLine,
    session: "valid",
    activeTrip,
  };
}

export function TripTracker({
  assignment,
  initialTrip,
  driverId,
  startUnavailableMessage,
}: {
  assignment: DriverTrackerAssignment | null;
  initialTrip: DriverTrackerTrip | null;
  /** Server-verified user id from the guarded driver page. */
  driverId: string;
  startUnavailableMessage?: string;
}) {
  const router = useRouter();
  const [trip, setTrip] = useState<DriverTrackerTrip | null>(initialTrip);
  const [gps, setGps] = useState<GpsState>("idle");
  const [syncedCount, setSyncedCount] = useState(0);
  const [bufferedCount, setBufferedCount] = useState(0);
  const [deadLetterCount, setDeadLetterCount] = useState(0);
  const [lastFix, setLastFix] = useState<GeolocationPosition | null>(null);
  const [error, setError] = useState<string>();
  const [storageReady, setStorageReady] = useState<boolean | null>(null);
  const [runtime, setRuntime] = useState<CapabilitySnapshot>(() => passiveSnapshot(false));
  const [serverTripVerified, setServerTripVerified] = useState(false);
  const [startUncertain, setStartUncertain] = useState(false);
  const [authorityUncertain, setAuthorityUncertain] = useState(false);
  const [busy, setBusy] = useState(false);

  const runtimeRef = useRef(runtime);
  const queueRef = useRef<PingQueue | null>(null);
  const watchRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const keepaliveRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const recoveryRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const flushPromiseRef = useRef<Promise<void> | null>(null);
  const releaseWriterRef = useRef<(() => void) | null>(null);
  const writerAcquireRef = useRef<Promise<boolean> | null>(null);
  const wakeRef = useRef<WakeSentinel | null>(null);
  const storageBrokenRef = useRef(false);
  const identityValidRef = useRef(true);
  const startUncertainRef = useRef(false);
  const authorityUncertainRef = useRef(false);
  const pendingEndCompleteRef = useRef<boolean | null>(null);
  const protocolByTripRef = useRef(new Map<string, 1 | 2>());
  const tripRef = useRef<DriverTrackerTrip | null>(initialTrip);
  const reconciledTripRef = useRef<string | null>(null);
  const terminalLeftoversRef = useRef(new Set<string>());
  const mountedRef = useRef(true);

  const patchRuntime = useCallback((patch: Partial<CapabilitySnapshot>) => {
    runtimeRef.current = { ...runtimeRef.current, ...patch };
    if (mountedRef.current) setRuntime(runtimeRef.current);
    return runtimeRef.current;
  }, []);
  const assessment = useMemo(() => assessPilotPwa(runtime), [runtime]);

  const stopWatch = useCallback(() => {
    if (watchRef.current !== null) {
      navigator.geolocation?.clearWatch(watchRef.current);
      watchRef.current = null;
    }
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    if (keepaliveRef.current) clearInterval(keepaliveRef.current);
    keepaliveRef.current = null;
  }, []);

  const releaseWake = useCallback(async () => {
    const sentinel = wakeRef.current;
    wakeRef.current = null;
    if (sentinel && !sentinel.released) await sentinel.release().catch(() => undefined);
    patchRuntime({ wakeLock: "released" });
  }, [patchRuntime]);

  const releaseWriter = useCallback(() => {
    releaseWriterRef.current?.();
    releaseWriterRef.current = null;
    patchRuntime({ webLocks: "contended" });
  }, [patchRuntime]);

  const invalidateIdentity = useCallback(
    (message: string) => {
      identityValidRef.current = false;
      stopWatch();
      void releaseWake();
      releaseWriter();
      queueRef.current?.close();
      queueRef.current = null;
      setStorageReady(false);
      patchRuntime({ session: "invalid", indexedDb: "failed", durableQueue: "failed" });
      setError(message);
    },
    [patchRuntime, releaseWake, releaseWriter, stopWatch],
  );

  const validateSession = useCallback(async () => {
    if (!navigator.onLine) {
      patchRuntime({ online: false, session: "offline" });
      return "offline" as const;
    }
    try {
      const response = await fetch("/driver/keepalive", {
        cache: "no-store",
        credentials: "same-origin",
        redirect: "manual",
      });
      if (response.ok) {
        const body = (await response.json()) as { status?: string; driverId?: string };
        if (body.status === "valid" && body.driverId === driverId) {
          identityValidRef.current = true;
          patchRuntime({ online: true, session: "valid" });
          return "valid" as const;
        }
      }
      if (
        response.status === 401 ||
        response.status === 403 ||
        response.type === "opaqueredirect"
      ) {
        invalidateIdentity("Your driver session ended. Sign in again to resume safely.");
        return "invalid" as const;
      }
      patchRuntime({ online: true, session: "unavailable" });
      return "unavailable" as const;
    } catch {
      patchRuntime({
        online: navigator.onLine,
        session: navigator.onLine ? "unavailable" : "offline",
      });
      return navigator.onLine ? ("unavailable" as const) : ("offline" as const);
    }
  }, [driverId, invalidateIdentity, patchRuntime]);

  const observeInstallability = useCallback(async () => {
    let serviceWorker: CapabilitySnapshot["serviceWorker"] = "unavailable";
    if ("serviceWorker" in navigator) {
      try {
        const registration = await navigator.serviceWorker.getRegistration("/driver");
        serviceWorker = registration ? "registered" : "not-registered";
      } catch {
        serviceWorker = "not-registered";
      }
    }
    const observed = passiveSnapshot(Boolean(tripRef.current));
    return patchRuntime({
      secureContext: observed.secureContext,
      manifestLinked: observed.manifestLinked,
      displayMode: observed.displayMode,
      visibility: observed.visibility,
      online: observed.online,
      activeTrip: observed.activeTrip,
      serviceWorker,
    });
  }, [patchRuntime]);

  const acquireWriter = useCallback(async (): Promise<boolean> => {
    if (releaseWriterRef.current) return true;
    if (writerAcquireRef.current) return writerAcquireRef.current;
    if (!("locks" in navigator)) {
      patchRuntime({ webLocks: "unavailable" });
      setError("This browser cannot provide the exclusive tracking lock Cardvert requires.");
      return false;
    }
    let resolveAcquisition!: (held: boolean) => void;
    const acquisition = new Promise<boolean>((resolve) => {
      resolveAcquisition = resolve;
    });
    writerAcquireRef.current = acquisition;
    let resolved = false;
    void navigator.locks
      .request(TRACKING_LOCK, { ifAvailable: true }, async (lock) => {
        writerAcquireRef.current = null;
        if (!lock) {
          patchRuntime({ webLocks: "contended" });
          setError("This trip is controlled by another Cardvert tab or window.");
          resolved = true;
          resolveAcquisition(false);
          return;
        }
        if (!identityValidRef.current) {
          resolved = true;
          resolveAcquisition(false);
          return;
        }
        patchRuntime({ webLocks: "pass" });
        resolved = true;
        resolveAcquisition(true);
        await new Promise<void>((release) => {
          releaseWriterRef.current = release;
        });
      })
      .catch(() => {
        writerAcquireRef.current = null;
        patchRuntime({ webLocks: "denied" });
        setError("Cardvert could not acquire the exclusive tracking lock.");
        if (!resolved) resolveAcquisition(false);
      });
    return acquisition;
  }, [patchRuntime]);

  const acquireWake = useCallback(async (): Promise<boolean> => {
    if (wakeRef.current && !wakeRef.current.released) {
      patchRuntime({ wakeLock: "pass" });
      return true;
    }
    const wake = (navigator as NavigatorWithRuntime).wakeLock;
    if (!wake) {
      patchRuntime({ wakeLock: "unavailable" });
      return false;
    }
    try {
      const sentinel = await wake.request("screen");
      wakeRef.current = sentinel;
      sentinel.addEventListener(
        "release",
        () => {
          // Ignore our own release during hide, End, or failed preparation.
          // Only an externally lost currently-held sentinel is a runtime fault.
          if (wakeRef.current !== sentinel) return;
          wakeRef.current = null;
          stopWatch();
          patchRuntime({ wakeLock: "released" });
          setError("The screen wake lock was released, so GPS capture paused.");
        },
        { once: true },
      );
      patchRuntime({ wakeLock: "pass" });
      return true;
    } catch {
      patchRuntime({ wakeLock: "denied" });
      return false;
    }
  }, [patchRuntime, stopWatch]);

  const probeLocation = useCallback(async (): Promise<boolean> => {
    if (!("geolocation" in navigator)) {
      setGps("unavailable");
      patchRuntime({ location: "unavailable" });
      return false;
    }
    return new Promise<boolean>((resolve) => {
      navigator.geolocation.getCurrentPosition(
        () => {
          setGps("granted");
          patchRuntime({ location: "granted" });
          resolve(true);
        },
        (positionError) => {
          const denied = positionError.code === positionError.PERMISSION_DENIED;
          setGps(denied ? "denied" : "unavailable");
          patchRuntime({ location: denied ? "denied" : "unavailable" });
          resolve(false);
        },
        { enableHighAccuracy: true, maximumAge: 0, timeout: 20_000 },
      );
    });
  }, [patchRuntime]);

  const refreshCounts = useCallback(async (tripId: string) => {
    const queue = queueRef.current;
    if (!queue || !identityValidRef.current) return;
    const [meta, unsynced, deadLetters] = await Promise.all([
      queue.meta(tripId),
      queue.unsyncedCount(tripId),
      queue.listDeadLetters(tripId),
    ]);
    const rejectedPings = deadLetters.reduce((sum, deadLetter) => sum + deadLetter.pings.length, 0);
    setSyncedCount(Math.max(0, meta.pingsRecorded - unsynced - rejectedPings));
    setBufferedCount(unsynced);
    setDeadLetterCount(deadLetters.length);
  }, []);

  const flush = useCallback(
    async (tripId: string) => {
      while (flushPromiseRef.current) await flushPromiseRef.current;
      const queue = queueRef.current;
      if (!queue || !identityValidRef.current) return;
      const operation = (async () => {
        try {
          let protocolVersion = protocolByTripRef.current.get(tripId);
          if (!protocolVersion) {
            const authority = await getTripEvidenceAuthorityAction(tripId);
            if (!authority) {
              if (mountedRef.current)
                setError("Cardvert could not verify the trip evidence protocol.");
              return;
            }
            protocolVersion = authority.protocolVersion;
            protocolByTripRef.current.set(tripId, protocolVersion);
          }
          const backlog = await queue.listBatches(tripId);
          for (;;) {
            const batch = backlog.shift() ?? (await queue.cutBatch(tripId, MAX_BATCH_PINGS));
            if (!batch) break;
            await queue.recordAttempt(batch.key);
            const result = await sendPingBatchAction({
              tripId: batch.tripId,
              idempotencyKey: batch.key,
              batchSequence: batch.cutSeq,
              evidenceProtocolVersion: protocolVersion,
              pings: batch.pings,
            });
            if (result.error) {
              if (result.deferred) {
                // OFF-006: already captured evidence refused only because the
                // assignment was deactivated. End commits its manifest and the
                // ended-policy authority accepts this exact batch, so it stays
                // queued — dead-lettering it here would destroy valid evidence.
                // Capture stops here though: new points need active authority.
                // Only for the trip actually being tracked — draining an older
                // trip must never halt the current one's capture.
                if (tripRef.current?.id === tripId) stopWatch();
                if (mountedRef.current)
                  setError(
                    "This campaign was deactivated. Captured GPS evidence is held and uploads when you end the trip.",
                  );
                break;
              }
              if (result.retryable === false) {
                await queue.dropBatch(batch.key, {
                  status: result.terminalStatus,
                  code: result.terminalCode,
                });
                if (mountedRef.current)
                  setError("Some GPS evidence was rejected and retained locally for diagnosis.");
                continue;
              }
              if (mountedRef.current) setError(result.error);
              break;
            }
            if (!result.acknowledged) {
              if (mountedRef.current)
                setError("Cardvert could not confirm the GPS batch acknowledgement.");
              break;
            }
            if (protocolVersion === 1) {
              await queue.acknowledgeLegacyBatch(batch.key);
            } else if (!result.receipt) {
              if (mountedRef.current)
                setError("Cardvert did not return a signed GPS evidence receipt.");
              break;
            } else {
              await queue.acknowledgeBatch(batch, result.receipt);
            }
            if (mountedRef.current) setError(undefined);
          }
        } catch {
          storageBrokenRef.current = true;
          if (mountedRef.current) {
            setStorageReady(false);
            setError(
              "Encrypted GPS storage failed, so tracking stopped without discarding evidence.",
            );
          }
          stopWatch();
          patchRuntime({ indexedDb: "failed", durableQueue: "failed" });
        }
      })();
      flushPromiseRef.current = operation;
      try {
        await operation;
      } finally {
        if (flushPromiseRef.current === operation) flushPromiseRef.current = null;
      }
      if (mountedRef.current) await refreshCounts(tripId).catch(() => undefined);
    },
    [patchRuntime, refreshCounts, stopWatch],
  );

  const beginWatch = useCallback(
    (tripId: string) => {
      if (watchRef.current !== null || !assessPilotPwa(runtimeRef.current).actions.capture) return;
      if (!("geolocation" in navigator)) return;
      watchRef.current = navigator.geolocation.watchPosition(
        (position) => {
          if (!assessPilotPwa(runtimeRef.current).actions.capture) {
            stopWatch();
            return;
          }
          setGps("granted");
          const queue = queueRef.current;
          if (!queue || !identityValidRef.current) return;
          void queue
            .addPing(tripId, {
              recorded_at: new Date(position.timestamp).toISOString(),
              lat: position.coords.latitude,
              lon: position.coords.longitude,
              accuracy_m: position.coords.accuracy ?? null,
              speed_mps: position.coords.speed ?? null,
              heading_degrees:
                position.coords.heading !== null && !Number.isNaN(position.coords.heading)
                  ? position.coords.heading
                  : null,
            })
            .then(async () => {
              // Acknowledge the capture only once the durable write has committed.
              if (mountedRef.current) setLastFix(position);
              const pending = await queue.pendingCount(tripId);
              if (pending >= FLUSH_AT_COUNT) await flush(tripId);
              else await refreshCounts(tripId);
            })
            .catch(() => {
              storageBrokenRef.current = true;
              stopWatch();
              patchRuntime({ indexedDb: "failed", durableQueue: "failed" });
              if (!mountedRef.current) return;
              setStorageReady(false);
              setError("This device stopped storing encrypted GPS evidence; capture is stopped.");
            });
        },
        (positionError) => {
          const denied = positionError.code === positionError.PERMISSION_DENIED;
          setGps(denied ? "denied" : "unavailable");
          stopWatch();
          patchRuntime({ location: denied ? "revoked" : "unavailable" });
        },
        { enableHighAccuracy: true, maximumAge: 5_000, timeout: 20_000 },
      );
      timerRef.current = setInterval(() => void flush(tripId), FLUSH_INTERVAL_MS);
      keepaliveRef.current = setInterval(() => void validateSession(), KEEPALIVE_INTERVAL_MS);
    },
    [flush, patchRuntime, refreshCounts, stopWatch, validateSession],
  );

  const prepareCapture = useCallback(
    async (validate: boolean) => {
      await observeInstallability();
      const installability = assessPilotPwa(runtimeRef.current).results.find(
        (result) => result.id === "installability",
      );
      if (installability?.status !== "supported") return false;
      if (document.visibilityState !== "visible") {
        patchRuntime({ visibility: document.visibilityState === "hidden" ? "hidden" : "unknown" });
        return false;
      }
      const [locationReady, wakeReady] = await Promise.all([probeLocation(), acquireWake()]);
      if (validate) await validateSession();
      return locationReady && wakeReady && assessPilotPwa(runtimeRef.current).actions.capture;
    },
    [acquireWake, observeInstallability, patchRuntime, probeLocation, validateSession],
  );

  const drainLeftovers = useCallback(
    async (currentTripId: string | null) => {
      const queue = queueRef.current;
      if (!queue || !identityValidRef.current) return;
      for (const leftoverTripId of await queue.tripsWithLeftovers()) {
        if (leftoverTripId === currentTripId) continue;
        if (terminalLeftoversRef.current.has(leftoverTripId)) continue;
        await flush(leftoverTripId);
        // Terminal evidence is never resent. Reconciliation below may dispose it,
        // so this wording must stay true after disposal.
        if ((await queue.deadLetterCount(leftoverTripId)) > 0 && mountedRef.current)
          setError("Earlier GPS evidence was rejected by the server and could not be delivered.");
        if ((await queue.unsyncedCount(leftoverTripId)) === 0) {
          const authority = await getTripEvidenceAuthorityAction(leftoverTripId);
          if (authority?.protocolVersion === 2) {
            const reconciled = await reconcileTripEvidenceAction(leftoverTripId);
            if (reconciled.outcome === "ended") {
              if (reconciled.adjudication) {
                terminalLeftoversRef.current.add(leftoverTripId);
                if (mountedRef.current)
                  setError(
                    "Earlier GPS evidence could not be delivered, so Cardvert closed that trip's record as incomplete.",
                  );
              } else {
                await queue.forgetTrip(leftoverTripId);
              }
            }
            // Retrying cannot help while the server still refuses to settle,
            // so report it once instead of looping every minute.
            else if (reconciled.outcome === "failed") {
              terminalLeftoversRef.current.add(leftoverTripId);
              if (mountedRef.current)
                setError(
                  "Earlier GPS evidence could not be delivered, so this trip's record stays incomplete.",
                );
            }
          } else if (authority?.protocolVersion === 1 && authority.status === "sealed") {
            await queue.forgetTrip(leftoverTripId);
          }
        }
      }
    },
    [flush],
  );

  const reportRecoveryFault = useCallback(() => {
    // Recovering earlier trips is best-effort: it must never be mistaken for a
    // failed queue open, and must never block capture of the current trip.
    if (mountedRef.current) setError("Cardvert could not finish recovering earlier trip evidence.");
  }, []);

  const recoverWithWriter = useCallback(async () => {
    const queue = queueRef.current;
    if (!queue || !identityValidRef.current) return;
    const currentTripId = tripRef.current?.id ?? null;
    const leftovers = await queue.tripsWithLeftovers();
    if (
      !leftovers.some(
        (tripId) => tripId !== currentTripId && !terminalLeftoversRef.current.has(tripId),
      )
    )
      return;
    if (!(await acquireWriter())) return;
    try {
      await drainLeftovers(currentTripId);
    } finally {
      if (!tripRef.current) releaseWriter();
    }
  }, [acquireWriter, drainLeftovers, releaseWriter]);

  useEffect(() => {
    mountedRef.current = true;
    let cancelled = false;
    const currentTripId = initialTrip?.id ?? null;
    const recover = () => void recoverWithWriter().catch(reportRecoveryFault);
    void openPingQueue({ driverId, verifyTripOwner: verifyDriverTripOwnershipAction })
      .then(async (queue) => {
        if (cancelled) return queue.close();
        queueRef.current = queue;
        setStorageReady(true);
        patchRuntime({ indexedDb: "pass", durableQueue: "pass" });
        if (currentTripId) await refreshCounts(currentTripId);
        // The queue opened; a recovery fault must not be reported as an open failure
        // nor prevent later retries from being scheduled.
        await recoverWithWriter().catch(reportRecoveryFault);
        recoveryRef.current = setInterval(recover, RECOVERY_INTERVAL_MS);
        window.addEventListener("online", recover);
      })
      .catch((openError: unknown) => {
        setStorageReady(false);
        patchRuntime({ indexedDb: "failed", durableQueue: "failed" });
        setError(
          (openError as { code?: string } | null)?.code === UNREADABLE_EVIDENCE_CODE
            ? "Earlier encrypted GPS evidence on this device can no longer be read, so it cannot be recovered or resent."
            : "Encrypted offline storage is unavailable, blocked, or could not be verified.",
        );
      });
    return () => {
      cancelled = true;
      mountedRef.current = false;
      if (recoveryRef.current) clearInterval(recoveryRef.current);
      recoveryRef.current = null;
      window.removeEventListener("online", recover);
      stopWatch();
      void releaseWake();
      releaseWriter();
      queueRef.current?.close();
      queueRef.current = null;
    };
    // Driver identity is immutable for this guarded page instance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [driverId]);

  useEffect(() => {
    if (!trip || storageReady !== true) return;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      void acquireWriter().then(async (held) => {
        if (!held || cancelled) return;
        if (reconciledTripRef.current !== trip.id) {
          const current = await getCurrentTripAction();
          if (cancelled) return;
          if (!current.trip) {
            stopWatch();
            setServerTripVerified(false);
            patchRuntime({ activeTrip: false });
            if (current.outcome === "failed") {
              tripRef.current = null;
              setTrip(null);
              releaseWriter();
            } else {
              setError(
                "Cardvert could not reconcile the current trip; the writer remains reserved.",
              );
            }
            return;
          }
          reconciledTripRef.current = current.trip.id;
          protocolByTripRef.current.set(current.trip.id, current.trip.evidenceProtocolVersion);
          tripRef.current = current.trip;
          setServerTripVerified(true);
          patchRuntime({ activeTrip: true });
          if (current.trip.id !== trip.id) setTrip(current.trip);
        }
        await drainLeftovers(tripRef.current?.id ?? null).catch(reportRecoveryFault);
        const ready = await prepareCapture(false);
        if (ready && !cancelled && tripRef.current) beginWatch(tripRef.current.id);
      });
    });
    return () => {
      cancelled = true;
    };
  }, [
    acquireWriter,
    reportRecoveryFault,
    beginWatch,
    drainLeftovers,
    patchRuntime,
    prepareCapture,
    releaseWriter,
    stopWatch,
    storageReady,
    trip,
  ]);

  useEffect(() => {
    const onVisibility = () => {
      const visibility =
        document.visibilityState === "visible"
          ? "visible"
          : document.visibilityState === "hidden"
            ? "hidden"
            : "unknown";
      patchRuntime({ visibility });
      if (visibility !== "visible") {
        stopWatch();
        void releaseWake();
      } else if (tripRef.current && releaseWriterRef.current && storageReady === true) {
        void prepareCapture(true).then((ready) => {
          if (ready && tripRef.current) beginWatch(tripRef.current.id);
        });
      }
    };
    const onOnline = () => {
      patchRuntime({ online: navigator.onLine });
      void validateSession();
    };
    const onLogout = () =>
      invalidateIdentity("You signed out. Encrypted trip evidence was retained.");
    const channel =
      "BroadcastChannel" in window ? new BroadcastChannel(DRIVER_SESSION_CHANNEL) : null;
    if (channel)
      channel.onmessage = (event) => {
        if ((event.data as { type?: string })?.type === "logout") onLogout();
      };
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOnline);
    window.addEventListener("cardvert-driver-logout", onLogout);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOnline);
      window.removeEventListener("cardvert-driver-logout", onLogout);
      channel?.close();
    };
  }, [
    beginWatch,
    invalidateIdentity,
    patchRuntime,
    prepareCapture,
    releaseWake,
    stopWatch,
    storageReady,
    validateSession,
  ]);

  function start() {
    if (!assignment || storageReady !== true || busy) return;
    setError(undefined);
    setBusy(true);
    void (async () => {
      if (!(await acquireWriter())) return;
      let result;
      let captureReady = false;
      if (startUncertainRef.current) {
        result = await getCurrentTripAction();
      } else {
        captureReady = await prepareCapture(true);
        if (!mountedRef.current || !identityValidRef.current || !releaseWriterRef.current) return;
        if (!captureReady) {
          stopWatch();
          await releaseWake();
          releaseWriter();
          setError("Start is blocked until every live Cardvert capability is held.");
          return;
        }
        result = await startTripAction(assignment.id);
        if (result.outcome === "unknown") result = await getCurrentTripAction();
      }
      if (!mountedRef.current || !identityValidRef.current || !releaseWriterRef.current) return;
      if (!result.trip) {
        setError(result.error ?? "Cardvert could not prove whether the trip started.");
        if (result.outcome === "failed") {
          startUncertainRef.current = false;
          setStartUncertain(false);
          await releaseWake();
          releaseWriter();
        } else {
          startUncertainRef.current = true;
          setStartUncertain(true);
        }
        return;
      }
      startUncertainRef.current = false;
      setStartUncertain(false);
      tripRef.current = result.trip;
      protocolByTripRef.current.set(result.trip.id, result.trip.evidenceProtocolVersion);
      reconciledTripRef.current = result.trip.id;
      setServerTripVerified(true);
      setTrip(result.trip);
      patchRuntime({ activeTrip: true });
      setSyncedCount(0);
      setBufferedCount(0);
      setDeadLetterCount(0);
      if (captureReady || (await prepareCapture(true))) beginWatch(result.trip.id);
    })().finally(() => {
      if (mountedRef.current) setBusy(false);
    });
  }

  const finishEndedTrip = useCallback(
    async (complete: boolean | null) => {
      const activeTripId = tripRef.current?.id;
      if (complete && activeTripId) {
        await queueRef.current?.forgetTrip(activeTripId).catch(() => undefined);
      }
      tripRef.current = null;
      reconciledTripRef.current = null;
      authorityUncertainRef.current = false;
      pendingEndCompleteRef.current = null;
      if (mountedRef.current) {
        setAuthorityUncertain(false);
        setServerTripVerified(false);
        setTrip(null);
        setGps("idle");
      }
      patchRuntime({ activeTrip: false });
      await releaseWake();
      releaseWriter();
      if (mountedRef.current) router.refresh();
    },
    [patchRuntime, releaseWake, releaseWriter, router],
  );

  const reconcileAfterEnd = useCallback(
    async (complete: boolean | null) => {
      const current = await getCurrentTripAction();
      if (!mountedRef.current || !identityValidRef.current || !releaseWriterRef.current) return;
      if (current.trip) {
        tripRef.current = current.trip;
        reconciledTripRef.current = current.trip.id;
        authorityUncertainRef.current = false;
        pendingEndCompleteRef.current = null;
        setAuthorityUncertain(false);
        setServerTripVerified(true);
        setTrip(current.trip);
        patchRuntime({ activeTrip: true });
        const ready = await prepareCapture(true);
        if (ready && mountedRef.current && identityValidRef.current && tripRef.current) {
          beginWatch(tripRef.current.id);
        } else if (mountedRef.current) {
          await releaseWake();
        }
        return;
      }
      if (current.outcome === "failed") {
        const endedTripId = tripRef.current?.id;
        const protocolVersion = endedTripId
          ? protocolByTripRef.current.get(endedTripId)
          : undefined;
        if (endedTripId && protocolVersion === 2) {
          const reconciled = await reconcileTripEvidenceAction(endedTripId);
          if (reconciled.outcome === "ended" && reconciled.adjudication) {
            terminalLeftoversRef.current.add(endedTripId);
            await finishEndedTrip(false);
            return;
          }
          if (reconciled.outcome === "ended" && reconciled.status === "sealed") {
            await finishEndedTrip(complete);
            return;
          }
        } else if (endedTripId && protocolVersion === 1) {
          const authority = await getTripEvidenceAuthorityAction(endedTripId);
          if (authority?.status === "sealed") {
            await finishEndedTrip(complete);
            return;
          }
        }
      }
      stopWatch();
      await releaseWake();
      authorityUncertainRef.current = true;
      pendingEndCompleteRef.current = complete;
      setAuthorityUncertain(true);
      setServerTripVerified(false);
      setError("Cardvert could not reconcile trip authority; the writer remains reserved.");
    },
    [beginWatch, finishEndedTrip, patchRuntime, prepareCapture, releaseWake, stopWatch],
  );

  function end() {
    const activeTrip = tripRef.current;
    if (
      !activeTrip ||
      (!serverTripVerified && !authorityUncertainRef.current) ||
      !assessment.actions.end ||
      busy ||
      !identityValidRef.current
    )
      return;
    setBusy(true);
    void (async () => {
      if (authorityUncertainRef.current) {
        await reconcileAfterEnd(pendingEndCompleteRef.current);
        return;
      }
      stopWatch();
      const queue = queueRef.current;
      if (!queue) return;
      await flush(activeTrip.id);
      if (
        !mountedRef.current ||
        !identityValidRef.current ||
        storageBrokenRef.current ||
        !releaseWriterRef.current ||
        !assessPilotPwa(runtimeRef.current).actions.end
      ) {
        if (mountedRef.current)
          setError("End stopped because Cardvert can no longer vouch for the durable watermark.");
        return;
      }
      const [unsynced, deadLetters, meta] = await Promise.all([
        queue.unsyncedCount(activeTrip.id),
        queue.deadLetterCount(activeTrip.id),
        queue.meta(activeTrip.id),
      ]);
      const complete = !storageBrokenRef.current && unsynced === 0 && deadLetters === 0;
      const message = complete
        ? "End this trip? Tracking stops and the trip is sent for analysis."
        : "Some GPS evidence is unsynced or diagnostically retained. End with an incomplete client watermark?";
      if (!window.confirm(message)) {
        await reconcileAfterEnd(null);
        return;
      }
      const protocolVersion = protocolByTripRef.current.get(activeTrip.id);
      if (!protocolVersion) {
        if (mountedRef.current) setError("Cardvert could not verify the trip evidence protocol.");
        return;
      }
      const result =
        protocolVersion === 1
          ? await endLegacyTripAction(activeTrip.id, {
              clientBatchCount: meta.batchesCut,
              clientPingCount: meta.pingsRecorded,
              clientComplete: complete,
            })
          : await endTripAction(
              activeTrip.id,
              await queue.evidenceManifest(activeTrip.id, complete),
            );
      if (result.outcome !== "ended") {
        if (mountedRef.current)
          setError(result.error ?? "Cardvert could not confirm whether the trip ended.");
        authorityUncertainRef.current = true;
        pendingEndCompleteRef.current = complete;
        if (mountedRef.current) setAuthorityUncertain(true);
        await reconcileAfterEnd(complete);
        return;
      }
      if (result.status === "sealed") await finishEndedTrip(complete);
      else {
        await flush(activeTrip.id);
        await reconcileAfterEnd(complete);
      }
    })().finally(() => {
      if (mountedRef.current) setBusy(false);
    });
  }

  if (!assignment && !trip) {
    return (
      <Panel className="p-6 text-center">
        <p className="text-sm font-medium">No active campaign</p>
        <p className="text-muted mt-1 text-xs">
          {startUnavailableMessage ??
            "Accept an offer and wait for admin activation — then your trips earn."}
        </p>
      </Panel>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {trip ? (
        <>
          <Panel className={assessment.health === "active" ? "border-green/40 p-5" : "p-5"}>
            <p className="micro flex items-center gap-1.5" data-testid="tracking-health">
              <span
                className={`inline-block size-1.5 rounded-full ${assessment.health === "active" ? "bg-green animate-pulse-dot" : assessment.health === "degraded" ? "bg-amber" : "bg-coral"}`}
              />
              {assessment.health}
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
                <p className="micro text-faint">Diagnostics</p>
                <p className="text-sm">{deadLetterCount} retained</p>
              </div>
            </div>
          </Panel>
          <Button
            type="button"
            variant="danger"
            onClick={end}
            disabled={
              busy || (!serverTripVerified && !authorityUncertain) || !assessment.actions.end
            }
            className="h-14 w-full text-base"
          >
            {busy
              ? authorityUncertain
                ? "Reconciling…"
                : "Ending…"
              : authorityUncertain
                ? "Reconcile trip"
                : "■ End trip"}
          </Button>
        </>
      ) : (
        <>
          <Panel className="p-5">
            <p className="micro text-muted">Ready to drive</p>
            <p className="mt-2 text-base font-medium">{assignment?.campaignName}</p>
            <p className="micro text-faint mt-1">
              {assignment?.plateNumber} · earnings accrue from verified driving time
            </p>
          </Panel>
          <Button
            type="button"
            onClick={start}
            disabled={busy || storageReady !== true}
            className="h-14 w-full text-base"
          >
            {busy
              ? startUncertain
                ? "Reconciling…"
                : "Starting…"
              : storageReady === null
                ? "Preparing…"
                : startUncertain
                  ? "Reconcile trip"
                  : "▶ Start trip"}
          </Button>
          <p className="text-faint text-center text-xs">
            Cardvert captures only while the installed app is visible and every live safety check
            remains held.
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
