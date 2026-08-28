import { createServer } from "node:http";

const port = 38101;
const ids = {
  user: "20000000-0000-4000-8000-000000000001",
  profile: "20000000-0000-4000-8000-000000000002",
  vehicle: "20000000-0000-4000-8000-000000000003",
  campaign: "20000000-0000-4000-8000-000000000004",
  assignment: "20000000-0000-4000-8000-000000000005",
  heldTrip: "20000000-0000-4000-8000-000000000006",
  releasedTrip: "20000000-0000-4000-8000-000000000007",
  hold: "20000000-0000-4000-8000-000000000008",
  dispute: "20000000-0000-4000-8000-000000000009",
  notice: "20000000-0000-4000-8000-000000000010",
};
const states = new Map();

function send(response, status, payload) {
  response.writeHead(status, {
    "cache-control": "no-store",
    "content-type": "application/json",
  });
  response.end(JSON.stringify(payload));
}

function fail(response, status, code, message) {
  send(response, status, { error: { code, message, details: null } });
}

async function readBody(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {};
}

function bearer(request) {
  return request.headers.authorization?.replace(/^Bearer /, "") ?? "";
}

function scopeFromToken(token) {
  return token.replace(/^w401d-(driver|wrong-role|revoked)-/, "") || "default";
}

function state(scope) {
  if (!states.has(scope)) {
    states.set(scope, { dispute: null, resolved: false, disputeRequests: 0 });
  }
  return states.get(scope);
}

function assignment() {
  return {
    id: ids.assignment,
    campaign_id: ids.campaign,
    driver_profile_id: ids.profile,
    vehicle_id: ids.vehicle,
    assigned_by_user_id: ids.user,
    status: "completed",
    offered_at: "2026-08-01T08:00:00Z",
    accepted_at: "2026-08-01T09:00:00Z",
    activated_at: "2026-08-02T08:00:00Z",
    declined_at: null,
    expired_at: null,
    expires_at: null,
    deactivated_at: null,
    cancelled_at: null,
    completed_at: "2026-08-26T18:00:00Z",
    notes: null,
    offer_terms: null,
    offer_terms_sha256: null,
    metadata: {},
    created_at: "2026-08-01T08:00:00Z",
    updated_at: "2026-08-26T18:00:00Z",
    campaign: {
      id: ids.campaign,
      name: "Lagos Release Rehearsal",
      status: "completed",
      start_at: "2026-08-01T00:00:00Z",
      end_at: "2026-08-26T23:00:00Z",
    },
    vehicle: {
      id: ids.vehicle,
      plate_number: "SYN-401D",
      plate_country_code: "NG",
      vehicle_type: "car",
      status: "active",
    },
  };
}

function hold(current) {
  return {
    id: ids.hold,
    trip_session_id: ids.heldTrip,
    public_status: current.resolved ? "review_cleared" : "under_review",
    reason: {
      code: "route_pattern_review",
      title: "Route pattern needs review",
      body: "We are checking an unusual route pattern before releasing these earnings.",
      version: "v1",
    },
    detected_at: "2026-08-26T10:00:00Z",
    reviewed_at: current.resolved ? "2026-08-27T13:00:00Z" : null,
    dispute: current.dispute
      ? {
          id: ids.dispute,
          message: current.dispute,
          status: current.resolved ? "replied" : "open",
          submitted_at: "2026-08-27T12:00:00Z",
          reply: current.resolved ? "We reviewed the trip and cleared the earnings review." : null,
          replied_at: current.resolved ? "2026-08-27T13:00:00Z" : null,
        }
      : null,
    notices: current.resolved
      ? [
          {
            id: ids.notice,
            type_key: "fraud_dispute_replied",
            fraud_flag_id: ids.hold,
            fraud_dispute_id: ids.dispute,
            trip_session_id: ids.heldTrip,
            template_version: "v1",
            outcome: "review_cleared",
            created_at: "2026-08-27T13:00:00Z",
          },
        ]
      : [],
  };
}

