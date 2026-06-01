You are implementing Slice 10 of the Mobility AdTech & Audience Attribution backend.

Slice 0 project foundation, Slice 1 auth/users/advertiser organizations, Slice 2 driver/vehicle foundations, Slice 3 campaign/creative metadata, Slice 4 campaign zones/geofences, Slice 5 campaign assignment/activation, Slice 6 trip tracking/GPS ping ingestion, Slice 7 route analytics/fraud flags, Slice 8 impression estimation, and Slice 9 payout calculations/driver earnings ledger have been accepted by Pro review. Build on the existing repo foundation. Do not replace the stack, restructure the project unnecessarily, or introduce speculative scope.

Before starting implementation, confirm Slice 9 has been committed or that the working tree contains only the accepted Slice 9 state. If the repo has uncommitted unrelated changes, stop and report them.

PROJECT CONTEXT

Product:
Mobility AdTech & Audience Attribution Platform.

Backend goal:
Build the backend for a platform where advertisers run campaigns on shared ride vehicles, drivers and vehicles activate campaigns, GPS movement data is ingested, and analytics support route analytics, impression estimation, payout calculations, advertiser reporting, and heatmap-ready geospatial data.

Slice 10 goal:
Implement advertiser dashboard summary and campaign reporting APIs using existing stored campaign, assignment, trip, analytics, fraud, impression, payout, ledger, creative, and zone data. This slice should make the backend useful for a future advertiser frontend by exposing stable aggregate performance contracts. It must not introduce heatmap APIs, materialized reporting tables, background jobs, billing, settlement, or new analytics calculations.

FIXED STACK â€” DO NOT CHANGE

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
- Existing payout/earnings foundation from Slice 9
- pytest
- ruff
- Docker Compose

IMPORTANT LOCAL NOTE

The local coding-guidelines file is named `agent.md`, even if other instructions mention `AGENTS.md`. Read and follow `agent.md`.

REQUIRED LOCAL INVESTIGATION BEFORE CODING

1. Inspect the current repo state.
2. Read `agent.md`.
3. Read the accepted Slice 0 through Slice 9 implementation reports under `docs/build-loop/reports/`.
4. Inspect existing app structure, routers, settings, error handling, request ID middleware, DB session setup, Alembic setup, auth dependencies, RBAC patterns, models, schemas, services, and tests.
5. Inspect existing campaign, creative, zone, assignment, trip, trip analytics, fraud flag, impression estimate, payout calculation, earnings ledger, and advertiser organization service patterns.
6. Confirm the existing API prefix is `/api/v1`.
7. Confirm the existing standard error envelope and reuse it.
8. Confirm the current Alembic head is `0010_payouts_and_earnings`.
9. Confirm no Slice 10 reporting/dashboard tables already exist.
10. Review the Slice 9 known issue about future parent-delete cascade risk. Do not fix cascade policy in Slice 10 unless local evidence shows an active bug. Do not add destructive delete APIs.
11. Determine existing Decimal serialization conventions and reuse them.
12. Determine existing pagination and date-filter patterns and reuse them.
13. Determine existing advertiser campaign tenancy helper behavior and reuse it.
14. If any local evidence conflicts with this prompt, stop and produce a reconciliation report instead of implementing blindly.

ALLOWED SCOPE

Implement only Slice 10:

1. Advertiser dashboard summary API.
2. Advertiser campaign summary API.
3. Advertiser campaign daily metrics API.
4. Advertiser campaign trip summaries API.
5. Advertiser campaign report API.
6. Reporting schemas and read-only reporting service logic.
7. Aggregation from existing stored tables only:
   - `campaigns`
   - `campaign_creatives`
   - `campaign_zones`
   - `campaign_assignments`
   - `trip_sessions`
   - `trip_analytics`
   - `fraud_flags`
   - `impression_estimates`
   - `payout_calculations`
   - `earnings_ledger_entries`
8. Tests for advertiser org scoping, aggregate correctness, zero states, date filters, pagination, privacy boundaries, RBAC, and out-of-scope guardrails.
9. README/OpenAPI documentation updates only where needed for Slice 10 usage.

IMPORTANT DATA MODEL DECISION

Do not create new reporting or daily-metric tables in Slice 10.

For MVP, use on-demand SQL aggregation over existing stored analytics, impression, payout, and ledger records. This avoids premature materialized read models before frontend usage patterns are known.

