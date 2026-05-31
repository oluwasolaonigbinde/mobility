You are implementing Slice 3 of the Mobility AdTech & Audience Attribution backend.

Slice 0 project foundation, Slice 1 auth/users/advertiser organizations, and Slice 2 driver/vehicle foundations have been accepted by Pro review. Build on the existing repo foundation. Do not replace the stack, restructure the project unnecessarily, or introduce speculative scope.

Before starting implementation, confirm Slice 2 has been committed or that the working tree contains only the accepted Slice 2 state. If the repo has uncommitted unrelated changes, stop and report them.

PROJECT CONTEXT

Product:
Mobility AdTech & Audience Attribution Platform.

Backend goal:
Build the backend for a platform where advertisers run campaigns on shared ride vehicles, drivers and vehicles activate campaigns, GPS movement data is ingested, and later analytics support route analytics, impression estimation, payout calculations, advertiser reporting, and heatmap-ready geospatial data.

Slice 3 goal:
Implement advertiser campaign management and campaign creative metadata. This lets advertiser organizations create and manage campaigns and associate creative metadata with those campaigns before later slices add geofences, campaign assignment, GPS tracking, analytics, impressions, payouts, reports, and heatmaps.

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
- pytest
- ruff
- Docker Compose

IMPORTANT LOCAL NOTE

The local coding-guidelines file is named `agent.md`, even if other instructions mention `AGENTS.md`. Read and follow `agent.md`.

REQUIRED LOCAL INVESTIGATION BEFORE CODING

1. Inspect the current repo state.
2. Read `agent.md`.
3. Read the accepted Slice 0, Slice 1, and Slice 2 implementation reports under `docs/build-loop/reports/`.
4. Inspect existing app structure, routers, settings, error handling, request ID middleware, DB session setup, Alembic setup, auth dependencies, RBAC patterns, models, schemas, services, and tests.
5. Confirm the existing API prefix is `/api/v1`.
6. Confirm the existing standard error envelope and reuse it.
7. Confirm existing advertiser organization and membership model/service behavior.
8. Confirm existing pagination patterns.
9. Confirm no Slice 3 campaign or creative tables already exist.
10. If any local evidence conflicts with this prompt, stop and produce a reconciliation report instead of implementing blindly.

ALLOWED SCOPE

Implement only Slice 3:

1. Campaign model, schema, service, and API support.
2. Campaign creative metadata model, schema, service, and API support.
3. Advertiser endpoints for creating/listing/reading/updating campaigns in the current advertiser organization.
4. Advertiser endpoints for creating/listing/reading/updating creative metadata for campaigns in the current advertiser organization.
5. Admin read-only campaign oversight endpoints.
6. Alembic migration for exactly the Slice 3 campaign and campaign creative metadata tables, constraints, and indexes.
7. Tests for advertiser tenancy, campaign validation, creative metadata validation, RBAC, admin read-only visibility, migration behavior, and out-of-scope guardrails.
8. README/OpenAPI documentation updates only where needed for Slice 3 usage.
9. Audit events for campaign and creative create/update actions where they are straightforward using the existing audit event mechanism.

DO NOT IMPLEMENT

- Campaign target zones/geofences
- PostGIS geometry tables for campaign zones
- Campaign assignments
- Campaign activation by drivers/vehicles
- GPS pings
- Trip sessions
- Route analytics
- Fraud flags
- Impression estimation
- Payout calculation
- Earnings ledger
- Advertiser dashboard/reporting APIs
- Heatmap APIs
- Creative binary upload/storage pipeline
- S3/GCS/local file upload handling
- Asset processing/transcoding
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

Create a new Alembic migration after the Slice 2 migration.

Expected migration name:
`0004_campaigns_and_creatives`

Expected down revision:
`0003_driver_vehicle_foundations`

Use UUID primary keys. Prefer database-side UUID generation using `gen_random_uuid()`.

Use timezone-aware timestamps.

Use either PostgreSQL enums or string columns with database check constraints. Match the existing repo style unless there is a strong local reason not to.

Create exactly these new business tables:

1. `campaigns`

Required columns:

- `id` UUID primary key
- `organization_id` UUID foreign key to `advertiser_organizations.id`, not null
- `created_by_user_id` UUID foreign key to `users.id`, nullable or not null depending on existing service style; prefer not null for advertiser-created campaigns
- `name` text, not null
- `description` text nullable
- `status` constrained to:
  - `draft`
  - `scheduled`
  - `active`
  - `paused`
  - `completed`
  - `cancelled`