function ledgerEntry(id, tripId, entryType, status, amount, description) {
  return {
    id,
    driver_profile_id: ids.profile,
    campaign_id: ids.campaign,
    vehicle_id: ids.vehicle,
    trip_session_id: tripId,
    payout_calculation_id: null,
    entry_type: entryType,
    status,
    amount,
    currency: "NGN",
    description,
    metadata: {},
    occurred_at: "2026-08-26T18:00:00Z",
    created_at: "2026-08-26T18:00:00Z",
  };
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", `http://127.0.0.1:${port}`);

  if (url.pathname === "/health") return send(response, 200, { status: "ok" });
  if (request.method === "GET" && url.pathname === "/__test__/state") {
    const current = state(url.searchParams.get("scope") ?? "default");
    return send(response, 200, current);
  }
  if (request.method === "POST" && url.pathname === "/__test__/resolve") {
    const payload = await readBody(request);
    const current = state(String(payload.scope ?? "default"));
    current.resolved = true;
    return send(response, 200, current);
  }

  const token = bearer(request);
  if (!token) return fail(response, 401, "AUTH_REQUIRED", "Authentication required");
  if (token.startsWith("w401d-revoked-")) {
    return fail(response, 401, "SESSION_REVOKED", "Session revoked");
  }
  const scope = scopeFromToken(token);
  const current = state(scope);

  if (request.method === "GET" && url.pathname === "/api/v1/me") {
    return send(response, 200, {
      advertiser_organization: null,
      user: {
        id: ids.user,
        email: "synthetic-driver@example.invalid",
        full_name: "Synthetic Driver",
        phone: null,
        role: token.startsWith("w401d-wrong-role-") ? "advertiser" : "driver",
        status: "active",
        must_change_password: false,
      },
    });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/notifications/unread-count") {
    return send(response, 200, { unread_count: current.resolved ? 1 : 0 });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/notifications") {
    const items = current.resolved
      ? [
          {
            id: ids.notice,
            title: "Trip review completed",
            body: "Staff completed their review of a trip.",
            channel: "in_app",
            type_key: "fraud_review_resolved",
            created_at: "2026-08-27T13:00:00Z",
            read_at: null,
          },
        ]
      : [];
    return send(response, 200, { items, total: items.length, limit: 50, offset: 0 });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/advertiser/dashboard/summary") {
    return send(response, 200, {
      impressions: {
        estimated_impressions: null,
        estimated_trip_count: null,
        average_confidence_score: null,
      },
      campaigns: { active: 0, total: 0 },
      assignments: { active: 0 },
      trips: { total: 0 },
      costs: { totals_by_currency: [] },
      quality: { fraud_flags: { open: 0 } },
    });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/driver/earnings/summary") {
    return send(response, 200, {
      driver_profile_id: ids.profile,
      totals_by_currency: [
        {
          currency: "NGN",
          batch_payable_amount: "4000.00",
          pending_amount: current.resolved ? "0.00" : "1250.00",
          released_available_amount: current.resolved ? "4250.00" : "3000.00",
          available_amount: current.resolved ? "4250.00" : "3000.00",
          cash_paid_amount: "2000.00",
          paid_amount: "2000.00",
          carry_forward_debt_amount: "250.00",
          voided_amount: "100.00",
          lifetime_earned_amount: "7250.00",
          ledger_entry_count: 5,
        },
      ],
    });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/driver/earnings/ledger") {
    const heldStatus = current.resolved ? "available" : "pending";
    const items = [
      ledgerEntry(
        "21000000-0000-4000-8000-000000000001",
        ids.heldTrip,
        "trip_payout",
        heldStatus,
        "1250.00",
        "Held trip payout",
      ),
      ledgerEntry(
        "21000000-0000-4000-8000-000000000002",
        ids.releasedTrip,
        "trip_payout",
        "available",
        "3000.00",
        "Released trip payout",
      ),
      ledgerEntry(
        "21000000-0000-4000-8000-000000000003",
        null,
        "adjustment",
        "paid",
        "2000.00",
        "Paid adjustment",
      ),
      ledgerEntry(
        "21000000-0000-4000-8000-000000000004",
        null,
        "debt_remainder",
        "pending",
        "250.00",
        "Debt remainder",
      ),
      ledgerEntry(
        "21000000-0000-4000-8000-000000000005",
        null,
        "reversal",
        "voided",
        "100.00",
        "Voided reversal",
      ),
    ];
    return send(response, 200, { items, total: items.length, limit: 50, offset: 0 });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/driver/fraud-holds") {
    const items =
      !url.searchParams.get("trip_session_id") ||
      url.searchParams.get("trip_session_id") === ids.heldTrip
        ? [hold(current)]
        : [];
    return send(response, 200, { items });
  }
  if (
    request.method === "GET" &&
    url.pathname === `/api/v1/driver/trips/${ids.heldTrip}/earnings-breakdown`
  ) {
    return send(response, 200, {
      trip_session_id: ids.heldTrip,
      formula_version: "payout_v3",
      amount: "1250.00",
      currency: "NGN",
      hourly_rate: "1000.00",
      eligible_seconds: 4500,
      capped_seconds: 4500,
      excluded_seconds_by_reason: { gps_gap: 60 },
      cap: { lagos_day: "2026-08-26", day_payable_seconds: 4500, cap_seconds: 28800 },
      entries: [
        ledgerEntry(
          "21000000-0000-4000-8000-000000000001",
          ids.heldTrip,
          "trip_payout",
          current.resolved ? "available" : "pending",
          "1250.00",
          "Held trip payout",
        ),
      ],
      superseded_by_recompute: false,
      base_payable_seconds: 3600,
      premium_payable_seconds: 900,
      base_hourly_rate: "1000.00",
      premium_hourly_rate: "1000.00",
      base_amount: "1000.00",
      premium_amount: "250.00",
    });
  }
  if (
    request.method === "POST" &&
    url.pathname === `/api/v1/driver/fraud-holds/${ids.hold}/disputes`
  ) {
    const payload = await readBody(request);
    current.disputeRequests += 1;
    if (current.dispute && current.dispute !== payload.message) {
      return fail(response, 409, "DISPUTE_ALREADY_EXISTS", "A different dispute already exists");
    }
    current.dispute = String(payload.message);
    return send(response, 200, {
      id: ids.dispute,
      message: current.dispute,
      status: "open",
      submitted_at: "2026-08-27T12:00:00Z",
      reply: null,
      replied_at: null,
    });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/driver/campaign-assignments") {
    const wanted = url.searchParams.get("status");
    const items = !wanted || wanted === "completed" ? [assignment()] : [];
    return send(response, 200, {
      items,
      total: items.length,
      limit: Number(url.searchParams.get("limit") ?? 50),
      offset: 0,
    });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/driver/campaign-assignments/active") {
    return send(response, 200, { assignment: null });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/driver/trips/current") {
    return send(response, 200, { trip: null });
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
      id: "22000000-0000-4000-8000-000000000001",
      driver_profile_id: ids.profile,
      status: "approved",
      version: 1,
      masked_nin: "*******0000",
      document_file_ids: {},
    });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/driver/vehicles") {
    return send(response, 200, { items: [assignment().vehicle], total: 1, limit: 100, offset: 0 });
  }
  if (
    request.method === "GET" &&
    url.pathname === `/api/v1/driver/vehicles/${ids.vehicle}/evidence-current`
  ) {
    return send(response, 200, {
      id: "22000000-0000-4000-8000-000000000002",
      vehicle_id: ids.vehicle,
      status: "approved",
      snapshot_trusted: true,
      version: 1,
      document_file_ids: {},
    });
  }
  if (request.method === "GET" && url.pathname === "/api/v1/driver/installation-evidence/policy") {
    return send(response, 200, { configured: false, can_upload: false, required_views: [] });
  }
  if (
    request.method === "GET" &&
    url.pathname === "/api/v1/driver/evidence-verifications/pending"
  ) {
    return send(response, 200, { items: [] });
  }

  return fail(response, 404, "NOT_FOUND", "Synthetic route was not found");
});

server.listen(port, "127.0.0.1");
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
