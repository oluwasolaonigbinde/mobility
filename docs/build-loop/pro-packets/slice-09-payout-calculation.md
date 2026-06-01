PRO REVIEW PACKET

Slice:
Slice 9 - Payout calculation v1 and driver earnings ledger.

Repo state summary:
- Branch: `slice-09-payout-calculation`.
- Slice 8 was accepted and committed before this work.
- This slice builds only on existing FastAPI/Pydantic v2/SQLAlchemy async/Alembic/Postgres/PostGIS/JWT/RBAC foundations.
- Clean implementation/fix workers were used for the feature pass and follow-up fixes. A final clean read-only auditor returned `PASS_CANDIDATE` with no blockers.

Commit status:
- Not committed yet.
- Feature commit should only happen after Pro PASS and local reconciliation.

Files changed:
- `.env.example`
- `README.md`
- `alembic/versions/0010_payouts_and_earnings.py`
- `app/api/v1/payouts.py`
- `app/api/v1/router.py`
- `app/core/config.py`
- `app/db/base.py`
- `app/models/payout.py`
- `app/schemas/payouts.py`
- `app/services/payouts.py`
- `docs/build-loop/reports/slice-09-payout-calculation.md`
- `docs/build-loop/slice-log.md`
- `tests/conftest.py`
- `tests/test_config.py`
- `tests/test_migration_slice8.py`
- `tests/test_migration_slice9.py`
- `tests/test_payouts.py`

Diff summary:
- Adds Slice 9 payout/earnings domain model, service, schemas, router, settings, migration, tests, and README usage notes.
- Mounts the payout router under the existing `/api/v1` router.
- Adds explicit payout settings with validation and `.env.example` entries.
- Updates test fixtures for payout rules, payout calculations, ledger entries, impression estimates, and tracking-derived source data.
- Updates Slice 8 migration tests so they pin the Slice 8 revision and remain head-safe after Slice 9.
- Does not add settlement, withdrawal, billing, invoice, dashboard daily metrics, heatmap, seed, audience, or payment provider scope.

Database migrations:
- Adds Alembic revision `0010_payouts_and_earnings`, down revision `0009_impression_estimation`.
- Creates exactly these new business tables:
  - `campaign_payout_rules`
  - `payout_calculations`
  - `earnings_ledger_entries`
- Uses UUID primary keys with database-side generation, timezone-aware timestamps, JSONB metadata defaults, decimal/numeric money fields, string status/type checks, nonnegative money/rate checks, multiplier range checks, currency length checks, min/max payout checks, and required foreign keys.
- Adds partial unique active payout rule index per campaign.
- Adds unique payout idempotency constraint on `(trip_session_id, formula_version, payout_rule_id)`.
- Adds partial unique ledger mapping on `payout_calculation_id IS NOT NULL`.
- Adds campaign, driver, trip, vehicle, status, and date reporting indexes.

