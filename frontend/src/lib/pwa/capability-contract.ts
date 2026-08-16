export const R14A_CONTRACT_VERSION = "r14-a-v1" as const;
export const R14A_SESSION_PROBE_PATH = "/driver/capabilities?session-probe=1" as const;

export const D15_D16_PROTOCOL = {
  version: "d15-d16-v1",
  auth: { boundary: "next-bff-http-only-cookie", browserBearerToken: false },
  queue: {
    storage: "indexeddb",
    singleWriter: "web-locks-exclusive",
    idempotencyKey: "mint-once-at-batch-cut",
    retry: "reuse-identical-key-and-payload",
    ackDeletes: ["accepted", "duplicate", "quarantined"],
    terminalHttpStatuses: [400, 409, 422],
    terminalAction: "dead-letter-without-rekey",
  },
  watermark: {
    sealPredicate: "server-batch-count-gte-client-batch-count",
    clientPingCount: "diagnostic-only",
    clientComplete: "diagnostic-queue-health-only",
  },
  lifecycle: ["active", "ended", "sealed"],
  lateData: {
    endedTrip: "accept-with-end-skew-bound",
    assignmentActiveGate: "not-required-for-ended-delivery",
    graceSeal: true,
  },
  quarantine: {
    postSealBatches: "preserve-never-reject",
    resolution: "audited-admin-apply-or-discard",
    applyRequiresInitialPayout: true,
    applyAutoRecomputesMoney: false,
    preSealAnalyticsReusableForMoney: false,
  },
} as const;

export type CapabilityStatus = "supported" | "degraded" | "rejected";
export type TrackingHealth = "active" | "degraded" | "stopped";
export type ProbeState<T extends string> = T | "unprobed";
export type CapabilitySnapshot = {
  secureContext: boolean;
  manifestLinked: boolean;
  serviceWorker: ProbeState<"registered" | "not-registered" | "unavailable">;
  displayMode: "standalone" | "browser" | "unknown";
  visibility: "visible" | "hidden" | "unknown";
  online: boolean;
  location: ProbeState<"granted" | "prompt" | "denied" | "revoked" | "unavailable">;
  indexedDb: ProbeState<"pass" | "failed" | "unavailable">;
  durableQueue: ProbeState<"pass" | "failed">;
  webLocks: ProbeState<"pass" | "contended" | "denied" | "unavailable">;
  wakeLock: ProbeState<"pass" | "released" | "denied" | "unavailable">;
  session: ProbeState<"valid" | "invalid" | "unavailable" | "offline">;
};

export const EMPTY_CAPABILITY_SNAPSHOT: CapabilitySnapshot = {
  secureContext: false,
  manifestLinked: false,
  serviceWorker: "unprobed",
  displayMode: "unknown",
  visibility: "unknown",
  online: true,
  location: "unprobed",
  indexedDb: "unprobed",
  durableQueue: "unprobed",
  webLocks: "unprobed",
  wakeLock: "unprobed",
  session: "unprobed",
};

export type CapabilityId =
  | "installability"
  | "screen-on"
  | "visibility-background"
  | "location"
  | "offline-reload"
  | "indexeddb-storage"
  | "web-locks"
  | "bff-session"
  | "start-end"
  | "d15-d16-protocol"
  | "background-capture";
export type CapabilityResult = {
  id: CapabilityId;
  label: string;
  status: CapabilityStatus;
  code: string;
  summary: string;
  blocking: boolean;
};
export type CapabilityAssessment = {
  contractVersion: typeof R14A_CONTRACT_VERSION;
  health: TrackingHealth;
  actions: { start: boolean; capture: boolean; end: boolean };
  results: CapabilityResult[];
  blockingCodes: string[];
};

function row(
  id: CapabilityId,
  label: string,
  status: CapabilityStatus,
  code: string,
  summary: string,
  blocking = true,
): CapabilityResult {
  return { id, label, status, code, summary, blocking };
}

