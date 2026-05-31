PASS

Safe to commit: Yes. Commit Slice 8 before starting Slice 9.

The nested-transaction default-profile race recovery is sufficient for Slice 8 acceptance. The implementation also has a PostgreSQL partial unique index for active-default uniqueness and re-reads after IntegrityError, which is enough for this slice. A true concurrent race simulation test can be deferred unless the race becomes observable.

Basis: Slice 8 added exactly the approved traffic_density_profiles and impression_estimates tables, implemented deterministic impressions_v1, profile handling, fraud/quality adjustments, advertiser campaign impression summary, and the required admin endpoints. The packet reports passing host/PostGIS/Docker pytest, ruff, Alembic checks, Python 3.12 Docker verification, and no Slice 9+ payout/ledger/reporting/heatmap scope.

Pasted text

Pasted text

Pasted text

Pasted text

Pasted text

Recommended commit message:

feat: add impression estimation

Full Slice 9 implementation prompt:

You are implementing Slice 9 of the Mobility AdTech & Audience Attribution backend.

Slice 0 project foundation, Slice 1 auth/users/advertiser organizations, Slice 2 driver/vehicle foundations, Slice 3 campaign/creative metadata, Slice 4 campaign zones/geofences, Slice 5 campaign assignment/activation, Slice 6 trip tracking/GPS ping ingestion, Slice 7 route analytics/fraud flags, and Slice 8 impression estimation have been accepted by Pro review. Build on the existing repo foundation. Do not replace the stack, restructure the project unnecessarily, or introduce speculative scope.

Before starting implementation, confirm Slice 8 has been committed or that the working tree contains only the accepted Slice 8 state. If the repo has uncommitted unrelated changes, stop and report them.

PROJECT CONTEXT

Product:
Mobility AdTech & Audience Attribution Platform.

Backend goal:
Build the backend for a platform where advertisers run campaigns on shared ride vehicles, drivers and vehicles activate campaigns, GPS movement data is ingested, and analytics support route analytics, impression estimation, payout calculations, advertiser reporting, and heatmap-ready geospatial data.

Slice 9 goal:
Implement payout calculation v1 and the driver earnings ledger. This slice converts accepted route analytics and impression estimates into transparent, formula-versioned driver payout calculations, then records immutable driver earnings ledger entries. Real settlement, withdrawals, billing, invoices, and automated payment processing remain deferred.

FIXED STACK — DO NOT CHANGE

- Python 3.12
- FastAPI
- Pydantic v2
- pydantic-settings
- SQLAlchemy 2.x async
- asyncpg
- Alembic
- PostgreSQL + PostGIS
- Redis in Docker Compose
- JWT bearer auth
- Existing password hashing/JWT/RBAC from Slice 1
- Existing driver/vehicle foundation from Slice 2
- Existing campaign/creative foundation from Slice 3
- Existing campaign zone/geofence foundation from Slice 4
- Existing campaign assignment/activation foundation from Slice 5
- Existing trip/session/location ping foundation from Slice 6
- Existing route analytics/fraud flag foundation from Slice 7
- Existing impression estimation foundation from Slice 8
- pytest
- ruff
- Docker Compose

IMPORTANT LOCAL NOTE

The local coding-guidelines file is named `agent.md`, even if other instructions mention `AGENTS.md`. Read and follow `agent.md`.

REQUIRED LOCAL INVESTIGATION BEFORE CODING

1. Inspect the current repo state.
2. Read `agent.md`.
3. Read the accepted Slice 0 through Slice 8 implementation reports under `docs/build-loop/reports/`.
4. Inspect existing app structure, routers, settings, error handling, request ID middleware, DB session setup, Alembic setup, auth dependencies, RBAC patterns, models, schemas, services, and tests.
5. Inspect existing campaign, trip analytics, fraud flag, impression estimate, driver profile, vehicle, assignment, and advertiser organization service patterns.
6. Confirm the existing API prefix is `/api/v1`.
7. Confirm the existing standard error envelope and reuse it.
8. Confirm the current Alembic head is `0009_impression_estimation`.
9. Confirm no Slice 9 payout rule, payout calculation, or earnings ledger tables already exist.
10. Determine existing Decimal serialization conventions and reuse them.
11. Determine existing Postgres/PostGIS test strategy and preserve it.
12. If any local evidence conflicts with this prompt, stop and produce a reconciliation report instead of implementing blindly.

ALLOWED SCOPE

Implement only Slice 9:

1. Campaign payout rule model, schema, service, and admin API support.
2. Payout calculation model, schema, service, and admin API support.
3. Driver earnings ledger model, schema, service, and driver API support.
4. Deterministic payout calculation v1 from existing trip analytics, impression estimates, fraud flags, and campaign payout rules.
5. Admin endpoints to create/list/read/update campaign payout rules.
6. Admin endpoint to calculate payout for one ended/analyzed/estimated trip.
7. Admin endpoint to list payout calculations.
8. Driver endpoint to view earnings summary.
9. Driver endpoint to view earnings ledger entries.
10. Advertiser endpoint to view aggregate campaign cost summary for campaigns in their own organization.
11. Formula-versioned payout storage.
12. Immutable ledger entry creation for successful payout calculations.
13. Idempotent payout calculation behavior that avoids duplicate payout calculations and duplicate ledger entries.
14. Alembic migration for exactly the Slice 9 payout rule, payout calculation, and earnings ledger tables, constraints, and indexes.
15. Tests for payout formulas, rule validation, idempotency, ledger immutability, driver ownership boundaries, advertiser org scoping, RBAC, migration behavior, and out-of-scope guardrails.
16. README/OpenAPI documentation updates only where needed for Slice 9 usage.
17. Audit events for admin payout-rule create/update and admin payout calculation actions using the existing audit event mechanism.