- `start_at` timezone-aware timestamp nullable
- `end_at` timezone-aware timestamp nullable
- `budget_amount` numeric/decimal nullable
- `daily_budget_amount` numeric/decimal nullable
- `currency` text, not null, default from advertiser organization currency or settings default
- `metadata` JSON/JSONB, not null, default empty object
- `created_at` timezone-aware timestamp, not null
- `updated_at` timezone-aware timestamp, not null

Rules:

- Campaign belongs to exactly one advertiser organization.
- Advertiser users can only access campaigns in their own organization.
- Admin users can list/read all campaigns through admin endpoints.
- `name` must be trimmed and non-empty.
- `description`, if supplied, should be trimmed.
- `currency` must be normalized uppercase and should be a simple 3-letter code.
- `budget_amount`, if supplied, must be >= 0.
- `daily_budget_amount`, if supplied, must be >= 0.
- If both `budget_amount` and `daily_budget_amount` are supplied, `daily_budget_amount` must not exceed `budget_amount`.
- If both `start_at` and `end_at` are supplied, `start_at` must be before `end_at`.
- `metadata` must be an object when supplied.
- No geofence/zone data belongs in this table in Slice 3.
- No assignment, tracking, analytics, impressions, or payout data belongs in this table in Slice 3.

Suggested indexes:

- `campaigns(organization_id)`
- `campaigns(organization_id, status)`
- `campaigns(start_at, end_at)`
- `campaigns(created_by_user_id)`

2. `campaign_creatives`

Required columns:

- `id` UUID primary key
- `campaign_id` UUID foreign key to `campaigns.id`, not null
- `name` text, not null
- `creative_type` constrained to:
  - `image`
  - `video`
  - `html`
  - `text`
  - `other`
- `placement` constrained to:
  - `vehicle_exterior`
  - `vehicle_interior`
  - `digital_screen`
  - `print`
  - `other`
- `asset_url` text nullable
- `mime_type` text nullable
- `width_px` integer nullable
- `height_px` integer nullable
- `duration_seconds` integer nullable
- `checksum` text nullable
- `status` constrained to:
  - `draft`
  - `ready`
  - `archived`
- `metadata` JSON/JSONB, not null, default empty object
- `created_at` timezone-aware timestamp, not null
- `updated_at` timezone-aware timestamp, not null

Rules:

- Creative belongs to exactly one campaign.
- Creative inherits advertiser org access through the campaign.
- Advertiser users can only access creatives for campaigns in their own organization.
- `name` must be trimmed and non-empty.
- `asset_url`, if supplied, must be an HTTP or HTTPS URL string. Do not fetch it.
- `mime_type`, if supplied, must be trimmed and non-empty.
- `width_px` and `height_px`, if supplied, must be positive integers.
- `duration_seconds`, if supplied, must be a positive integer.
- `checksum`, if supplied, must be trimmed.
- `metadata` must be an object when supplied.
- No binary upload, asset storage, image processing, transcoding, or external file validation in Slice 3.

Suggested indexes:

- `campaign_creatives(campaign_id)`
- `campaign_creatives(campaign_id, status)`
- `campaign_creatives(creative_type)`

AUDIT EVENT REQUIREMENTS

Use the existing `audit_events` table/service from Slice 1.

Write audit events for:

- `advertiser.campaign.created`
- `advertiser.campaign.updated`
- `advertiser.campaign_creative.created`
- `advertiser.campaign_creative.updated`

If admin read-only endpoints are implemented as specified, they do not need audit events.

Do not create a new audit table.

SECURITY AND VALIDATION REQUIREMENTS

1. Advertiser campaign endpoints require role `advertiser`.
2. Advertiser creative endpoints require role `advertiser`.
3. Admin campaign oversight endpoints require role `admin`.
4. Driver users must be rejected from campaign and creative endpoints.
5. Unauthenticated users must be rejected from all campaign and creative endpoints.
6. Advertiser users must only access campaigns and creatives in their own organization.
7. If existing memberships support `owner`, `manager`, and `viewer`:
   - `owner` and `manager` may create/update campaigns and creatives.
   - `viewer` may list/read campaigns and creatives but may not create/update.
   - If the existing code has no helper for this yet, implement a small focused helper without over-abstracting.
8. Advertiser users without an active organization membership must not create campaigns.
9. Admin users use admin endpoints for read-only oversight; do not let admin bypass advertiser endpoints unless existing patterns already allow it.
10. Use the existing standard error envelope from previous slices.
11. Reuse existing auth/current-user dependencies and role-check patterns.
12. Do not introduce new auth schemes.
13. Do not expose password hashes in any embedded user summary.
14. Do not expose unrelated driver/vehicle data from campaign responses.

