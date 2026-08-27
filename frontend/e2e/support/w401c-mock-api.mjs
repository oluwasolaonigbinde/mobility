import { createServer } from "node:http";

const port = 38100;
const ids = {
  user: "10000000-0000-4000-8000-000000000001",
  profile: "10000000-0000-4000-8000-000000000002",
  vehicle: "10000000-0000-4000-8000-000000000003",
  campaign: "10000000-0000-4000-8000-000000000004",
  assignment: "10000000-0000-4000-8000-000000000005",
  trip: "10000000-0000-4000-8000-000000000006",
};
const trips = new Map();

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
    campaign: { id: ids.campaign, name: "Synthetic Lagos Campaign" },
    vehicle: { id: ids.vehicle, plate_number: "SYN-001" },
  };
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", `http://127.0.0.1:${port}`);
  const authToken = token(request);
  const degraded = authToken === "w401c-degraded";

  if (url.pathname === "/health") return send(response, 200, { status: "ok" });
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
      service_city: "Lagos",
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
    return send(response, 200, { trip: activeTrip ? { id: ids.trip, status: "active" } : null });
  }
  if (request.method === "POST" && url.pathname === "/api/v1/driver/trips/start") {
    trips.set(authToken, true);
    return send(response, 201, { id: ids.trip, status: "active", assignment_id: ids.assignment });
  }
  if (request.method === "GET" && url.pathname === `/api/v1/driver/trips/${ids.trip}`) {
    return trips.get(authToken)
      ? send(response, 200, { id: ids.trip, status: "active" })
      : fail(response, 404, "TRIP_NOT_FOUND", "Trip was not found");
  }
  if (request.method === "POST" && url.pathname === `/api/v1/driver/trips/${ids.trip}/pings`) {
    const payload = await body(request);
    return send(response, 200, {
      batch_id: "10000000-0000-4000-8000-000000000009",
      trip_id: ids.trip,
      accepted_count: payload.pings?.length ?? 0,
      duplicate: false,
      quarantined: false,
    });
  }
  if (request.method === "POST" && url.pathname === `/api/v1/driver/trips/${ids.trip}/end`) {
    trips.delete(authToken);
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
