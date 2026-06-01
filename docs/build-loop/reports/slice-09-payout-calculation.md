CODEX BUILD REPORT

Slice:
Slice 9 - Payout calculation v1 and driver earnings ledger

Status: PASS_CANDIDATE

Summary:
Finished the Slice 9 implementation from the current dirty draft. The slice adds
admin-managed campaign payout rules, deterministic formula-versioned payout
calculations from stored route analytics and impression estimates, immutable pending
driver earnings ledger entries for positive calculated payouts, driver earnings
summary and ledger reads, advertiser campaign cost summaries, migration guards,
settings/docs updates, and focused/full verification. No commit was created.

Clean fix pass update:
- Fixed PATCH payout-rule explicit `null` handling for required update fields.
  Schema validation now returns the standard validation envelope, and the service
  also rejects constructed/bypassed null payloads with `INVALID_PAYOUT_RULE` instead
  of allowing TypeError or DB integrity failures. `max_payout_per_trip` remains
  intentionally nullable and can be cleared.
- Fixed payout idempotency after rule supersession. When no explicit
  `payout_rule_id` is supplied, a trip with an existing payout calculation for the
  current payout formula returns the existing calculation and ledger even if a newer
  active campaign rule has superseded the old rule. Explicit inactive old rules
  continue to return `PAYOUT_RULE_INACTIVE`.
- Added source consistency validation before payout calculation. Trip analytics and
  impression estimate rows must agree with the trip on campaign, assignment, driver
  profile, and vehicle ids; estimate-to-analytics id mismatch is also rejected with
  `PAYOUT_SOURCE_MISMATCH`.
- Added acceptance coverage for closed fraud flags, mixed fraud severity precedence,
  `impression_estimate.status=insufficient_data`, `trip_analytics.status=blocked`,
  admin payout RBAC, admin payout list `driver_profile_id` filtering, driver ledger
  RBAC, advertiser cost-summary driver denial, true no-calculation cost summary, and
  naive datetime validation on cost summary query params.
- Strengthened Slice 9 migration tests to inspect important Postgres
  columns/nullability/defaults, constraints, FKs/on-delete actions, and indexes.
  Slice 8 migration tests now upgrade explicitly to the Slice 8 revision and assert
  Slice 9 payout/ledger tables are absent, keeping the test head-safe.
- Added environment-loading coverage for all `PAYOUT_*` settings and verified an
  empty `PAYOUT_DEFAULT_MAX_PAYOUT_PER_TRIP` env value parses as unset. `.env.example`
  remains valid and does not set an empty max payout value.

Clean fix pass command results:
- `python -m ruff check .`: passed.
- `python -m pytest tests/test_config.py tests/test_payouts.py -q`: 80 passed,
  1 existing FastAPI/TestClient warning.
