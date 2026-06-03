CODEX BUILD REPORT

Slice:
Slice 13 - MVP hardening and contract freeze

Status: PASS_CANDIDATE

Summary:
MVP hardening and contract freeze are implemented without adding product scope,
endpoints, tables, or migrations. The slice tightens production settings validation,
standardizes campaign-list, payout, and impression date-range error envelopes, adds
an OpenAPI contract snapshot, adds focused hardening guard tests, and updates the
README frontend/runbook baseline.

Local investigation performed:
- Inspected `git status --short`.
- Inspected current diffs for README, impressions, payouts, config, config tests,
  MVP hardening tests, and the OpenAPI snapshot.
- Read `docs/build-loop/prompts/slice-13-mvp-hardening-and-contract-freeze.md`.
- Read `agent.md`.
- Read Slice 9 and Slice 12 accepted reports for payout/ledger and seed/docs context.
- Read `docs/build-loop/slice-log.md` only for context; it was not edited.
- Confirmed branch is `slice-13-mvp-hardening`.
- Confirmed current Alembic versions stop at `0010_payouts_and_earnings.py`.
- Confirmed no Slice 13 migration file is present.

Files changed:
- `README.md`
- `app/api/v1/impressions.py`
- `app/api/v1/campaigns.py`
- `app/api/v1/payouts.py`
- `app/core/config.py`
- `tests/test_config.py`
- `tests/test_mvp_hardening.py`
- `docs/api/openapi.snapshot.json`
- `docs/build-loop/reports/slice-13-mvp-hardening.md`

Orchestrator ledger note:
- `docs/build-loop/slice-log.md` is managed separately by the orchestrator.

Database migrations:
- None added.
- Current migration guard in `tests/test_mvp_hardening.py` expects exactly migrations
  `0001` through `0010`.
- Alembic runtime verification passed and current head remains `0010_payouts_and_earnings`.

API endpoints implemented/changed:
- No new endpoints were added.
- `GET /api/v1/advertiser/campaigns` now routes `start_at_from`/`start_at_to`
  query datetime timezone validation through the standard `AppError` envelope and
  rejects `start_at_from > start_at_to`.
- `GET /api/v1/advertiser/campaigns/{campaign_id}/impressions/summary` now routes
  query datetime timezone validation through the standard `AppError` envelope and
  rejects `start_at > end_at`.
- `GET /api/v1/advertiser/campaigns/{campaign_id}/cost-summary` preserves payout
  date range hardening for timezone-aware query values and `start_at > end_at`.

Security/RBAC hardening implemented:
- Hardening tests verify representative protected GET routes reject missing
  auth with the standard error envelope and request id.
- Config hardening rejects wildcard CORS origins outside local/test-like
  environments.
- Config hardening rejects the default JWT secret outside local/test-like
  environments.
- Added a guard that a sufficiently long custom JWT secret still allows production
  settings construction.

Privacy hardening implemented:
- OpenAPI tests verify the snapshot omits obvious secrets and
  advertiser-sensitive terms such as password hashes, vehicle plate numbers,
  driver PII, raw GPS/idempotency terms, and ledger entry details.
- No response schema changes were made in this clean-finish pass.

API consistency/contract implemented:
- Hardening tests verify major MVP endpoint groups exist in the OpenAPI
  snapshot.
- Hardening tests compare generated OpenAPI path keys against the checked-in
  snapshot.
- Date-range error envelopes are covered for payout cost summary and impression
  summary, and advertiser campaign list filters.
- Added a focused impression summary naive-datetime test for the `ValueError` to
  `AppError` envelope behavior.

OpenAPI snapshot implemented:
- `docs/api/openapi.snapshot.json` exists.
- Checked locally that `json.dumps(create_app().openapi(), indent=2, sort_keys=True)`
  matches the checked-in snapshot exactly.
- Snapshot was verified against the generated schema after implementation.

Payout/ledger cascade review result:
- Current tests guard that the only public DELETE route is campaign-zone deletion.
- No destructive public/API delete endpoint exists for payout/ledger-critical
  parents in the current route table.
- Existing FK cascade risk from Slice 9 remains documented as non-blocking because
  no destructive API path currently reaches those parents.
- No migration was added to change FK policy because that would require a broader
  accounting/settlement policy decision.

README/runbook implemented:
- README notes Slice 13 scope, OpenAPI snapshot contract baseline, frontend auth
  baseline, local docs, config hardening notes, and no-new-migration/no-new-table
  status.