API endpoints:
- `POST /api/v1/admin/campaigns/{campaign_id}/payout-rules`
- `GET /api/v1/admin/campaigns/{campaign_id}/payout-rules`
- `GET /api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}`
- `PATCH /api/v1/admin/campaigns/{campaign_id}/payout-rules/{rule_id}`
- `POST /api/v1/admin/trips/{trip_id}/calculate-payout`
- `GET /api/v1/admin/payout-calculations`
- `GET /api/v1/driver/earnings/summary`
- `GET /api/v1/driver/earnings/ledger`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/cost-summary`

Security/validation implemented:
- Admin-only payout rule and payout calculation endpoints.
- Driver-only earnings summary and ledger endpoints.
- Advertiser-only campaign cost summary endpoint.
- Advertiser campaign lookup uses existing organization scoping and returns non-leaking 404 for cross-organization access.
- Driver earnings reads filter by both `driver_profile_id` and `driver_user_id`.
- Currency normalizes to uppercase and must be a three-letter code.
- Rates and min/max payout values are nonnegative.
- Fraud multipliers are constrained to 0..1.
- `max_payout_per_trip` must be greater than or equal to `min_payout_per_trip`.
- Metadata must be JSON objects.
- Payout calculation requires ended trip, analytics row, impression estimate row, and active payout rule unless an explicit active rule is supplied.
- Source consistency validation rejects mismatched trip analytics or impression estimate rows with `PAYOUT_SOURCE_MISMATCH`.
- API responses avoid password hashes, raw pings, payment account data, settlement internals, and advertiser-visible driver identities.

Payout rule handling implemented:
- Admins can create/list/read/update campaign payout rules.
- Creating or updating a rule as active inactivates other active rules for the same campaign in the same transaction.
- The partial unique index enforces one active rule per campaign at the database layer.
- Payout rule changes do not mutate existing payout calculations.
- Audit events:
  - `admin.campaign_payout_rule.created`
  - `admin.campaign_payout_rule.updated`

Payout formula implemented:
- Formula version: `payout_v1`.
- Uses stored `trip_analytics.distance_m`, `active_tracking_seconds`, `target_zone_distance_m`, `bonus_zone_distance_m`, `impression_estimate.estimated_impressions`, `trip_analytics.quality_score`, open fraud flags, and payout rule rates/multipliers.
- Computes distance, active-time, target-zone, bonus-zone, and impression components.
- Applies quality multiplier, fraud multiplier, nonnegative clamp, optional max cap, and min floor only when gross payout is positive.
- Stores copied campaign, assignment, driver profile, vehicle, analytics, estimate, payout rule ids, formula version, component outputs, and request metadata.

Fraud/quality adjustment implemented:
- Quality score is clamped to 0..1 and stored as `quality_multiplier`.
- Only open fraud flags affect payout.
- High open severity wins over medium/low; medium wins over low; low applies only when no higher open severity exists.
- Acknowledged and dismissed fraud flags do not reduce payout.

Ledger immutability/idempotency implemented:
- Positive `calculated` payouts create exactly one pending `trip_payout` ledger entry.
- `insufficient_data`, `blocked`, and zero-final-payout calculations create no ledger entry.
- Re-running calculation for the same trip/formula/rule returns the existing calculation and existing ledger entry.
- Re-running without explicit `payout_rule_id` after a newer active rule supersedes the old one returns the existing trip/formula calculation rather than creating a second payout.
- Explicit inactive old rules still return `PAYOUT_RULE_INACTIVE`.
- Payout calculation and ledger insert paths use nested transactions with `IntegrityError` recovery plus unique constraints to recover from duplicate insert attempts.
- No ledger update/delete endpoints were added.
- Audit event `admin.payout_calculation.created` is written only for first-time calculations.

Driver earnings aggregation implemented:
- Driver summary groups pending, available, voided, lifetime earned, and count by currency.
- Empty driver earnings return a stable zero row using requested currency or default currency.
- Driver ledger list supports pagination plus status, entry type, and currency filters.
- Drivers cannot see other drivers' ledger entries.

Advertiser cost summary implemented:
- Aggregates stored payout calculations only; it does not auto-calculate payouts.
- Uses `calculated_at` for optional `start_at` and `end_at` filters.
- Groups final payout total, gross payout total, status counts, and ledger count by currency.
- Empty summaries return a stable zero row.
- Does not expose driver identities, raw pings, ledger entry details, or payment settlement data.

Tests/checks run:
- `python -m ruff check .`
- `python -m pytest tests/test_config.py tests/test_payouts.py tests/test_migration_slice8.py tests/test_migration_slice9.py -q`
- `python -m pytest -q`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head; if ($LASTEXITCODE -eq 0) { python -m alembic current }`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest tests/test_migration_slice8.py tests/test_migration_slice9.py -q`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest -q`
- `docker compose build api`
- `docker compose run --rm api python --version`
- `docker compose run --rm api python -m ruff check .`
- `docker compose run --rm api python -m pytest -q`

