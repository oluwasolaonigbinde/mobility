CODEX BUILD REPORT

Slice:
Slice 3 - Campaigns and campaign creative metadata

Status: PASS_CANDIDATE

Summary:
Implemented the approved Slice 3 backend only: advertiser campaign metadata, campaign
creative metadata, advertiser tenant-scoped CRUD-style metadata endpoints, admin
read-only campaign oversight endpoints, audit events for advertiser create/update
actions, the Slice 3 Alembic migration, README endpoint notes, and focused tests.
A clean verification/fix worker found and fixed one partial campaign date PATCH edge
case where SQLite can return a stored datetime as naive while the request datetime is
timezone-aware; combined date validation now returns `INVALID_CAMPAIGN_DATES` instead
of a server error.

Local investigation performed:
- Confirmed current branch: `slice-03-campaigns-and-creatives`.
- Confirmed the only pre-existing uncommitted file was `docs/build-loop/slice-log.md`,
  already marking Slice 3 in progress; it was left intact.
- Read `agent.md`.
- Read the approved Slice 3 prompt.
- Read accepted Slice 0, Slice 1, and Slice 2 build reports.
- Inspected existing `/api/v1` router prefix, settings, error envelope, request ID
  middleware, DB session setup, Alembic setup, auth/RBAC dependencies, advertiser
  organization membership behavior, model/schema/service style, pagination patterns,
  audit event service, README, and tests.
- Confirmed no campaign or creative tables/models existed before Slice 3.

Files changed:
- `README.md`
- `alembic/versions/0004_campaigns_and_creatives.py`
- `app/api/v1/campaigns.py`
- `app/api/v1/router.py`
- `app/db/base.py`
- `app/models/campaign.py`
- `app/schemas/campaigns.py`
- `app/services/campaigns.py`
- `docs/build-loop/reports/slice-03-campaigns-and-creatives.md`
- `tests/conftest.py`
- `tests/test_campaign_creatives.py`
- `tests/test_campaigns.py`
- `tests/test_migration_slice3.py`

Pre-existing dirty file left intact:
- `docs/build-loop/slice-log.md`

Database migrations:
- Added `0004_campaigns_and_creatives`, after `0003_driver_vehicle_foundations`.
- Creates exactly the new Slice 3 business tables:
  - `campaigns`
  - `campaign_creatives`
- Uses UUID primary keys with `gen_random_uuid()`.
- Adds timestamp, JSONB metadata, status/type/placement, budget, date-range,
  positive-dimension/duration constraints, FKs, and requested indexes.
- Adds no zones, geofences, assignments, GPS, trips, analytics, impressions,
  payouts, earnings, report, heatmap, seed, storage, or upload tables.

API endpoints implemented:
- `POST /api/v1/advertiser/campaigns`
- `GET /api/v1/advertiser/campaigns`
- `GET /api/v1/advertiser/campaigns/{campaign_id}`
- `PATCH /api/v1/advertiser/campaigns/{campaign_id}`
- `POST /api/v1/advertiser/campaigns/{campaign_id}/creatives`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/creatives`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}`
- `PATCH /api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}`
- `GET /api/v1/admin/campaigns`
- `GET /api/v1/admin/campaigns/{campaign_id}`

Security/validation implemented:
- Advertiser endpoints require role `advertiser`.
- Admin campaign oversight endpoints require role `admin`.
- Driver, admin-on-advertiser-endpoint, non-admin-on-admin-endpoint, and
  unauthenticated access are rejected through the existing error envelope.
- Advertiser organization is inferred from the current membership; clients cannot set
  `organization_id`, `created_by_user_id`, or `campaign_id` on writes.
- Active `owner` and `manager` memberships can create/update.
- `viewer` and invited memberships cannot create/update.
- Advertisers can list/read/update only campaigns and creatives in their own
  organization, with non-leaking 404s for cross-org/cross-campaign access.
- Campaign validation covers status, trimmed non-empty name, trimmed description,
  timezone-aware dates, valid date range, nonnegative budgets, daily budget not
  exceeding total budget, mixed stored/request datetime comparison, uppercase
  3-letter currency, and object metadata.
- Creative validation covers type, placement, status, trimmed non-empty name, HTTP(S)
  asset URL, trimmed non-empty MIME type, positive dimensions/duration, trimmed
  checksum, object metadata, and extra-field rejection for deferred binary/upload data.
- Audit events are written for campaign create/update and creative create/update.
- Responses do not expose password hashes or driver/vehicle/tracking data.

