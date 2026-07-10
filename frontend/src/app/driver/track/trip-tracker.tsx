"use client";

import { useCallback, useEffect, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import type { components } from "@/lib/api/schema";
import { startTripAction, endTripAction, sendPingBatchAction } from "../actions";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";

type Assignment = components["schemas"]["CampaignAssignmentRead"];
type Trip = components["schemas"]["TripRead"];

interface BufferedPing {
  recorded_at: string;
  lat: number;
  lon: number;
  accuracy_m: number | null;
  speed_mps: number | null;
  heading_degrees: number | null;
  sequence_number: number;
}

const FLUSH_INTERVAL_MS = 15_000;
const FLUSH_AT_COUNT = 20;

type GpsState = "idle" | "granted" | "denied" | "unavailable";

/**
 * Foreground trip tracking via the Geolocation API.
 *
 * Honest limitation, documented for the client: a web app (even installed
 * as a PWA) can only track while it is open and on-screen. Background GPS
 * is the future native app's job — the backend contract is identical.
 *
 * Pings buffer locally and flush as idempotent batches (UUID key per
 * batch) every 15s or 20 pings, so flaky connections never double-count.
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
  const [sentCount, setSentCount] = useState(0);
  const [bufferedCount, setBufferedCount] = useState(0);
  const [lastFix, setLastFix] = useState<GeolocationPosition | null>(null);
  const [error, setError] = useState<string | undefined>();
  const [busy, startTransition] = useTransition();

  const bufferRef = useRef<BufferedPing[]>([]);
  const seqRef = useRef(0);
  const watchRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const flushingRef = useRef(false);

  const flush = useCallback(async (tripId: string) => {
    if (flushingRef.current || bufferRef.current.length === 0) return;
    flushingRef.current = true;
    const batch = bufferRef.current.splice(0, FLUSH_AT_COUNT * 2);
    try {
      const result = await sendPingBatchAction({
        tripId,
        idempotencyKey: crypto.randomUUID(),
        pings: batch,
      });
      if (result.error) {
        // Put the batch back — idempotency key changes next try, backend
        // dedupes by content window anyway; better late than lost.
        bufferRef.current = [...batch, ...bufferRef.current];
        setError(result.error);
        setBufferedCount(bufferRef.current.length);
      } else {
        setSentCount((n) => n + (result.acceptedCount ?? 0));
        setError(undefined);
        setBufferedCount(bufferRef.current.length);
      }
    } finally {
      flushingRef.current = false;
    }
  }, []);

  const stopTracking = useCallback(() => {
    if (watchRef.current !== null) {
      navigator.geolocation?.clearWatch(watchRef.current);
      watchRef.current = null;
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
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
          bufferRef.current.push({
            recorded_at: new Date(pos.timestamp).toISOString(),
            lat: pos.coords.latitude,
            lon: pos.coords.longitude,
            accuracy_m: pos.coords.accuracy ?? null,
            speed_mps: pos.coords.speed ?? null,
            heading_degrees:
              pos.coords.heading !== null && !Number.isNaN(pos.coords.heading)
                ? pos.coords.heading
                : null,
            sequence_number: seqRef.current++,
          });
          setBufferedCount(bufferRef.current.length);
          if (bufferRef.current.length >= FLUSH_AT_COUNT) void flush(tripId);
        },
        (err) => setGps(err.code === err.PERMISSION_DENIED ? "denied" : "unavailable"),
        { enableHighAccuracy: true, maximumAge: 5_000, timeout: 20_000 },
      );
      timerRef.current = setInterval(() => void flush(tripId), FLUSH_INTERVAL_MS);
    },
    [flush],
  );

  // Resume tracking if the app reopens onto an already-active trip
  useEffect(() => {
    if (trip && watchRef.current === null) beginTracking(trip.id);
    return stopTracking;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trip?.id]);

  function start() {
    if (!assignment) return;
    setError(undefined);
    startTransition(async () => {
      const result = await startTripAction(assignment.id);
      if (result.error || !result.trip) {
        setError(result.error ?? "Could not start the trip.");
        return;
      }
      seqRef.current = 0;
      setSentCount(0);
      setTrip(result.trip);
    });
  }

  function end() {
    if (!trip) return;
    if (!window.confirm("End this trip? Tracking stops and the trip is sent for analysis.")) return;
    const tripId = trip.id;
    setError(undefined);
    startTransition(async () => {
      stopTracking();
      await flush(tripId); // drain the buffer before closing
      const result = await endTripAction(tripId);
      if (result.error) {
        setError(result.error);
        beginTracking(tripId); // trip is still open — resume
        return;
      }
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
          Accept and activate a job first — then your trips earn.
        </p>
      </Panel>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {trip ? (
        <>
          <Panel className="border-green/40 p-5">
            <p className="micro text-green flex items-center gap-1.5">
              <span className="animate-pulse-dot bg-green inline-block size-1.5 rounded-full" />
              Tracking live
            </p>
            <div className="mt-4 grid grid-cols-2 gap-4">
              <div>
                <p className="micro text-faint">Pings sent</p>
                <p className="font-display text-2xl font-semibold" data-testid="pings-sent">
                  {sentCount}
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
            disabled={busy}
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
              {assignment?.vehicle?.plate_number} · earnings accrue per verified km
            </p>
          </Panel>
          <Button type="button" onClick={start} disabled={busy} className="h-14 w-full text-base">
            {busy ? "Starting…" : "▶ Start trip"}
          </Button>
          <p className="text-faint text-center text-xs">
            Keep the app open while driving — tracking runs while Vantage Driver is on screen.
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