function installability(s: CapabilitySnapshot): CapabilityResult {
  if (!s.secureContext)
    return row("installability", "Installability", "rejected", "INSECURE_CONTEXT", "HTTPS required.");
  if (!s.manifestLinked)
    return row("installability", "Installability", "rejected", "MANIFEST_MISSING", "Manifest missing.");
  if (s.serviceWorker === "unavailable")
    return row("installability", "Installability", "rejected", "SERVICE_WORKER_UNAVAILABLE", "Service workers unavailable.");
  if (s.serviceWorker !== "registered")
    return row("installability", "Installability", "degraded", `SERVICE_WORKER_${s.serviceWorker.toUpperCase().replace("-", "_")}`, "Registration not proven.");
  if (s.displayMode !== "standalone")
    return row("installability", "Installability", "degraded", "NOT_STANDALONE", "Installed standalone PWA required.");
  return row("installability", "Installability", "supported", "INSTALLED_STANDALONE", "Standalone PWA proven.");
}

function stateRow(
  id: CapabilityId,
  label: string,
  state: string,
  pass: string,
  failures: Record<string, [string, string]>,
  degraded: string[] = [],
): CapabilityResult {
  if (state === pass) return row(id, label, "supported", `${id.toUpperCase().replaceAll("-", "_")}_PROVEN`, `${label} is proven.`);
  const [code, summary] = failures[state] ?? [`${id.toUpperCase().replaceAll("-", "_")}_UNPROBED`, `${label} requires its explicit probe.`];
  return row(id, label, state === "unprobed" || degraded.includes(state) ? "degraded" : "rejected", code, summary);
}

export function reconcileLocationPermission(
  current: CapabilitySnapshot["location"],
  state: PermissionState,
): CapabilitySnapshot["location"] {
  if (state === "denied") return current === "granted" ? "revoked" : "denied";
  if (state === "prompt") return current === "granted" ? "revoked" : "prompt";
  return current === "granted" ? "granted" : "unprobed";
}

export function assessPilotPwa(s: CapabilitySnapshot): CapabilityAssessment {
  const results: CapabilityResult[] = [
    installability(s),
    stateRow("screen-on", "Screen Wake Lock", s.wakeLock, "pass", {
      released: ["WAKE_LOCK_RELEASED", "Wake lock released; capture pauses."],
      denied: ["WAKE_LOCK_DENIED", "Wake lock denied."],
      unavailable: ["WAKE_LOCK_UNAVAILABLE", "Wake lock unavailable."],
    }),
    s.visibility === "visible"
      ? row("visibility-background", "Foreground visibility", "supported", "FOREGROUND_VISIBLE", "Visible.")
      : s.visibility === "hidden"
        ? row("visibility-background", "Foreground visibility", "degraded", "BACKGROUND_PAUSED", "Background capture paused.")
        : row("visibility-background", "Foreground visibility", "rejected", "VISIBILITY_UNKNOWN", "Visibility unknown."),
    stateRow("location", "Foreground location", s.location, "granted", {
      prompt: ["LOCATION_UNPROBED", "Explicit location probe required."],
      denied: ["LOCATION_DENIED", "Location denied."],
      revoked: ["LOCATION_REVOKED", "Location revoked."],
      unavailable: ["LOCATION_UNAVAILABLE", "Location unavailable."],
    }, ["prompt"]),
    stateRow("indexeddb-storage", "IndexedDB storage", s.indexedDb, "pass", {
      failed: ["INDEXEDDB_FAILED", "IndexedDB probe failed."],
      unavailable: ["INDEXEDDB_UNAVAILABLE", "IndexedDB unavailable."],
    }),
    stateRow("offline-reload", "Durable queue/reload", s.durableQueue, "pass", {
      failed: ["DURABLE_QUEUE_FAILED", "Queue contract failed."],
    }),
    stateRow("web-locks", "Exclusive Web Locks", s.webLocks, "pass", {
      contended: ["WEB_LOCK_CONTENDED", "Writer lock contended."],
      denied: ["WEB_LOCK_DENIED", "Lock request failed."],
      unavailable: ["WEB_LOCKS_UNAVAILABLE", "Web Locks unavailable."],
    }),
    stateRow("bff-session", "BFF session", s.session, "valid", {
      invalid: ["SESSION_INVALID", "Session invalid."],
      unavailable: ["SESSION_UNAVAILABLE", "Session unavailable."],
      offline: ["SESSION_OFFLINE", "Session offline."],
    }, ["unavailable", "offline"]),
    row("d15-d16-protocol", "D15/D16 protocol", "supported", "D15_D16_FROZEN", "Protocol unchanged."),
    row("background-capture", "Background capture", "rejected", "BACKGROUND_CAPTURE_OUT_OF_SCOPE", "Foreground-only pilot.", false),
  ];

  const installed = results[0]?.status === "supported";
  const healthyQueue = s.indexedDb === "pass" && s.durableQueue === "pass";
  const ownsWriter = s.webLocks === "pass";
  const sessionUsableForCapture = s.session === "valid" || s.session === "unavailable" || s.session === "offline";
  const capture =
    installed &&
    s.visibility === "visible" &&
    s.location === "granted" &&
    s.wakeLock === "pass" &&
    healthyQueue &&
    ownsWriter &&
    sessionUsableForCapture;
  const start = capture && s.online && s.session === "valid";
  const end = s.online && s.session === "valid" && healthyQueue && ownsWriter;
  results.push(
    row(
      "start-end",
      "Start / capture / End",
      start && capture && end ? "supported" : end ? "degraded" : "rejected",
      start && capture && end ? "ACTIONS_READY" : end ? "SAFE_END_ONLY" : "ACTIONS_BLOCKED",
      `Start ${start ? "allowed" : "blocked"}; capture ${capture ? "allowed" : "paused"}; End ${end ? "allowed" : "blocked"}.`,
    ),
  );
  const blocking = results.filter((r) => r.blocking && r.status === "rejected");
  return {
    contractVersion: R14A_CONTRACT_VERSION,
    health: capture ? "active" : blocking.length ? "stopped" : "degraded",
    actions: { start, capture, end },
    results,
    blockingCodes: blocking.map((r) => r.code),
  };
}