Tests added/updated:
- Added campaign endpoint tests for owner/manager create, viewer and invited
  membership write denial, missing organization denial, role/RBAC rejection,
  unauthenticated rejection, tenant-scoped list/read/update, cross-org non-leakage,
  validation failures, partial date PATCH validation, admin list/read across
  organizations, audit events, and password-hash non-exposure.
- Added creative endpoint tests for owner/manager create, viewer write denial,
  cross-org create denial, campaign/cross-campaign scoping, list/read/update,
  validation failures, role/RBAC rejection, unauthenticated rejection, audit events,
  and out-of-scope binary-field rejection.
- Added Slice 3 migration guard test.
- Extended test fixtures with campaign and campaign creative factories.

Commands run:
- `python -m ruff check .`
- `python -m pytest tests/test_campaigns.py`
- `python -m pytest tests/test_campaigns.py tests/test_campaign_creatives.py tests/test_migration_slice3.py`
- `python -m pytest`
- `docker compose up -d db`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic current`
- `docker compose build api`
- `docker compose run --rm api python --version`
- `docker compose run --rm api python -m pytest`
- `docker compose run --rm api python -m ruff check .`

Command results:
- Host `python -m ruff check .`: all checks passed.
- Host targeted `python -m pytest tests/test_campaigns.py`: 8 passed, 1 existing
  FastAPI/TestClient deprecation warning.
- Host targeted `python -m pytest tests/test_campaigns.py tests/test_campaign_creatives.py tests/test_migration_slice3.py`: 17 passed, 1 existing FastAPI/TestClient deprecation warning.
- Host `python -m pytest`: 70 passed, 1 existing FastAPI/TestClient deprecation warning.
- `docker compose up -d db`: DB container running.
- Host Alembic upgrade with configured Postgres URL: passed.
- Host Alembic current with configured Postgres URL: `0004_campaigns_and_creatives (head)`.
- Docker API build: succeeded.
- Docker Python version: Python 3.12.13.
- Docker `python -m pytest`: 70 passed, 1 existing FastAPI/TestClient deprecation warning.
- Docker `python -m ruff check .`: all checks passed.

Known issues:
- Host Python is 3.14.4, while the fixed stack is Python 3.12; Docker verified
  Python 3.12.13 successfully.
- The existing FastAPI/TestClient stack still emits a deprecation warning about
  `httpx`; tests pass.
- `docs/build-loop/slice-log.md` remains dirty from the orchestrator's pre-existing
  Slice 3 in-progress update.

Out-of-scope compliance:
- No geofence/zone/PostGIS campaign geometry, campaign assignments, driver activation,
  GPS pings, trip sessions, route analytics, fraud flags, impression estimation,
  payout calculation, earnings ledger, dashboard/report APIs, heatmap APIs, binary
  upload/storage/processing, seed/demo data, background jobs, frontend/mobile code,
  deployment, retargeting, audience pooling, AI/CV, payments, OAuth, refresh tokens,
  public registration, GitHub setup, Pro packets, Pro responses, or commits were added.

Acceptance criteria checklist:
- Alembic migration creates only `campaigns` and `campaign_creatives`: yes.
- Campaigns belong to advertiser organizations: yes.
- Advertiser users can create/list/read/update only own-organization campaigns: yes.
- Organization write permissions are enforced for campaign writes: yes.
- Admin can list/read campaigns across organizations through read-only endpoints: yes.
- Campaign validation covers status, name, budget, currency, date range, metadata: yes.
- Creative metadata belongs to campaigns: yes.
- Advertiser users can create/list/read/update only creatives for own campaigns: yes.
- Creative validation covers type, placement, status, name, asset URL, dimensions,
  duration, checksum, metadata: yes.
- Audit events are written for campaign and creative create/update actions: yes.
- API responses do not expose password hashes: yes.
- Tests pass: yes.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres/PostGIS: yes.
- Python 3.12 verification performed: yes, via Docker.
- No deferred/future scope implemented: yes.

Manual verification steps:
- Use an advertiser owner/manager bearer token to create and update
  `/api/v1/advertiser/campaigns`.
- Use the same advertiser token to create and update
  `/api/v1/advertiser/campaigns/{campaign_id}/creatives`.
- Use another advertiser token to confirm cross-org campaign and creative reads return
  non-leaking 404s.
- Use an admin bearer token to call `/api/v1/admin/campaigns` and
  `/api/v1/admin/campaigns/{campaign_id}` across organizations.

Questions for Pro reviewer:
- None.