Exact command outputs or concise failure excerpts:
- Host `python -m ruff check .`: all checks passed.
- Host targeted config/payout/migration tests: `82 passed, 2 skipped, 1 warning`.
- Host full `python -m pytest -q`: `191 passed, 21 skipped, 1 warning`.
- Host Alembic/PostGIS upgrade: current revision `0010_payouts_and_earnings (head)`.
- Host PostGIS migration tests: `4 passed, 1 warning`.
- Host full PostGIS `python -m pytest -q`: `212 passed, 1 warning`.
- Docker `docker compose build api`: image built successfully.
- Docker Python version: `Python 3.12.13`.
- Docker `python -m ruff check .`: all checks passed.
- Docker `python -m pytest -q`: `212 passed, 1 warning in 779.68s`.
- Existing warning: FastAPI/TestClient emits a StarletteDeprecationWarning about `httpx`; tests pass.

Known issues:
- Host Python is 3.14.4, while the fixed stack is Python 3.12. Docker verifies Python 3.12.13 successfully.
- Plain host tests skip PostGIS-specific checks when no PostGIS URL is configured; those checks pass with the local PostGIS URL and in Docker.
- True parallel race coverage is not present. The implementation uses DB uniqueness plus nested transaction `IntegrityError` recovery and deterministic duplicate-call tests.
- Ledger append-only is enforced through no public update/delete endpoints, but future destructive parent deletes should review cascade policy before settlement/accounting work. `payout_calculation_id` is `ON DELETE RESTRICT`; trip/vehicle links are `SET NULL`; campaign and driver-profile parent deletes can still cascade ledger rows through existing parent relationships.

Out-of-scope confirmation:
- No real settlement.
- No withdrawals, cash-out, driver wallet, bank, mobile-money, or payment-provider integrations.
- No invoices, tax, advertiser billing, or advertiser charging.
- No campaign daily metrics or full dashboard/reporting APIs beyond the approved cost summary endpoint.
- No heatmap APIs or heatmap cache tables.
- No automated scheduling or background jobs.
- No notifications, manual fraud review workflow, or suspension/payout enforcement.
- No seed/demo trip data.
- No external map, traffic, geocoding, map matching, tile provider, audience identity, retargeting, device pooling, frontend/mobile, OAuth, refresh-token, GitHub/PR, or deployment scope.

Acceptance criteria checklist:
- Migration creates exactly the three approved Slice 9 tables: yes.
- No deferred/future tables added: yes.
- Admin can create/list/read/update payout rules: yes.
- One active payout rule per campaign is deterministically resolved and indexed: yes.
- Admin can calculate payout for ended trips with analytics, estimate, and active rule: yes.
- Calculation is idempotent for same trip/formula/rule: yes.
- Positive calculated payout creates exactly one pending ledger entry: yes.
- Duplicate calculation does not duplicate ledger entries: yes.
- Formula uses analytics distance, active time, zone distances, impressions, quality, fraud flags, and rule rates/multipliers: yes.
- Insufficient-data and blocked/excluded sources create zero payout and no ledger: yes.
- Metadata explains inputs, components, rates, fraud counts, and request metadata: yes.
- Admin can list/filter payout calculations: yes.
- Driver can read only own earnings summary and ledger: yes.
- Advertiser can read only own campaign aggregate cost summary: yes.
- Cost summary aggregates stored calculations and returns stable zero shape: yes.
- Admin/advertiser/driver/unauthenticated boundaries are enforced: yes.
- API responses avoid password hashes, raw pings, payment account data, other-driver ledger data, and unrelated sensitive data: yes.
- Tests pass: yes.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres/PostGIS: yes.
- Python 3.12 verification performed: yes, via Docker.
- No deferred/future scope implemented: yes.

Codex questions:
- Please review whether the nested-transaction `IntegrityError` recovery for payout calculation and ledger idempotency is sufficient for the expected concurrency envelope. It is backed by unique constraints and duplicate-call tests, but not by a true parallel race simulation.
- Please review whether the disclosed future parent-delete cascade risk should block Slice 9, or whether it can remain a later hardening item before destructive parent deletes/settlement workflows exist.

Orchestrator recommendation: PASS_CANDIDATE
