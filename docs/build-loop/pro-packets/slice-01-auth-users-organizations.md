PRO REVIEW PACKET

Slice: Slice 1 - Auth, users, roles, advertiser organizations

Repo state summary:
- Branch: `slice-01-auth-users-organizations`.
- Slice 0 Pro verdict: PASS.
- Slice 0 implementation commit: `0da3e30`.
- Slice 0 commit-hash ledger commit: `bfb3973`.
- Approved Slice 1 prompt: `docs/build-loop/prompts/slice-01-auth-users-organizations.md`.
- Slice 1 implementation report: `docs/build-loop/reports/slice-01-auth-users-organizations.md`.
- A clean verification/fix-pass worker independently audited Slice 1 and returned `PASS_CANDIDATE` with no file changes.

Commit status:
- Slice 1 is not committed.
- Awaiting Pro verdict before committing.

Files changed:
- `.env.example`
- `README.md`
- `alembic/versions/0002_identity_and_organizations.py`
- `app/api/v1/admin.py`
- `app/api/v1/advertiser_organizations.py`
- `app/api/v1/auth.py`
- `app/api/v1/dependencies.py`
- `app/api/v1/me.py`
- `app/api/v1/router.py`
- `app/core/config.py`
- `app/core/errors.py`
- `app/core/security.py`
- `app/db/base.py`
- `app/models/__init__.py`
- `app/models/audit.py`
- `app/models/organization.py`
- `app/models/user.py`
- `app/schemas/auth.py`
- `app/schemas/organizations.py`
- `app/schemas/users.py`
- `app/services/audit.py`
- `app/services/auth.py`
- `app/services/organizations.py`
- `app/services/users.py`
- `docker-compose.yml`
- `docs/build-loop/reports/slice-01-auth-users-organizations.md`
- `docs/build-loop/slice-log.md`
- `pyproject.toml`
- `tests/conftest.py`
- `tests/test_admin_users.py`
- `tests/test_auth.py`
- `tests/test_migration_slice1.py`
- `tests/test_organizations.py`

Diff summary:
- Added Argon2 password hashing and PyJWT bearer-token helpers.
- Extended settings with `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `PASSWORD_MIN_LENGTH`, and `DEFAULT_CURRENCY`.
- Added SQLAlchemy models for users, advertiser organizations, organization memberships, and audit events.
- Added schemas and services for auth, users, organizations, and audit events.
- Added auth/current-user/RBAC dependencies.
- Added auth, me, admin, and advertiser organization routers.
- Added Slice 1 Alembic migration.
- Added API tests covering auth, RBAC, tenancy, audit events, redaction, normalized email behavior, and migration guardrails.
- Updated README and `.env.example` for Slice 1 usage.

Database migrations:
- New migration: `0002_identity_and_organizations`.
- Revises: `0001_enable_extensions`.
- Creates:
  - `users`
  - `advertiser_organizations`
  - `organization_memberships`
  - `audit_events`
- Uses UUID primary keys with database-side `gen_random_uuid()`.
- Adds role/status constraints.
- Adds unique email and unique membership constraints.
- Adds only approved Slice 1 tables.

API endpoints:
- `POST /api/v1/auth/login`
- `GET /api/v1/me`
- `POST /api/v1/admin/users`
- `GET /api/v1/admin/users`
- `PATCH /api/v1/admin/users/{user_id}`
- `POST /api/v1/admin/advertiser-organizations`
- `GET /api/v1/advertiser/organization`

Security/validation implemented:
- Argon2 password hashing; no plaintext password storage.
- Password minimum length defaults to 12 and is configurable.
- Emails normalize to lowercase before storage and login lookup.
- JWT secret, algorithm, and expiration come from settings/environment.
- Disabled/suspended users cannot log in.
- Admin endpoints require admin role.
- Advertiser organization endpoint requires advertiser role.
- Advertiser organization lookup is scoped to current user membership.
- Password hashes are not included in response schemas.
- Expected errors use Slice 0 envelope and request ID behavior.
- Audit events are written for admin-created users and advertiser organizations.

Tests/checks run:
- `python -m pytest`
- `python -m ruff check .`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic current`
- `docker compose build api`
- `docker compose run --rm api python --version`
- `docker compose run --rm api python -m pytest`
- `docker compose run --rm api python -m ruff check .`

Exact command outputs or concise failure excerpts:
- Host pytest: `31 passed, 1 warning in 7.20s`.
- Host ruff: `All checks passed!`
- Host Alembic current: `0002_identity_and_organizations (head)`.
- Docker Python version: `Python 3.12.13`.
- Docker pytest: `31 passed, 1 warning in 10.31s`.
- Docker ruff: `All checks passed!`
- Clean verifier worker: `PASS_CANDIDATE`; no changes; no exact fixes remaining.

Known issues:
- Host Python is 3.14.4, but Python 3.12 verification passed in Docker.
- API/unit tests use SQLite for speed while migration is verified against Postgres/PostGIS.
- FastAPI/TestClient emits a deprecation warning about `httpx`; tests pass.

Out-of-scope confirmation:
- No drivers, vehicles, campaigns, creatives, geofences, assignments, GPS, trip sessions, route analytics, fraud flags, impression estimation, payouts, ledgers, reporting, heatmaps, seed/demo trip data, Celery jobs, public self-registration, OAuth/social login, refresh-token flow, frontend/mobile, GitHub remote/PR, production cloud deployment, retargeting, audience pooling, AI/computer vision, or payment settlement were implemented.

Acceptance criteria checklist:
- Alembic migration creates exactly the approved identity, organization, membership, and audit tables: yes.
- No Slice 2+ domain tables are added: yes.
- Password hashing is secure and verified by tests: yes.
- JWT login works: yes.
- `/api/v1/me` works for authenticated users: yes.
- Admin-only user endpoints are protected: yes.
- Advertiser organization endpoint is protected and tenant-scoped: yes.
- Advertiser organization owner membership can be created by admin: yes.
- Audit events are written for admin-created users and organizations: yes.
- Duplicate email handling works with normalized lowercase email: yes.
- Suspended/disabled users cannot log in: yes.
- API responses do not expose password hashes: yes.
- Tests pass: yes.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres: yes.
- Python 3.12 verification performed: yes.
- No deferred/future scope is implemented: yes.

Codex questions:
- None.

Orchestrator recommendation: PASS_CANDIDATE