DO NOT IMPLEMENT

- Real payment settlement
- Withdrawal requests
- Bank/mobile-money payout integrations
- Payment provider integrations
- Driver wallet cash-out
- Invoices
- Tax handling
- Advertiser billing and charging
- Campaign daily metrics
- Full advertiser dashboard/reporting APIs beyond the approved campaign cost summary endpoint
- Heatmap APIs
- Heatmap cache tables
- Automated payout scheduling
- Background jobs/Celery workers
- Notifications
- Manual review workflow for fraud flags
- Driver suspension or payout enforcement workflows
- Seed/demo trip data
- External traffic provider integrations
- Map tiles
- Mapbox integration
- Geocoding/reverse-geocoding
- External map matching
- Audience identity, retargeting, or device pooling
- Creative binary upload/storage pipeline
- Public self-registration
- OAuth/social login
- Refresh-token flow
- Frontend/mobile implementation
- GitHub remote/PR setup
- Production cloud deployment
- AI/computer vision

DATA MODEL REQUIREMENTS

Create a new Alembic migration after the Slice 8 migration.

Expected migration name:
`0010_payouts_and_earnings`

Expected down revision:
`0009_impression_estimation`

Use UUID primary keys. Prefer database-side UUID generation using `gen_random_uuid()`.

Use timezone-aware timestamps.

Use numeric/decimal columns where precision matters. Match existing project conventions for Decimal serialization.

Use either PostgreSQL enums or string columns with database check constraints. Match the existing repo style unless there is a strong local reason not to.

Create exactly these new business tables:

1. `campaign_payout_rules`

Required columns:

- `id` UUID primary key
- `campaign_id` UUID foreign key to `campaigns.id`, not null
- `created_by_user_id` UUID foreign key to `users.id`, nullable or not null depending on existing service style; prefer not null for admin-created rules
- `updated_by_user_id` UUID foreign key to `users.id`, nullable
- `formula_version` text not null, default `payout_v1`
- `status` constrained to:
  - `active`
  - `inactive`
- `currency` text not null
- `base_rate_per_km` numeric not null, default 0
- `base_rate_per_active_hour` numeric not null, default 0
- `target_zone_bonus_rate_per_km` numeric not null, default 0
- `bonus_zone_bonus_rate_per_km` numeric not null, default 0
- `estimated_impression_rate_per_1000` numeric not null, default 0
- `min_payout_per_trip` numeric not null, default 0
- `max_payout_per_trip` numeric nullable
- `low_fraud_multiplier` numeric not null, default 0.90
- `medium_fraud_multiplier` numeric not null, default 0.70
- `high_fraud_multiplier` numeric not null, default 0.25
- `metadata` JSON/JSONB not null, default empty object
- `created_at` timezone-aware timestamp not null
- `updated_at` timezone-aware timestamp not null

Rules:

- Payout rules are admin-managed.
- Campaign must exist.
- Currency must be normalized uppercase and should be a simple 3-letter code.
- Numeric rates must be nonnegative.
- Fraud multipliers must be between 0 and 1.
- `min_payout_per_trip` must be nonnegative.
- `max_payout_per_trip`, if supplied, must be nonnegative and must be greater than or equal to `min_payout_per_trip`.
- `metadata` must be an object.
- Only one active payout rule per campaign should exist. Use a PostgreSQL partial unique index where feasible and service-level supersession or rejection.
- Preferred behavior: when creating or updating a rule as active, mark other active rules for the same campaign inactive in the same transaction.
- Do not mutate existing payout calculations when a payout rule changes.

Suggested constraints/indexes:

- Check constraint for `status`.
- Check constraints for nonnegative rates and min/max values.
- Check constraints for multipliers between 0 and 1.
- Index on `campaign_id`.
- Index on `(campaign_id, status)`.
- Partial unique index on `campaign_id` where `status = 'active'`, where feasible.

2. `payout_calculations`

Required columns:

- `id` UUID primary key
- `trip_session_id` UUID foreign key to `trip_sessions.id`, not null
- `trip_analytics_id` UUID foreign key to `trip_analytics.id`, not null
- `impression_estimate_id` UUID foreign key to `impression_estimates.id`, not null
- `payout_rule_id` UUID foreign key to `campaign_payout_rules.id`, not null
- `assignment_id` UUID foreign key to `campaign_assignments.id`, not null
- `campaign_id` UUID foreign key to `campaigns.id`, not null
- `driver_profile_id` UUID foreign key to `driver_profiles.id`, not null
- `vehicle_id` UUID foreign key to `vehicles.id`, not null
- `formula_version` text not null, default `payout_v1`
- `status` constrained to:
  - `calculated`
  - `insufficient_data`
  - `blocked`
