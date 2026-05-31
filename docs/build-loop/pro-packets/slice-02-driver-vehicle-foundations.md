PRO REVIEW PACKET

Slice:
Slice 2 - Driver and vehicle foundations.

Repo state summary:
- Branch: `slice-02-driver-vehicle-foundations`.
- Base/previous accepted slice: Slice 1 on `slice-01-auth-users-organizations`, commit `3403f2f`, with ledger commit `62d2ed7`.
- Current state: uncommitted Slice 2 implementation pending Pro review. No local commit has been made for Slice 2.
- Local constraints file is `agent.md`.
- API prefix remains `/api/v1`.
- Existing roles remain `admin`, `advertiser`, `driver`.

Approved Slice 2 scope:
- Add driver profiles and vehicles as the supply-side backend foundation.
- Add admin endpoints for driver profile create/list/read/update.
- Add driver endpoints for current driver's profile read/update.
- Add admin endpoints for vehicle create/list/read/update.
- Add driver endpoints for listing and reading only the current driver's vehicles.
- Add Alembic migration for exactly `driver_profiles` and `vehicles`.
- Add access-control, validation, ownership, migration, and audit-event tests.
- Keep campaigns, creatives, geofences/zones, assignments, GPS, analytics, payouts, reports, heatmaps, seed/demo data, background jobs, frontend/mobile, deployment, retargeting, audience pooling, AI/CV, and payment settlement out of scope.

Commit status:
- Not committed.
- Pro packet added by orchestrator after implementation and local verification.
- Pro response pending.

Files changed:
- `README.md`
- `alembic/versions/0003_driver_vehicle_foundations.py`
- `app/api/v1/dependencies.py`
- `app/api/v1/driver_profiles.py`
- `app/api/v1/router.py`
- `app/api/v1/vehicles.py`
- `app/core/errors.py`
- `app/db/base.py`
- `app/models/driver.py`
- `app/models/vehicle.py`
- `app/schemas/drivers.py`
- `app/schemas/vehicles.py`
- `app/services/drivers.py`
- `app/services/vehicles.py`
- `docs/build-loop/reports/slice-02-driver-vehicle-foundations.md`
- `docs/build-loop/slice-log.md`
- `tests/conftest.py`
- `tests/test_driver_profiles.py`
- `tests/test_migration_slice2.py`
- `tests/test_vehicles.py`

Diff summary:
- Adds `DriverProfile` model with UUID primary key, one-to-one `user_id`, onboarding status constraint, optional license/city/country fields, JSON metadata, timestamps, and indexes.
- Adds `Vehicle` model with UUID primary key, `driver_profile_id`, display and normalized plate fields, country, vehicle type/status constraints, optional make/model/year/color, JSON metadata, timestamps, ownership/indexes, and unique `(plate_country_code, plate_number_normalized)`.
- Adds driver profile schemas/services/router functions for admin and driver flows.
- Adds vehicle schemas/services/router functions for admin and driver flows.
- Adds `require_driver_user` auth dependency and includes new routers in `app/api/v1/router.py`.
- Updates standard validation error handling to JSON-encode Pydantic error details, preserving the standard error envelope.
- Extends test fixtures for driver profiles and vehicles.
- Adds focused API tests and migration guard tests.
- Updates README endpoint notes and plate normalization documentation.

Database migrations:
- New revision: `0003_driver_vehicle_foundations`.
- Down revision: `0002_identity_and_organizations`.
- Creates exactly:
  - `driver_profiles`
  - `vehicles`
- Uses PostgreSQL UUID columns with `gen_random_uuid()`.
- Uses JSONB defaults of empty object in Alembic.
- Adds:
  - `ck_driver_profiles_onboarding_status`
  - `uq_driver_profiles_user_id`
  - `ix_driver_profiles_user_id`
  - `ix_driver_profiles_onboarding_status`
  - `ix_driver_profiles_country_city`
  - `ck_vehicles_vehicle_type`
  - `ck_vehicles_status`
  - `uq_vehicles_plate_country_normalized`
  - `ix_vehicles_driver_profile_id`
  - `ix_vehicles_status`
  - `ix_vehicles_plate_country_normalized`
- Does not add Slice 3+ tables.

API endpoints:
- `GET /api/v1/driver/profile`
- `PATCH /api/v1/driver/profile`
- `GET /api/v1/driver/vehicles`
- `GET /api/v1/driver/vehicles/{vehicle_id}`
- `POST /api/v1/admin/drivers/{user_id}/profile`
- `GET /api/v1/admin/drivers`
- `GET /api/v1/admin/drivers/{driver_profile_id}`
- `PATCH /api/v1/admin/drivers/{driver_profile_id}`
- `POST /api/v1/admin/drivers/{user_id}/vehicles`
- `GET /api/v1/admin/vehicles`
- `GET /api/v1/admin/vehicles/{vehicle_id}`
- `PATCH /api/v1/admin/vehicles/{vehicle_id}`

