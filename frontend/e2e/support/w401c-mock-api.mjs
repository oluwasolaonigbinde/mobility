import { createServer } from "node:http";
import { createHash } from "node:crypto";

const port = 38100;
const w403bSynthetic = process.env.W403B_SYNTHETIC === "1";
const correlationId = "w403b-abuja-pilot-001";
const ids = {
  user: "10000000-0000-4000-8000-000000000001",
  profile: "10000000-0000-4000-8000-000000000002",
  vehicle: "10000000-0000-4000-8000-000000000003",
  campaign: "10000000-0000-4000-8000-000000000004",
  assignment: "10000000-0000-4000-8000-000000000005",
  trip: "10000000-0000-4000-8000-000000000006",
};
const trips = new Map();

const encoder = new TextEncoder();
const batchDomain = encoder.encode("cardvert.trip-batch.v2\0");

class CanonicalFloat {
  constructor(value) {
    this.value = value;
  }
}

function concat(...parts) {
  const result = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
  let offset = 0;
  for (const part of parts) {
    result.set(part, offset);
    offset += part.length;
  }
  return result;
}

function u32(value) {
  const result = new Uint8Array(4);
  new DataView(result.buffer).setUint32(0, value, false);
  return result;
}

function i64(value) {
  const result = new Uint8Array(8);
  new DataView(result.buffer).setBigInt64(0, BigInt(value), false);
  return result;
}

function binary64(value) {
  const result = new Uint8Array(8);
  new DataView(result.buffer).setFloat64(0, Object.is(value, -0) ? 0 : value, false);
  return result;
}

function compareBytes(left, right) {
  for (let index = 0; index < Math.min(left.length, right.length); index += 1) {
    if (left[index] !== right[index]) return left[index] - right[index];
  }
  return left.length - right.length;
}

function canonicalBytes(value) {
  if (value === null) return encoder.encode("n");
  if (value === false) return encoder.encode("f");
  if (value === true) return encoder.encode("t");
  if (value instanceof CanonicalFloat) return concat(encoder.encode("d"), binary64(value.value));
  if (typeof value === "number")
    return Number.isInteger(value)
      ? concat(encoder.encode("i"), i64(value))
      : concat(encoder.encode("d"), binary64(value));
  if (typeof value === "string") {
    const encoded = encoder.encode(value);
    return concat(encoder.encode("s"), u32(encoded.length), encoded);
  }
  if (Array.isArray(value))
    return concat(
      encoder.encode("a"),
      u32(value.length),
      ...value.map((item) => canonicalBytes(item)),
    );
  const entries = Object.entries(value).sort(([left], [right]) =>
    compareBytes(encoder.encode(left), encoder.encode(right)),
  );
  return concat(
    encoder.encode("o"),
    u32(entries.length),
    ...entries.flatMap(([key, item]) => [canonicalBytes(key), canonicalBytes(item)]),
  );
}

function batchPayloadHash(pings) {
  const value = {
    pings: pings.map((ping) => ({
      recorded_at_ms: Date.parse(ping.recorded_at),
      lat: new CanonicalFloat(ping.lat),
      lon: new CanonicalFloat(ping.lon),
      accuracy_m: ping.accuracy_m === null ? null : new CanonicalFloat(ping.accuracy_m),
      speed_mps: ping.speed_mps === null ? null : new CanonicalFloat(ping.speed_mps),
      heading_degrees:
        ping.heading_degrees === null ? null : new CanonicalFloat(ping.heading_degrees),
      altitude_m: null,
      sequence_number: ping.sequence_number,
      metadata: {},
    })),
    metadata: {},
  };
  return createHash("sha256")
    .update(concat(batchDomain, canonicalBytes(value)))
    .digest("hex");
}

function send(response, status, body) {
  response.writeHead(status, {
    "cache-control": "no-store",
    "content-type": "application/json",
  });
  response.end(JSON.stringify(body));
}

function fail(response, status, code, message) {
  send(response, status, { error: { code, message, details: null } });
}

async function body(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {};
}

function token(request) {
  return request.headers.authorization?.replace(/^Bearer /, "") ?? "";
}

