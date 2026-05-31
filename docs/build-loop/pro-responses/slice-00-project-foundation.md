Verdict: PASS

Safe to commit: Yes. Commit Slice 0 before starting Slice 1.

Slice 0 is accepted based on the review packet: the foundation files were added, the initial migration enables only pgcrypto and postgis, the required health/readiness/OpenAPI endpoints exist, pytest/ruff/Alembic/Docker Compose checks passed, and the packet confirms no Slice 1+ domain scope was implemented. 

Pasted text

Recommended commit message:

feat: add backend project foundation

Full Slice 1 implementation prompt:

You are implementing Slice 1 of the Mobility AdTech & Audience Attribution backend.

Slice 0 foundation has been accepted by Pro review. Build on the existing repo foundation. Do not replace the stack, restructure the project unnecessarily, or introduce speculative scope.

Before starting implementation, confirm Slice 0 has been committed or that the working tree contains only the accepted Slice 0 state. If the repo has uncommitted unrelated changes, stop and report them.

PROJECT CONTEXT

Product:
Mobility AdTech & Audience Attribution Platform.

Backend goal:
Build the backend for a platform where advertisers run campaigns on shared ride vehicles, drivers and vehicles activate campaigns, GPS movement data is ingested, and later analytics support route analytics, impression estimation, payout calculations, advertiser reporting, and heatmap-ready geospatial data.

Slice 1 goal:
Establish identity, role-based access control, admin user management, advertiser organization tenancy, and current-user context for future frontend/mobile work.

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
- Secure password hashing
- pytest
- ruff
- Docker Compose

IMPORTANT LOCAL NOTE

The local coding-guidelines file is named `agent.md`, even if other instructions mention `AGENTS.md`. Read and follow `agent.md`.

REQUIRED LOCAL INVESTIGATION BEFORE CODING

1. Inspect the current repo state.
2. Read `agent.md`.
3. Read the accepted Slice 0 implementation report under `docs/build-loop/reports/`.
4. Inspect existing app structure, settings, error handling, request ID middleware, DB session setup, Alembic setup, and tests.
5. Confirm the existing API prefix is `/api/v1`.
6. Confirm the existing standard error envelope and reuse it.
7. Confirm whether password/security dependencies already exist in `pyproject.toml`; add only what is needed.
8. Confirm no Slice 1 domain tables already exist.
9. If any local evidence conflicts with this prompt, stop and produce a reconciliation report instead of implementing blindly.

ALLOWED SCOPE

Implement only Slice 1:

1. User accounts.
2. Password hashing and verification.
3. JWT bearer login.
4. Current-user dependency.
5. Role-based access dependencies.
6. Admin user creation/list/update.
7. Advertiser organization creation.
8. Advertiser organization membership.
9. Current advertiser organization lookup.
10. Audit events for admin-created users and organizations.
11. Alembic migration for Slice 1 tables/enums/constraints.
12. Tests for auth, RBAC, tenancy, password hashing, duplicate email handling, and migration behavior.
13. README/OpenAPI documentation updates only where needed for Slice 1 usage.

DO NOT IMPLEMENT

- Driver profiles
- Vehicle profiles
- Campaigns
- Creatives
- Campaign zones/geofences
- Campaign assignments
- Campaign activation
- GPS pings
- Trip sessions
- Route analytics
- Fraud flags
- Impression estimation
- Payout calculation
- Earnings ledger
- Advertiser dashboard/reporting APIs
- Heatmap APIs
- Seed/demo trip data
- Celery/background jobs
- Public self-registration
- OAuth/social login
- Refresh-token flow unless already trivially present and approved by existing architecture
- Frontend/mobile implementation
- GitHub remote/PR setup
- Production cloud deployment
- Retargeting
- Audience pooling
- AI/computer vision
- Real payment settlement

DATA MODEL REQUIREMENTS

Create an Alembic migration after the Slice 0 extension migration.

Use UUID primary keys. Prefer database-side UUID generation using `gen_random_uuid()` now that `pgcrypto` is enabled.

Use timezone-aware timestamps.

Use either PostgreSQL enums or string columns with database check constraints. Keep the implementation simple and migration-safe.

Required tables:

1. `users`

Required columns:

- `id` UUID primary key
- `email` unique, not null, normalized lowercase
- `password_hash` not null
- `full_name` not null
- `phone` nullable
- `role` constrained to:
  - `admin`
  - `advertiser`
  - `driver`
- `status` constrained to:
  - `active`
  - `invited`
  - `suspended`
  - `disabled`
- `created_at` timezone-aware timestamp, not null
- `updated_at` timezone-aware timestamp, not null

Rules:

- Email must be unique case-insensitively in practical behavior.
- Password hashes must never store plaintext.
- Do not expose `password_hash` in API responses.

2. `advertiser_organizations`

Required columns:

- `id` UUID primary key
- `name` not null
- `billing_email` nullable
- `country_code` nullable
- `currency` not null, default `NGN` unless existing config already defines another default
- `status` constrained to:
  - `active`
  - `suspended`
  - `disabled`
