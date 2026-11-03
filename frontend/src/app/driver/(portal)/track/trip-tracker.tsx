"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { DriverTrackerAssignment, DriverTrackerTrip } from "@/lib/driver/campaign-journey";
import {
  endTripAction,
  getCurrentTripAction,
  getTripEvidenceAction,
  getTripEvidenceAuthorityAction,
  reconcileTripEvidenceAction,
  sendPingBatchAction,
  startTripAction,
  verifyDriverTripOwnershipAction,
} from "@/app/driver/actions";
import { UNREADABLE_EVIDENCE_CODE, openPingQueue, type PingQueue } from "@/lib/trips/ping-queue";
import type { EvidenceManifest } from "@/lib/trips/trip-evidence";
import {
  EMPTY_CAPABILITY_SNAPSHOT,
  assessPilotPwa,
  type CapabilitySnapshot,
} from "@/lib/pwa/capability-contract";
import { DRIVER_SESSION_CHANNEL } from "@/components/driver/logout-button";
import { Panel } from "@/components/ui/panel";
import { readinessRows, type ReadinessRow } from "@/lib/pwa/readiness-rows";
import { Button } from "@/components/ui/button";

const REJECTION_LABELS: Record<string, string> = {
  INVALID_SPEED: "The recorded speed was too high",
  INVALID_ACCURACY: "The location wasn't accurate enough",
  INVALID_RECORDED_AT: "The location update was outside this trip's time",
  INVALID_ASSIGNMENT_AUTHORITY: "The job was no longer active",
};

type GpsState = "idle" | "granted" | "denied" | "unavailable";
type WakeSentinel = EventTarget & { release(): Promise<void>; released?: boolean };
type NavigatorWithRuntime = Navigator & {
  wakeLock?: { request(type: "screen"): Promise<WakeSentinel> };
};

const FLUSH_INTERVAL_MS = 15_000;
const FLUSH_AT_COUNT = 20;
const MAX_BATCH_PINGS = 40;
const KEEPALIVE_INTERVAL_MS = 10 * 60_000;
// While a trip is open and the last session check could not complete, check
// again soon: End needs a confirmed session and must not wait ten minutes.
const SESSION_RECHECK_INTERVAL_MS = 20_000;
const RECOVERY_INTERVAL_MS = 60_000;
const GPS_RETRY_INTERVAL_MS = 30_000;
const TRACKING_LOCK = "cardvert-driver-trip-writer-v2";

function trackingPresentation({
  authorityUncertain,
  bufferedCount,
  error,
  health,
  hasEvidenceIssue,
  isSending,
  online,
  queueHealthy,
  session,
  syncedCount,
  waitingForGps,
}: {
  authorityUncertain: boolean;
  bufferedCount: number;
  error?: string;
  health: "active" | "degraded" | "stopped";
  hasEvidenceIssue: boolean;
  isSending: boolean;
  online: boolean;
  queueHealthy: boolean;
  session: CapabilitySnapshot["session"];
  syncedCount: number;
  waitingForGps: boolean;
}) {
  if (authorityUncertain) {
    return {
      label: "Check trip status",
      detail: "Tracking is paused while Cardvert checks whether this trip is still running.",
      tone: "text-amber",
      dot: "bg-amber",
    } as const;
  }
  if (session === "invalid" || hasEvidenceIssue) {
    return {
      label: "Needs attention",
      detail: "Some trip updates need attention. Follow the message below before continuing.",
      tone: "text-coral",
      dot: "bg-coral",
    } as const;
  }
  if (bufferedCount > 0 && !online && queueHealthy) {
    return {
      label: "Saved on this phone",
      detail: "Trip updates are safe on this phone and will wait here until Cardvert is online.",
      tone: "text-amber",
      dot: "bg-amber",
    } as const;
  }
  if (error) {
    return {
      label: "Needs attention",
      detail: "Some trip updates need attention. Follow the message below before continuing.",
      tone: "text-coral",
      dot: "bg-coral",
    } as const;
  }
  if (bufferedCount > 0 && isSending && session === "valid") {
    return {
      label: "Sending",
      detail: "Sending the trip updates saved on this phone.",
      tone: "text-cyan",
      dot: "bg-cyan",
    } as const;
  }
  if (bufferedCount > 0 && session !== "valid") {
    return {
      label: "Waiting to send",
      detail: "Trip updates are saved and waiting while Cardvert checks the connection.",
      tone: "text-amber",
      dot: "bg-amber",
    } as const;
  }
  if (waitingForGps) {
    return {
      label: "Waiting for GPS",
      detail:
        "The phone has lost its location for now. Cardvert keeps trying and records again when GPS returns.",
      tone: "text-amber",
      dot: "bg-amber",
    } as const;
  }
  if (health !== "active") {
    return {
      label: "Paused",
      detail: "No new locations are being recorded until the phone is ready to track again.",
      tone: "text-amber",
      dot: "bg-amber",
    } as const;
  }
  if (isSending) {
    return {
      label: "Sending",
      detail: "Sending the trip updates saved on this phone.",
      tone: "text-cyan",
      dot: "bg-cyan",
    } as const;
  }
  if (syncedCount > 0) {
    return {
      label: "Sent",
      detail: "Everything saved for this trip has reached Cardvert. Tracking continues on screen.",
      tone: "text-green",
      dot: "bg-green animate-pulse-dot",
    } as const;
  }
  return {
    label: "Tracking",
    detail: "Cardvert is recording this trip while the app stays open on screen.",
    tone: "text-green",
    dot: "bg-green animate-pulse-dot",
  } as const;
}

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

const START_BLOCKED = "You can't start a trip yet. Fix this first:";
const AUTO_ENDED_NOTICE =
  "Your last trip ended on its own after 2 hours with no location. Miles already sent still count.";
const autoEndedNoticeKey = (tripId: string) => `cardvert.trip-auto-ended-notice.${tripId}`;