No new Alembic migration is expected for Slice 10.

If you discover a local technical reason that a new table or migration is required, stop and report the reason instead of adding it.

DO NOT IMPLEMENT

- New database tables
- New Alembic migration
- Campaign daily metrics materialization table
- Heatmap APIs
- Heatmap cache tables
- Map tiles
- Mapbox integration
- Geospatial grid/cell aggregation
- Route polyline generation
- Raw GPS ping export
- New route analytics calculations
- New impression estimation calculations
- New payout calculations
- Automatic report materialization
- Background jobs/Celery workers
- Scheduled rollups
- PDF/CSV export
- Billing/invoicing
- Advertiser charging
- Settlement/payment APIs
- Withdrawal/cash-out APIs
- Tax handling
- Manual fraud review workflow
- Notifications
- Seed/demo data
- External traffic provider integrations
- External map matching
- Geocoding/reverse-geocoding
- Audience identity, retargeting, or device pooling
- Creative binary upload/storage pipeline
- Public self-registration
- OAuth/social login
- Refresh-token flow
- Frontend/mobile implementation
- GitHub remote/PR setup
- Production cloud deployment
- AI/computer vision

REPORTING PRINCIPLES

1. Reporting endpoints are read-only.
2. Reporting endpoints aggregate existing stored records only.
3. Reporting endpoints must not auto-run route analytics, impression estimation, or payout calculation.
4. Reporting endpoints must not mutate campaigns, assignments, trips, analytics, impressions, payouts, ledger entries, fraud flags, creatives, or zones.
5. Reporting endpoints must be strictly advertiser-tenant scoped.
6. Advertisers must see only campaigns in their own organization.
7. Cross-organization campaign access must not leak data. Prefer non-leaking 404.
8. Advertiser reports must not expose:
   - driver user id
   - driver full name
   - driver email
   - driver phone
   - driver license number
   - vehicle plate number
   - raw GPS coordinates
   - raw ping rows
   - idempotency keys
   - internal audit events
   - payment account data
9. Advertiser reports may expose aggregate or opaque operational identifiers where necessary:
   - campaign id
   - trip id
   - assignment id
   - creative id
   - zone id
   - vehicle type
   - trip started/ended timestamps
   - analytics/impression/payout metrics
10. Admin users should be rejected from advertiser reporting endpoints unless the existing project has a deliberate pattern allowing admin on advertiser routes. Prefer rejection.
11. Driver users and unauthenticated users must be rejected from all Slice 10 endpoints.
12. Use the existing standard error envelope for expected errors.

DATE FILTERING RULES

Use optional query parameters consistently:

- `start_at`
- `end_at`

Validation:

- If both are provided, `start_at` must be before or equal to `end_at`.
- Dates must be timezone-aware if the existing project requires that; otherwise normalize to UTC consistently with existing conventions.
- Return the applied `start_at` and `end_at` in response metadata.

Aggregation field conventions:

- Trip counts and route analytics should filter by `trip_sessions.started_at` where available.
- Impression metrics should filter by `impression_estimates.estimated_at`.
- Cost/payout metrics should filter by `payout_calculations.calculated_at`.
- Fraud flags should filter by `fraud_flags.detected_at`.
- Daily metrics should group by UTC calendar day based primarily on `trip_sessions.started_at`, with impression/payout/fraud values joined where possible.
- Document these choices in metadata or README notes.

If no date filter is supplied:
- Aggregate all stored data for the advertiser organization/campaign.
- Return `start_at: null` and `end_at: null`.

API ENDPOINTS

Implement these endpoints under `/api/v1`.

1. `GET /api/v1/advertiser/dashboard/summary`

Advertiser-only.

Query parameters:

- optional `start_at`
- optional `end_at`

Output shape:

```json
{
  "organization_id": "uuid",
  "currency": "NGN",
  "start_at": null,
  "end_at": null,
  "campaigns": {
    "total": 10,
    "draft": 1,
    "scheduled": 2,
    "active": 3,
    "paused": 1,
    "completed": 2,
    "cancelled": 1
  },
  "assignments": {
    "total": 25,
    "offered": 4,
    "accepted": 3,
    "active": 8,
    "deactivated": 5,
    "cancelled": 3,
    "completed": 2
  },
  "trips": {
    "total": 100,
    "ended": 90,
    "active": 10
  },
  "impressions": {
    "estimated_impressions": "123456.78",
    "estimated_trip_count": 80,
    "insufficient_data_trip_count": 5,
    "excluded_trip_count": 2,
    "average_confidence_score": "0.82"
  },
  "costs": {
    "totals_by_currency": [
      {
        "currency": "NGN",
        "final_payout_total": "100000.00",
        "gross_payout_total": "120000.00",
        "ledger_entry_count": 80
      }
    ]
  },
  "quality": {
    "average_quality_score": "0.88",
    "fraud_flags": {
      "open": 5,
      "acknowledged": 0,
      "dismissed": 1,
      "low": 2,
      "medium": 3,
      "high": 1
    }
  }
}

Rules:

Aggregate across campaigns belonging to the current advertiser organization.

Return stable zero shapes if no data exists.

Do not expose driver identities, plate numbers, raw pings, or ledger entry details.

Do not create missing estimates or payouts.

GET /api/v1/advertiser/campaigns/{campaign_id}/summary

Advertiser-only.

Query parameters:

optional start_at

optional end_at

Output shape:

JSON
{
  "campaign": {
    "id": "uuid",
    "name": "Lagos Launch Campaign",
    "status": "active",
    "start_at": "2026-06-01T00:00:00Z",
    "end_at": "2026-06-30T23:59:59Z",
    "budget_amount": "500000.00",
    "daily_budget_amount": "25000.00",
    "currency": "NGN"
  },
  "start_at": null,
  "end_at": null,
  "creatives": {
    "total": 2,
    "ready": 1,
    "draft": 1,
    "archived": 0
  },
  "zones": {
    "total": 3,
    "target": 1,
    "bonus": 1,
    "exclusion": 1
  },
  "assignments": {
    "total": 10,
    "offered": 1,
    "accepted": 1,
    "active": 4,
    "deactivated": 2,
    "cancelled": 1,
    "completed": 1
  },
  "trips": {
    "total": 20,
    "ended": 18,
    "active": 2
  },
  "route_analytics": {
    "analyzed_trip_count": 18,
    "total_distance_m": "250000.00",
    "target_zone_distance_m": "100000.00",
    "bonus_zone_distance_m": "50000.00",
    "exclusion_zone_distance_m": "1000.00",
    "average_quality_score": "0.87"
  },
  "impressions": {
    "estimated_impressions": "123456.78",
    "estimated_trip_count": 17,
    "insufficient_data_trip_count": 1,
    "excluded_trip_count": 0,
    "average_confidence_score": "0.84"
  },
  "costs": {
    "totals_by_currency": [
      {
        "currency": "NGN",
        "final_payout_total": "100000.00",
        "gross_payout_total": "120000.00",
        "calculated_trip_count": 17,
        "blocked_trip_count": 0,
        "insufficient_data_trip_count": 1,
        "ledger_entry_count": 17
      }
    ]
  },
  "fraud_flags": {
    "open": 3,
    "acknowledged": 0,
    "dismissed": 1,
    "low": 1,
    "medium": 2,
    "high": 1
  }
}

Rules:

Campaign must belong to the current advertiser organization.

Return stable zero shapes if campaign has no downstream data.

Do not expose driver identities, plate numbers, raw pings, or ledger entry details.

GET /api/v1/advertiser/campaigns/{campaign_id}/daily-metrics

Advertiser-only.

Query parameters:

optional start_at

optional end_at

optional limit, default 90, max 366

optional offset, default 0

Output shape:

JSON
{
  "campaign_id": "uuid",
  "start_at": null,
  "end_at": null,
  "items": [
    {
      "date": "2026-06-01",
      "trip_count": 5,
      "analyzed_trip_count": 5,
      "distance_m": "50000.00",
      "estimated_impressions": "10000.00",
      "average_confidence_score": "0.82",
      "final_payout_total": "5000.00",
      "gross_payout_total": "6000.00",
      "open_fraud_flag_count": 1,
      "average_quality_score": "0.88"
    }
  ],
  "total": 1,
  "limit": 90,
  "offset": 0
}

Rules:

Campaign must belong to the current advertiser organization.

Group by UTC calendar date.

Use existing stored data only.

If no data exists, return items: [] with stable pagination shape.

Do not create a campaign_daily_metrics table.

Do not auto-run calculations.

GET /api/v1/advertiser/campaigns/{campaign_id}/trips

Advertiser-only.

Query parameters:

optional start_at

optional end_at

optional limit, default 50, max 100

optional offset, default 0

optional status

optional has_fraud_flags, boolean

optional analytics_status

optional impression_status

optional payout_status

Output shape:

JSON
{
  "campaign_id": "uuid",
  "items": [
    {
      "trip_id": "uuid",
      "assignment_id": "uuid",
      "vehicle_type": "car",
      "trip_status": "ended",
      "started_at": "2026-06-01T10:00:00Z",
      "ended_at": "2026-06-01T11:00:00Z",
      "analytics": {
        "status": "computed",
        "distance_m": "10000.00",
        "moving_seconds": 3000,
        "stationary_seconds": 600,
        "quality_score": "0.90"
      },
      "impressions": {
        "status": "estimated",
        "estimated_impressions": "500.00",
        "confidence_score": "0.85"
      },
      "cost": {
        "status": "calculated",
        "currency": "NGN",
        "final_payout": "1200.00",
        "gross_payout": "1400.00"
      },
      "fraud_flags": {
        "open_count": 0,
        "high_count": 0,
        "medium_count": 0,
        "low_count": 0
      }
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}

Rules:

Campaign must belong to the current advertiser organization.

Return trip-level performance summaries only.

Do not expose:

driver user id

driver full name

driver email

driver phone

driver license number

driver profile id unless there is an existing public/anonymized convention

vehicle plate number

raw GPS coordinates

raw pings

idempotency keys

ledger entry ids/details

Use opaque trip_id and assignment_id only.

It is acceptable to include vehicle_type.

If analytics/impression/payout rows do not exist for a trip, return the nested section as null or a documented empty shape. Keep the response stable.

GET /api/v1/advertiser/campaigns/{campaign_id}/report

Advertiser-only.

Query parameters:

optional start_at

optional end_at

Output shape:

JSON
{
  "campaign_id": "uuid",
  "start_at": null,
  "end_at": null,
  "summary": {},
  "daily_metrics": [],
  "creative_summary": {},
  "zone_summary": {},
  "assignment_summary": {},
  "trip_summary": {},
  "impression_summary": {},
  "cost_summary": {},
  "fraud_summary": {}
}

Rules:

Campaign must belong to the current advertiser organization.

This endpoint is a bundled JSON report for frontend convenience.

It should reuse the same service aggregation logic as the summary and daily metrics endpoints.

It must not create PDF/CSV exports.

It must not create records or trigger calculations.

It must not include raw pings, driver identities, plate numbers, ledger entry details, or payment data.

Keep the response compact enough for an MVP dashboard. Do not add huge nested trip lists here; use the campaign trips endpoint for paginated trip details.

RESPONSE SERIALIZATION REQUIREMENTS

Use existing project conventions.

If Decimal values are already serialized as strings, continue that convention.

All reporting monetary and impression values should avoid JSON float precision ambiguity.

Use stable zero values:

Decimal totals: "0.00" or existing decimal-string convention.

Counts: 0.

Lists: [].

Nullable date range fields: null.

SECURITY AND VALIDATION REQUIREMENTS

All Slice 10 endpoints are advertiser-only.

Admin users must be rejected from Slice 10 advertiser endpoints unless the existing codebase has an explicit accepted admin-on-advertiser route pattern. Prefer rejection.

Driver users must be rejected from Slice 10 endpoints.

Unauthenticated users must be rejected from Slice 10 endpoints.

Advertiser users must see only campaigns in their own organization.

Cross-organization campaign access must return non-leaking 404 where practical.

Advertiser users without an active/invited organization membership should receive the existing advertiser organization error behavior.

Use existing standard error envelope for expected errors.

Do not introduce a new auth scheme.

Do not expose password hashes.

Do not expose raw pings.

Do not expose driver PII.

Do not expose vehicle plate numbers.

Do not expose payment account/settlement data.

Validate pagination limits and offsets.

Validate date ranges.

Reject invalid filter values with standard validation errors.

LIKELY FILES/AREAS TO CREATE OR CHANGE

Use existing Slice 0-Slice 9 conventions. Likely create/change:

app/api/v1/router.py

app/api/v1/reports.py or app/api/v1/advertiser_reports.py

app/schemas/reports.py

app/services/reports.py

Possibly app/schemas/common.py if existing pagination helpers need reuse

Possibly app/services/campaigns.py only if reusing campaign/org lookup helpers

README.md

tests/test_advertiser_dashboard.py

tests/test_campaign_reports.py

tests/test_reporting_privacy.py

tests/test_migration_slice10.py or update existing migration guard tests to assert no new tables

Possibly fixture updates in tests/conftest.py

docs/build-loop/reports/slice-10-advertiser-reporting.md

Do not create or modify Alembic migration files unless stopped/reconciled and explicitly approved.

TEST REQUIREMENTS

Add/extend tests for:

Dashboard summary:

Advertiser can read dashboard summary for own organization.

Dashboard summary aggregates only campaigns from current advertiser organization.

Dashboard summary excludes another organizationâ€™s campaigns and metrics.

Dashboard summary returns stable zero shapes for an organization with no campaigns or metrics.

Dashboard summary counts campaigns by status.

Dashboard summary counts assignments by status.

Dashboard summary counts trips by status.

Dashboard summary aggregates stored impression estimates.

Dashboard summary aggregates stored payout calculations by currency.

Dashboard summary aggregates fraud flag counts.

Dashboard summary applies optional date filters.

Dashboard summary does not auto-create impressions or payouts.

Campaign summary:

Advertiser can read summary for own campaign.

Advertiser cannot read summary for another organizationâ€™s campaign.

Campaign summary returns stable zero shapes for campaign with no downstream data.

Campaign summary includes creative counts by status.

Campaign summary includes zone counts by type.

Campaign summary includes assignment counts by status.

Campaign summary includes trip counts.

Campaign summary includes route analytics totals.

Campaign summary includes stored impression totals.

Campaign summary includes stored payout/cost totals by currency.

Campaign summary includes fraud flag counts.

Campaign summary applies optional date filters.

Campaign summary does not expose driver PII, vehicle plates, raw pings, or ledger details.

Daily metrics:

Advertiser can read daily metrics for own campaign.

Daily metrics group by UTC date.

Daily metrics aggregate trip count, analyzed trip count, distance, impressions, cost, fraud flag count, and quality score.

Daily metrics applies date filters.

Daily metrics supports pagination.

Daily metrics returns empty items for no data.

Daily metrics does not require or create a materialized table.

Campaign trips:

Advertiser can list trip summaries for own campaign.

Advertiser cannot list trip summaries for another organizationâ€™s campaign.

Campaign trips endpoint supports pagination.

Campaign trips endpoint supports status/filter parameters.

Campaign trips include analytics summary when analytics exists.

Campaign trips include impression summary when estimate exists.

Campaign trips include payout/cost summary when calculation exists.

Campaign trips include fraud flag counts.

Campaign trips do not expose driver user id, name, email, phone, license number, vehicle plate number, raw GPS coordinates, raw pings, idempotency keys, or ledger entry details.

Campaign trips uses stable null/empty nested shapes when optional downstream records are missing.

Campaign report:

Advertiser can read bundled report for own campaign.

Bundled report reuses summary/daily aggregation logic.

Bundled report does not include huge unpaginated trip lists.

Bundled report applies date filters.

Bundled report returns stable zero shapes when no metrics exist.

Bundled report does not create records or trigger calculations.

RBAC and validation:

Admin user is rejected from Slice 10 advertiser endpoints unless existing accepted pattern explicitly permits admin; prefer rejection.

Driver user is rejected from Slice 10 endpoints.

Unauthenticated user is rejected from Slice 10 endpoints.

Advertiser without organization membership receives existing standard error.

Invalid date range is rejected.

Invalid pagination values are rejected.

Invalid filter values are rejected.

Standard error envelope is used for expected errors.

Migration/scope guardrails:

No new Alembic migration is added.

No new database tables are added.

Existing Alembic head remains 0010_payouts_and_earnings.

Existing Slice 0-Slice 9 tests continue to pass.

No heatmap, billing, settlement, withdrawal, seed, background-job, map-tile, or audience/retargeting tables are added.

API responses do not expose password hashes or sensitive driver/payment data.

Testing implementation guidance:

Reuse existing test fixtures and auth helpers from prior slices.

Reuse existing campaign, trip analytics, impression estimate, payout calculation, and ledger factories/helpers where available.

Do not require external network access.

If existing tests use SQLite for speed, maintain compatibility where practical.

Postgres/PostGIS migration verification remains required even though this slice should not add a migration.

Keep tests deterministic.

Avoid making any reporting endpoint perform automatic calculations.

CHECKS THAT MUST WORK

The final implementation should support:

python -m pytest
python -m ruff check .
alembic upgrade head

Also verify Python 3.12 through Docker as in prior slices:

docker compose run --rm api python --version
docker compose run --rm api python -m pytest
docker compose run --rm api python -m ruff check .

Postgres/PostGIS migration and full-test verification is required:

$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic current
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest

If any command cannot be run locally due to missing external runtime or local environment issues, report that honestly with exact evidence.

FRONTEND CONTRACT NOTES

Advertiser dashboard can use:

http
GET /api/v1/advertiser/dashboard/summary

Advertiser campaign pages can use:

http
GET /api/v1/advertiser/campaigns/{campaign_id}/summary
GET /api/v1/advertiser/campaigns/{campaign_id}/daily-metrics
GET /api/v1/advertiser/campaigns/{campaign_id}/trips
GET /api/v1/advertiser/campaigns/{campaign_id}/report

All protected endpoints must use bearer token auth:

http
Authorization: Bearer <token>

After this slice, advertiser dashboards and campaign report pages can render from stored backend data. Heatmaps are still not available until Slice 11. Seed/demo data is still not available until Slice 12. MVP hardening remains Slice 13.

STANDARD ERROR BEHAVIOR

Use the existing Slice 0-Slice 9 error envelope for expected errors.

Expected examples:

Missing token

Invalid token

Forbidden role

Advertiser organization missing

Campaign not found

Campaign belongs to another organization

Invalid date range

Invalid pagination

Invalid filter value

Do not return raw stack traces.

ACCEPTANCE CRITERIA

Slice 10 is acceptable only if:

No new database tables are created.

No new Alembic migration is created.

Existing Alembic head remains 0010_payouts_and_earnings.

Advertiser can read organization dashboard summary.

Advertiser dashboard summary aggregates only current organization data.

Advertiser can read own campaign summary.

Advertiser can read own campaign daily metrics.

Advertiser can read own campaign trip summaries.

Advertiser can read own campaign bundled report.

Cross-organization campaign reporting access is blocked with non-leaking behavior.

Date filters are validated and applied consistently.

Pagination is enforced where applicable.

Reporting aggregates stored data only and does not auto-run analytics, impression estimation, or payout calculation.

Reporting endpoints return stable zero shapes when no data exists.

Reporting endpoints do not expose driver PII, vehicle plate numbers, raw pings, idempotency keys, ledger details, payment account data, password hashes, or unrelated sensitive data.

Admin/driver/unauthenticated access boundaries are enforced.

Tests pass.

Ruff passes.

Alembic upgrade head passes against Postgres/PostGIS.

Python 3.12 verification is performed through Docker or explicitly reported if impossible.

No deferred/future scope is implemented.

STOP CONDITIONS

Stop and report instead of implementing if:

Slice 9 accepted foundation is missing or materially different from the packet.

The existing project uses a materially different stack than the approved stack.

agent.md conflicts with this prompt.

Existing campaign, analytics, impression, payout, or ledger models make advertiser reporting ambiguous in a way that requires a product decision.

Existing advertiser campaign tenancy behavior makes report scoping ambiguous in a way that requires a product decision.

Implementing Slice 10 would require a new reporting/materialized metrics table.

Implementing Slice 10 would require generating missing analytics, impression estimates, or payout calculations automatically.

You are tempted to add heatmaps, map tiles, campaign daily metric tables, seed/demo data, background jobs, billing, settlement, withdrawals, invoices, or audience identity.

Otherwise, stop after Slice 10. Do not continue to Slice 11.

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
Dashboard aggregation approach:
Campaign summary approach:
Daily metrics aggregation approach:
Campaign trip reporting/privacy approach:
Bundled report approach:
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
Dashboard aggregation implemented:
Campaign summary implemented:
Daily metrics aggregation implemented:
Campaign trip reporting/privacy implemented:
Bundled report implemented:
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
Dashboard aggregation implemented:
Campaign summary implemented:
Daily metrics aggregation implemented:
Campaign trip reporting/privacy implemented:
Bundled report implemented:
Tests/checks run:
Exact command outputs or concise failure excerpts:
Known issues:
Out-of-scope confirmation:
Acceptance criteria checklist:
Codex questions:
Orchestrator recommendation: PASS_CANDIDATE | NEEDS_FIX | BLOCKED
