import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const PROJECT_PATTERN = /^cardvert-r59-[a-z0-9-]+$/;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required for R59`);
  return value;
}

const project = required("R59_PROJECT");
if (!PROJECT_PATTERN.test(project)) throw new Error("invalid R59 project scope");

const root = path.resolve(__dirname, "../../..");
const composeFiles = [
  "-f",
  path.join(root, "docker-compose.yml"),
  "-f",
  path.join(root, "frontend/e2e/support/docker-compose.r59.yml"),
];

function compose(args: string[], capture = false): string {
  const output = execFileSync(
    "docker",
    ["compose", "-p", project, "--profile", "full", ...composeFiles, ...args],
    {
      cwd: root,
      encoding: "utf8",
      stdio: capture ? ["ignore", "pipe", "pipe"] : "inherit",
    },
  );
  return typeof output === "string" ? output.trim() : "";
}

export function stopService(service: "api" | "worker"): void {
  compose(["stop", service]);
}

export function startService(service: "api" | "worker"): void {
  compose(["start", service]);
}

export async function waitForService(
  service: "api" | "worker",
  wanted: "ready" | "stopped",
  timeoutMs = 60_000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (service === "api") {
      try {
        const response = await fetch(
          `http://127.0.0.1:${process.env.R59_API_PORT ?? "48159"}/health`,
        );
        if ((wanted === "ready") === response.ok) return;
      } catch {
        if (wanted === "stopped") return;
      }
    } else {
      const id = compose(["ps", "-q", "worker"], true);
      const running = id
        ? execFileSync("docker", ["inspect", "-f", "{{.State.Running}}", id], {
            encoding: "utf8",
          }).trim() === "true"
        : false;
      if ((wanted === "ready") === running) return;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`${service} did not become ${wanted}`);
}

function assertTripId(tripId: string): void {
  if (!UUID_PATTERN.test(tripId)) throw new Error("invalid trip id");
}

function queryJson(sql: string): unknown {
  const output = compose(
    [
      "exec",
      "-T",
      "db",
      "psql",
      "-XAt",
      "-v",
      "ON_ERROR_STOP=1",
      "-U",
      "mobility",
      "-d",
      "mobility",
      "-c",
      sql,
    ],
    true,
  );
  if (!output) throw new Error("R59 SELECT returned no row");
  return JSON.parse(output);
}

export type TripSnapshot = {
  tripId: string;
  status: string;
  manifestRoot: string | null;
  manifestCount: number | null;
  manifestPingCount: number | null;
  sealReason: string | null;
  amount: string | null;
  currency: string | null;
  counts: {
    analytics: number;
    fraud: number;
    impression: number;
    payout: number;
    ledger: number;
    workerAudit: number;
  };
};

export function latestR59Trip(): TripSnapshot {
  return queryJson(`
    SELECT json_build_object(
      'tripId', t.id,
      'status', t.status,
      'manifestRoot', t.evidence_manifest_root_sha256,
      'manifestCount', t.evidence_manifest_batch_count,
      'manifestPingCount', t.evidence_manifest_ping_count,
      'sealReason', t.seal_reason,
      'amount', (SELECT final_payout::text FROM payout_calculations WHERE trip_session_id=t.id ORDER BY calculated_at DESC LIMIT 1),
      'currency', (SELECT currency FROM payout_calculations WHERE trip_session_id=t.id ORDER BY calculated_at DESC LIMIT 1),
      'counts', json_build_object(
        'analytics', (SELECT count(*) FROM trip_analytics WHERE trip_session_id=t.id),
        'fraud', (SELECT count(*) FROM fraud_assessments WHERE trip_session_id=t.id),
        'impression', (SELECT count(*) FROM impression_estimates WHERE trip_session_id=t.id),
        'payout', (SELECT count(*) FROM payout_calculations WHERE trip_session_id=t.id),
        'ledger', (SELECT count(*) FROM earnings_ledger_entries WHERE trip_session_id=t.id),
        'workerAudit', (SELECT count(*) FROM audit_events WHERE entity_id=t.id::text AND action='worker.trip_processing.completed')
      )
    )
    FROM trip_sessions t
    JOIN driver_profiles d ON d.id=t.driver_profile_id
    JOIN users u ON u.id=d.user_id
    WHERE u.email='driver@demo.mobility.local'
    ORDER BY t.created_at DESC
    LIMIT 1
  `) as TripSnapshot;
}

