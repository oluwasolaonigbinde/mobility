CODEX BUILD REPORT

Slice:
Slice 4 - Campaign zones/geofences

Status: PASS_CANDIDATE

Summary:
Recovered, completed, and verified the partial Slice 4 implementation for advertiser campaign zones/geofences. The slice adds a single `campaign_zones` business table with real PostGIS `geometry(MultiPolygon,4326)` storage, advertiser-scoped zone CRUD endpoints, GeoJSON Polygon/MultiPolygon normalization and validation, PostGIS validity and geography-area enforcement, lifecycle mutation guards, owner/manager write permissions, viewer read permissions, audit events, docs/config updates, and focused tests.

Local investigation performed:
- Read `agent.md`.
- Read `docs/build-loop/prompts/slice-04-campaign-zones.md`.
- Read accepted Slice 0, Slice 1, Slice 2, and Slice 3 reports under `docs/build-loop/reports/`.
- Inspected current git status and confirmed the dirty tree was Slice 4-shaped partial work.
- Inspected existing campaign, creative, advertiser organization, membership, auth dependency, audit event, router, settings, DB base, and test fixture patterns.
- Confirmed API prefix remains `/api/v1`.
- Confirmed current Alembic head moves from `0004_campaigns_and_creatives` to `0005_campaign_zones`.
- Confirmed campaign zone tests use a real PostgreSQL/PostGIS database when `DATABASE_URL` or `TEST_DATABASE_URL` is configured and skip only when no PostGIS database URL is available.

Files changed:
- `.env.example`
- `README.md`
- `alembic/versions/0005_campaign_zones.py`
- `app/api/v1/campaign_zones.py`
- `app/api/v1/router.py`
- `app/core/config.py`
- `app/db/base.py`
- `app/models/campaign_zone.py`
- `app/schemas/campaign_zones.py`
- `app/services/campaign_zones.py`
- `docker-compose.yml`
- `docs/build-loop/reports/slice-04-campaign-zones.md`
- `docs/build-loop/slice-log.md`
- `tests/conftest.py`
- `tests/test_campaign_zones.py`
- `tests/test_migration_slice4.py`

Database migrations:
- Added `0005_campaign_zones`, after `0004_campaigns_and_creatives`.
- Creates exactly one new Slice 4 business table: `campaign_zones`.
- Uses UUID primary key with `gen_random_uuid()`.
- Adds `campaign_id`, `created_by_user_id`, name/description, constrained `zone_type`, PostGIS `geometry(MultiPolygon,4326)` `geom`, JSONB `metadata`, and timezone-aware timestamps.
- Adds FK constraints to `campaigns.id` and `users.id`.
- Adds indexes on `campaign_id`, `(campaign_id, zone_type)`, `created_by_user_id`, and a GiST index on `geom`.
- Adds no assignment, GPS, trip, analytics, impression, payout, report, heatmap, seed, or future-scope tables.

API endpoints implemented:
- `POST /api/v1/advertiser/campaigns/{campaign_id}/zones`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/zones`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}`
- `PATCH /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}`
- `DELETE /api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}`

Security/validation implemented:
- Campaign zone endpoints require authenticated advertiser users.
- Admin, driver, and unauthenticated access are rejected through the existing error envelope.
- Campaign access is inherited through existing advertiser organization membership and campaign ownership.
- Owner and manager memberships can create/update/delete.
- Viewer memberships can list/read but cannot create/update/delete.
- Advertisers without an organization membership are rejected.
- Cross-organization and cross-campaign access returns non-leaking 404s where practical.
- Client cannot set `campaign_id` or `created_by_user_id` in request bodies.
- Mutations are allowed only for campaigns in `draft`, `scheduled`, `active`, or `paused`.
- Mutations are blocked for `completed` and `cancelled`; reads remain allowed.
- Audit events are written for `advertiser.campaign_zone.created`, `advertiser.campaign_zone.updated`, and `advertiser.campaign_zone.deleted`.

Geospatial validation/storage implemented:
- Accepts GeoJSON `Polygon` and `MultiPolygon`.
- Normalizes `Polygon` inputs to `MultiPolygon`.
- Enforces `[longitude, latitude]` coordinate pairs, finite numeric coordinates, lon/lat bounds, closed rings, and minimum ring size before persistence.
- Uses PostGIS `ST_GeomFromGeoJSON`, `ST_SetSRID`, `ST_Multi`, `ST_IsValid`, `ST_IsValidReason`, `ST_GeometryType`, and `ST_SRID` for authoritative geometry validation.
- Computes area with `ST_Area(geom::geography)`.
- Enforces `MAX_CAMPAIGN_ZONE_AREA_SQ_KM`, default `5000`.
- Stores real PostGIS geometry and returns GeoJSON through `ST_AsGeoJSON`, never WKT/WKB.