- `currency` text not null
- `distance_component` numeric not null, default 0
- `active_time_component` numeric not null, default 0
- `target_zone_bonus_component` numeric not null, default 0
- `bonus_zone_bonus_component` numeric not null, default 0
- `impression_component` numeric not null, default 0
- `gross_payout` numeric not null, default 0
- `quality_multiplier` numeric not null
- `fraud_multiplier` numeric not null
- `cap_adjustment` numeric not null, default 0
- `final_payout` numeric not null, default 0
- `calculated_at` timezone-aware timestamp not null
- `metadata` JSON/JSONB not null, default empty object
- `created_at` timezone-aware timestamp not null
- `updated_at` timezone-aware timestamp not null

Rules:

- Exactly one current payout calculation per trip/formula/rule is acceptable for v1.
- Re-calculating payout for the same trip/formula/rule should return the existing calculation and must not create duplicate payout rows or duplicate ledger entries.
- Payout calculation requires:
  - ended trip
  - existing trip analytics for the trip
  - existing impression estimate for the trip
  - active campaign payout rule for the campaign unless an explicit `payout_rule_id` is supplied
- If a supplied payout rule is inactive, reject it.
- `trip_analytics.status = computed` and `impression_estimate.status = estimated` produce normal `status = calculated`.
- `trip_analytics.status = insufficient_data` or `impression_estimate.status = insufficient_data` produces `status = insufficient_data`, final payout 0, and no ledger entry.
- `trip_analytics.status = blocked` or `impression_estimate.status = excluded` produces `status = blocked`, final payout 0, and no ledger entry.
- Store formula version as `payout_v1`.
- Store campaign/assignment/driver/vehicle foreign keys copied from analytics/estimate for efficient reporting.
- Store transparent formula inputs/outputs in `metadata`.
- Do not trigger real settlement or payment provider calls.

Suggested constraints/indexes:

- Unique index on `(trip_session_id, formula_version, payout_rule_id)`.
- Index on `trip_analytics_id`.
- Index on `impression_estimate_id`.
- Index on `campaign_id`.
- Index on `assignment_id`.
- Index on `driver_profile_id`.
- Index on `vehicle_id`.
- Index on `(campaign_id, calculated_at)`.
- Index on `(driver_profile_id, calculated_at)`.
- Index on `(campaign_id, status)`.
- Check constraints for nonnegative payout components, gross payout, and final payout.
- Check constraints for `quality_multiplier` and `fraud_multiplier` between 0 and 1 if cleanly supported.

3. `earnings_ledger_entries`

Required columns:

- `id` UUID primary key
- `payout_calculation_id` UUID foreign key to `payout_calculations.id`, nullable but unique when present
- `driver_profile_id` UUID foreign key to `driver_profiles.id`, not null
- `driver_user_id` UUID foreign key to `users.id`, not null
- `campaign_id` UUID foreign key to `campaigns.id`, not null
- `trip_session_id` UUID foreign key to `trip_sessions.id`, nullable
- `vehicle_id` UUID foreign key to `vehicles.id`, nullable
- `entry_type` constrained to:
  - `trip_payout`
  - `adjustment`
  - `reversal`
- `status` constrained to:
  - `pending`
  - `available`
  - `voided`
  - `reversed`
- `amount` numeric not null
- `currency` text not null
- `description` text nullable
- `occurred_at` timezone-aware timestamp not null
- `metadata` JSON/JSONB not null, default empty object
- `created_at` timezone-aware timestamp not null

Rules:

- Ledger entries are append-only.
- Do not implement update/delete endpoints for ledger entries.
- Slice 9 should create `trip_payout` entries only.
- `trip_payout` entries should use status `pending`.
- `trip_payout` entries must have nonnegative amount.
- If final payout is 0 or payout calculation status is not `calculated`, do not create a ledger entry.
- One ledger entry per payout calculation is allowed.
- Re-running payout calculation must not duplicate ledger entries.
- Reversal and adjustment statuses are reserved for future use; do not implement manual adjustment/reversal APIs in Slice 9.
- Driver users can see only their own ledger entries.
- Advertisers can see aggregate campaign cost summary only, not driver ledger details.

Suggested constraints/indexes:

- Unique index on `payout_calculation_id` where not null, if feasible.
- Index on `driver_profile_id`.
- Index on `driver_user_id`.
- Index on `campaign_id`.
- Index on `trip_session_id`.
- Index on `vehicle_id`.
- Index on `(driver_profile_id, occurred_at)`.
- Index on `(campaign_id, occurred_at)`.
- Index on `(driver_profile_id, status)`.
- Check constraint for `entry_type`.
- Check constraint for `status`.
- Check constraint for simple 3-letter currency if consistent with existing style.

Do not create campaign daily metrics, advertiser reports, heatmap, billing, invoice, settlement, withdrawal, audience, retargeting, or seed tables.

CONFIGURATION REQUIREMENTS

Extend existing settings only as needed.

Add settings such as:

- `PAYOUT_FORMULA_VERSION`, default `payout_v1`
- `PAYOUT_DEFAULT_BASE_RATE_PER_KM`, default `0`
- `PAYOUT_DEFAULT_BASE_RATE_PER_ACTIVE_HOUR`, default `0`
- `PAYOUT_DEFAULT_TARGET_ZONE_BONUS_RATE_PER_KM`, default `0`
- `PAYOUT_DEFAULT_BONUS_ZONE_BONUS_RATE_PER_KM`, default `0`
- `PAYOUT_DEFAULT_ESTIMATED_IMPRESSION_RATE_PER_1000`, default `0`
- `PAYOUT_DEFAULT_LOW_FRAUD_MULTIPLIER`, default `0.90`
- `PAYOUT_DEFAULT_MEDIUM_FRAUD_MULTIPLIER`, default `0.70`
- `PAYOUT_DEFAULT_HIGH_FRAUD_MULTIPLIER`, default `0.25`
- `PAYOUT_DEFAULT_MIN_PAYOUT_PER_TRIP`, default `0`
- `PAYOUT_DEFAULT_MAX_PAYOUT_PER_TRIP`, nullable or default unset

Update `.env.example` and Docker Compose only if needed.

Validate settings for nonnegative rates and multipliers between 0 and 1 where applicable.

PAYOUT FORMULA V1 REQUIREMENTS

Implement a deterministic transparent formula.

Recommended formula:

distance_km =
  trip_analytics.distance_m / 1000

active_hours =
  trip_analytics.active_tracking_seconds / 3600

target_zone_distance_km =
  trip_analytics.target_zone_distance_m / 1000

bonus_zone_distance_km =
  trip_analytics.bonus_zone_distance_m / 1000

distance_component =
  distance_km * base_rate_per_km

active_time_component =
  active_hours * base_rate_per_active_hour

target_zone_bonus_component =
  target_zone_distance_km * target_zone_bonus_rate_per_km

bonus_zone_bonus_component =
  bonus_zone_distance_km * bonus_zone_bonus_rate_per_km

impression_component =
  (impression_estimate.estimated_impressions / 1000)
  * estimated_impression_rate_per_1000

gross_payout =
  distance_component
  + active_time_component
  + target_zone_bonus_component
  + bonus_zone_bonus_component
  + impression_component

quality_multiplier =
  clamp(trip_analytics.quality_score, 0, 1)

quality_adjusted_payout =
  gross_payout * quality_multiplier

fraud_adjusted_payout =
  quality_adjusted_payout * fraud_multiplier

final_payout_before_cap =
  max(0, fraud_adjusted_payout)

final_payout =
  apply min/max rule caps to final_payout_before_cap

Rules:

- Use `trip_analytics.distance_m`.
- Use `trip_analytics.active_tracking_seconds`.
- Use `trip_analytics.target_zone_distance_m` and `bonus_zone_distance_m`.
- Use `impression_estimate.estimated_impressions`.
- Use `trip_analytics.quality_score` as quality multiplier.
- Determine fraud multiplier from open fraud flags for the trip:
  - If any open high-severity fraud flag exists, use payout rule `high_fraud_multiplier`.
  - Else if any open medium-severity fraud flag exists, use payout rule `medium_fraud_multiplier`.
  - Else if any open low-severity fraud flag exists, use payout rule `low_fraud_multiplier`.
  - Else use `1.0`.
- Dismissed or acknowledged fraud flags must not reduce payout.
- If `max_payout_per_trip` is set and payout exceeds it, cap to that maximum and store the negative cap adjustment.
- If final payout is positive but below `min_payout_per_trip`, raise it to `min_payout_per_trip`.
- If gross payout is zero, do not apply the minimum payout floor.
- Clamp final payout to be nonnegative.
- Store metadata with:
  - formula version
  - source analytics id
  - source impression estimate id
  - payout rule id
  - fraud flag counts by severity
  - quality score
  - formula inputs
  - formula components
  - cap/floor adjustments
  - request metadata

Do not implement real settlement, invoices, advertiser billing, or payment provider calls.

DEFAULT PAYOUT RULE BEHAVIOR

Unlike Slice 8 traffic-density profiles, payout rules represent business-money configuration and should be explicit.

Preferred behavior:

- Admin must create an active payout rule for a campaign before payout calculation.
- If no active payout rule exists and no `payout_rule_id` is supplied, return a clear `PAYOUT_RULE_NOT_FOUND` error using the standard error envelope.

Acceptable local-development helper:

- You may include a documented helper/service method that creates a default local payout rule only in tests or local-only fixtures, but do not silently create money rules in production runtime.

API ENDPOINTS

Implement these endpoints under `/api/v1`.

Admin payout rule endpoints:

1. `POST /api/v1/admin/campaigns/{campaign_id}/payout-rules`

Admin-only.

Input:

{
  "formula_version": "payout_v1",
  "status": "active",
  "currency": "NGN",
  "base_rate_per_km": "100.00",
  "base_rate_per_active_hour": "500.00",
  "target_zone_bonus_rate_per_km": "50.00",
  "bonus_zone_bonus_rate_per_km": "75.00",
  "estimated_impression_rate_per_1000": "25.00",
  "min_payout_per_trip": "0.00",
  "max_payout_per_trip": "10000.00",
  "low_fraud_multiplier": "0.90",
  "medium_fraud_multiplier": "0.70",
  "high_fraud_multiplier": "0.25",
  "metadata": {}
}

Output: created payout rule.

Rules:

- Admin-only.
- Campaign must exist.
- If creating an active rule, supersede or reject other active campaign payout rules deterministically. Preferred behavior: mark prior active rules inactive in the same transaction.
- Normalize currency uppercase.
- Write audit event `admin.campaign_payout_rule.created`.

2. `GET /api/v1/admin/campaigns/{campaign_id}/payout-rules`