- `python -m pytest tests/test_migration_slice8.py tests/test_migration_slice9.py -q`:
  2 passed, 2 skipped, 1 existing FastAPI/TestClient warning.
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest tests/test_migration_slice8.py tests/test_migration_slice9.py -q`:
  4 passed, 1 existing FastAPI/TestClient warning.
- `python -m pytest -q`: 191 passed, 21 skipped, 1 existing FastAPI/TestClient
  warning.

Local investigation performed:
- Read `agent.md`.
- Read `docs/build-loop/prompts/slice-09-payout-calculation.md`.
- Read accepted Slice 0 through Slice 8 reports under `docs/build-loop/reports/`.
- Confirmed branch `slice-09-payout-calculation`.
- Confirmed existing API prefix is `/api/v1`.
- Confirmed existing error envelope uses `AppError`.
- Confirmed current Slice 8 foundation includes route analytics, fraud flags,
  traffic density profiles, and impression estimates.
- Confirmed draft Alembic head is `0010_payouts_and_earnings` after
  `0009_impression_estimation`.
- Confirmed existing Decimal response convention serializes money/numeric values as
  strings.
- Confirmed PostGIS tests use `DATABASE_URL` or `TEST_DATABASE_URL` and skip only
  when no PostGIS URL is configured.
- Preserved pre-existing orchestrator dirty marker `docs/build-loop/slice-log.md`.

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
- `tests/conftest.py`
- `tests/test_config.py`
- `tests/test_migration_slice8.py`
- `tests/test_migration_slice9.py`
- `tests/test_payouts.py`

Pre-existing dirty file preserved:
- `docs/build-loop/slice-log.md`

Database migrations:
- Added `0010_payouts_and_earnings`, down revision `0009_impression_estimation`.
- Creates exactly:
  - `campaign_payout_rules`
  - `payout_calculations`
  - `earnings_ledger_entries`
- Adds UUID primary keys with `gen_random_uuid()`, timezone-aware timestamps, JSONB
  metadata defaults, string status/type checks, nonnegative money/rate checks,
  multiplier range checks, currency length checks, min/max payout checks, and
  required foreign keys.
- Adds partial unique active payout rule index per campaign.
- Adds payout calculation idempotency unique constraint on
  `(trip_session_id, formula_version, payout_rule_id)`.
- Adds partial unique ledger mapping on `payout_calculation_id IS NOT NULL`.
- Adds campaign, driver, trip, vehicle, status, and date reporting indexes.
- Adds no settlement, withdrawal, payment, billing, invoice, campaign daily metric,
  heatmap, audience, retargeting, or seed tables.

API endpoints implemented:
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
- Advertiser campaign access uses existing organization-scoped lookup and returns
  non-leaking 404 for cross-organization campaigns.
- Driver earnings reads filter by both `driver_profile_id` and `driver_user_id`.
- Currency is normalized uppercase and validated as a 3-letter code.
- Payout rule rates and min/max values are nonnegative.
- Fraud multipliers are constrained to 0..1.
- `max_payout_per_trip` must be greater than or equal to `min_payout_per_trip`.
- Metadata must be JSON objects.
- Trip payout calculation requires an ended trip, existing analytics, existing
  impression estimate, and an active payout rule.
- API responses do not expose password hashes, raw pings, driver identities in
  advertiser summaries, payment account data, or settlement internals.

Payout rule handling implemented:
- Admins can create/list/read/update campaign payout rules.
- Creating or updating a rule as active deterministically inactivates other active
  rules for the same campaign in the same transaction.
- Partial unique index backs one active rule per campaign.
- Rule changes do not mutate existing payout calculations.
- Audit events:
  - `admin.campaign_payout_rule.created`
  - `admin.campaign_payout_rule.updated`

Payout formula implemented:
- Formula version: `payout_v1`.
- Uses:
  - `trip_analytics.distance_m`
  - `trip_analytics.active_tracking_seconds`
  - `trip_analytics.target_zone_distance_m`
  - `trip_analytics.bonus_zone_distance_m`
  - `impression_estimate.estimated_impressions`
  - `trip_analytics.quality_score`
  - campaign payout rule rates and caps
- Computes distance, active-time, target-zone, bonus-zone, and impression components.
- Applies quality multiplier, fraud multiplier, nonnegative clamp, optional max cap,
  and min floor only when gross payout is positive.
- Stores copied campaign, assignment, driver profile, vehicle, analytics, estimate,
  rule ids, formula version, transparent component outputs, and request metadata.

Fraud/quality adjustment implemented:
- Quality score is clamped to 0..1 and stored as `quality_multiplier`.
- Only open fraud flags affect payouts.
- High severity open flags use the high multiplier.
- Else medium severity open flags use the medium multiplier.
- Else low severity open flags use the low multiplier.
- Acknowledged and dismissed fraud flags do not reduce payout.

Ledger immutability/idempotency implemented:
- Positive `calculated` payouts create exactly one pending `trip_payout` ledger entry.
- `insufficient_data`, `blocked`, and zero-final-payout calculations create no ledger
  entry.
- Re-running calculation for the same trip/formula/rule returns the existing
  calculation and existing ledger entry.
- Payout calculation and ledger insert paths use nested transactions with
  `IntegrityError` recovery so duplicate concurrent inserts re-read existing rows.
- No ledger update/delete endpoints were added.
- Audit event `admin.payout_calculation.created` is written only for first-time
  calculations.

Driver earnings aggregation implemented:
- Driver summary groups pending, available, voided, lifetime earned, and count by
  currency.
- Empty driver earnings return a stable zero row using requested currency or default
  currency.
- Driver ledger list supports pagination plus status, entry type, and currency
  filters.
- Drivers cannot see other drivers' ledger entries.

Advertiser cost summary implemented:
- Summary aggregates stored payout calculations only; it does not auto-calculate.
- Uses `calculated_at` for optional `start_at` and `end_at` filters.
- Groups final payout total, gross payout total, status counts, and ledger count by
  currency.
- Empty summaries return a stable zero row.
- Does not expose driver identities, raw pings, or ledger entry details.

Tests added/updated:
- Added payout rule CRUD/list/read/update, validation, supersession, RBAC, and audit
  tests.
- Added payout formula, copied foreign keys, metadata, idempotency, ledger creation,
  ledger non-duplication, fraud multiplier, floor/cap, zero payout, insufficient
  data, blocked/excluded, missing analytics, missing impression estimate, missing
  rule, inactive rule, active trip, list/filter, and audit tests.
- Added driver earnings summary, zero shape, ledger filtering, cross-driver scoping,
  role boundaries, unauthenticated boundary, and no public ledger mutation tests.
- Added advertiser campaign cost summary scoping, aggregation, empty date filter,
  role boundaries, and no driver identity leakage tests.
- Added Slice 9 migration guard and Postgres schema verification tests.
- Updated Slice 8 migration test to upgrade and verify the Slice 8 revision
  explicitly now that Slice 9 is head.
- Extended settings tests for payout defaults, multiplier validation, cap validation,
  blank optional cap parsing, and default currency validation.
- Extended fixtures for impression estimates, payout rules, payout calculations,
  earnings ledger entries, and active tracking seconds.

Commands run:
- `python -m ruff check .`
- `python -m pytest tests/test_config.py tests/test_payouts.py tests/test_migration_slice8.py tests/test_migration_slice9.py -q`
- `python -m pytest tests/test_payouts.py -q`
- `python -m pytest`
- `python -m pytest -q`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head; if ($LASTEXITCODE -eq 0) { python -m alembic current }`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest tests/test_migration_slice8.py tests/test_migration_slice9.py -q`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest -q`
- `docker compose build api`
- `docker compose run --rm api python --version`
- `docker compose run --rm api python -m ruff check .`
- `docker compose run --rm api python -m pytest -q`

