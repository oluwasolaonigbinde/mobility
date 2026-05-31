PRO REVIEW PACKET

Slice:
Slice 3 - Campaign management and creative metadata.

Repo state summary:
- Branch: `slice-03-campaigns-and-creatives`.
- Base/previous accepted slice: Slice 2 on `slice-02-driver-vehicle-foundations`, commit `ab59754`, with ledger commit `70cb4e3`.
- Current state: uncommitted Slice 3 implementation pending Pro review.
- Local constraints file is `agent.md`.
- API prefix remains `/api/v1`.
- Existing roles remain `admin`, `advertiser`, `driver`.
- Existing advertiser organization membership roles remain `owner`, `manager`, `viewer`.

Approved Slice 3 scope:
- Campaign metadata model/schema/service/API.
- Campaign creative metadata model/schema/service/API.
- Advertiser endpoints for tenant-scoped campaign create/list/read/update.
- Advertiser endpoints for campaign-scoped creative metadata create/list/read/update.
- Admin read-only campaign oversight endpoints.
- Alembic migration for exactly `campaigns` and `campaign_creatives`.
- Tests for tenancy, validation, RBAC, admin visibility, migration, audit events, and out-of-scope guardrails.
- README/OpenAPI notes as needed.

Commit status:
- Not committed.
- Pro packet added by orchestrator after implementation, clean fix pass, and local verification.
- Pro response pending.

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
- `docs/build-loop/slice-log.md`
- `tests/conftest.py`
- `tests/test_campaigns.py`
- `tests/test_campaign_creatives.py`
- `tests/test_migration_slice3.py`

Diff summary:
- Adds campaign and campaign creative SQLAlchemy models and enums.
- Adds Pydantic schemas for campaign create/update/read/list/admin responses and creative create/update/read/list.
- Adds services for advertiser context, membership write checks, campaign CRUD, creative metadata CRUD, admin campaign listing/reading, and combined validation after patching.
- Adds advertiser campaign/creative endpoints and admin read-only campaign endpoints.
- Wires the campaign router into `/api/v1`.
- Imports the new model module into DB metadata setup.
- Adds Alembic revision `0004_campaigns_and_creatives`.
- Extends tests with campaign and creative factories.
- Adds campaign, creative, and migration tests.
- Updates README with Slice 3 endpoint and scope notes.
- Updates the build-loop report and slice log.

Database migrations:
- New revision: `0004_campaigns_and_creatives`.
- Down revision: `0003_driver_vehicle_foundations`.
- Creates exactly:
  - `campaigns`
  - `campaign_creatives`
- Uses UUID primary keys with `gen_random_uuid()`.
- Uses JSONB defaults of empty object in Alembic.
- Adds campaign constraints:
  - `ck_campaigns_status`
  - `ck_campaigns_currency_length`
  - `ck_campaigns_budget_amount_non_negative`
  - `ck_campaigns_daily_budget_amount_non_negative`
  - `ck_campaigns_daily_budget_not_exceed_budget`
  - `ck_campaigns_date_range`
- Adds campaign indexes:
  - `ix_campaigns_organization_id`
  - `ix_campaigns_organization_status`
  - `ix_campaigns_start_end`
  - `ix_campaigns_created_by_user_id`
- Adds creative constraints:
  - `ck_campaign_creatives_creative_type`
  - `ck_campaign_creatives_placement`
  - `ck_campaign_creatives_status`
  - `ck_campaign_creatives_width_positive`
  - `ck_campaign_creatives_height_positive`
  - `ck_campaign_creatives_duration_positive`
- Adds creative indexes:
  - `ix_campaign_creatives_campaign_id`
  - `ix_campaign_creatives_campaign_status`
  - `ix_campaign_creatives_creative_type`
- Does not add Slice 4+ tables.

API endpoints:
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
- Driver users, admin users on advertiser endpoints, non-admin users on admin endpoints, and unauthenticated users are rejected through the existing error envelope.
- Advertiser organization is inferred from current membership; clients cannot set `organization_id`, `created_by_user_id`, or `campaign_id` on writes.
- Active `owner` and `manager` memberships can create/update campaigns and creatives.
- `viewer` and invited memberships cannot create/update campaigns or creatives.
- Advertisers can list/read/update only campaigns in their own organization.
- Advertisers can create/list/read/update only creatives for campaigns in their own organization.
- Cross-organization and cross-campaign reads/writes use non-leaking 404s where applicable.
- Admin endpoints are read-only list/read only.
- Campaign validation covers status, trimmed non-empty name, trimmed description, timezone-aware dates, date range, nonnegative budgets, daily budget not exceeding total budget, uppercase 3-letter currency, and object metadata.
- Clean fix pass added mixed stored/request datetime comparison handling so partial date PATCH returns `INVALID_CAMPAIGN_DATES` instead of a server error when SQLite returns an existing stored datetime as naive.
- Creative validation covers type, placement, status, trimmed non-empty name, HTTP(S) asset URL without fetching, trimmed non-empty MIME type, positive dimensions/duration, trimmed checksum, object metadata, and extra-field rejection for deferred binary/upload data.
- Audit events are written for:
  - `advertiser.campaign.created`
  - `advertiser.campaign.updated`
  - `advertiser.campaign_creative.created`
  - `advertiser.campaign_creative.updated`