Security/validation implemented:
- Admin supply endpoints require `admin`.
- Driver supply endpoints require `driver`.
- Advertisers and unauthenticated users are rejected from protected supply endpoints.
- Driver profiles can only be created for existing users with role `driver`.
- One driver profile per driver user is enforced by service checks and DB uniqueness.
- Drivers can update only allowed own-profile fields: `license_number`, `service_city`, `country_code`.
- Drivers cannot change onboarding status.
- Drivers can list/read only vehicles attached to their own driver profile. Cross-driver vehicle reads return non-leaking 404.
- Admin vehicle creation requires an existing driver user with an existing driver profile.
- Duplicate normalized plates are rejected within the same country.
- Same normalized plate in a different country is allowed.
- Country codes are uppercased.
- Driver text fields are trimmed.
- Vehicle plate normalization uppercases and removes whitespace/hyphens.
- Vehicle type/status enums are validated.
- Vehicle year is validated as 1980 through current year plus 1.
- Metadata must be an object when supplied.
- Password hashes are not exposed in embedded user summaries.
- Audit events are written for:
  - `admin.driver_profile.created`
  - `admin.driver_profile.updated`
  - `admin.vehicle.created`
  - `admin.vehicle.updated`

Tests/checks run:
- `python -m pytest`
- `python -m ruff check .`
- `python -m pytest tests/test_driver_profiles.py`
- `git diff --check`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic current`
- `docker compose build api`
- `docker compose run --rm api python --version`
- `docker compose run --rm api python -m pytest`
- `docker compose run --rm api python -m ruff check .`

Exact command outputs or concise failure excerpts:
- Host `python -m pytest`: `53 passed, 1 warning`.
- Host `python -m ruff check .`: `All checks passed!`
- Targeted `python -m pytest tests/test_driver_profiles.py`: `11 passed, 1 warning`.
- `git diff --check`: no whitespace errors; Git reported only expected CRLF conversion warnings.
- Host Alembic upgrade: passed with PostgreSQL transactional DDL context.
- Host Alembic current: `0003_driver_vehicle_foundations (head)`.
- `docker compose build api`: image built successfully.
- Docker Python version: `Python 3.12.13`.
- Docker `python -m pytest`: `53 passed, 1 warning`.
- Docker `python -m ruff check .`: `All checks passed!`

Implementation reports:
- Primary implementation worker: `PASS_CANDIDATE`.
- Clean fix-pass worker: `PASS_CANDIDATE`; added missing direct invalid `onboarding_status` coverage. No code fix was required.
- Final build report path: `docs/build-loop/reports/slice-02-driver-vehicle-foundations.md`.

Known issues:
- Host Python is 3.14.4, while the fixed stack requires Python 3.12. Docker verified Python 3.12.13 successfully.
- Existing FastAPI/TestClient stack emits a Starlette deprecation warning about `httpx`; tests pass.
- No acceptance blockers known locally.

Out-of-scope confirmation:
- No campaigns, creatives, geofences/zones, campaign assignments, activation, GPS pings, trip sessions, route analytics, fraud flags, impression estimation, payouts, earnings ledger, advertiser dashboards/report APIs, heatmaps, seed/demo data, Celery/background jobs, frontend/mobile code, GitHub remote/PR setup, cloud deployment, retargeting, audience pooling, AI/CV, or payment settlement were implemented.

Acceptance criteria checklist:
- Alembic migration creates approved `driver_profiles` and `vehicles` tables: yes.
- No Slice 3+ domain tables are added: yes.
- Driver profiles can only be associated with users whose role is `driver`: yes.
- One driver profile per driver user is enforced: yes.
- Admin can create/list/read/update driver profiles: yes.
- Driver can read/update only own existing profile: yes.
- Admin can create/list/read/update vehicles: yes.
- Vehicle ownership is tied to driver profiles: yes.
- Driver can list/read only own vehicles: yes.
- Duplicate normalized vehicle plates are rejected within the same plate country: yes.
- Vehicle validation covers type, status, country code normalization, plate normalization, and year: yes.
- Admin/driver/advertiser access boundaries are enforced: yes.
- Audit events are written for admin-created/updated driver profiles and vehicles: yes.
- API responses do not expose password hashes: yes.
- Tests pass: yes, 53 passed.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres/PostGIS: yes.
- Python 3.12 verification performed: yes, Docker Python 3.12.13.
- No deferred/future scope implemented: yes.

Codex questions:
- None.

Orchestrator recommendation:
PASS_CANDIDATE. If Pro agrees, please return `Verdict: PASS`, say whether it is safe to commit, provide the recommended commit message, and provide the complete Slice 3 implementation prompt.