Admin-only.

Query parameters:

- `limit`, default 50, max 100
- `offset`, default 0
- optional `status`

Output shape:

{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}

3. `GET /api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}`

Admin-only.

Returns one payout rule for the campaign.

4. `PATCH /api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}`

Admin-only.

Allowed update fields:

{
  "status": "active",
  "currency": "NGN",
  "base_rate_per_km": "100.00",
  "base_rate_per_active_hour": "500.00",
  "target_zone_bonus_rate_per_km": "50.00",
  "bonus_zone_bonus_rate_per_km": "75.00",
  "estimated_impression_rate_per_1000": "25.00",
  "min_payout_per_trip": "0.00",
  "max_payout_per_trip": "10000.00",
  "low_fraud_multiplier": "0.90",
  "medium_fraud_multiplier": "0.70",
  "high_fraud_multiplier": "0.25",
  "metadata": {}
}

Rules:

- Admin-only.
- Do not allow campaign id updates.
- If setting this rule active, supersede or reject other active campaign payout rules deterministically. Preferred behavior: mark prior active rules inactive in the same transaction.
- Do not mutate existing payout calculations.
- Write audit event `admin.campaign_payout_rule.updated`.

Admin payout calculation endpoints:

5. `POST /api/v1/admin/trips/{trip_id}/calculate-payout`

Admin-only.

Input body optional. If implemented, use:

{
  "payout_rule_id": "optional-payout-rule-uuid",
  "metadata": {}
}

Output: payout calculation response, including ledger entry summary when one was created or already exists.

Rules:

- Admin-only.
- Trip must exist.
- Trip must be ended.
- Trip analytics must exist and belong to the trip.
- Impression estimate must exist and belong to the trip.
- Payout rule must exist and be active.
- If `payout_rule_id` is omitted, use the campaign’s active payout rule.
- If no active rule exists, return `PAYOUT_RULE_NOT_FOUND`.
- Calculation is idempotent for the same trip/formula/rule.
- If an existing payout calculation already exists for the same trip/formula/rule, return it and do not create a duplicate ledger entry.
- If calculation status is `calculated` and final payout is greater than zero, create exactly one pending `trip_payout` ledger entry.
- If calculation status is `insufficient_data` or `blocked`, do not create a ledger entry.
- Write audit event `admin.payout_calculation.created` for first-time calculations.
- Do not trigger settlement, withdrawal, bank transfer, mobile-money transfer, invoice, or billing actions.

6. `GET /api/v1/admin/payout-calculations`

Admin-only.

Query parameters:

- `limit`, default 50, max 100
- `offset`, default 0
- optional `campaign_id`
- optional `trip_session_id`
- optional `driver_profile_id`
- optional `vehicle_id`
- optional `status`
- optional `currency`

Output shape:

{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}

Rules:

- Admin can list calculations across campaigns/drivers.
- Do not expose password hashes.
- Do not expose raw pings.

Driver earnings endpoints:

7. `GET /api/v1/driver/earnings/summary`

Driver-only.

Query parameters:

- optional `currency`

Output shape:

{
  "driver_profile_id": "uuid",
  "totals_by_currency": [
    {
      "currency": "NGN",
      "pending_amount": "1000.00",
      "available_amount": "0.00",
      "voided_amount": "0.00",
      "lifetime_earned_amount": "1000.00",
      "ledger_entry_count": 1
    }
  ]
}

Rules:

- Driver-only.
- Driver must have a driver profile.
- Driver can see only their own earnings.
- Do not implement withdrawal, cash-out, settlement, or payment account data.
- If no ledger entries exist, return stable zero shape.

8. `GET /api/v1/driver/earnings/ledger`

Driver-only.

Query parameters:

- `limit`, default 50, max 100
- `offset`, default 0
- optional `status`
- optional `entry_type`
- optional `currency`

Output shape:

{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}

Rules:

- Driver-only.
- Driver can see only ledger entries tied to their own driver profile/user.
- Do not expose advertiser billing internals.
- Do not expose other drivers.

Advertiser campaign cost summary endpoint:

9. `GET /api/v1/advertiser/campaigns/{campaign_id}/cost-summary`

Advertiser-only.

Query parameters:

- optional `start_at`
- optional `end_at`
- optional `currency`

Output shape:

{
  "campaign_id": "uuid",
  "formula_version": "payout_v1",
  "totals_by_currency": [
    {
      "currency": "NGN",
      "final_payout_total": "10000.00",
      "gross_payout_total": "12000.00",
      "calculated_trip_count": 10,
      "blocked_trip_count": 1,
      "insufficient_data_trip_count": 2,
      "ledger_entry_count": 10
    }
  ],
  "start_at": "2026-05-01T00:00:00Z",
  "end_at": "2026-05-31T23:59:59Z"
}

Rules:

- Advertiser-only.
- Campaign must belong to the current advertiser organization.
- Cross-organization campaign access must not leak data. Prefer 404.
- Summary uses stored `payout_calculations` and `earnings_ledger_entries`.
- Date filtering should use `calculated_at` unless a better existing convention is obvious; document the choice.
- Do not generate payout calculations automatically in this endpoint.
- If no calculations exist, return stable zero shape.
- Do not expose driver identities, raw pings, ledger entry details, or payment settlement data.
- Admin should use admin endpoints, not advertiser endpoint.

