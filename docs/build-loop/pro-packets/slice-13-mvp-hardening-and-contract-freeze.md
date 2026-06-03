PRO REVIEW PACKET

Slice:
Slice 13 - MVP hardening and contract freeze

Decision to review:
Is Slice 13 safe to commit, and does this complete the MVP backend build loop for frontend integration? If not, identify only blocking fixes required before commit/closure.

Repo state summary:
- Branch: `slice-13-mvp-hardening`
- Base state includes Pro-accepted Slices 0 through 12.
- Slice 12 was committed before this work:
  - `acbcabf feat: add demo seed data and API docs hardening`
  - `6b7347a docs: record slice 12 commit`
- Current uncommitted changes are Slice 13 implementation/report artifacts plus the orchestrator ledger marker in `docs/build-loop/slice-log.md`.
- API prefix remains `/api/v1`.
- Alembic head remains `0010_payouts_and_earnings`.
- No Slice 13 product tables, endpoints, SDKs, jobs, materialized views, map tiles, settlement flows, or migrations were added.

Commit status:
- Not committed yet.
- Orchestrator will commit only after Pro PASS and local reconciliation.

Files changed:
- `README.md`
- `app/api/v1/campaigns.py`
- `app/api/v1/impressions.py`
- `app/api/v1/payouts.py`
- `app/core/config.py`
- `tests/test_config.py`
- `tests/test_seed_demo.py`
- `tests/test_mvp_hardening.py`
- `docs/api/openapi.snapshot.json`
- `docs/build-loop/reports/slice-13-mvp-hardening.md`
- `docs/build-loop/slice-log.md` is changed only by the orchestrator to mark Slice 13 in progress and is not part of the worker implementation.

Diff summary:
- README now states Slice 13 status, `/api/v1` frontend base URL, login/auth flow, OpenAPI snapshot path, live docs path, snapshot regeneration command, production config hardening notes, and no-new-migration/no-new-table status.
- `app/core/config.py`
  - Extracts local/test-like environment constants.
  - Rejects wildcard CORS outside local/test-like environments.
  - Rejects the default JWT secret outside local/test-like environments.
  - Rejects blank/short JWT secrets.
- `app/api/v1/campaigns.py`
  - Adds query datetime validation helpers for `start_at_from` and `start_at_to`.
  - Naive datetimes now use the standard `VALIDATION_ERROR` envelope with request id.
  - `start_at_from > start_at_to` now returns `INVALID_DATE_RANGE`.
- `app/api/v1/impressions.py`
  - Wraps `ensure_timezone_aware` errors for advertiser impression summary query params in `AppError`.
  - Adds `start_at > end_at` validation for the advertiser impression summary endpoint.
- `app/api/v1/payouts.py`
  - Adds shared payout date-range validation for advertiser campaign cost summary.
  - Preserves timezone-aware query validation and adds `start_at > end_at` rejection.
- `tests/test_mvp_hardening.py`
  - Verifies OpenAPI snapshot presence and major MVP route groups.
  - Verifies generated OpenAPI path set matches the checked-in snapshot.
  - Verifies snapshot omits secrets and advertiser-sensitive terms.
  - Verifies representative protected GET routes reject missing auth with request id.
  - Verifies static routes precede dynamic siblings.
  - Verifies the public DELETE surface does not expose payout/ledger-critical parent deletion.
  - Verifies no Slice 13 migration/product table was added.
  - Verifies campaign-list, payout-cost-summary, and impression-summary invalid date envelopes.
- `tests/test_config.py`
  - Adds JWT default-secret, short-secret, and custom production-secret tests.
- `tests/test_seed_demo.py`
  - Supplies a non-default production test JWT secret so the seed production-refusal test reaches the intended demo-seed guard after config hardening.
- `docs/api/openapi.snapshot.json`
  - Checked-in OpenAPI baseline generated from `create_app().openapi()` with sorted JSON.

Database migrations:
- None added.
- Alembic versions remain `0001` through `0010`.
- Runtime verification: `0010_payouts_and_earnings (head)`.
- Test guard verifies no Slice 13 migration/product table was added.

API endpoints implemented/changed:
- No new endpoints.
- Existing endpoint hardening only:
  - `GET /api/v1/advertiser/campaigns`
  - `GET /api/v1/advertiser/campaigns/{campaign_id}/impressions/summary`
  - `GET /api/v1/advertiser/campaigns/{campaign_id}/cost-summary`

Security/RBAC hardening implemented:
- Production-like settings cannot use wildcard CORS.
- Production-like settings cannot use the local placeholder JWT secret.
- JWT secrets must be non-blank and at least 32 characters.
- Representative protected route groups are tested for unauthenticated rejection and request-id propagation.
- Route order guard tests prevent known static/dynamic conflicts from regressing.
- Demo seed remains explicit CLI-only behavior and production-like seed refusal remains tested.

Privacy hardening implemented:
- OpenAPI snapshot guard rejects obvious secret and advertiser-sensitive terms, including password hashes, driver PII field names, vehicle plate fields, raw GPS/idempotency terms, and ledger-entry identifiers in advertiser/heatmap contract surfaces.
- No advertiser report or heatmap response schema was broadened.
- Payout/ledger public delete safety is guarded at the route table.

