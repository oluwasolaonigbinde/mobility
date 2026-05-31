Verdict: PASS

Safe to commit: Yes. Commit Slice 3 before starting Slice 4.

Basis: the packet reports the approved campaigns and campaign_creatives migration only, the required advertiser/admin campaign and creative metadata endpoints, tenant-scoped advertiser access, owner/manager write checks, validation coverage, audit events, passing host and Docker checks, Python 3.12 Docker verification, and no Slice 4+ scope.

Pasted text

Recommended commit message:

feat: add campaign and creative metadata management

Full Slice 4 implementation prompt:

You are implementing Slice 4 of the Mobility AdTech & Audience Attribution backend.

Slice 0 project foundation, Slice 1 auth/users/advertiser organizations, Slice 2 driver/vehicle foundations, and Slice 3 campaign/creative metadata have been accepted by Pro review. Build on the existing repo foundation. Do not replace the stack, restructure the project unnecessarily, or introduce speculative scope.

Before starting implementation, confirm Slice 3 has been committed or that the working tree contains only the accepted Slice 3 state. If the repo has uncommitted unrelated changes, stop and report them.

PROJECT CONTEXT

Product:
Mobility AdTech & Audience Attribution Platform.

Backend goal:
Build the backend for a platform where advertisers run campaigns on shared ride vehicles, drivers and vehicles activate campaigns, GPS movement data is ingested, and later analytics support route analytics, impression estimation, payout calculations, advertiser reporting, and heatmap-ready geospatial data.

Slice 4 goal:
Implement campaign target zones/geofences. This lets advertiser organizations attach geospatial targeting, exclusion, and bonus zones to campaigns using GeoJSON polygons/multipolygons stored in PostGIS. Later slices will use these zones for campaign assignment context, trip-zone overlap analytics, impression estimation, payout logic, and heatmap/reporting support.

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
- pytest
- ruff
- Docker Compose

ALLOWED DEPENDENCY NOTE

This slice requires real PostGIS geometry storage/query behavior.

You may add `GeoAlchemy2` if it is the cleanest way to model PostGIS geometry columns with SQLAlchemy. If you can implement the geometry column and PostGIS operations cleanly with SQLAlchemy/Alembic/raw SQL only, that is also acceptable.

Do not add large geospatial frameworks, map SDKs, tile servers, shapely/geopandas, external geocoding APIs, or client-side map dependencies in this slice.

IMPORTANT LOCAL NOTE

The local coding-guidelines file is named `agent.md`, even if other instructions mention `AGENTS.md`. Read and follow `agent.md`.

REQUIRED LOCAL INVESTIGATION BEFORE CODING

1. Inspect the current repo state.
2. Read `agent.md`.
3. Read the accepted Slice 0, Slice 1, Slice 2, and Slice 3 implementation reports under `docs/build-loop/reports/`.
4. Inspect existing app structure, routers, settings, error handling, request ID middleware, DB session setup, Alembic setup, auth dependencies, RBAC patterns, models, schemas, services, and tests.
5. Inspect existing campaign model/service/router and advertiser membership write-permission helpers from Slice 3.
6. Confirm the existing API prefix is `/api/v1`.
7. Confirm the existing standard error envelope and reuse it.
8. Confirm the current Alembic head is `0004_campaigns_and_creatives`.
9. Confirm no Slice 4 campaign zone/geofence table already exists.
10. Determine whether current tests use SQLite for speed and how Postgres/PostGIS migration verification is run.
11. If any local evidence conflicts with this prompt, stop and produce a reconciliation report instead of implementing blindly.

ALLOWED SCOPE

Implement only Slice 4:

1. Campaign zone/geofence model, schema, service, and API support.
2. GeoJSON validation for Polygon and MultiPolygon inputs.
3. PostGIS geometry storage for campaign zones.
4. Advertiser endpoints for creating/listing/reading/updating/deleting zones for campaigns in the current advertiser organization.
5. Owner/manager write permissions for create/update/delete.
6. Viewer read permissions for list/read only.
7. Alembic migration for exactly the Slice 4 `campaign_zones` table, constraints, and indexes.
8. Tests for geospatial validation, tenant scoping, RBAC, membership permissions, zone CRUD, migration behavior, audit events, and out-of-scope guardrails.
9. README/OpenAPI documentation updates only where needed for Slice 4 usage.
10. Audit events for campaign zone create/update/delete actions using the existing audit event mechanism.

DO NOT IMPLEMENT

- Campaign assignment
- Campaign activation by drivers/vehicles
- Driver campaign availability
- GPS pings
- Trip sessions
- Route analytics
- Zone-overlap trip analytics
- Fraud flags
- Impression estimation
- Payout calculation
- Earnings ledger
- Advertiser dashboard/reporting APIs
- Heatmap APIs
- Map tiles
- Mapbox integration
- Geocoding/reverse-geocoding
- External map provider integration
- Automatic route matching
- Creative binary upload/storage pipeline
- Seed/demo trip data
- Celery/background jobs
- Public self-registration
- OAuth/social login
- Refresh-token flow
- Frontend/mobile implementation
- GitHub remote/PR setup
- Production cloud deployment
- Retargeting
- Audience pooling
- AI/computer vision
- Real payment settlement

DATA MODEL REQUIREMENTS

Create a new Alembic migration after the Slice 3 migration.

Expected migration name:
`0005_campaign_zones`

Expected down revision:
`0004_campaigns_and_creatives`

Use UUID primary keys. Prefer database-side UUID generation using `gen_random_uuid()`.

Use timezone-aware timestamps.

Use PostGIS geometry storage with SRID 4326.

Create exactly this new business table:

1. `campaign_zones`

Required columns:

- `id` UUID primary key
- `campaign_id` UUID foreign key to `campaigns.id`, not null
- `created_by_user_id` UUID foreign key to `users.id`, nullable or not null depending on existing service style; prefer not null for advertiser-created zones
- `name` text, not null
- `description` text nullable
- `zone_type` constrained to:
  - `target`
  - `exclusion`
  - `bonus`
- `geom` PostGIS geometry, not null
  - Preferred type: `geometry(MultiPolygon, 4326)`
  - If local implementation strongly favors `geometry(Geometry, 4326)`, document why and still enforce Polygon/MultiPolygon through service validation.
- `metadata` JSON/JSONB, not null, default empty object
- `created_at` timezone-aware timestamp, not null
- `updated_at` timezone-aware timestamp, not null

Rules:

- Campaign zone belongs to exactly one campaign.
- Campaign zone inherits advertiser organization access through the campaign.
- Advertiser users can only access zones for campaigns in their own organization.
- Store geometries in SRID 4326.
- Accept GeoJSON `Polygon` and `MultiPolygon`.
- Normalize incoming `Polygon` to `MultiPolygon` if using a MultiPolygon geometry column.
- Return GeoJSON geometry in API responses.
- Use GeoJSON coordinate order `[longitude, latitude]`.
- Enforce longitude between -180 and 180.
- Enforce latitude between -90 and 90.
- Enforce closed linear rings.
- Enforce valid polygons/multipolygons.
- Use PostGIS validity checks, such as `ST_IsValid`, as the authoritative geometry validity check.
- Enforce a configurable maximum zone area.
- Add a setting such as `MAX_CAMPAIGN_ZONE_AREA_SQ_KM`, defaulting to a reasonable local value such as `5000`.
- Compute area using geography-safe PostGIS behavior, for example `ST_Area(geom::geography)`, not naive degree-area math.
- `name` must be trimmed and non-empty.
- `description`, if supplied, should be trimmed.
- `metadata` must be an object when supplied.
- If SQLAlchemy requires the model attribute to be named `metadata_`, keep the database column and API field named `metadata`.

Suggested constraints/indexes:

- Check constraint for `zone_type`.
- GiST index on `geom`.
- Index on `campaign_id`.
- Composite index on `(campaign_id, zone_type)`.
- Index on `created_by_user_id` if included.

Do not create assignment, trip, ping, analytics, impression, payout, report, heatmap, or seed tables.

AUDIT EVENT REQUIREMENTS

Use the existing `audit_events` table/service from Slice 1.

Write audit events for:

- `advertiser.campaign_zone.created`
- `advertiser.campaign_zone.updated`
- `advertiser.campaign_zone.deleted`

For delete, record the audit event before deleting or otherwise ensure the deleted zone id/campaign id are captured in metadata.

Do not create a new audit table.

SECURITY AND VALIDATION REQUIREMENTS

1. Advertiser campaign-zone endpoints require role `advertiser`.
2. Driver users must be rejected from all campaign-zone endpoints.
3. Admin users must be rejected from advertiser campaign-zone endpoints unless an existing project-wide pattern explicitly allows admin impersonation, which should not be introduced here.
4. Unauthenticated users must be rejected from all campaign-zone endpoints.
5. Advertiser users must only access zones for campaigns in their own organization.
6. If existing memberships support `owner`, `manager`, and `viewer`:
   - `owner` and `manager` may create/update/delete campaign zones.
   - `viewer` may list/read campaign zones but may not create/update/delete.
7. Advertiser users without an active organization membership must not create campaign zones.
8. Cross-organization campaign/zone access should use non-leaking 404s where practical.
9. Cross-campaign zone access should use non-leaking 404s where practical.
10. Do not allow client to set `campaign_id` in the JSON body; it comes from the path.
11. Do not allow client to set `created_by_user_id`.
12. Use the existing standard error envelope from previous slices.
13. Reuse existing auth/current-user dependencies and role-check patterns.
14. Reuse existing advertiser membership write/read helpers where appropriate.
15. Do not introduce new auth schemes.
16. Do not expose password hashes in any embedded user summary.
17. Do not expose driver/vehicle/tracking data from campaign-zone responses.

CAMPAIGN LIFECYCLE RULES

Keep lifecycle behavior simple and deterministic:

- Zones may be listed/read for any accessible campaign.
- Zones may be created/updated/deleted for campaigns in statuses:
  - `draft`
  - `scheduled`
  - `active`
  - `paused`
- Zones must not be created/updated/deleted for campaigns in statuses:
  - `completed`
  - `cancelled`

Use the existing campaign status values from Slice 3.

If local Slice 3 implementation makes this difficult, stop and report a design ambiguity rather than silently ignoring campaign lifecycle rules.

API ENDPOINTS

Implement these endpoints under `/api/v1`.

1. `POST /api/v1/advertiser/campaigns/{campaign_id}/zones`

Advertiser-only. Requires organization membership with write permission.

Input:

```json
{
  "name": "Lagos Island Target Zone",
  "description": "Primary campaign exposure area.",
  "zone_type": "target",
  "geometry": {
    "type": "Polygon",
    "coordinates": [
      [
        [3.3900, 6.4500],
        [3.4100, 6.4500],
        [3.4100, 6.4700],
        [3.3900, 6.4700],
        [3.3900, 6.4500]
      ]
    ]
  },
  "metadata": {}
}

Output: created campaign zone.

Rules:

Campaign must belong to current advertiser organization.

Organization is inferred through campaign ownership and current membership.

Do not allow client to set campaign_id in request body.

Do not allow client to set created_by_user_id.

Validate geometry before persistence.

Persist geometry in PostGIS.

Write audit event advertiser.campaign_zone.created.

GET /api/v1/advertiser/campaigns/{campaign_id}/zones

Advertiser-only.

Query parameters:

limit, default 50, max 100

offset, default 0

optional zone_type

Output shape:

JSON
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}

Rules:

Campaign must belong to current advertiser organization.

Viewer membership may list zones.

Return only zones for the campaign.

GET /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}

Advertiser-only.

Rules:

Campaign must belong to current advertiser organization.

Zone must belong to the campaign.

Cross-organization or cross-campaign reads must not leak data.

PATCH /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}

Advertiser-only. Requires organization membership with write permission.

Allowed update fields:

JSON
{
  "name": "Updated Lagos Island Target Zone",
  "description": "Updated description.",
  "zone_type": "bonus",
  "geometry": {
    "type": "MultiPolygon",
    "coordinates": [
      [
        [
          [3.3900, 6.4500],
          [3.4100, 6.4500],
          [3.4100, 6.4700],
          [3.3900, 6.4700],
          [3.3900, 6.4500]
        ]
      ]
    ]
  },
  "metadata": {}
}

Rules:

Campaign must belong to current advertiser organization.

Zone must belong to campaign.

Do not allow campaign_id or created_by_user_id updates.

Enforce all validation rules after patching.

If geometry is supplied, validate and replace the stored geometry.

Write audit event advertiser.campaign_zone.updated.

DELETE /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}

Advertiser-only. Requires organization membership with write permission.

Rules:

Campaign must belong to current advertiser organization.

Zone must belong to campaign.

Cross-organization or cross-campaign deletes must not leak data.

Hard delete is acceptable for Slice 4.

Write audit event advertiser.campaign_zone.deleted.

Return 204 No Content on success.

Do not add admin zone endpoints in Slice 4 unless the existing local architecture clearly already provides a generic admin read-only pattern and implementation remains tiny. Prefer no admin zone endpoints for this slice.

RESPONSE SHAPE GUIDANCE

Campaign zone response should include at minimum:

JSON
{
  "id": "uuid",
  "campaign_id": "uuid",
  "name": "Lagos Island Target Zone",
  "description": "Primary campaign exposure area.",
  "zone_type": "target",
  "geometry": {
    "type": "MultiPolygon",
    "coordinates": [
      [
        [
          [3.3900, 6.4500],
          [3.4100, 6.4500],
          [3.4100, 6.4700],
          [3.3900, 6.4700],
          [3.3900, 6.4500]
        ]
      ]
    ]
  },
  "area_sq_m": "4938271.12",
  "metadata": {},
  "created_at": "2026-05-31T00:00:00Z",
  "updated_at": "2026-05-31T00:00:00Z"
}

Notes:

If Decimal values are used for area_sq_m, follow existing Decimal response conventions. If no convention exists, return area as a string to avoid JSON float precision ambiguity.

If the implementation returns Polygon for Polygon input instead of normalized MultiPolygon, document that choice and keep it consistent.

Do not return raw WKB/WKT geometry.

LIKELY FILES/AREAS TO CREATE OR CHANGE

Use existing Slice 0-Slice 3 conventions. Likely create/change:

app/api/v1/router.py

app/api/v1/campaign_zones.py or existing campaign router if cleaner

app/models/campaign_zone.py

app/models/__init__.py

app/schemas/campaign_zones.py

app/services/campaign_zones.py

app/services/campaigns.py only if needed to reuse campaign/org lookup

app/services/audit.py only if needed to add action helpers

app/api/v1/dependencies.py only if needed to reuse/add advertiser membership helpers

app/core/config.py for MAX_CAMPAIGN_ZONE_AREA_SQ_KM

app/db/base.py only if model imports require update

alembic/versions/0005_campaign_zones.py

.env.example

README.md

tests/test_campaign_zones.py

tests/test_migration_slice4.py

Possibly test fixture updates in tests/conftest.py

docs/build-loop/reports/slice-04-campaign-zones.md

Keep code simple. Avoid unnecessary abstractions.

GEOSPATIAL IMPLEMENTATION GUIDANCE

Use PostGIS for authoritative geometry persistence and validation.

Recommended service behavior:

Validate high-level GeoJSON shape in Python:

type must be Polygon or MultiPolygon.

Coordinates must be arrays of valid lon/lat pairs.

Linear rings must have at least 4 coordinate pairs.

Linear rings must be closed.

Coordinates must be finite numbers.

Longitude/latitude bounds must be enforced.

Convert Polygon to MultiPolygon if storing geometry(MultiPolygon, 4326).

Serialize normalized GeoJSON to JSON.

Use PostGIS to create geometry:

ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326)

If needed, use ST_Multi(...).

Validate:

ST_IsValid(geom)

GeometryType or equivalent type check

ST_SRID(geom) = 4326

area cap using ST_Area(geom::geography)

Return geometry using:

ST_AsGeoJSON(geom)

Add GiST index on geom.

Do not store zones as JSON-only. PostGIS geometry storage is required.

TEST REQUIREMENTS

Add/extend tests for:

Zone CRUD and permissions:

Advertiser owner can create a target zone for own organization campaign.

Advertiser manager can create a zone for own organization campaign.

Advertiser viewer can list/read zones but cannot create/update/delete zones.

Advertiser without organization membership cannot create/list/read zones.

Driver user is rejected from campaign-zone endpoints.

Admin user is rejected from advertiser campaign-zone endpoints.

Unauthenticated users are rejected from campaign-zone endpoints.

Campaign ownership is inferred through current advertiser organization.

Advertiser cannot create zone for another organization’s campaign.

Advertiser can list only zones for own organization campaign.

Advertiser can read own campaign zone.

Advertiser cannot read another organization’s campaign zone.

Advertiser cannot read a zone through the wrong campaign ID.

Advertiser owner/manager can update own campaign zone.

Advertiser cannot update another organization’s campaign zone.

Advertiser owner/manager can delete own campaign zone.

Advertiser cannot delete another organization’s campaign zone.

Deleted zone is no longer returned by list/read if hard delete is used.

Campaign lifecycle:

Zone create/update/delete is rejected for completed campaigns.

Zone create/update/delete is rejected for cancelled campaigns.

Zone list/read still works for completed/cancelled campaigns.

GeoJSON and geometry validation:

Valid Polygon is accepted.

Valid MultiPolygon is accepted.

Invalid GeoJSON type is rejected.

FeatureCollection is rejected unless explicitly and consistently supported; preferred behavior is reject.

Coordinates outside longitude/latitude bounds are rejected.

Non-closed polygon ring is rejected.

Polygon ring with fewer than 4 points is rejected.

Self-intersecting or otherwise invalid polygon is rejected through PostGIS validity checks.

Area greater than configured max is rejected.

Blank zone name is rejected.

Invalid zone type is rejected.

Metadata must be an object.

Patch with invalid geometry does not corrupt existing zone.

Patch recomputes returned area if geometry changes.

Response returns GeoJSON, not WKT/WKB.

Audit and migration:

Audit event is created for zone creation.

Audit event is created for zone update.

Audit event is created for zone delete.

Alembic migration creates exactly campaign_zones as the new Slice 4 table.

Migration creates a PostGIS geometry column with SRID 4326.

Migration creates a GiST index on zone geometry.

Migration does not create assignments, pings, trips, analytics, impressions, payouts, reports, heatmaps, or seed tables.

Existing Slice 0-Slice 3 tests continue to pass.

Testing implementation guidance:

This slice depends on PostGIS. Do not fake geospatial behavior with JSON-only tests.

It is acceptable to run campaign-zone API tests against a real PostgreSQL/PostGIS test database if SQLite cannot support the geometry behavior.

If the existing default test suite uses SQLite for speed, update the test strategy carefully so python -m pytest still passes and PostGIS-specific tests are either:

run against a configured Postgres/PostGIS test database, or

explicitly skipped only when PostGIS is unavailable, while Docker-based pytest must run them.

Migration verification against Postgres/PostGIS is required.

Keep tests deterministic.

Do not require external network access.

CHECKS THAT MUST WORK

The final implementation should support:

python -m pytest
python -m ruff check .
alembic upgrade head

Also verify Python 3.12 through Docker as in prior slices:

docker compose run --rm api python --version
docker compose run --rm api python -m pytest
docker compose run --rm api python -m ruff check .

PostGIS migration verification is required:

$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic current

If any command cannot be run locally due to missing external runtime or local environment issues, report that honestly with exact evidence.

FRONTEND CONTRACT NOTES

Advertiser dashboard map editor can use:

http
POST   /api/v1/advertiser/campaigns/{campaign_id}/zones
GET    /api/v1/advertiser/campaigns/{campaign_id}/zones
GET    /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}
PATCH  /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}
DELETE /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}

All protected endpoints must use bearer token auth:

http
Authorization: Bearer <token>

Frontend should send GeoJSON Polygon or MultiPolygon geometry using [longitude, latitude] coordinate order.

Backend returns GeoJSON geometry and calculated area.

No heatmap API is available yet. No map tiles are available yet. No route overlap analytics are available yet.

STANDARD ERROR BEHAVIOR

Use the existing Slice 0-Slice 3 error envelope for expected errors.

Expected examples:

Missing token

Invalid token

Forbidden role

Advertiser organization missing

Membership lacks write permission

Campaign not found

Campaign belongs to another organization

Campaign status does not allow zone mutation

Zone not found

Zone belongs to another campaign

Invalid zone type

Invalid GeoJSON

Invalid polygon

Invalid coordinate bounds

Zone area exceeds configured maximum

Invalid metadata

Do not return raw stack traces.

ACCEPTANCE CRITERIA

Slice 4 is acceptable only if:

Alembic migration creates exactly the approved campaign_zones table, constraints, and indexes.

campaign_zones.geom is stored as a real PostGIS geometry with SRID 4326.

A GiST index exists on the geometry column.

No Slice 5+ domain tables are added.

Campaign zones belong to campaigns.

Campaign zones inherit advertiser organization access through campaigns.

Advertiser users can create/list/read/update/delete only zones for campaigns in their own organization.

Advertiser organization write permissions are enforced for create/update/delete.

Viewer memberships can list/read but cannot create/update/delete.

Driver/admin/unauthenticated access boundaries are enforced.

Campaign lifecycle restrictions for completed/cancelled zone mutation are enforced.

GeoJSON validation covers type, coordinate bounds, closed rings, minimum ring size, metadata, and invalid geometry.

PostGIS validity and area cap checks are enforced.

API responses return GeoJSON geometry and calculated area, not raw WKT/WKB.

Audit events are written for zone create/update/delete actions.

API responses do not expose password hashes or unrelated driver/vehicle/tracking data.

Tests pass.

Ruff passes.

Alembic upgrade head passes against Postgres/PostGIS.

Python 3.12 verification is performed through Docker or explicitly reported if impossible.

No deferred/future scope is implemented.

STOP CONDITIONS

Stop and report instead of implementing if:

Slice 3 accepted foundation is missing or materially different from the packet.

The existing project uses a materially different stack than the approved stack.

agent.md conflicts with this prompt.

The DB/migration setup cannot support PostGIS geometry columns without reworking previous slices.

The test infrastructure cannot support any meaningful PostGIS-backed validation path.

Existing advertiser organization membership behavior makes tenant scoping ambiguous in a way that requires a product decision.

GeoJSON handling requires deciding a frontend map-library contract beyond standard GeoJSON.

You are tempted to add assignments, GPS, trip sessions, analytics, impressions, payouts, reports, heatmaps, map tiles, or seed/demo scope.

Otherwise, stop after Slice 4. Do not continue to Slice 5.

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
Geospatial validation/storage approach:
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
Geospatial validation/storage implemented:
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
Geospatial validation/storage implemented:
Tests/checks run:
Exact command outputs or concise failure excerpts:
Known issues:
Out-of-scope confirmation:
Acceptance criteria checklist:
Codex questions:
Orchestrator recommendation: PASS_CANDIDATE | NEEDS_FIX | BLOCKED