RESPONSE SHAPE GUIDANCE

Campaign payout rule response should include at minimum:

{
  "id": "uuid",
  "campaign_id": "uuid",
  "formula_version": "payout_v1",
  "status": "active",
  "currency": "NGN",
  "base_rate_per_km": "100.00",
  "base_rate_per_active_hour": "500.00",
  "target_zone_bonus_rate_per_km": "50.00",
  "bonus_zone_bonus_rate_per_km": "75.00",
  "estimated_impression_rate_per_1000": "25.00",
  "min_payout_per_trip": "0.00",
  "max_payout_per_trip": "10000.00",
  "low_fraud_multiplier": "0.90",
  "medium_fraud_multiplier": "0.70",
  "high_fraud_multiplier": "0.25",
  "metadata": {},
  "created_at": "2026-05-31T00:00:00Z",
  "updated_at": "2026-05-31T00:00:00Z"
}

Payout calculation response should include at minimum:

{
  "id": "uuid",
  "trip_session_id": "uuid",
  "trip_analytics_id": "uuid",
  "impression_estimate_id": "uuid",
  "payout_rule_id": "uuid",
  "assignment_id": "uuid",
  "campaign_id": "uuid",
  "driver_profile_id": "uuid",
  "vehicle_id": "uuid",
  "formula_version": "payout_v1",
  "status": "calculated",
  "currency": "NGN",
  "distance_component": "850.00",
  "active_time_component": "250.00",
  "target_zone_bonus_component": "100.00",
  "bonus_zone_bonus_component": "75.00",
  "impression_component": "30.00",
  "gross_payout": "1305.00",
  "quality_multiplier": "0.95",
  "fraud_multiplier": "1.00",
  "cap_adjustment": "0.00",
  "final_payout": "1239.75",
  "calculated_at": "2026-05-31T12:35:00Z",
  "metadata": {},
  "ledger_entry": {
    "id": "uuid",
    "status": "pending",
    "amount": "1239.75",
    "currency": "NGN"
  }
}

Earnings ledger entry response should include at minimum:

{
  "id": "uuid",
  "payout_calculation_id": "uuid",
  "driver_profile_id": "uuid",
  "campaign_id": "uuid",
  "trip_session_id": "uuid",
  "vehicle_id": "uuid",
  "entry_type": "trip_payout",
  "status": "pending",
  "amount": "1239.75",
  "currency": "NGN",
  "description": "Trip payout",
  "occurred_at": "2026-05-31T12:35:00Z",
  "metadata": {},
  "created_at": "2026-05-31T12:35:00Z"
}

For Decimal values, use the existing project convention. If no convention exists, return Decimal values as strings to avoid JSON float precision ambiguity.

LIKELY FILES/AREAS TO CREATE OR CHANGE

Use existing Slice 0-Slice 8 conventions. Likely create/change:

- `app/api/v1/router.py`
- `app/api/v1/payouts.py` or similar
- `app/models/payout.py`
- `app/models/__init__.py`
- `app/schemas/payouts.py`
- `app/services/payouts.py`
- `app/services/audit.py` only if needed to add action helpers
- `app/core/config.py`
- `app/api/v1/dependencies.py` only if needed to reuse admin/advertiser/driver helpers
- `app/db/base.py` only if model imports require update
- `alembic/versions/0010_payouts_and_earnings.py`
- `.env.example`
- `README.md`
- `tests/test_campaign_payout_rules.py`
- `tests/test_payout_calculations.py`
- `tests/test_driver_earnings.py`
- `tests/test_advertiser_cost_summary.py`
- `tests/test_migration_slice9.py`
- Possibly fixture updates in `tests/conftest.py`
- `docs/build-loop/reports/slice-09-payouts-earnings.md`

Keep code simple. Avoid unnecessary abstractions.

TEST REQUIREMENTS

Add/extend tests for:

Campaign payout rules:

1. Admin can create a campaign payout rule.
2. Admin can list campaign payout rules with pagination response shape.
3. Admin can read a campaign payout rule.
4. Admin can update a campaign payout rule.
5. Creating or updating one active rule supersedes or rejects other active rules deterministically.
6. Invalid status is rejected.
7. Invalid currency is rejected.
8. Negative base rate is rejected.
9. Negative bonus rate is rejected.
10. Negative impression rate is rejected.
11. Fraud multipliers outside 0..1 are rejected.
12. `max_payout_per_trip` below `min_payout_per_trip` is rejected.
13. Metadata must be an object.
14. Advertiser, driver, and unauthenticated users are rejected from payout rule endpoints.
15. Audit event is created for payout rule creation.
16. Audit event is created for payout rule update.

Payout calculation:

17. Admin can calculate payout for a trip with ended trip, computed analytics, estimated impressions, and active payout rule.
18. Calculation creates a `payout_calculations` row.
19. Successful positive calculation creates exactly one pending `trip_payout` ledger entry.
20. Re-running the same trip/formula/rule returns existing calculation and does not duplicate ledger entry.
21. Calculation copies campaign, assignment, driver profile, vehicle, analytics, estimate, and rule ids.
22. Calculation stores formula version `payout_v1`.
23. Calculation stores transparent formula metadata.
24. Distance component uses analytics distance.
25. Active-time component uses analytics active tracking seconds.
26. Target-zone component uses analytics target zone distance.
27. Bonus-zone component uses analytics bonus zone distance.
28. Impression component uses impression estimate value.
29. Quality score affects quality multiplier.
30. High-severity open fraud flag applies high fraud multiplier.
31. Medium-severity open fraud flag applies medium fraud multiplier when no high flag exists.
32. Low-severity open fraud flag applies low fraud multiplier when no high/medium flag exists.
33. Dismissed/acknowledged fraud flags do not affect multiplier.
34. Final payout is clamped nonnegative.
35. Min payout floor applies only when gross payout is positive.
36. Max payout cap applies and records cap adjustment.
37. Insufficient-data analytics creates `insufficient_data` calculation and no ledger entry.
38. Insufficient-data impression estimate creates `insufficient_data` calculation and no ledger entry.
39. Blocked analytics creates `blocked` calculation and no ledger entry.
40. Excluded impression estimate creates `blocked` calculation and no ledger entry.
41. Missing analytics returns standard analytics-not-found error.
42. Missing impression estimate returns standard impression-estimate-not-found error.
43. Missing active payout rule returns standard payout-rule-not-found error.
44. Inactive explicit payout rule is rejected.
45. Active/non-ended trip is rejected.
46. Admin can list payout calculations with pagination response shape.
47. Admin can filter payout calculations by campaign id.
48. Admin can filter payout calculations by driver profile id.
49. Admin can filter payout calculations by status.
50. Advertiser, driver, and unauthenticated users are rejected from admin payout calculation endpoints.
51. Audit event is created for first-time payout calculation.

Driver earnings:

52. Driver can read own earnings summary.
53. Driver with no ledger entries receives stable zero summary.
54. Driver earnings summary groups totals by currency.
55. Driver can list own ledger entries with pagination response shape.
56. Driver can filter own ledger entries by status, entry type, and currency.
57. Driver cannot see another driver’s ledger entries.
58. Admin is rejected from driver earnings endpoints.
59. Advertiser is rejected from driver earnings endpoints.
60. Unauthenticated users are rejected from driver earnings endpoints.
61. Ledger entries are append-only through public APIs; no update/delete endpoints exist.
62. Duplicate payout calculation does not create duplicate ledger entries.

Advertiser campaign cost summary:

63. Advertiser can read cost summary for own campaign.
64. Advertiser cannot read cost summary for another organization’s campaign.
65. Cost summary returns stable zero shape when no payout calculations exist.
66. Cost summary aggregates final payout totals by currency.
67. Cost summary counts calculated, blocked, and insufficient-data calculations.
68. Cost summary date filters work using the documented date field.
69. Cost summary does not expose driver identities or ledger entry details.
70. Driver and unauthenticated users are rejected from advertiser cost summary endpoint.
71. Admin is rejected from advertiser cost summary endpoint unless existing project pattern explicitly allows admin on advertiser routes; prefer rejection.

Migration and scope:

72. Alembic migration creates exactly `campaign_payout_rules`, `payout_calculations`, and `earnings_ledger_entries` as new Slice 9 tables.
73. Migration creates expected constraints and indexes.
74. Migration creates uniqueness for one active payout rule per campaign where feasible.
75. Migration creates idempotency uniqueness for payout calculations.
76. Migration creates unique payout-calculation ledger mapping where feasible.
77. Migration does not create campaign daily metrics, advertiser reports, heatmaps, billing, invoices, settlement, withdrawal, payment, audience, retargeting, or seed tables.
78. Existing Slice 0-Slice 8 tests continue to pass.
79. API responses do not expose password hashes, raw pings, payment account data, or unrelated sensitive data.

Testing implementation guidance:

- Reuse existing test fixtures and auth helpers from prior slices.
- Reuse existing trip analytics and impression estimate factories/helpers where available.
- Do not require external network access.
- If existing tests use SQLite for speed, maintain compatibility where practical.
- Migration verification against Postgres/PostGIS remains required.
- Keep tests deterministic.
- Avoid making advertiser cost summary perform automatic payout calculation; it should aggregate stored calculations only.
- Do not add payment provider mocks because real settlement is out of scope.

CHECKS THAT MUST WORK

The final implementation should support:

python -m pytest
python -m ruff check .
alembic upgrade head

Also verify Python 3.12 through Docker as in prior slices:

docker compose run --rm api python --version
docker compose run --rm api python -m pytest
docker compose run --rm api python -m ruff check .

Postgres/PostGIS migration verification is required:

$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic current
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest

If any command cannot be run locally due to missing external runtime or local environment issues, report that honestly with exact evidence.

FRONTEND CONTRACT NOTES

Admin tools can use:

POST  /api/v1/admin/campaigns/{campaign_id}/payout-rules
GET   /api/v1/admin/campaigns/{campaign_id}/payout-rules
GET   /api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}
PATCH /api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}

POST /api/v1/admin/trips/{trip_id}/calculate-payout
GET  /api/v1/admin/payout-calculations

Driver app can use:

GET /api/v1/driver/earnings/summary
GET /api/v1/driver/earnings/ledger

Advertiser dashboard can use:

GET /api/v1/advertiser/campaigns/{campaign_id}/cost-summary

All protected endpoints must use bearer token auth:

Authorization: Bearer <token>