API consistency/contract implemented:
- List/date filters now have standard envelopes for key MVP frontend routes:
  - campaign list `start_at_from`/`start_at_to`
  - impression summary `start_at`/`end_at`
  - cost summary `start_at`/`end_at`
- Invalid reverse ranges return `INVALID_DATE_RANGE`.
- Naive query datetimes return `VALIDATION_ERROR` with request id.
- Existing response shapes and paths were preserved.

OpenAPI snapshot implemented:
- `docs/api/openapi.snapshot.json`
- Snapshot consistency check:
  - `MATCH=True`
  - `PATH_COUNT=63`
- Snapshot contains major MVP endpoint groups:
  - health
  - auth
  - me
  - admin users/orgs
  - driver profiles/vehicles
  - campaigns/creatives
  - campaign zones
  - assignments
  - trips/pings
  - analytics/fraud
  - impressions
  - payouts/earnings
  - advertiser reports
  - heatmaps

Payout/ledger cascade review result:
- Slice 9 noted FK cascade risk for future destructive parent deletes.
- Current public/API DELETE surface is only campaign-zone deletion:
  - `/api/v1/advertiser/campaigns/{campaign_id}/zones/{zone_id}`
- There is no public/API delete endpoint for payout/ledger-critical parents such as campaigns, driver profiles, vehicles, trip sessions, trip analytics, impression estimates, payout calculations, payout rules, or ledger entries.
- Because no destructive API path currently reaches those parents, no FK policy migration was added in Slice 13.
- This remains documented as a non-blocking future accounting/settlement policy decision.

README/runbook implemented:
- MVP backend status.
- `/api/v1` frontend base URL.
- Login then bearer-auth flow.
- `/api/v1/me` route-guard note.
- OpenAPI snapshot path and regeneration command.
- Live docs paths.
- Demo/local-only seed and credential notes preserved.
- Security notes for local placeholder JWT secret and wildcard CORS.
- No migration/table addition note for Slice 13.

Tests/checks run:
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

Exact command outputs or concise failure excerpts:
- `python -m ruff check .`: `All checks passed!`
- Focused hardening/config gate before final campaign-list fix: `79 passed, 1 warning in 10.98s`
- Final focused seed/config/hardening gate: `89 passed, 1 skipped, 1 warning in 14.67s`
- Local full suite: `222 passed, 26 skipped, 1 warning in 259.11s`
- Alembic current: `0010_payouts_and_earnings (head)`
- Postgres-backed full suite: `248 passed, 1 warning in 403.74s`
- Demo seed: completed successfully; counts were users 4, campaign_zones 3, trips 2, pings 12, analytics 2, impression_estimates 2, payout_calculations 2, ledger_entries 2.
- Docker Python: `Python 3.12.13`
- Docker ruff: `All checks passed!`
- Docker full suite: `248 passed, 1 warning in 375.02s`
- OpenAPI snapshot check: `MATCH=True`, `PATH_COUNT=63`

Known issues:
- Existing Starlette/httpx TestClient deprecation warning remains and predates Slice 13.
- No settlement/accounting FK policy migration was added because current public/API behavior has no destructive route to payout/ledger-critical parents.
- Reporting daily-metrics deeper SQL/performance rewrite is deferred because it would be broader than this contract-freeze hardening slice. Current API contract remains bounded/tested.

Out-of-scope confirmation:
- No new product features.
- No new endpoints.
- No new product tables.
- No new Alembic migration.
- No settlement, withdrawal, billing, invoice, payment account, or accounting workflow.
- No background job/scheduler.
- No client SDK generation.
- No frontend/mobile implementation.
- No AI/CV counting, map tiles/vector tiles, or automated scheduled rollups.

Acceptance criteria checklist:
- Security/RBAC representative protected route guard: implemented and tested.
- Production wildcard CORS rejection: implemented and tested.
- Production default JWT secret rejection: implemented and tested.
- Demo seed local-only/production refusal preserved: implemented and tested.
- Campaign-list date envelope hardening: implemented and tested.
- Impression-summary date envelope hardening: implemented and tested.
- Payout cost-summary date envelope hardening: implemented and tested.
- OpenAPI snapshot generated and checked in: implemented and verified.
- OpenAPI major endpoint group tests: implemented and tested.
- No new migration/table guard: implemented and tested.
- Payout/ledger destructive API delete guard: implemented and tested.
- README frontend contract/runbook notes: implemented.
- Full local/Postgres/Docker checks: passed.

Codex questions:
- Does Pro consider this safe to commit?
- Does this Slice 13 PASS also constitute final backend MVP build-loop closure, or should Codex send a separate final closure packet after committing?
- If final closure requires another packet, what exact closure evidence should it include?

Requested Pro response shape:
Verdict: PASS | FIX REQUIRED | BLOCKED

Required changes:
- ...

Risks:
- ...

Tests or verification:
- ...

Reasoning notes:
- ...

Next slice / closure:
- If more implementation is required, provide the exact next slice prompt.
- If backend implementation is done, state that no further implementation slice remains and whether a final closure packet is required after commit.