export type WebLocksLike = {
  request<T>(name: string, options: { ifAvailable: true }, callback: (lock: object | null) => T | Promise<T>): Promise<T>;
};
export async function probeExclusiveWebLock(locks?: WebLocksLike, name = "r14-a-capability-probe"): Promise<CapabilitySnapshot["webLocks"]> {
  if (!locks) return "unavailable";
  try {
    return await locks.request(name, { ifAvailable: true }, async (lock) => {
      if (!lock) return "contended";
      return locks.request(name, { ifAvailable: true }, (nested) => (nested ? "denied" : "pass"));
    });
  } catch {
    return "denied";
  }
}

export type WakeLockLike = { request(type: "screen"): Promise<{ release(): Promise<void> }> };
export async function probeScreenWakeLock(wake?: WakeLockLike): Promise<CapabilitySnapshot["wakeLock"]> {
  if (!wake) return "unavailable";
  try {
    const sentinel = await wake.request("screen");
    await sentinel.release();
    return "pass";
  } catch {
    return "denied";
  }
}

export type GeolocationLike = {
  getCurrentPosition(success: PositionCallback, error: PositionErrorCallback, options?: PositionOptions): void;
};
export function probeForegroundLocation(geo?: GeolocationLike): Promise<CapabilitySnapshot["location"]> {
  if (!geo) return Promise.resolve("unavailable");
  return new Promise((resolve) =>
    geo.getCurrentPosition(
      () => resolve("granted"),
      (error) => resolve(error.code === 1 ? "denied" : "unavailable"),
      { enableHighAccuracy: true, maximumAge: 0, timeout: 20_000 },
    ),
  );
}

export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Pick<Response, "ok" | "status" | "type">>;
export async function probeBffSession(fetcher: FetchLike, online: boolean, path = R14A_SESSION_PROBE_PATH): Promise<CapabilitySnapshot["session"]> {
  if (!online) return "offline";
  try {
    const response = await fetcher(path, { cache: "no-store", credentials: "same-origin", redirect: "manual" });
    if (response.ok) return "valid";
    if (response.type === "opaqueredirect" || response.status === 0 || response.status === 401 || response.status === 403 || (response.status >= 300 && response.status < 400)) return "invalid";
    return "unavailable";
  } catch {
    return "unavailable";
  }
}