export function TripTracker({
  assignment,
  initialTrip,
  driverId,
  startUnavailableMessage,
  pausedCampaignName,
  compact = false,
}: {
  assignment: DriverTrackerAssignment | null;
  initialTrip: DriverTrackerTrip | null;
  /** Server-verified user id from the guarded driver page. */
  driverId: string;
  startUnavailableMessage?: string;
  /** An activated campaign whose Start is currently not allowed (display only). */
  pausedCampaignName?: string;
  compact?: boolean;
}) {
  const router = useRouter();
  const [trip, setTrip] = useState<DriverTrackerTrip | null>(initialTrip);
  const [clock, setClock] = useState(() => Date.now());
  const [recordedMiles, setRecordedMiles] = useState<number | null>(null);
  const previousFix = useRef<GeolocationPosition | null>(null);
  useEffect(() => {
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const [gps, setGps] = useState<GpsState>("idle");
  const [syncedCount, setSyncedCount] = useState(0);
  const [bufferedCount, setBufferedCount] = useState(0);
  const [deadLetterCount, setDeadLetterCount] = useState(0);
  const [rejectedSampleCount, setRejectedSampleCount] = useState(0);
  const [quarantinedSampleCount, setQuarantinedSampleCount] = useState(0);
  const [rejectionCodes, setRejectionCodes] = useState<string[]>([]);
  const [lastFix, setLastFix] = useState<GeolocationPosition | null>(null);
  const [error, setError] = useState<string>();
  const [blockers, setBlockers] = useState<ReadinessRow[]>([]);
  const [storageReady, setStorageReady] = useState<boolean | null>(null);
  const [runtime, setRuntime] = useState<CapabilitySnapshot>(() => passiveSnapshot(false));
  const [serverTripVerified, setServerTripVerified] = useState(false);
  const [startUncertain, setStartUncertain] = useState(false);
  const [authorityUncertain, setAuthorityUncertain] = useState(false);
  const [busy, setBusy] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [autoEndedNotice, setAutoEndedNotice] = useState(false);

  const endPhaseRef = useRef<"capturing" | "preparing" | "submitted">("capturing");
  const captureGenerationRef = useRef(0);
  const runtimeRef = useRef(runtime);
  const queueRef = useRef<PingQueue | null>(null);
  const watchRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const recoveryRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const flushPromiseRef = useRef<Promise<void> | null>(null);
  const releaseWriterRef = useRef<(() => void) | null>(null);
  const writerAcquireRef = useRef<Promise<boolean> | null>(null);
  const wakeRef = useRef<WakeSentinel | null>(null);
  const gpsRetryRef = useRef(false);
  const storageBrokenRef = useRef(false);
  const identityValidRef = useRef(true);
  const startUncertainRef = useRef(false);
  const authorityUncertainRef = useRef(false);
  const pendingEndCompleteRef = useRef<boolean | null>(null);
  const protocolByTripRef = useRef(new Map<string, 2>());
  const tripRef = useRef<DriverTrackerTrip | null>(initialTrip);
  const reconciledTripRef = useRef<string | null>(null);
  const terminalLeftoversRef = useRef(new Set<string>());
  // Trips whose uploads the server refused because it already ended them.
  const serverEndedTripsRef = useRef(new Set<string>());
  const onServerEndedRef = useRef<(tripId: string) => void>(() => undefined);
  const mountedRef = useRef(true);
  const lifetimeRef = useRef(0);
  const startingRef = useRef(false);

  const patchRuntime = useCallback((patch: Partial<CapabilitySnapshot>) => {
    runtimeRef.current = { ...runtimeRef.current, ...patch };
    if (mountedRef.current) setRuntime(runtimeRef.current);
    return runtimeRef.current;
  }, []);
  const assessment = useMemo(() => assessPilotPwa(runtime), [runtime]);
  const hasEvidenceIssue =
    deadLetterCount > 0 || rejectedSampleCount > 0 || quarantinedSampleCount > 0;
  const presentedTracking = trackingPresentation({
    authorityUncertain,
    bufferedCount,
    error,
    health: assessment.health,
    hasEvidenceIssue,
    isSending,
    online: runtime.online,
    queueHealthy: runtime.indexedDb === "pass" && runtime.durableQueue === "pass",
    session: runtime.session,
    syncedCount,
    waitingForGps: gps === "unavailable",
  });

  const stopWatch = useCallback(() => {
    captureGenerationRef.current += 1;
    if (watchRef.current !== null) {
      navigator.geolocation?.clearWatch(watchRef.current);
      watchRef.current = null;
    }
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  }, []);

  const releaseWake = useCallback(
    async (expected?: WakeSentinel) => {
      const sentinel = wakeRef.current;
      if (expected && sentinel !== expected) return;
      wakeRef.current = null;
      patchRuntime({ wakeLock: "released" });
      if (sentinel && !sentinel.released) await sentinel.release().catch(() => undefined);
    },
    [patchRuntime],
  );

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
    const lifetime = lifetimeRef.current;
    if (!mountedRef.current || !identityValidRef.current) return "invalid" as const;
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
      if (lifetime !== lifetimeRef.current || !mountedRef.current || !identityValidRef.current)
        return "invalid" as const;
      if (response.ok) {
        const body = (await response.json()) as { status?: string; driverId?: string };
        if (lifetime !== lifetimeRef.current || !mountedRef.current || !identityValidRef.current)
          return "invalid" as const;
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
        invalidateIdentity("You've been signed out. Sign in again to carry on.");
        return "invalid" as const;
      }
      patchRuntime({ online: true, session: "unavailable" });
      return "unavailable" as const;
    } catch {
      if (lifetime !== lifetimeRef.current || !mountedRef.current || !identityValidRef.current)
        return "invalid" as const;
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
    const lifetime = lifetimeRef.current;
    if (!mountedRef.current || !identityValidRef.current) return false;
    if (releaseWriterRef.current) return true;
    if (writerAcquireRef.current) return writerAcquireRef.current;
    if (!("locks" in navigator)) {
      patchRuntime({ webLocks: "unavailable" });
      setError("This browser can't track trips. Try Chrome or Safari.");
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
          setError("This trip is open in another tab. Close it to carry on here.");
          resolved = true;
          resolveAcquisition(false);
          return;
        }
        if (lifetime !== lifetimeRef.current || !mountedRef.current || !identityValidRef.current) {
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
        if (lifetime === lifetimeRef.current && mountedRef.current && identityValidRef.current) {
          writerAcquireRef.current = null;
          patchRuntime({ webLocks: "denied" });
          setError(
            "Cardvert couldn't keep this trip's tracking in one tab. Close other Cardvert tabs and try again.",
          );
        }
        if (!resolved) resolveAcquisition(false);
      });
    return acquisition;
  }, [patchRuntime]);

  const acquireWake = useCallback(async (): Promise<WakeSentinel | null> => {
    const lifetime = lifetimeRef.current;
    const generation = captureGenerationRef.current;
    if (!mountedRef.current || !identityValidRef.current) return null;
    if (wakeRef.current && !wakeRef.current.released) {
      patchRuntime({ wakeLock: "pass" });
      return wakeRef.current;
    }
    const wake = (navigator as NavigatorWithRuntime).wakeLock;
    if (!wake) {
      patchRuntime({ wakeLock: "unavailable" });
      return null;
    }
    try {
      const sentinel = await wake.request("screen");
      if (
        lifetime !== lifetimeRef.current ||
        generation !== captureGenerationRef.current ||
        !mountedRef.current ||
        !identityValidRef.current
      ) {
        await sentinel.release().catch(() => undefined);
        return null;
      }
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
          setError(
            "Your screen could not stay on, so tracking paused. Keep Cardvert open and check your phone settings.",
          );
        },
        { once: true },
      );
      patchRuntime({ wakeLock: "pass" });
      return sentinel;
    } catch {
      if (
        lifetime !== lifetimeRef.current ||
        generation !== captureGenerationRef.current ||
        !mountedRef.current ||
        !identityValidRef.current
      )
        return null;
      patchRuntime({ wakeLock: "denied" });
      return null;
    }
  }, [patchRuntime, stopWatch]);

  const probeLocation = useCallback(async (): Promise<boolean> => {
    const lifetime = lifetimeRef.current;
    const generation = captureGenerationRef.current;
    if (!("geolocation" in navigator)) {
      setGps("unavailable");
      patchRuntime({ location: "unavailable" });
      return false;
    }
    return new Promise<boolean>((resolve) => {
      navigator.geolocation.getCurrentPosition(
        () => {
          if (
            lifetime !== lifetimeRef.current ||
            generation !== captureGenerationRef.current ||
            !mountedRef.current ||
            !identityValidRef.current
          ) {
            resolve(false);
            return;
          }
          setGps("granted");
          patchRuntime({ location: "granted" });
          resolve(true);
        },
        (positionError) => {
          if (
            lifetime !== lifetimeRef.current ||
            generation !== captureGenerationRef.current ||
            !mountedRef.current ||
            !identityValidRef.current
          ) {
            resolve(false);
            return;
          }
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
    const [meta, unsynced, deadLetters, receipts] = await Promise.all([
      queue.meta(tripId),
      queue.unsyncedCount(tripId),
      queue.listDeadLetters(tripId),
      queue.listReceipts(tripId),
    ]);
    const rejectedPings = deadLetters.reduce((sum, deadLetter) => sum + deadLetter.pings.length, 0);
    const rejected = receipts
      .filter((r) => r.outcome !== "quarantined")
      .reduce((sum, receipt) => sum + receipt.rejectedCount, 0);
    const quarantined = receipts
      .filter((r) => r.outcome === "quarantined")
      .reduce((sum, receipt) => sum + receipt.submitted_count, 0);
    setRejectedSampleCount(rejected);
    setQuarantinedSampleCount(quarantined);
    setRejectionCodes([
      ...new Set(
        receipts.flatMap((r) =>
          (r.sampleResults ?? []).flatMap((result) =>
            result.rejection_code ? [result.rejection_code] : [],
          ),
        ),
      ),
    ]);
    setSyncedCount(
      Math.max(0, meta.pingsRecorded - unsynced - rejectedPings - rejected - quarantined),
    );
    setBufferedCount(unsynced);
    setDeadLetterCount(deadLetters.length);
  }, []);

  // Learns the server's signed receipts for a trip this device has no full
  // record of (cleared site data, reinstalled app, new phone), so numbering
  // continues after them and End declares them. False when they can't be read.
  // `reopenEnd` re-opens an End boundary the server refused before writing
  // anything, but only once the receipts are in hand to correct it.
  const syncServerEvidence = useCallback(
    async (tripId: string, { reopenEnd = false } = {}): Promise<boolean> => {
      const queue = queueRef.current;
      if (!queue || !identityValidRef.current) return false;
      const receipts = await getTripEvidenceAction(tripId).catch(() => undefined);
      if (!receipts || queueRef.current !== queue) return false;
      if (reopenEnd) await queue.reopenEnd(tripId);
      await queue.adoptServerEvidence(tripId, receipts);
      return true;
    },
    [],
  );

  // REQ-264: shown once per trip, even across reloads.
  const showAutoEndedNotice = useCallback((tripId: string) => {
    try {
      if (window.localStorage.getItem(autoEndedNoticeKey(tripId))) return;
      window.localStorage.setItem(autoEndedNoticeKey(tripId), "1");
    } catch {
      // Storage unavailable: still tell the driver this time.
    }
    if (mountedRef.current) setAutoEndedNotice(true);
  }, []);

  // True when the server says it ended this trip on its own (seal_reason).
  const noticeIfAutoEnded = useCallback(
    async (tripId: string) => {
      const authority = await getTripEvidenceAuthorityAction(tripId).catch(() => undefined);
      if (authority?.sealReason !== "auto_ended") return false;
      showAutoEndedNotice(tripId);
      return true;
    },
    [showAutoEndedNotice],
  );

  const flush = useCallback(
    async (tripId: string) => {
      while (flushPromiseRef.current) await flushPromiseRef.current;
      const queue = queueRef.current;
      if (!queue || !identityValidRef.current) return;
      if (mountedRef.current) setIsSending(true);
      const operation = (async () => {
        try {
          let protocolVersion = protocolByTripRef.current.get(tripId);
          if (!protocolVersion) {
            const authority = await getTripEvidenceAuthorityAction(tripId).catch(() => null);
            if (!authority) {
              if (mountedRef.current)
                setError(
                  "Cardvert couldn't check how this trip's locations should be saved. Try again.",
                );
              return;
            }
            protocolVersion = authority.protocolVersion;
            protocolByTripRef.current.set(tripId, protocolVersion);
          }
          let backlog = await queue.listBatches(tripId);
          let resynced = false;
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
            }).catch((): Awaited<ReturnType<typeof sendPingBatchAction>> => ({
              error:
                "Cardvert couldn't receive these updates. They are saved on this phone and will be tried again.",
              retryable: true,
              acknowledged: false,
            }));
            if (result.error) {
              if (result.tripEnded) {
                // The server already ended this trip on its own: stop
                // recording. The refused updates stay on this phone.
                serverEndedTripsRef.current.add(tripId);
                if (tripRef.current?.id === tripId) {
                  stopWatch();
                  if (endPhaseRef.current === "capturing") onServerEndedRef.current(tripId);
                }
                break;
              }
              if (result.sequenceTaken) {
                // This device lost its record of the trip: adopt the server's
                // receipts (which renumbers this batch), then resend once.
                if (!resynced && (await syncServerEvidence(tripId))) {
                  resynced = true;
                  backlog = await queue.listBatches(tripId);
                  continue;
                }
                if (mountedRef.current)
                  setError(
                    "Cardvert couldn't match this trip's saved locations. They are kept on this phone and will be tried again.",
                  );
                break;
              }
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
                    "This job has stopped. Your saved trip updates will be sent when you end the trip.",
                  );
                break;
              }
              if (result.retryable === false) {
                await queue.dropBatch(batch.key, {
                  status: result.terminalStatus,
                  code: result.terminalCode,
                });
                if (mountedRef.current)
                  setError(
                    "Some location updates were not accepted. They remain on this phone for support to check.",
                  );
                continue;
              }
              if (mountedRef.current) setError(result.error);
              break;
            }
            if (!result.acknowledged) {
              if (mountedRef.current)
                setError(
                  "Cardvert could not confirm these location updates arrived. Keep the app open while it checks.",
                );
              break;
            }
            if (!result.receipt) {
              if (mountedRef.current)
                setError(
                  "Cardvert could not confirm these location updates were saved. Keep the app open while it checks.",
                );
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
              "This phone could not save new location updates, so tracking stopped. Earlier saved updates remain on the phone.",
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
        if (mountedRef.current) {
          await refreshCounts(tripId).catch(() => undefined);
          setIsSending(false);
        }
      }
    },
    [patchRuntime, refreshCounts, stopWatch, syncServerEvidence],
  );

  const beginWatch = useCallback(
    (tripId: string) => {
      if (
        !mountedRef.current ||
        !identityValidRef.current ||
        !releaseWriterRef.current ||
        reconciledTripRef.current !== tripId ||
        endPhaseRef.current !== "capturing" ||
        watchRef.current !== null ||
        !assessPilotPwa(runtimeRef.current).actions.capture
      )
        return;
      const generation = captureGenerationRef.current;
      if (!("geolocation" in navigator)) return;
      watchRef.current = navigator.geolocation.watchPosition(
        (position) => {
          if (generation !== captureGenerationRef.current || endPhaseRef.current !== "capturing")
            return;
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
                position.coords.heading !== null &&
                Number.isFinite(position.coords.heading) &&
                position.coords.heading >= 0 &&
                position.coords.heading < 360
                  ? position.coords.heading
                  : null,
            })
            .then(async () => {
              // Acknowledge the capture only once the durable write has committed.
              if (
                mountedRef.current &&
                generation === captureGenerationRef.current &&
                endPhaseRef.current === "capturing"
              ) {
                const previous = previousFix.current;
                if (previous) {
                  const radians = Math.PI / 180;
                  const dLat = (position.coords.latitude - previous.coords.latitude) * radians;
                  const dLon = (position.coords.longitude - previous.coords.longitude) * radians;
                  const a =
                    Math.sin(dLat / 2) ** 2 +
                    Math.cos(previous.coords.latitude * radians) *
                      Math.cos(position.coords.latitude * radians) *
                      Math.sin(dLon / 2) ** 2;
                  const miles =
                    (6371000 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))) / 1609.344;
                  setRecordedMiles((value) => (value ?? 0) + miles);
                } else {
                  setRecordedMiles(0);
                }
                previousFix.current = position;
                setLastFix(position);
              }
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
              setError(
                "This phone could not save location updates, so tracking stopped. Free up storage and ask support for help.",
              );
            });
        },
        (positionError) => {
          if (positionError.code !== positionError.PERMISSION_DENIED) {
            // A lost or slow fix (tunnel, weak signal) is temporary: the browser
            // keeps this watch alive and the next fix resumes capture.
            setGps("unavailable");
            return;
          }
          setGps("denied");
          stopWatch();
          patchRuntime({ location: "revoked" });
        },
        { enableHighAccuracy: true, maximumAge: 5_000, timeout: 20_000 },
      );
      timerRef.current = setInterval(() => void flush(tripId), FLUSH_INTERVAL_MS);
    },
    [flush, patchRuntime, refreshCounts, stopWatch],
  );

  // The session check runs for as long as a trip is open, not only while
  // location is being captured: once capture stops (location withdrawn, page
  // hidden) End still depends on it, and one failed check must not leave End
  // disabled until the driver happens to leave and return to the page.
  const sessionState = runtime.session;
  useEffect(() => {
    if (!trip || storageReady !== true) return;
    const unconfirmed = sessionState === "unavailable" || sessionState === "offline";
    const timer = setInterval(
      () => void validateSession(),
      unconfirmed ? SESSION_RECHECK_INTERVAL_MS : KEEPALIVE_INTERVAL_MS,
    );
    return () => clearInterval(timer);
  }, [sessionState, storageReady, trip, validateSession]);

  const prepareCapture = useCallback(
    async (validate: boolean) => {
      const generation = captureGenerationRef.current;
      if (endPhaseRef.current !== "capturing") return false;
      await observeInstallability();
      if (generation !== captureGenerationRef.current || endPhaseRef.current !== "capturing")
        return false;
      const installability = assessPilotPwa(runtimeRef.current).results.find(
        (result) => result.id === "installability",
      );
      if (installability?.status !== "supported") return false;
      if (document.visibilityState !== "visible") {
        patchRuntime({ visibility: document.visibilityState === "hidden" ? "hidden" : "unknown" });
        return false;
      }
      const [locationReady, wake] = await Promise.all([probeLocation(), acquireWake()]);
      if (validate && generation === captureGenerationRef.current) await validateSession();
      if (generation !== captureGenerationRef.current || endPhaseRef.current !== "capturing") {
        // A newer preparation may already own a different wake sentinel.
        if (wake) await releaseWake(wake);
        return false;
      }
      return locationReady && wake !== null && assessPilotPwa(runtimeRef.current).actions.capture;
    },
    [acquireWake, observeInstallability, patchRuntime, probeLocation, releaseWake, validateSession],
  );

  const drainLeftovers = useCallback(
    async (currentTripId: string | null) => {
      const queue = queueRef.current;
      if (!queue || !identityValidRef.current) return;
      for (const leftoverTripId of await queue.tripsWithLeftovers()) {
        if (leftoverTripId === currentTripId) continue;
        if (terminalLeftoversRef.current.has(leftoverTripId)) continue;
        await flush(leftoverTripId);
        if (serverEndedTripsRef.current.has(leftoverTripId)) {
          // Ended by the server: unsent updates can't be added any more.
          terminalLeftoversRef.current.add(leftoverTripId);
          await noticeIfAutoEnded(leftoverTripId);
          continue;
        }
        // Terminal evidence is never resent. Reconciliation below may dispose it,
        // so this wording must stay true after disposal.
        if ((await queue.deadLetterCount(leftoverTripId)) > 0 && mountedRef.current)
          setError(
            "Some earlier location updates were not accepted. Contact support before clearing app data.",
          );
        if ((await queue.unsyncedCount(leftoverTripId)) === 0) {
          const authority = await getTripEvidenceAuthorityAction(leftoverTripId);
          if (authority?.protocolVersion === 2) {
            const reconciled = await reconcileTripEvidenceAction(leftoverTripId);
            if (reconciled.outcome === "ended") {
              if (reconciled.adjudication) {
                terminalLeftoversRef.current.add(leftoverTripId);
                if (mountedRef.current)
                  setError(
                    "Some earlier location updates could not be sent. That trip's record is incomplete.",
                  );
              } else {
                if (authority.sealReason === "auto_ended") showAutoEndedNotice(leftoverTripId);
                const receipts = await queue.listReceipts(leftoverTripId);
                if (
                  receipts.some(
                    (receipt) => receipt.rejectedCount > 0 || receipt.outcome === "quarantined",
                  )
                ) {
                  terminalLeftoversRef.current.add(leftoverTripId);
                  if (mountedRef.current) {
                    const rejected = receipts
                      .filter((r) => r.outcome !== "quarantined")
                      .reduce((sum, r) => sum + r.rejectedCount, 0);
                    const quarantined = receipts
                      .filter((r) => r.outcome === "quarantined")
                      .reduce((sum, r) => sum + r.submitted_count, 0);
                    const reasons = [
                      ...new Set(
                        receipts.flatMap((r) =>
                          (r.sampleResults ?? []).flatMap((result) =>
                            result.rejection_code
                              ? [
                                  REJECTION_LABELS[result.rejection_code] ??
                                    "Location update not accepted",
                                ]
                              : [],
                          ),
                        ),
                      ),
                    ];
                    setError(
                      `Earlier location updates need checking: ${rejected} not accepted, ${quarantined} waiting for review. ${reasons.join("; ")}. They remain on this phone and will not be sent again.`,
                    );
                  }
                } else {
                  await queue.forgetTrip(leftoverTripId);
                }
              }
            }
            // Retrying cannot help while the server still refuses to settle,
            // so report it once instead of looping every minute.
            else if (reconciled.outcome === "failed") {
              terminalLeftoversRef.current.add(leftoverTripId);
              if (mountedRef.current)
                setError(
                  "Some earlier location updates could not be sent. This trip's record is still incomplete.",
                );
            }
          }
        }
      }
    },
    [flush, noticeIfAutoEnded, showAutoEndedNotice],
  );

  const reportRecoveryFault = useCallback(() => {
    // Recovering earlier trips is best-effort: it must never be mistaken for a
    // failed queue open, and must never block capture of the current trip.
    if (mountedRef.current)
      setError("Cardvert couldn't restore saved details from earlier trips. Try again.");
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
    lifetimeRef.current += 1;
    mountedRef.current = true;
    identityValidRef.current = true;
    startingRef.current = false;
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
        if (cancelled || !identityValidRef.current) return;
        recoveryRef.current = setInterval(recover, RECOVERY_INTERVAL_MS);
        window.addEventListener("online", recover);
      })
      .catch((openError: unknown) => {
        if (cancelled) return;
        setStorageReady(false);
        patchRuntime({ indexedDb: "failed", durableQueue: "failed" });
        setError(
          (openError as { code?: string } | null)?.code === UNREADABLE_EVIDENCE_CODE
            ? "Earlier saved trip updates on this phone cannot be read or sent. Contact support for help."
            : "Your phone couldn't save trip details securely for use offline.",
        );
      });
    return () => {
      cancelled = true;
      lifetimeRef.current += 1;
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
              setError("Cardvert couldn't check your current trip. Close this tab to carry on.");
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
        const activeTripId = tripRef.current?.id ?? trip.id;
        const queue = queueRef.current;
        // A device with no record of this open trip (cleared site data,
        // reinstalled app, new phone) adopts the server's receipts before it
        // captures, so its batch numbers continue after them.
        if (queue && !(await queue.hasTripRecord(activeTripId))) {
          await syncServerEvidence(activeTripId).catch(() => false);
          if (cancelled) return;
          await refreshCounts(activeTripId).catch(() => undefined);
        }
        const meta = await queueRef.current?.meta(activeTripId);
        if (meta?.endManifest) {
          endPhaseRef.current = "submitted";
          authorityUncertainRef.current = true;
          pendingEndCompleteRef.current = meta.endManifest.complete;
          setAuthorityUncertain(true);
          stopWatch();
          return;
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
    refreshCounts,
    releaseWriter,
    stopWatch,
    storageReady,
    syncServerEvidence,
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
      invalidateIdentity("You signed out. Your saved trip details are still stored securely.");
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

  useEffect(() => {
    // A start or resume can find no GPS yet (weak signal): keep asking instead of
    // waiting for the driver to leave and reopen the app.
    if (gps !== "unavailable" || storageReady !== true) return;
    const timer = setInterval(() => {
      if (
        runtimeRef.current.location !== "unavailable" ||
        gpsRetryRef.current ||
        watchRef.current !== null ||
        !tripRef.current ||
        !releaseWriterRef.current ||
        endPhaseRef.current !== "capturing" ||
        document.visibilityState !== "visible"
      )
        return;
      gpsRetryRef.current = true;
      void prepareCapture(false)
        .then((ready) => {
          if (ready && tripRef.current) beginWatch(tripRef.current.id);
        })
        .finally(() => {
          gpsRetryRef.current = false;
        });
    }, GPS_RETRY_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [beginWatch, gps, prepareCapture, storageReady]);

  function start() {
    if (!assignment || storageReady !== true || startingRef.current || !identityValidRef.current)
      return;
    startingRef.current = true;
    const lifetime = lifetimeRef.current;
    const current = () =>
      lifetime === lifetimeRef.current && mountedRef.current && identityValidRef.current;
    setError(undefined);
    setBlockers([]);
    setBusy(true);
    void (async () => {
      if (!(await acquireWriter())) return;
      let result: Awaited<ReturnType<typeof getCurrentTripAction>>;
      let captureReady = false;
      if (startUncertainRef.current) {
        result = await getCurrentTripAction().catch(() => ({ outcome: "unknown" as const }));
      } else {
        captureReady = await prepareCapture(true);
        if (!current() || !releaseWriterRef.current) return;
        if (!captureReady) {
          console.warn(
            `TRACKING_START_BLOCKED=${JSON.stringify(assessPilotPwa(runtimeRef.current))}`,
          );
          stopWatch();
          await releaseWake();
          releaseWriter();
          setBlockers(readinessRows(runtimeRef.current).filter((row) => !row.ok));
          setError(START_BLOCKED);
          return;
        }
        // A rejected browser-to-action request can have created a trip. Mark
        // uncertainty before reconciliation, so no subsequent click sends Start.
        result = await startTripAction(assignment.id).catch(() => ({
          outcome: "unknown" as const,
        }));
        if (!current() || !releaseWriterRef.current) return;
        if (result.outcome === "unknown") {
          startUncertainRef.current = true;
          setStartUncertain(true);
          result = await getCurrentTripAction().catch(() => ({ outcome: "unknown" as const }));
        }
      }
      if (!current() || !releaseWriterRef.current) return;
      if (!result.trip) {
        stopWatch();
        await releaseWake();
        if (!current()) return;
        setError(
          result.error ??
            "Cardvert couldn't confirm whether your trip started. Check its status before trying again.",
        );
        if (result.outcome === "failed") {
          startUncertainRef.current = false;
          setStartUncertain(false);
          releaseWriter();
        } else {
          startUncertainRef.current = true;
          setStartUncertain(true);
        }
        return;
      }
      startUncertainRef.current = false;
      setStartUncertain(false);
      endPhaseRef.current = "capturing";
      tripRef.current = result.trip;
      protocolByTripRef.current.set(result.trip.id, result.trip.evidenceProtocolVersion);
      reconciledTripRef.current = result.trip.id;
      setServerTripVerified(true);
      setRecordedMiles(null);
      previousFix.current = null;
      setTrip(result.trip);
      patchRuntime({ activeTrip: true });
      setSyncedCount(0);
      setBufferedCount(0);
      setDeadLetterCount(0);
      setRejectedSampleCount(0);
      setQuarantinedSampleCount(0);
      setRejectionCodes([]);
      if ((captureReady || (await prepareCapture(true))) && current()) beginWatch(result.trip.id);
    })()
      .catch(async () => {
        stopWatch();
        await releaseWake();
        if (!current()) return;
        if (!startUncertainRef.current && !tripRef.current) releaseWriter();
        setError("Cardvert couldn't confirm your trip status. Check again before continuing.");
      })
      .finally(() => {
        if (current()) {
          startingRef.current = false;
          setBusy(false);
        }
      });
  }

  const finishEndedTrip = useCallback(
    async (complete: boolean | null) => {
      const activeTripId = tripRef.current?.id;
      if (complete && activeTripId) {
        await queueRef.current?.forgetTrip(activeTripId).catch(() => undefined);
      }
      stopWatch();
      endPhaseRef.current = "capturing";
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
    [patchRuntime, releaseWake, releaseWriter, router, stopWatch],
  );

  // REQ-264: the server ended the trip after 2 hours with no location. Close
  // it here with the notice instead of an error. Unsent updates stay saved.
  const settleServerEndedTrip = useCallback(
    async (tripId: string) => {
      if (!(await noticeIfAutoEnded(tripId))) return false;
      if (tripRef.current?.id !== tripId) return true;
      terminalLeftoversRef.current.add(tripId);
      if (mountedRef.current) setError(undefined);
      await finishEndedTrip(false);
      return true;
    },
    [finishEndedTrip, noticeIfAutoEnded],
  );
  useEffect(() => {
    onServerEndedRef.current = (tripId) => void settleServerEndedTrip(tripId);
  }, [settleServerEndedTrip]);

  const reconcileAfterEnd = useCallback(
    async (complete: boolean | null) => {
      const endingTripId = tripRef.current?.id;
      if (endingTripId && endPhaseRef.current === "submitted") await flush(endingTripId);
      const current = await getCurrentTripAction().catch(
        (): Awaited<ReturnType<typeof getCurrentTripAction>> => ({ outcome: "unknown" }),
      );
      if (!mountedRef.current || !identityValidRef.current || !releaseWriterRef.current) return;
      if (current.trip && endPhaseRef.current === "submitted") {
        stopWatch();
        await releaseWake();
        authorityUncertainRef.current = true;
        pendingEndCompleteRef.current = complete;
        setAuthorityUncertain(true);
        setServerTripVerified(true);
        setError(
          "Cardvert hasn't confirmed the trip ended. Try End again; location recording is stopped.",
        );
        return;
      }
      if (current.trip) {
        endPhaseRef.current = "capturing";
        tripRef.current = current.trip;
        reconciledTripRef.current = current.trip.id;
        authorityUncertainRef.current = false;
        pendingEndCompleteRef.current = null;
        setAuthorityUncertain(false);
        setServerTripVerified(true);
        setTrip(current.trip);
        patchRuntime({ activeTrip: true });
        const generation = captureGenerationRef.current;
        const ready = await prepareCapture(true);
        if (generation !== captureGenerationRef.current) return;
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
          const reconciled = await reconcileTripEvidenceAction(endedTripId).catch(
            (): Awaited<ReturnType<typeof reconcileTripEvidenceAction>> => ({ outcome: "unknown" }),
          );
          if (reconciled.outcome === "ended" && reconciled.adjudication) {
            terminalLeftoversRef.current.add(endedTripId);
            await finishEndedTrip(false);
            return;
          }
          if (reconciled.outcome === "ended" && reconciled.status === "sealed") {
            if (!(await settleServerEndedTrip(endedTripId))) await finishEndedTrip(complete);
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
      setError("Cardvert could not confirm your trip status. Keep this page open and try again.");
    },
    [
      beginWatch,
      finishEndedTrip,
      flush,
      patchRuntime,
      prepareCapture,
      releaseWake,
      settleServerEndedTrip,
      stopWatch,
    ],
  );

  // Sends the frozen End manifest. If the server refuses it before writing
  // anything because it doesn't match the evidence the server holds (this
  // device lost part of its record), rebuild it from the server's receipts
  // and send once more.
  // A stored manifest is resent exactly as frozen.
  async function submitEnd(
    queue: PingQueue,
    tripId: string,
    complete: boolean,
    stored?: EvidenceManifest,
  ) {
    const send = (manifest: EvidenceManifest) =>
      endTripAction(tripId, manifest).catch((): Awaited<ReturnType<typeof endTripAction>> => ({
        outcome: "unknown",
      }));
    const result = await send(stored ?? (await queue.freezeEnd(tripId, complete)));
    if (
      result.outcome !== "evidence_mismatch" ||
      !(await syncServerEvidence(tripId, { reopenEnd: true }))
    )
      return result;
    return send(await queue.freezeEnd(tripId, complete));
  }

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
    if (endPhaseRef.current === "capturing") endPhaseRef.current = "preparing";
    stopWatch();
    void (async () => {
      if (authorityUncertainRef.current) {
        const uncertainQueue = queueRef.current;
        const meta = await uncertainQueue?.meta(activeTrip.id);
        if (uncertainQueue && meta?.endManifest) {
          endPhaseRef.current = "submitted";
          const complete = meta.endManifest.complete;
          const result = await submitEnd(uncertainQueue, activeTrip.id, complete, meta.endManifest);
          if (result.outcome === "ended" && result.status === "sealed") {
            await finishEndedTrip(complete);
            return;
          }
        }
        await reconcileAfterEnd(pendingEndCompleteRef.current);
        return;
      }
      const queue = queueRef.current;
      if (!queue) return;
      await flush(activeTrip.id);
      if (
        serverEndedTripsRef.current.has(activeTrip.id) &&
        (await settleServerEndedTrip(activeTrip.id))
      )
        return;
      if (
        !mountedRef.current ||
        !identityValidRef.current ||
        storageBrokenRef.current ||
        !releaseWriterRef.current ||
        !assessPilotPwa(runtimeRef.current).actions.end
      ) {
        if (mountedRef.current)
          setError("Cardvert couldn't confirm all saved locations, so the trip couldn't be ended.");
        return;
      }
      const [unsynced, deadLetters, receipts] = await Promise.all([
        queue.unsyncedCount(activeTrip.id),
        queue.deadLetterCount(activeTrip.id),
        queue.listReceipts(activeTrip.id),
      ]);
      const complete =
        !storageBrokenRef.current &&
        unsynced === 0 &&
        deadLetters === 0 &&
        receipts.every(
          (receipt) => receipt.rejectedCount === 0 && receipt.outcome !== "quarantined",
        );
      const message = complete
        ? "End this trip? Tracking stops and your miles are sent to Cardvert."
        : "Some trip updates have not reached Cardvert or need checking. End this trip? Some miles may not count.";
      if (!window.confirm(message)) {
        await reconcileAfterEnd(null);
        return;
      }
      const protocolVersion = protocolByTripRef.current.get(activeTrip.id);
      if (!protocolVersion) {
        if (mountedRef.current)
          setError("Cardvert couldn't check how this trip's locations should be saved. Try again.");
        return;
      }
      endPhaseRef.current = "submitted";
      const result = await submitEnd(queue, activeTrip.id, complete);
      if (result.outcome !== "ended") {
        // A late End on a trip the server already ended: notice, not error.
        if (result.outcome === "failed" && (await settleServerEndedTrip(activeTrip.id))) return;
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
    })()
      .catch(() => {
        stopWatch();
        storageBrokenRef.current = true;
        patchRuntime({ indexedDb: "failed", durableQueue: "failed" });
        if (mountedRef.current) {
          setStorageReady(false);
          setError(
            "This phone could not save your request to end the trip. Saved updates remain here. Free up storage, then reload Cardvert to try again.",
          );
        }
      })
      .finally(() => {
        if (mountedRef.current) setBusy(false);
      });
  }

  const autoEndedNoticeEl = autoEndedNotice ? (
    <p role="status" className="border-edge rounded-lg border px-3.5 py-2.5 text-sm">
      {AUTO_ENDED_NOTICE}
    </p>
  ) : null;

  if (!assignment && !trip) {
    return (
      <div className="flex flex-col gap-4">
        {autoEndedNoticeEl}
        <Panel className="p-6 text-center">
          <p className="text-sm font-medium">
            {pausedCampaignName ? `${pausedCampaignName} can't start yet` : "No job yet"}
          </p>
          <p className="text-muted mt-1 text-xs">
            {startUnavailableMessage ??
              "Accept an offer and wait for Terrax Media to start it — then your trips earn."}
          </p>
        </Panel>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {trip ? (
        <>
          {!compact ? (
            <p className="text-base font-medium">{assignment?.campaignName ?? "Current trip"}</p>
          ) : null}
          <Panel className="grid grid-cols-3 gap-3 p-4" aria-label="Live trip">
            <div>
              <p className="text-muted text-xs">Time</p>
              <p className="font-mono">
                {trip.startedAt
                  ? `${Math.floor(Math.max(0, clock - Date.parse(trip.startedAt)) / 60000)} min`
                  : "—"}
              </p>
            </div>
            <div>
              <p className="text-muted text-xs">Miles recorded</p>
              <p className="font-mono">{recordedMiles === null ? "—" : recordedMiles.toFixed(1)}</p>
            </div>
            <div>
              <p className="text-muted text-xs">Today’s earnings</p>
              <p className="text-sm">Being checked</p>
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
                ? "Checking…"
                : "Ending…"
              : authorityUncertain
                ? "Check trip status"
                : "End trip"}
          </Button>
          {assessment.health === "active" &&
          !error &&
          !hasEvidenceIssue &&
          !authorityUncertain &&
          gps !== "unavailable" ? (
            <p
              className={`text-sm ${presentedTracking.tone}`}
              data-testid="tracking-health"
              data-runtime-health={assessment.health}
            >
              {presentedTracking.label}
            </p>
          ) : (
            <Panel
              className={presentedTracking.tone === "text-green" ? "border-green/40 p-5" : "p-5"}
            >
              <p
                className={`micro flex items-center gap-1.5 ${presentedTracking.tone}`}
                data-testid="tracking-health"
                data-runtime-health={assessment.health}
              >
                <span className={`inline-block size-1.5 rounded-full ${presentedTracking.dot}`} />
                {presentedTracking.label}
              </p>
              <p className="text-muted mt-2 text-sm leading-6">{presentedTracking.detail}</p>
              <div className="mt-4 flex items-end justify-between gap-4">
                <div>
                  <p className="micro text-faint">Location</p>
                  <p className="text-sm">
                    {gps === "granted" && lastFix
                      ? `Accurate to about ${Math.round(lastFix.coords.accuracy)} m`
                      : gps === "denied"
                        ? "Permission denied"
                        : gps === "unavailable"
                          ? "Unavailable"
                          : "Waiting…"}
                  </p>
                </div>
                <Link href="/driver/capabilities" className="micro text-faint">
                  Phone check →
                </Link>
              </div>
              {hasEvidenceIssue ? (
                <div className="border-coral/30 bg-coral/10 mt-4 rounded-lg border px-3.5 py-2.5">
                  <p className="text-coral text-sm">Some saved trip updates need attention.</p>
                  {rejectionCodes.length > 0 ? (
                    <p className="text-muted mt-1 text-xs">
                      {rejectionCodes
                        .map((code) => REJECTION_LABELS[code] ?? "A GPS update was not accepted")
                        .join("; ")}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </Panel>
          )}
        </>
      ) : (
        <>
          {!compact ? (
            <p className="text-base font-medium">
              {assignment?.campaignName} · {assignment?.plateNumber}
            </p>
          ) : null}
          <Button
            type="button"
            onClick={start}
            disabled={busy || storageReady !== true}
            className="h-14 w-full text-base"
          >
            {busy
              ? startUncertain
                ? "Checking…"
                : "Starting…"
              : storageReady === null
                ? "Preparing…"
                : startUncertain
                  ? "Check trip status"
                  : "Start trip"}
          </Button>
          {!compact ? (
            <p className="text-faint text-center text-xs">
              Keep Cardvert open on your screen while tracking a trip.
            </p>
          ) : null}
        </>
      )}
      {autoEndedNoticeEl}
      {error ? (
        <div
          role="alert"
          className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-3.5 py-2.5 text-sm"
        >
          <p>{error}</p>
          {error === START_BLOCKED && blockers.length ? (
            <ul className="text-ink mt-2 grid gap-2">
              {blockers.map((row) => (
                <li key={row.label}>
                  <span className="block font-medium">{row.label}: not yet</span>
                  <span className="text-muted block text-xs leading-5">{row.fix}</span>
                </li>
              ))}
            </ul>
          ) : null}
          {!trip && error.includes("Jobs") ? (
            <Link href="/driver/assignments" className="text-ink mt-2 inline-block underline">
              Open Jobs
            </Link>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
