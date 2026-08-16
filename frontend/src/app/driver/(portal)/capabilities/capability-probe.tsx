"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { openPingQueue, type PingQueue } from "@/lib/trips/ping-queue";
import {
  D15_D16_PROTOCOL,
  EMPTY_CAPABILITY_SNAPSHOT,
  R14A_CONTRACT_VERSION,
  R14A_SESSION_PROBE_PATH,
  assessPilotPwa,
  probeBffSession,
  probeExclusiveWebLock,
  probeForegroundLocation,
  probeScreenWakeLock,
  reconcileLocationPermission,
  type CapabilitySnapshot,
  type WakeLockLike,
  type WebLocksLike,
} from "@/lib/pwa/capability-contract";

type Probe = "queue" | "locks" | "wake" | "location" | "session";
type NavigatorWithPwa = Navigator & {
  standalone?: boolean;
  locks?: WebLocksLike;
  wakeLock?: WakeLockLike;
};
const SYNTHETIC_TRIP = "r14-a-synthetic-probe";

function deleteDatabase(name: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(name);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error("probe database remained open"));
  });
}

export function CapabilityProbe() {
  const [snapshot, setSnapshot] = useState<CapabilitySnapshot>(EMPTY_CAPABILITY_SNAPSHOT);
  const [passiveReady, setPassiveReady] = useState(false);
  const [busy, setBusy] = useState<Probe | null>(null);
  const [notice, setNotice] = useState("Run each probe on the test device.");
  const [browser, setBrowser] = useState({ userAgent: "", platform: "" });
  const patch = useCallback(
    (value: Partial<CapabilitySnapshot>) =>
      setSnapshot((current) => ({ ...current, ...value })),
    [],
  );

  useEffect(() => {
    let cancelled = false;
    const nav = navigator as NavigatorWithPwa;
    const observe = () => {
      const displayMode =
        window.matchMedia("(display-mode: standalone)").matches || nav.standalone === true
          ? "standalone"
          : "browser";
      const visibility =
        document.visibilityState === "visible"
          ? "visible"
          : document.visibilityState === "hidden"
            ? "hidden"
            : "unknown";
      patch({ displayMode, visibility, online: navigator.onLine });
    };
    const initialise = async () => {
      const manifestLinked = [...document.querySelectorAll<HTMLLinkElement>('link[rel="manifest"]')]
        .some((link) => new URL(link.href, location.href).pathname === "/driver/manifest.webmanifest");
      let serviceWorker: CapabilitySnapshot["serviceWorker"] = "unavailable";
      if ("serviceWorker" in navigator) {
        try {
          serviceWorker = (await navigator.serviceWorker.getRegistration("/driver"))
            ? "registered"
            : "not-registered";
        } catch {
          serviceWorker = "unavailable";
        }
      }
      if (!cancelled) {
        patch({ secureContext: window.isSecureContext, manifestLinked, serviceWorker });
        setBrowser({ userAgent: navigator.userAgent, platform: navigator.platform });
        observe();
        setPassiveReady(true);
      }
    };
    void initialise();
    window.addEventListener("online", observe);
    window.addEventListener("offline", observe);
    document.addEventListener("visibilitychange", observe);
    return () => {
      cancelled = true;
      window.removeEventListener("online", observe);
      window.removeEventListener("offline", observe);
      document.removeEventListener("visibilitychange", observe);
    };
  }, [patch]);

  useEffect(() => {
    if (!("permissions" in navigator)) return;
    let status: PermissionStatus | undefined;
    const update = () => {
      if (!status) return;
      const state = status.state;
      setSnapshot((current) => ({
        ...current,
        location: reconcileLocationPermission(current.location, state),
      }));
    };
    void navigator.permissions
      .query({ name: "geolocation" })
      .then((value) => {
        status = value;
        update();
        status.addEventListener("change", update);
      })
      .catch(() => undefined);
    return () => status?.removeEventListener("change", update);
  }, []);

  const assessment = useMemo(() => assessPilotPwa(snapshot), [snapshot]);
  const report = useMemo(
    () =>
      JSON.stringify(
        {
          contractVersion: R14A_CONTRACT_VERSION,
          sessionProbePath: R14A_SESSION_PROBE_PATH,
          observedAt: new Date().toISOString(),
          userAgent: browser.userAgent,
          platform: browser.platform,
          snapshot,
          assessment,
          protocol: D15_D16_PROTOCOL,
          redaction: "No coordinates, trip IDs, tokens or backend payloads are retained.",
        },
        null,
        2,
      ),
    [assessment, browser, snapshot],
  );

  async function run(name: Probe, task: () => Promise<string>) {
    setBusy(name);
    try {
      setNotice(await task());
    } catch {
      setNotice(`${name} probe failed closed.`);
    } finally {
      setBusy(null);
    }
  }

  const probeQueue = () =>
    run("queue", async () => {
      if (!("indexedDB" in window)) {
        patch({ indexedDb: "unavailable", durableQueue: "failed" });
        return "IndexedDB is unavailable.";
      }
      const name = `r14-a-probe-${Date.now()}-${Math.random()}`;
      let queue: PingQueue | undefined;
      try {
        queue = await openPingQueue(name);
        await queue.addPing(SYNTHETIC_TRIP, {
          recorded_at: "2000-01-01T00:00:00.000Z",
          lat: 0,
          lon: 0,
          accuracy_m: 1,
          speed_mps: 0,
          heading_degrees: null,
        });
        const first = await queue.cutBatch(SYNTHETIC_TRIP, 1);
        if (!first) throw new Error("batch not cut");
        const payload = JSON.stringify(first.pings);
        queue.close();
        queue = await openPingQueue(name);
        patch({ indexedDb: "pass" });
        const reopened = (await queue.listBatches(SYNTHETIC_TRIP))[0];
        const meta = await queue.meta(SYNTHETIC_TRIP);
        if (!reopened || reopened.key !== first.key || JSON.stringify(reopened.pings) !== payload || meta.batchesCut !== 1 || meta.pingsRecorded !== 1)
          throw new Error("identity/watermark changed after reload");
        await queue.recordAttempt(first.key);
        const retried = (await queue.listBatches(SYNTHETIC_TRIP))[0];
        if (!retried || retried.key !== first.key || retried.attempts !== 1)
          throw new Error("retry identity changed");
        await queue.dropBatch(first.key);
        if ((await queue.listBatches(SYNTHETIC_TRIP)).length) throw new Error("dead letter retained");
        await queue.forgetTrip(SYNTHETIC_TRIP);
        patch({ indexedDb: "pass", durableQueue: "pass" });
        return "Durable queue probe passed: reload, stable retry identity and dead-letter removal.";
      } catch {
        patch({ durableQueue: "failed" });
        return "Durable queue probe failed closed.";
      } finally {
        queue?.close();
        await deleteDatabase(name).catch(() => undefined);
      }
    });

  const probeLocks = () =>
    run("locks", async () => {
      const state = await probeExclusiveWebLock((navigator as NavigatorWithPwa).locks);
      patch({ webLocks: state });
      return state === "pass" ? "Web Locks probe passed." : `Web Locks probe returned ${state}.`;
    });
  const probeWake = () =>
    run("wake", async () => {
      const state = await probeScreenWakeLock((navigator as NavigatorWithPwa).wakeLock);
      patch({ wakeLock: state });
      return state === "pass" ? "Screen Wake Lock probe passed." : `Screen Wake Lock probe returned ${state}.`;
    });
  const probeLocation = () =>
    run("location", async () => {
      const state = await probeForegroundLocation(navigator.geolocation);
      patch({ location: state });
      return `Foreground location probe returned ${state}; the position was discarded.`;
    });
  const probeSession = () =>
    run("session", async () => {
      const state = await probeBffSession(fetch, navigator.onLine);
      patch({ session: state });
      return state === "valid" ? "BFF session probe passed." : `BFF session probe returned ${state}.`;
    });

  if (!passiveReady) return <p role="status">Observing passive PWA capabilities…</p>;
  const buttons: Array<[Probe, string, () => void]> = [
    ["queue", "Test storage + queue", probeQueue],
    ["locks", "Test Web Locks", probeLocks],
    ["wake", "Test screen wake lock", probeWake],
    ["session", "Test BFF session", probeSession],
    ["location", "Test foreground location", probeLocation],
  ];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="micro text-amber">R14-A · contract {R14A_CONTRACT_VERSION}</p>
        <h1 className="mt-1 text-2xl font-semibold">Production PWA capability probe</h1>
        <p className="text-muted mt-2 text-sm leading-6">
          Probe-only: no trip mutation, ping upload, or location request before its button.
        </p>
      </div>

      <section className="rounded border p-4">
        <p className="micro text-muted">State</p>
        <p className="mt-2 text-lg font-semibold">Health: {assessment.health}</p>
        <p className="text-muted mt-1 text-sm">
          Start {assessment.actions.start ? "allowed" : "blocked"} · capture {assessment.actions.capture ? "allowed" : "paused"} · End {assessment.actions.end ? "allowed" : "blocked"}
        </p>
      </section>

      <div className="grid grid-cols-2 gap-2">
        {buttons.map(([name, label, action]) => (
          <button key={name} type="button" onClick={action} disabled={busy !== null} className="rounded border p-3 text-sm disabled:opacity-50">
            {busy === name ? "Test…" : label}
          </button>
        ))}
      </div>
      <p role="status" className="text-muted text-sm">{notice}</p>

      <section aria-label="Capability decisions" className="flex flex-col gap-2">
        {assessment.results.map((item) => (
          <article key={item.id} data-testid={`capability-${item.id}`} data-status={item.status} className="rounded border p-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-medium">{item.label}</p>
              <code className="text-faint text-[10px]">{item.status}</code>
            </div>
            <p className="text-amber mt-1 font-mono text-[11px]">{item.code}</p>
            <p className="text-muted mt-1 text-xs leading-5">{item.summary}</p>
          </article>
        ))}
      </section>

      <section className="rounded border p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="micro text-muted">Redacted report</p>
          <button type="button" className="text-amber text-xs" onClick={() => void navigator.clipboard?.writeText(report)}>Copy</button>
        </div>
        <pre data-testid="capability-report" className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap text-[10px] leading-4">{report}</pre>
      </section>

      <p className="rounded border p-3 text-xs leading-5">
        R14-A remains TODO. Fable/R14-B owns physical Android/iPhone journey evidence, measurements, and independent reviews.
      </p>
    </div>
  );
}