Command results:
- Host `python -m ruff check .`: all checks passed.
- Host targeted config/payout/migration tests: 82 passed, 2 skipped, 1 existing
  FastAPI/TestClient warning.
- Host focused payout tests: 8 passed, 1 existing FastAPI/TestClient warning.
- First host full `python -m pytest`: timed out after 244073 ms before result.
- Host full rerun `python -m pytest -q`: 191 passed, 21 skipped, 1 existing
  FastAPI/TestClient warning.
- Host Alembic with local PostGIS URL: upgraded to `0010_payouts_and_earnings`; current
  reported `0010_payouts_and_earnings (head)`.
- Host PostGIS migration tests: 4 passed, 1 existing FastAPI/TestClient warning.
- Host full PostGIS `python -m pytest -q`: 212 passed, 1 existing FastAPI/TestClient
  warning.
- Docker `docker compose build api`: image built successfully.
- Docker Python version: Python 3.12.13.
- Docker `python -m ruff check .`: all checks passed.
- Docker `python -m pytest -q`: 212 passed, 1 existing FastAPI/TestClient warning in
  779.68 seconds.

Known issues:
- Host Python is 3.14.4, while the fixed stack is Python 3.12. Docker verified
  Python 3.12.13 successfully.
- Existing FastAPI/TestClient stack emits a deprecation warning about `httpx`; tests
  pass.