- Responses do not expose password hashes or driver/vehicle/tracking data.

Tests/checks run:
- `python -m pytest tests/test_campaigns.py`
- `python -m pytest tests/test_campaigns.py tests/test_campaign_creatives.py tests/test_migration_slice3.py`
- `python -m pytest`
- `python -m ruff check .`
- `git diff --check`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic current`
- `docker compose build api`
- `docker compose run --rm api python --version`
- `docker compose run --rm api python -m pytest`
- `docker compose run --rm api python -m ruff check .`

Exact command outputs or concise failure excerpts:
- Host targeted `python -m pytest tests/test_campaigns.py`: `8 passed, 1 warning`.
- Host targeted `python -m pytest tests/test_campaigns.py tests/test_campaign_creatives.py tests/test_migration_slice3.py`: `17 passed, 1 warning`.
- Host `python -m pytest`: `70 passed, 1 warning`.
- Host `python -m ruff check .`: `All checks passed!`
- `git diff --check`: no whitespace errors; Git reported only expected CRLF conversion warnings.
- Host Alembic upgrade: passed with PostgreSQL transactional DDL context.
- Host Alembic current: `0004_campaigns_and_creatives (head)`.
- `docker compose build api`: image built successfully.
- Docker Python version: `Python 3.12.13`.
- Docker `python -m pytest`: `70 passed, 1 warning`.
- Docker `python -m ruff check .`: `All checks passed!`

Implementation/fix-pass reports:
- Primary implementation worker: `PASS_CANDIDATE`.
- Clean verification/fix worker: `PASS_CANDIDATE`; fixed partial campaign date PATCH mixed naive/aware datetime comparison and added regression coverage.
- Final build report path: `docs/build-loop/reports/slice-03-campaigns-and-creatives.md`.

Known issues:
- Host Python is 3.14.4, while the fixed stack requires Python 3.12. Docker verified Python 3.12.13 successfully.
- Existing FastAPI/TestClient stack emits a Starlette deprecation warning about `httpx`; tests pass.
- No acceptance blockers known locally.

Out-of-scope confirmation:
- No campaign zones/geofences/PostGIS campaign geometry, campaign assignments, driver activation, GPS pings, trip sessions, route analytics, fraud flags, impression estimation, payouts, earnings ledger, dashboard/report APIs, heatmaps, binary upload/storage/processing, seed/demo data, background jobs, frontend/mobile code, deployment, retargeting, audience pooling, AI/CV, payments, OAuth, refresh tokens, public registration, or GitHub setup were implemented.

Acceptance criteria checklist:
- Alembic migration creates exactly approved `campaigns` and `campaign_creatives` tables: yes.
- No Slice 4+ domain tables are added: yes.
- Campaigns belong to advertiser organizations: yes.
- Advertiser users can create/list/read/update only own-organization campaigns: yes.
- Advertiser organization write permissions are enforced for campaign writes: yes.
- Admin can list/read campaigns across organizations through read-only admin endpoints: yes.
- Campaign validation covers status, name, budget, currency, date range, and metadata: yes.
- Creative metadata belongs to campaigns: yes.
- Advertiser users can create/list/read/update only creatives for own-organization campaigns: yes.
- Creative validation covers type, placement, status, name, asset URL, dimensions, duration, checksum, and metadata: yes.
- Audit events are written for campaign and creative create/update actions: yes.
- API responses do not expose password hashes: yes.
- Tests pass: yes, 70 passed.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres/PostGIS: yes.
- Python 3.12 verification performed: yes, Docker Python 3.12.13.
- No deferred/future scope implemented: yes.

Codex questions:
- None.

Orchestrator recommendation:
PASS_CANDIDATE. If Pro agrees, please return `Verdict: PASS`, say whether it is safe to commit, provide the recommended commit message, and provide the complete Slice 4 implementation prompt.