After this slice, payout calculations and driver earnings ledger entries exist as stored records. Real settlement, withdrawal, billing, invoices, advertiser charging, campaign daily metrics, full advertiser dashboard reporting, and heatmaps are not available yet.

STANDARD ERROR BEHAVIOR

Use the existing Slice 0-Slice 8 error envelope for expected errors.

Expected examples:

- Missing token
- Invalid token
- Forbidden role
- Campaign not found
- Campaign belongs to another organization
- Payout rule not found
- Payout rule inactive
- Invalid payout rule values
- Trip not found
- Trip not ended
- Analytics not found
- Impression estimate not found
- Payout calculation not found
- Driver profile missing
- Invalid metadata
- Invalid pagination/filter values

Do not return raw stack traces.

ACCEPTANCE CRITERIA

Slice 9 is acceptable only if:

1. Alembic migration creates exactly the approved `campaign_payout_rules`, `payout_calculations`, and `earnings_ledger_entries` tables, constraints, and indexes.
2. No Slice 10+ reporting/dashboard/heatmap/billing/settlement/seed/audience tables are added.
3. Admin can create/list/read/update campaign payout rules.
4. One active payout rule per campaign is enforced or deterministically resolved.
5. Admin can calculate payout for trips with existing ended trip, computed analytics, impression estimate, and active payout rule.
6. Payout calculation is idempotent for the same trip/formula/rule.
7. Successful positive payout calculation creates exactly one pending immutable ledger entry.
8. Duplicate payout calculation requests do not duplicate ledger entries.
9. Payout formula uses analytics distance, active tracking seconds, zone distances, impression estimate, quality score, fraud flags, and payout rule rates/multipliers.
10. Insufficient-data and blocked/excluded analytics or impression estimates are handled deterministically with zero payout and no ledger entry.
11. Payout metadata explains formula inputs, rates, multipliers, and adjustments.
12. Admin can list/filter payout calculations.
13. Driver can read only their own earnings summary and ledger entries.
14. Advertiser can read only own campaign aggregate cost summary.
15. Advertiser cost summary aggregates stored payout calculations and returns stable zero shape when empty.
16. Admin/advertiser/driver/unauthenticated access boundaries are enforced.
17. API responses do not expose password hashes, raw pings, payment account data, other-driver ledger data, or unrelated sensitive data.
18. Tests pass.
19. Ruff passes.
20. Alembic upgrade head passes against Postgres/PostGIS.
21. Python 3.12 verification is performed through Docker or explicitly reported if impossible.
22. No deferred/future scope is implemented.

STOP CONDITIONS

Stop and report instead of implementing if:

1. Slice 8 accepted foundation is missing or materially different from the packet.
2. The existing project uses a materially different stack than the approved stack.
3. `agent.md` conflicts with this prompt.
4. The DB/migration setup cannot support Slice 9 tables without reworking previous slices.
5. Existing analytics, impression estimate, fraud flag, or campaign models make payout calculation ambiguous in a way that requires a product decision.
6. Existing advertiser campaign tenancy behavior makes cost-summary scoping ambiguous in a way that requires a product decision.
7. Implementing payouts would require real payment provider integration.
8. You are tempted to add real settlement, withdrawals, driver wallet cash-out, advertiser billing, invoices, campaign daily metrics, full dashboard reports, heatmaps, background jobs, seed/demo data, or audience identity.

Otherwise, stop after Slice 9. Do not continue to Slice 10.

REQUIRED CODEX PLAN FORMAT BEFORE CODING

Before coding, output:

CODEX PLAN

Slice:
Scope understood:
Local investigation findings:
Files to create/change:
Database migrations:
API endpoints:
Tests to add/update:
Security/validation checks:
Payout rule approach:
Payout formula approach:
Fraud/quality adjustment approach:
Ledger immutability/idempotency approach:
Driver earnings aggregation approach:
Advertiser cost summary approach:
Explicitly out of scope:
Assumptions:
Risks or blockers:

REQUIRED CODEX BUILD REPORT FORMAT AFTER CODING

After coding, output:

CODEX BUILD REPORT

Slice:
Status: PASS_CANDIDATE | PARTIAL | BLOCKED

Summary:
Local investigation performed:
Files changed:
Database migrations:
API endpoints implemented:
Security/validation implemented:
Payout rule handling implemented:
Payout formula implemented:
Fraud/quality adjustment implemented:
Ledger immutability/idempotency implemented:
Driver earnings aggregation implemented:
Advertiser cost summary implemented:
Tests added/updated:
Commands run:
Command results:
Known issues:
Out-of-scope compliance:
Acceptance criteria checklist:
Manual verification steps:
Questions for Pro reviewer:

REQUIRED PRO REVIEW PACKET FORMAT

The orchestrator must send the Pro reviewer a packet with:

PRO REVIEW PACKET

Slice:
Repo state summary:
Commit status:
Files changed:
Diff summary:
Database migrations:
API endpoints:
Security/validation implemented:
Payout rule handling implemented:
Payout formula implemented:
Fraud/quality adjustment implemented:
Ledger immutability/idempotency implemented:
Driver earnings aggregation implemented:
Advertiser cost summary implemented:
Tests/checks run:
Exact command outputs or concise failure excerpts:
Known issues:
Out-of-scope confirmation:
Acceptance criteria checklist:
Codex questions:
Orchestrator recommendation: PASS_CANDIDATE | NEEDS_FIX | BLOCKED