API ENDPOINTS

Implement these endpoints under `/api/v1`.

Advertiser campaign endpoints:

1. `POST /api/v1/advertiser/campaigns`

Advertiser-only. Requires organization membership with write permission.

Input:

```json
{
  "name": "Lagos Launch Campaign",
  "description": "Brand campaign across shared ride vehicles.",
  "status": "draft",
  "start_at": "2026-06-01T00:00:00Z",
  "end_at": "2026-06-30T23:59:59Z",
  "budget_amount": "500000.00",
  "daily_budget_amount": "25000.00",
  "currency": "NGN",
  "metadata": {}
}

Output: created campaign.

Rules:

Organization is inferred from the current advertiser user's organization membership.

Do not allow client to set organization_id.

Do not allow client to set created_by_user_id.

Write audit event advertiser.campaign.created.

GET /api/v1/advertiser/campaigns

Advertiser-only.

Query parameters:

limit, default 50, max 100

offset, default 0

optional status

optional start_at_from

optional start_at_to

Output shape:

JSON
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}

Rules:

Returns only campaigns in the current advertiser organization.

GET /api/v1/advertiser/campaigns/{campaign_id}

Advertiser-only.

Rules:

Returns campaign only if it belongs to the current advertiser organization.

If campaign belongs to another organization, return 404 or forbidden using standard error envelope. Prefer non-leaking 404.

PATCH /api/v1/advertiser/campaigns/{campaign_id}

Advertiser-only. Requires organization membership with write permission.

Allowed update fields:

JSON
{
  "name": "Updated Campaign Name",
  "description": "Updated description",
  "status": "paused",
  "start_at": "2026-06-01T00:00:00Z",
  "end_at": "2026-06-30T23:59:59Z",
  "budget_amount": "500000.00",
  "daily_budget_amount": "25000.00",
  "currency": "NGN",
  "metadata": {}
}

Rules:

Advertiser can update only campaigns in their own organization.

Do not allow organization_id or created_by_user_id updates.

Enforce all campaign validation rules after patching.

Write audit event advertiser.campaign.updated.

Advertiser creative endpoints:

POST /api/v1/advertiser/campaigns/{campaign_id}/creatives

Advertiser-only. Requires organization membership with write permission.

Input:

JSON
{
  "name": "Exterior Wrap Artwork",
  "creative_type": "image",
  "placement": "vehicle_exterior",
  "asset_url": "https://example.com/assets/wrap.png",
  "mime_type": "image/png",
  "width_px": 1200,
  "height_px": 800,
  "duration_seconds": null,
  "checksum": "sha256-placeholder",
  "status": "draft",
  "metadata": {}
}

Output: created creative.

Rules:

Campaign must belong to current advertiser organization.

Do not fetch or upload the asset.

Write audit event advertiser.campaign_creative.created.

GET /api/v1/advertiser/campaigns/{campaign_id}/creatives

Advertiser-only.

Query parameters:

limit, default 50, max 100

offset, default 0

optional status

optional creative_type

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

GET /api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}

Advertiser-only.

Rules:

Campaign must belong to current advertiser organization.

Creative must belong to the campaign.

Cross-org or cross-campaign access must not leak data.

PATCH /api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}

Advertiser-only. Requires organization membership with write permission.

Allowed update fields:

JSON
{
  "name": "Updated Creative Name",
  "creative_type": "image",
  "placement": "vehicle_exterior",
  "asset_url": "https://example.com/assets/wrap-v2.png",
  "mime_type": "image/png",
  "width_px": 1200,
  "height_px": 800,
  "duration_seconds": null,
  "checksum": "sha256-placeholder-v2",
  "status": "ready",
  "metadata": {}
}

Rules:

Campaign must belong to current advertiser organization.

Creative must belong to campaign.

Do not allow campaign_id updates.

Enforce all creative validation rules after patching.

Write audit event advertiser.campaign_creative.updated.

Admin read-only oversight endpoints:

GET /api/v1/admin/campaigns

Admin-only.

Query parameters:

limit, default 50, max 100

offset, default 0

optional organization_id

optional status

Output shape:

JSON
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}

Rules:

Admin can list campaigns across organizations.

Do not include creative binary data.

Include minimal organization summary if straightforward.

GET /api/v1/admin/campaigns/{campaign_id}

Admin-only.

Rules:

Admin can read a campaign across organizations.

Include campaign fields and minimal organization summary if straightforward.

Do not include unrelated driver/vehicle/tracking data.

Do not add admin write endpoints for campaigns in Slice 3 unless existing repo patterns make it trivial and it remains strictly within campaign metadata management. Prefer advertiser-owned writes for this slice.

RESPONSE SHAPE GUIDANCE

Campaign response should include at minimum:

JSON
{
  "id": "uuid",
  "organization_id": "uuid",
  "name": "Lagos Launch Campaign",
  "description": "Brand campaign across shared ride vehicles.",
  "status": "draft",
  "start_at": "2026-06-01T00:00:00Z",
  "end_at": "2026-06-30T23:59:59Z",
  "budget_amount": "500000.00",
  "daily_budget_amount": "25000.00",
  "currency": "NGN",
  "metadata": {},
  "created_at": "2026-05-31T00:00:00Z",
  "updated_at": "2026-05-31T00:00:00Z"
}

Creative response should include at minimum:

JSON
{
  "id": "uuid",
  "campaign_id": "uuid",
  "name": "Exterior Wrap Artwork",
  "creative_type": "image",
  "placement": "vehicle_exterior",
  "asset_url": "https://example.com/assets/wrap.png",
  "mime_type": "image/png",
  "width_px": 1200,
  "height_px": 800,
  "duration_seconds": null,
  "checksum": "sha256-placeholder",
  "status": "draft",
  "metadata": {},
  "created_at": "2026-05-31T00:00:00Z",
  "updated_at": "2026-05-31T00:00:00Z"
}

For Decimal values, use the existing project convention. If no convention exists, return them as strings to avoid JSON float precision ambiguity.

LIKELY FILES/AREAS TO CREATE OR CHANGE

Use existing Slice 0/Slice 1/Slice 2 conventions. Likely create/change:

app/api/v1/router.py

app/api/v1/campaigns.py or similar

app/api/v1/admin_campaigns.py or existing admin router if cleaner

app/models/campaign.py

app/models/__init__.py

app/schemas/campaigns.py

app/services/campaigns.py

app/services/audit.py only if needed to add action helpers

app/api/v1/dependencies.py only if needed to add advertiser membership write/read helpers

app/db/base.py only if model imports require update

alembic/versions/0004_campaigns_and_creatives.py

README.md

tests for campaigns, creatives, access control, validation, admin read-only views, migration behavior

docs/build-loop/reports/slice-03-campaigns-creatives.md

Keep code simple. Avoid unnecessary abstractions.

TEST REQUIREMENTS

Add/extend tests for:

Campaign access and validation:

Advertiser owner can create a campaign in own organization.

Advertiser manager can create a campaign in own organization if membership roles are already supported.

Advertiser viewer cannot create/update campaigns.

Advertiser without organization membership cannot create campaigns.

Driver user is rejected from advertiser campaign endpoints.

Admin user is rejected from advertiser campaign endpoints unless existing patterns explicitly allow otherwise; admin should use admin endpoints.

Unauthenticated users are rejected from campaign endpoints.

Campaign organization is inferred from current advertiser membership, not client input.

Advertiser can list only own organization campaigns.

Advertiser can read only own organization campaign.

Advertiser cannot read another organization’s campaign.

Advertiser can update own organization campaign.

Advertiser cannot update another organization’s campaign.

Invalid campaign status is rejected.

Empty/blank campaign name is rejected.

Invalid budget values are rejected.

daily_budget_amount greater than budget_amount is rejected.

Invalid date range is rejected.

Currency is normalized uppercase and invalid currency shape is rejected.

Metadata must be an object.

Creative access and validation:

Advertiser owner/manager can create creative metadata for own campaign.

Advertiser viewer cannot create/update creative metadata.

Advertiser cannot create creative metadata for another organization’s campaign.

Advertiser can list creatives for own campaign.

Advertiser cannot list creatives for another organization’s campaign.

Advertiser can read own campaign creative.

Advertiser cannot read creative through wrong campaign ID.

Advertiser can update own campaign creative.

Invalid creative type is rejected.

Invalid placement is rejected.

Invalid creative status is rejected.

Blank creative name is rejected.

Invalid asset URL is rejected.

Non-positive width/height/duration values are rejected.

Metadata must be an object.

Admin and audit:

Admin can list campaigns across organizations.

Admin can read a campaign across organizations.

Non-admin users are rejected from admin campaign endpoints.

Audit event is created for advertiser campaign creation.

Audit event is created for advertiser campaign update.

Audit event is created for creative creation.

Audit event is created for creative update.

Migration and scope:

Alembic migration creates exactly campaigns and campaign_creatives as new Slice 3 tables.

Migration does not create zones, assignments, pings, trips, analytics, impression, payout, report, heatmap, or seed tables.

Password hashes are still not returned in any embedded user summaries.

Existing Slice 0-Slice 2 tests continue to pass.

Testing implementation guidance:

Reuse existing test fixtures and auth helpers from prior slices.

If existing tests use SQLite for speed, maintain compatibility where practical, but do not weaken Postgres migration verification.

Migration verification against Postgres/PostGIS remains required.

Keep tests deterministic.

Do not require external network access; asset URLs are strings only.

CHECKS THAT MUST WORK

The final implementation should support:

python -m pytest
python -m ruff check .
alembic upgrade head

Also verify Python 3.12 through Docker as in prior slices:

docker compose run --rm api python --version
docker compose run --rm api python -m pytest
docker compose run --rm api python -m ruff check .

If any command cannot be run locally due to missing external runtime or local environment issues, report that honestly with exact evidence.

FRONTEND CONTRACT NOTES

Advertiser dashboard can use:

http
POST  /api/v1/advertiser/campaigns
GET   /api/v1/advertiser/campaigns
GET   /api/v1/advertiser/campaigns/{campaign_id}
PATCH /api/v1/advertiser/campaigns/{campaign_id}

POST  /api/v1/advertiser/campaigns/{campaign_id}/creatives
GET   /api/v1/advertiser/campaigns/{campaign_id}/creatives
GET   /api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}
PATCH /api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}

Admin tools can use:

http
GET /api/v1/admin/campaigns
GET /api/v1/admin/campaigns/{campaign_id}

All protected endpoints must use bearer token auth:

http
Authorization: Bearer <token>

Campaign and creative response shapes must be stable enough for future frontend work.

Creative binary uploads are explicitly deferred. Frontend may provide asset_url metadata only in this slice.

STANDARD ERROR BEHAVIOR

Use the existing Slice 0/Slice 1/Slice 2 error envelope for expected errors.

Expected examples:

Missing token

Invalid token

Forbidden role

Advertiser organization missing

Membership lacks write permission

Campaign not found

Campaign belongs to another organization

Creative not found

Creative belongs to another campaign

Invalid campaign status

Invalid campaign dates

Invalid campaign budget

Invalid creative type/status/placement

Invalid asset URL

Invalid metadata

Do not return raw stack traces.

ACCEPTANCE CRITERIA

Slice 3 is acceptable only if:

Alembic migration creates exactly the approved campaigns and campaign_creatives tables, constraints, and indexes.

No Slice 4+ domain tables are added.

Campaigns belong to advertiser organizations.

Advertiser users can create/list/read/update only campaigns in their own organization.

Advertiser organization write permissions are enforced for create/update.

Admin can list/read campaigns across organizations through admin endpoints.

Campaign validation covers status, name, budget, currency, date range, and metadata.

Creative metadata belongs to campaigns.

Advertiser users can create/list/read/update only creatives for campaigns in their own organization.

Creative validation covers type, placement, status, name, asset URL, dimensions, duration, checksum, and metadata.

Audit events are written for campaign and creative create/update actions.

API responses do not expose password hashes.

Tests pass.

Ruff passes.

Alembic upgrade head passes against Postgres/PostGIS.

Python 3.12 verification is performed through Docker or explicitly reported if impossible.

No deferred/future scope is implemented.

STOP CONDITIONS

Stop and report instead of implementing if:

Slice 2 accepted foundation is missing or materially different from the packet.

The existing project uses a materially different stack than the approved stack.

agent.md conflicts with this prompt.

The DB/migration setup cannot support Slice 3 without reworking previous slices.

Existing advertiser organization membership behavior makes tenant scoping ambiguous in a way that requires a product decision.

Creative metadata cannot be implemented without deciding actual binary storage.

You are tempted to add zones/geofences, assignments, GPS, analytics, payouts, reports, heatmaps, or seed/demo scope.

Otherwise, stop after Slice 3. Do not continue to Slice 4.

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
Tests/checks run:
Exact command outputs or concise failure excerpts:
Known issues:
Out-of-scope confirmation:
Acceptance criteria checklist:
Codex questions:
Orchestrator recommendation: PASS_CANDIDATE | NEEDS_FIX | BLOCKED