export function tripSnapshot(tripId: string): TripSnapshot {
  assertTripId(tripId);
  return queryJson(`
    SELECT json_build_object(
      'tripId', t.id, 'status', t.status,
      'manifestRoot', t.evidence_manifest_root_sha256,
      'manifestCount', t.evidence_manifest_batch_count,
      'manifestPingCount', t.evidence_manifest_ping_count,
      'sealReason', t.seal_reason,
      'amount', (SELECT final_payout::text FROM payout_calculations WHERE trip_session_id=t.id ORDER BY calculated_at DESC LIMIT 1),
      'currency', (SELECT currency FROM payout_calculations WHERE trip_session_id=t.id ORDER BY calculated_at DESC LIMIT 1),
      'counts', json_build_object(
        'analytics', (SELECT count(*) FROM trip_analytics WHERE trip_session_id=t.id),
        'fraud', (SELECT count(*) FROM fraud_assessments WHERE trip_session_id=t.id),
        'impression', (SELECT count(*) FROM impression_estimates WHERE trip_session_id=t.id),
        'payout', (SELECT count(*) FROM payout_calculations WHERE trip_session_id=t.id),
        'ledger', (SELECT count(*) FROM earnings_ledger_entries WHERE trip_session_id=t.id),
        'workerAudit', (SELECT count(*) FROM audit_events WHERE entity_id=t.id::text AND action='worker.trip_processing.completed')
      )
    ) FROM trip_sessions t WHERE t.id='${tripId}'::uuid
  `) as TripSnapshot;
}

export function redisQueueDepth(): number {
  return Number(compose(["exec", "-T", "redis", "redis-cli", "ZCARD", "arq:queue"], true));
}

const forbiddenReceiptKeys =
  /email|password|token|cookie|latitude|longitude|location|signature|secret/i;

export function assertNoSensitiveReceiptData(value: unknown): void {
  if (!value || typeof value !== "object") return;
  for (const [key, nested] of Object.entries(value)) {
    if (forbiddenReceiptKeys.test(key)) throw new Error(`sensitive receipt key: ${key}`);
    assertNoSensitiveReceiptData(nested);
  }
}

export function sanitizeReceipt(value: Record<string, unknown>): Record<string, unknown> {
  assertNoSensitiveReceiptData(value);
  return JSON.parse(JSON.stringify(value)) as Record<string, unknown>;
}

export function writeReceipt(snapshot: TripSnapshot): string {
  const receipt = sanitizeReceipt({
    schema: "r59-real-stack-v1",
    gitSha: required("R59_GIT_SHA"),
    leasedFilesDigest: required("R59_LEASED_FILES_DIGEST"),
    imageIds: required("R59_IMAGE_IDS").split(",").sort(),
    project,
    tripId: snapshot.tripId,
    state: snapshot.status,
    sealReason: snapshot.sealReason,
    manifestRoot: snapshot.manifestRoot,
    manifestCount: snapshot.manifestCount,
    manifestPingCount: snapshot.manifestPingCount,
    counts: snapshot.counts,
    amount: snapshot.amount,
    currency: snapshot.currency,
  });
  const canonical = JSON.stringify(receipt);
  const bound = { ...receipt, receiptHash: createHash("sha256").update(canonical).digest("hex") };
  const directory = required("R59_ARTIFACT_DIR");
  mkdirSync(directory, { recursive: true });
  const filename = path.join(directory, "R59_REAL_STACK_RECEIPT.json");
  writeFileSync(filename, `${JSON.stringify(bound, null, 2)}\n`, { mode: 0o600 });
  return filename;
}