Tests added/updated:
- Added PostGIS-backed campaign zone API tests for owner/manager creation, viewer read-only access, role and authentication rejection, missing membership rejection, tenant and campaign scoping, update/delete behavior, lifecycle restrictions, GeoJSON/schema validation, PostGIS invalid polygon detection, area cap enforcement, patch integrity, response shape, and audit events.
- Added Slice 4 migration guard test for table, geometry column, indexes, down revision, and out-of-scope table exclusions.
- Extended test fixtures with isolated PostGIS schema setup when a Postgres/PostGIS URL is configured.

Commands run:
- `python -m pytest`
- `python -m ruff check .`
- `docker compose up -d db`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest tests/test_campaign_zones.py`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head; if ($LASTEXITCODE -eq 0) { python -m alembic current }`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest`
- `docker compose build api`
- `docker compose run --rm api python --version`
- `docker compose run --rm api python -m pytest`
- `docker compose run --rm api python -m ruff check .`

Command results:
- Host `python -m pytest` without `DATABASE_URL`: 71 passed, 8 skipped, 1 existing FastAPI/TestClient deprecation warning. Skips were the PostGIS-specific campaign zone API tests due to no configured PostGIS URL.
- Host `python -m ruff check .`: all checks passed.
- `docker compose up -d db`: DB container running.
- Host PostGIS targeted `python -m pytest tests/test_campaign_zones.py` with `DATABASE_URL`: 8 passed, 1 existing FastAPI/TestClient deprecation warning.
- Host Alembic upgrade/current with `DATABASE_URL`: upgrade passed; current reported `0005_campaign_zones (head)`.
- Host full `python -m pytest` with `DATABASE_URL`: 79 passed, 1 existing FastAPI/TestClient deprecation warning.
- `docker compose build api`: succeeded.
- Docker Python version: Python 3.12.13.
- Docker `python -m pytest`: 79 passed, 1 existing FastAPI/TestClient deprecation warning.
- Docker `python -m ruff check .`: all checks passed.

Known issues:
- Host Python is 3.14.4, while the fixed stack is Python 3.12. Docker verified Python 3.12.13 successfully.
- Existing FastAPI/TestClient stack emits a deprecation warning about `httpx`; tests pass.
- PostGIS-specific API tests intentionally skip on host when no `DATABASE_URL` or `TEST_DATABASE_URL` is configured.

Out-of-scope compliance:
- No campaign assignments, driver campaign activation, GPS pings, trip sessions, route analytics, fraud flags, impression estimation, payout calculation, earnings ledger, advertiser dashboard/reporting APIs, heatmap APIs, map tiles, external map providers, geocoding, creative binary upload/storage pipeline, seed/demo trip data, background jobs, frontend/mobile code, GitHub remote/PR setup, production deployment, retargeting, audience pooling, AI/computer vision, or payment settlement were implemented.
- No commit was created.

Acceptance criteria checklist:
- Alembic migration creates only the approved `campaign_zones` table: yes.
- `campaign_zones.geom` is real PostGIS geometry with SRID 4326: yes.
- GiST index exists on the geometry column: yes.
- No Slice 5+ domain tables were added: yes.
- Campaign zones belong to campaigns: yes.
- Zones inherit advertiser organization access through campaigns: yes.
- Advertisers can access only own-organization campaign zones: yes.
- Owner/manager write permissions are enforced: yes.
- Viewer list/read-only behavior is enforced: yes.
- Driver/admin/unauthenticated boundaries are enforced: yes.
- Completed/cancelled campaign mutation restrictions are enforced: yes.
- GeoJSON validation covers type, coordinate bounds, closed rings, minimum ring size, metadata, and invalid geometry: yes.
- PostGIS validity and geography area cap checks are enforced: yes.
- Responses return GeoJSON geometry and calculated area: yes.
- Audit events are written for create/update/delete: yes.
- Responses do not expose password hashes or unrelated driver/vehicle/tracking data: yes.
- Tests pass: yes.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres/PostGIS: yes.
- Python 3.12 verification performed: yes, via Docker.
- No deferred/future scope implemented: yes.

Manual verification steps:
- Use an advertiser owner or manager bearer token to create a campaign, then call `POST /api/v1/advertiser/campaigns/{campaign_id}/zones` with GeoJSON Polygon or MultiPolygon coordinates in `[longitude, latitude]` order.
- Use a viewer membership bearer token for the same organization to confirm list/read succeed while create/update/delete return forbidden.
- Use a different advertiser organization token to confirm cross-organization reads and mutations return 404.
- Set the campaign status to `completed` or `cancelled` and confirm list/read still work while create/update/delete are blocked.

Questions for Pro reviewer:
- None.