- Plain host tests skip PostGIS-specific checks when no PostGIS URL is configured;
  those checks pass with the requested local PostGIS URL and in Docker.
- The first full host pytest command timed out with a 4-minute ceiling; the rerun
  with a longer timeout passed.
- Clean fix pass did not change ledger parent FK behavior beyond the existing
  approved migration. `payout_calculation_id` remains `ON DELETE RESTRICT` and
  trip/vehicle links remain `SET NULL`, but campaign and driver-profile parent
  deletes can still cascade ledger rows. This should be reviewed before enabling
  destructive parent deletes in later settlement/accounting slices.

Out-of-scope compliance:
- No real settlement.
- No withdrawals, cash-out, driver wallet, bank, mobile-money, or payment-provider
  integrations.
- No invoices, tax, advertiser billing, or advertiser charging.
- No campaign daily metrics or full dashboard/reporting APIs beyond approved cost
  summary.
- No heatmap APIs or heatmap cache tables.
- No automated scheduling or background jobs.
- No notifications, manual fraud review workflow, or suspension/payout enforcement.
- No seed/demo trip data.
- No external map, traffic, geocoding, map matching, or tile providers.
- No audience identity, retargeting, or device pooling.
- No frontend/mobile, OAuth, refresh tokens, GitHub/PR setup, or deployment.

Acceptance criteria checklist:
- Migration creates exactly the three approved Slice 9 tables: yes.
- No deferred/future tables added: yes.
- Admin can create/list/read/update payout rules: yes.
- One active payout rule per campaign is deterministically resolved and indexed: yes.
- Admin can calculate payout for ended trips with analytics, estimate, and active rule:
  yes.
- Calculation is idempotent for same trip/formula/rule: yes.
- Positive calculated payout creates exactly one pending ledger entry: yes.
- Duplicate calculation does not duplicate ledger entries: yes.
- Formula uses analytics distance, active time, zone distances, impressions, quality,
  fraud flags, and rule rates/multipliers: yes.
- Insufficient-data and blocked/excluded sources create zero payout and no ledger:
  yes.
- Metadata explains inputs, components, rates, fraud counts, and request metadata:
  yes.
- Admin can list/filter payout calculations: yes.
- Driver can read only own earnings summary and ledger: yes.
- Advertiser can read only own campaign aggregate cost summary: yes.
- Cost summary aggregates stored calculations and returns stable zero shape: yes.
- Admin/advertiser/driver/unauthenticated boundaries are enforced: yes.
- API responses avoid password hashes, raw pings, payment account data, other-driver
  ledger data, and unrelated sensitive data: yes.
- Tests pass: yes.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres/PostGIS: yes.
- Python 3.12 verification performed: yes, via Docker.
- No deferred/future scope implemented: yes.

Manual verification steps:
- Use an admin bearer token to create an active payout rule with
  `POST /api/v1/admin/campaigns/{campaign_id}/payout-rules`.
- Use an admin bearer token to calculate payout for an ended trip with stored
  analytics and impressions via `POST /api/v1/admin/trips/{trip_id}/calculate-payout`.
- Re-call the same calculation and confirm the same calculation id and ledger id are
  returned.
- Use a driver bearer token to call `GET /api/v1/driver/earnings/summary` and
  `GET /api/v1/driver/earnings/ledger`.
- Use an advertiser bearer token for the owning organization to call
  `GET /api/v1/advertiser/campaigns/{campaign_id}/cost-summary`.
- Use another advertiser organization token to confirm cross-org campaign access
  returns 404.

Questions for Pro reviewer:
- Please review whether the nested-transaction `IntegrityError` recovery for payout
  calculation and ledger idempotency is sufficient for the expected concurrency
  envelope. It is backed by unique constraints and covered by deterministic
  duplicate-call tests, but not by a true parallel race simulation.