function assignment() {
  return {
    id: ids.assignment,
    campaign_id: ids.campaign,
    driver_profile_id: ids.profile,
    vehicle_id: ids.vehicle,
    status: "active",
    campaign: {
      id: ids.campaign,
      name: w403bSynthetic
        ? `Synthetic Abuja Campaign · ${correlationId}`
        : "Synthetic Lagos Campaign",
    },
    vehicle: { id: ids.vehicle, plate_number: "SYN-001" },
  };
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", `http://127.0.0.1:${port}`);
  const authToken = token(request);
  const degraded = authToken === "w401c-degraded";

  if (url.pathname === "/health") return send(response, 200, { status: "ok" });
  if (url.pathname === "/__test__/state") {
    const current = trips.get(`w403b-driver-${correlationId}`);
    return send(response, 200, {
      correlation_id: correlationId,
      city: w403bSynthetic ? "Abuja" : "Lagos",
      identities: [
        "w403b-advertiser@cardvert.invalid",
        "w403b-admin@cardvert.invalid",
        "w403b-driver@cardvert.invalid",
      ],
      trip_status: current?.status ?? "not_started",
      synthetic_ping_batches: current?.pingBatches ?? 0,
      live_gps_claims: 0,
      live_report_issuances: 0,
      live_payout_submissions: 0,
      live_ad_activations: 0,
    });
  }
  if (!authToken) return fail(response, 401, "AUTH_REQUIRED", "Authentication required");

  if (request.method === "GET" && url.pathname === "/api/v1/me") {
    return send(response, 200, {
      advertiser_organization: null,
      user: {
        id: ids.user,
        email: "synthetic-driver@example.invalid",
        full_name: "Synthetic Driver",
        phone: null,
        role: "driver",
        status: "active",
        must_change_password: false,
      },
    });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/driver/profile") {
    return send(response, 200, {
      id: ids.profile,
      user_id: ids.user,
      full_name: "Synthetic Driver",
      email: "synthetic-driver@example.invalid",
      license_number: "SYNTHETIC",
      service_city: w403bSynthetic ? "Abuja" : "Lagos",
      country_code: "NG",
      onboarding_status: "active",
    });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/driver/kyc/current") {
    return send(response, 200, {
      id: "10000000-0000-4000-8000-000000000007",
      driver_profile_id: ids.profile,
      status: "approved",
      version: 1,
      masked_nin: "*******0000",
      document_file_ids: {},
    });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/driver/vehicles") {
    return send(response, 200, {
      items: [
        {
          id: ids.vehicle,
          plate_number: "SYN-001",
          plate_country_code: "NG",
          vehicle_type: "car",
          status: "active",
        },
      ],
      total: 1,
      limit: 100,
      offset: 0,
    });
  }
  if (request.method === "GET" && url.pathname === `/api/v1/driver/vehicles/${ids.vehicle}`) {
    return send(response, 200, {
      id: ids.vehicle,
      plate_number: "SYN-001",
      status: "active",
    });
  }
  if (
    request.method === "GET" &&
    url.pathname === `/api/v1/driver/vehicles/${ids.vehicle}/evidence-current`
  ) {
    if (degraded)
      return fail(response, 503, "STORAGE_UNAVAILABLE", "Evidence authority is unavailable");
    return send(response, 200, {
      id: "10000000-0000-4000-8000-000000000008",
      vehicle_id: ids.vehicle,
      status: "approved",
      snapshot_trusted: true,
      version: 1,
      document_file_ids: {},
    });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/driver/campaign-assignments/active") {
    return send(response, 200, { assignment: assignment() });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/driver/campaign-assignments") {
    const status = url.searchParams.get("status");
    const items = !status || status === "active" ? [assignment()] : [];
    return send(response, 200, { items, total: items.length, limit: 50, offset: 0 });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/driver/trips/current") {
    const activeTrip = trips.get(authToken);
    return send(response, 200, {
      trip:
        activeTrip?.status === "active"
          ? { id: ids.trip, status: "active", evidence_protocol_version: 2 }
          : null,
    });
  }
  if (request.method === "POST" && url.pathname === "/api/v1/driver/trips/start") {
    trips.set(authToken, { status: "active", pingBatches: 0 });
    return send(response, 201, {
      id: ids.trip,
      status: "active",
      assignment_id: ids.assignment,
      evidence_protocol_version: 2,
    });
  }
  if (request.method === "GET" && url.pathname === `/api/v1/driver/trips/${ids.trip}`) {
    return trips.get(authToken)?.status === "active"
      ? send(response, 200, { id: ids.trip, status: "active", evidence_protocol_version: 2 })
      : fail(response, 404, "TRIP_NOT_FOUND", "Trip was not found");
  }
  if (request.method === "POST" && url.pathname === `/api/v1/driver/trips/${ids.trip}/pings`) {
    const payload = await body(request);
    const current = trips.get(authToken);
    if (current) current.pingBatches += 1;
    const pings = payload.pings ?? [];
    return send(response, 200, {
      batch_id: "10000000-0000-4000-8000-000000000009",
      trip_id: ids.trip,
      batch_sequence: payload.batch_sequence,
      payload_hash_version: 2,
      payload_hash: batchPayloadHash(pings),
      submitted_count: pings.length,
      accepted_count: pings.length,
      rejected_count: 0,
      outcome: "accepted",
      receipt_format_version: 2,
      receipt_key_version: 1,
      receipt_signature: "w403b-synthetic-signed-receipt",
      duplicate: false,
      quarantined: false,
      sample_results: pings.map((ping, index) => ({
        index,
        sequence_number: ping.sequence_number ?? null,
        status: "accepted",
        rejection_code: null,
      })),
    });
  }
  if (request.method === "POST" && url.pathname === `/api/v1/driver/trips/${ids.trip}/end`) {
    const current = trips.get(authToken);
    trips.set(authToken, { status: "sealed", pingBatches: current?.pingBatches ?? 0 });
    return send(response, 200, { id: ids.trip, status: "sealed" });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/driver/earnings/ledger") {
    return send(response, 200, { items: [], total: 0, limit: 4, offset: 0 });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/notifications/unread-count") {
    return send(response, 200, { unread_count: 0 });
  }

  return fail(response, 404, "NOT_FOUND", "Synthetic route was not found");
});

server.listen(port, "127.0.0.1");

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