Tests added/updated:
- `tests/test_mvp_hardening.py`
  - OpenAPI snapshot presence and major route groups.
  - Generated OpenAPI path set vs snapshot path set.
  - Snapshot sensitive-term guard.
  - Representative protected-route unauthenticated guard.
  - Static route ordering guard.
  - No public DELETE routes for payout/ledger-critical parents.
  - No new Slice 13 migration/product table guard.
  - Campaign list invalid date range and naive datetime validation envelopes.
  - Payout cost summary invalid date range envelope.
  - Impression summary invalid date range envelope.
  - Impression summary naive datetime validation envelope.
- `tests/test_config.py`
  - JWT default-secret production rejection.
  - JWT short-secret rejection.
  - JWT custom production secret acceptance.

Commands run:
- `python -m ruff check .`
- `python -m pytest tests/test_mvp_hardening.py tests/test_config.py -q`
- `python -m pytest tests/test_seed_demo.py tests/test_config.py tests/test_mvp_hardening.py -q`
- `python -m pytest -q`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head; if ($LASTEXITCODE -eq 0) { python -m alembic current }`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest -q`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; $env:ALLOW_DEMO_SEED='true'; python -m app.seeds.demo`
- `docker compose run --rm api python --version`
- `docker compose run --rm api python -m ruff check .`
- `docker compose run --rm api python -m pytest -q`

Command results:
- `python -m ruff check .`: passed, `All checks passed!`.
- `python -m pytest tests/test_mvp_hardening.py tests/test_config.py -q`: earlier focused gate passed, `79 passed, 1 warning in 10.98s`.
- `python -m pytest tests/test_seed_demo.py tests/test_config.py tests/test_mvp_hardening.py -q`: final focused gate passed, `89 passed, 1 skipped, 1 warning in 14.67s`.
- `python -m pytest -q`: final local full suite passed, `222 passed, 26 skipped, 1 warning in 259.11s`.
- Alembic/Postgres upgrade/current: `0010_payouts_and_earnings (head)`.
- Postgres-backed `python -m pytest -q`: final suite passed, `248 passed, 1 warning in 403.74s`.
- Demo seed: completed successfully with 4 users, 3 zones, 2 trips, 12 pings, 2 analytics rows, 2 impression estimates, 2 payout calculations, and 2 ledger entries.
- `docker compose run --rm api python --version`: `Python 3.12.13`.
- `docker compose run --rm api python -m ruff check .`: passed, `All checks passed!`.
- `docker compose run --rm api python -m pytest -q`: final Docker suite passed, `248 passed, 1 warning in 375.02s`.
- OpenAPI snapshot consistency check: `MATCH=True`, `PATH_COUNT=63`.

Known issues:
- Existing Starlette/httpx TestClient deprecation warning remains; it predates this slice.
- No settlement/accounting FK policy migration was added because the current public
  API exposes no destructive route for payout/ledger-critical parents.
- Reporting daily-metrics performance hardening beyond current bounded contract tests
  is deferred because pushing those aggregations deeper into SQL would be broader than
  this contract-freeze slice.
- Pro accepted these as non-blocking risks in
  `docs/build-loop/pro-responses/slice-13-mvp-hardening-and-contract-freeze.md`.

Out-of-scope compliance:
- Implementation workers made no commits.
- Pro review completed after implementation and returned PASS.
- Worker implementation did not edit `docs/build-loop/slice-log.md`; ledger updates are handled by the orchestrator.
- No new product feature.
- No new endpoint.
- No new Alembic migration.
- No new product table.

Acceptance criteria checklist:
- Impression summary timezone `ValueError` wrapper: implemented and tested.
- Impression summary `start_at > end_at`: implemented and tested.
- Campaign list timezone `ValueError` wrapper and `start_at_from > start_at_to`:
  implemented and tested.
- Payout/report date-range hardening: implemented and tested.
- OpenAPI snapshot exists and matches generated schema: verified.
- Config CORS/JWT hardening without breaking custom production settings: implemented and tested.
- Payout/ledger parent delete risk documented/test-guarded: implemented and tested.
- No new Alembic migration/no new product tables guard: implemented and tested.
- README MVP backend/runbook/frontend contract baseline: implemented.
- Ruff: passed.
- Focused pytest: passed.
- Full pytest: passed locally and in Docker.
- Alembic upgrade/current: passed at `0010_payouts_and_earnings (head)`.

Manual verification steps:
- Start Docker Compose services.
- Run `python -m ruff check .`.
- Run `python -m pytest -q`.
- Run Postgres-backed Alembic/current/full tests with
  `DATABASE_URL=postgresql+asyncpg://mobility:mobility@localhost:5433/mobility`.
- Run the demo seed with `ALLOW_DEMO_SEED=true`.

Questions for Pro reviewer:
- Does this Slice 13 hardening set qualify as the MVP backend contract freeze, or is
  any additional closure packet/fix required before declaring the backend build loop done?