- `created_at` timezone-aware timestamp, not null
- `updated_at` timezone-aware timestamp, not null

3. `organization_memberships`

Required columns:

- `id` UUID primary key
- `organization_id` foreign key to `advertiser_organizations.id`, not null
- `user_id` foreign key to `users.id`, not null
- `role` constrained to:
  - `owner`
  - `manager`
  - `viewer`
- `status` constrained to:
  - `active`
  - `invited`
  - `disabled`
- `created_at` timezone-aware timestamp, not null

Required constraints:

- Unique constraint on `(organization_id, user_id)`.

4. `audit_events`

Required columns:

- `id` UUID primary key
- `actor_user_id` nullable foreign key to `users.id`
- `action` text, not null
- `entity_type` text, not null
- `entity_id` text nullable
- `metadata` JSON/JSONB, not null default empty object
- `created_at` timezone-aware timestamp, not null

Suggested audit actions:

- `admin.user.created`
- `admin.user.updated`
- `admin.advertiser_organization.created`

SECURITY REQUIREMENTS

1. Use secure password hashing.
   - Argon2 or bcrypt is acceptable.
   - Do not invent a custom hash.
   - Do not store plaintext passwords.
2. Minimum password length: 12 characters.
3. Normalize emails to lowercase before storage and login lookup.
4. JWT secret must come from environment/settings.
5. JWT expiration must be configurable.
6. JWT algorithm must be explicit.
7. Disabled or suspended users cannot log in.
8. Admin-only endpoints must reject advertiser and driver users.
9. Advertiser-only endpoint must reject admin and driver users unless a separate admin endpoint exists.
10. Advertiser users must only see their own organization context.
11. Use the existing standard error envelope from Slice 0.
12. Include request ID behavior from Slice 0 in error responses where already supported.
13. Do not leak whether an email exists beyond normal login failure messaging.
14. Do not return password hashes in any response.

CONFIGURATION REQUIREMENTS

Extend existing settings only as needed.

Add settings such as:

- `JWT_SECRET_KEY`
- `JWT_ALGORITHM`, default acceptable value such as `HS256`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `PASSWORD_MIN_LENGTH`, default `12`
- `DEFAULT_CURRENCY`, default `NGN`

Update `.env.example` with safe local placeholders. Do not commit real secrets.

API ENDPOINTS

Implement these endpoints under `/api/v1`.

1. `POST /api/v1/auth/login`

Input:

```json
{
  "email": "admin@example.com",
  "password": "long-secure-password"
}

Output:

JSON
{
  "access_token": "jwt-token",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "uuid",
    "email": "admin@example.com",
    "full_name": "Admin User",
    "role": "admin",
    "status": "active"
  }
}

Rules:

Login succeeds only with valid credentials.

Login fails for invalid password.

Login fails for disabled/suspended users.

Response must not include password hash.

GET /api/v1/me

Requires auth.

Output:

JSON
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "full_name": "User Name",
    "phone": null,
    "role": "advertiser",
    "status": "active"
  },
  "advertiser_organization": {
    "id": "uuid",
    "name": "Acme Ads",
    "currency": "NGN",
    "membership_role": "owner",
    "membership_status": "active"
  }
}

Rules:

For admin and driver users without advertiser org membership, advertiser_organization may be null.

Must be enough for frontend route guards.

POST /api/v1/admin/users

Admin-only.

Input:

JSON
{
  "email": "advertiser@example.com",
  "password": "long-secure-password",
  "full_name": "Advertiser User",
  "phone": null,
  "role": "advertiser",
  "status": "active"
}

Output: created user summary.

Rules:

Duplicate normalized email is rejected.

Password must meet minimum length.

Password is hashed.

Audit event is written.

GET /api/v1/admin/users

Admin-only.

Query parameters:

limit, default 50, max 100

offset, default 0

Optional filters may be added only if simple: role, status

Output:

JSON
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}

Rules:

Must not expose password hashes.

PATCH /api/v1/admin/users/{user_id}

Admin-only.

Allowed updates:

full_name

phone

status

role, only if safe and does not break constraints

Rules:

Do not require password update in this endpoint.

Do not allow direct password hash modification.

Audit event is written.

POST /api/v1/admin/advertiser-organizations

Admin-only.

Input:

JSON
{
  "name": "Acme Ads",
  "billing_email": "billing@acme.test",
  "country_code": "NG",
  "currency": "NGN",
  "status": "active",
  "owner_user_id": "optional-existing-advertiser-user-uuid"
}

Output: organization summary, and owner membership if owner was attached.

Rules:

If owner_user_id is supplied, the user must exist and must have role advertiser.

Create organization_memberships row with role owner and status active.

Reject duplicate membership.

Audit event is written.

GET /api/v1/advertiser/organization

Advertiser-only.

Output:

JSON
{
  "organization": {
    "id": "uuid",
    "name": "Acme Ads",
    "billing_email": "billing@acme.test",
    "country_code": "NG",
    "currency": "NGN",
    "status": "active"
  },
  "membership": {
    "role": "owner",
    "status": "active"
  }
}

Rules:

Advertiser can retrieve only their own active/invited organization membership as appropriate.

If no organization membership exists, return a clear 404 or domain error using the standard envelope.

Admin and driver users must be rejected from this advertiser endpoint.

LIKELY FILES/AREAS TO CREATE OR CHANGE

Use existing Slice 0 conventions. Likely create/change:

app/api/v1/router.py

app/api/v1/auth.py

app/api/v1/me.py or equivalent current-user route

app/api/v1/admin_users.py or app/api/v1/admin.py

app/api/v1/advertiser_organizations.py

app/core/config.py

app/core/security.py

app/core/errors.py only if needed to reuse envelope cleanly

app/db/base.py

app/db/session.py only if needed

app/models/user.py

app/models/organization.py

app/models/audit.py

app/models/__init__.py

app/schemas/auth.py

app/schemas/users.py

app/schemas/organizations.py

app/schemas/common.py if pagination schemas are useful

app/services/auth.py

app/services/users.py

app/services/organizations.py

app/services/audit.py

app/repositories/ only if helpful; do not over-abstract

alembic/versions/<slice1_revision>_identity_and_organizations.py

.env.example

README.md

tests for auth, users, organizations, RBAC, migration-relevant behavior

Keep code simple. Avoid unnecessary abstractions.

TEST REQUIREMENTS

Add/extend tests for:

Login succeeds with correct credentials.

Login fails with bad password.

Login fails for disabled user.

Login fails for suspended user.

Password hash is not plaintext.

Password hash is never returned in API responses.

Duplicate email is rejected.

Email normalization is enforced.

/api/v1/me requires auth.

/api/v1/me returns user role/status.

/api/v1/me returns advertiser organization context for advertiser users with membership.

Admin endpoint rejects unauthenticated users.

Admin endpoint rejects non-admin users.

Admin can create users.

Admin can list users with pagination response shape.

Admin can update allowed user fields.

Admin can create advertiser organization.

Admin can attach existing advertiser user as organization owner.

Organization owner attachment rejects non-advertiser user.

Advertiser user can retrieve only own organization context.

Driver user is rejected from advertiser organization endpoint.

Audit event is created for admin-created user.

Audit event is created for admin-created advertiser organization.

Alembic migration applies cleanly.

Testing implementation guidance:

Prefer isolated test database setup compatible with async SQLAlchemy.

Do not require Docker for normal unit/API tests unless the existing project test pattern already does.

If tests use SQLite, be careful not to hide Postgres-specific constraints. Since this project depends on PostgreSQL/PostGIS, integration-style tests against Postgres are acceptable if documented and runnable.

At minimum, command reports must include migration verification against Postgres.

CHECKS THAT MUST WORK

The final implementation should support:

python -m pytest
ruff check .
alembic upgrade head

Additionally, because local Python was reported as 3.14 while the fixed stack is Python 3.12, verify one of the following and report it:

Option A:

docker compose run --rm api python -m pytest
docker compose run --rm api python -m ruff check .

Option B:
A local Python 3.12 environment was used for tests/checks.

If neither is possible, report that honestly as a known issue with exact evidence. Do not hide it.

FRONTEND CONTRACT NOTES

Login response must include:

access_token

token_type

expires_in

user.id

user.email

user.full_name

user.role

user.status

GET /api/v1/me must be sufficient for frontend route guards.

Advertiser organization context must include:

organization id

organization name

currency

membership role

membership status

All protected endpoints must use bearer token auth:

http
Authorization: Bearer <token>

STANDARD ERROR BEHAVIOR

Use the existing Slice 0 error envelope for expected errors.

Expected examples:

Invalid credentials

Missing token

Invalid token

Inactive/suspended/disabled user

Forbidden role

Duplicate email

Missing advertiser organization

Invalid owner user for organization

Do not return raw stack traces.

ACCEPTANCE CRITERIA

Slice 1 is acceptable only if:

Alembic migration creates exactly the approved identity, organization, membership, and audit tables.

No Slice 2+ domain tables are added.

Password hashing is secure and verified by tests.

JWT login works.

/api/v1/me works for authenticated users.

Admin-only user endpoints are protected.

Advertiser organization endpoint is protected and tenant-scoped.

Advertiser organization owner membership can be created by admin.

Audit events are written for admin-created users and organizations.

Duplicate email handling works with normalized lowercase email.

Suspended/disabled users cannot log in.

API responses do not expose password hashes.

Tests pass.

Ruff passes.

Alembic upgrade head passes against Postgres.

Either Python 3.12 test verification is performed or the inability to do so is explicitly reported.

No deferred/future scope is implemented.

STOP CONDITIONS

Stop and report instead of implementing if:

Slice 0 accepted foundation is missing or materially different from the packet.

The existing project uses a materially different stack than the approved stack.

agent.md conflicts with this prompt.

The DB/migration setup cannot support Slice 1 without reworking Slice 0.

Auth requires a product decision not covered here.

You are tempted to add driver, vehicle, campaign, GPS, analytics, payout, report, or heatmap scope.

Otherwise, stop after Slice 1. Do not continue to Slice 2.

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