You are implementing Slice 13 of the Mobility AdTech & Audience Attribution backend.

Slice 0 project foundation, Slice 1 auth/users/advertiser organizations, Slice 2 driver/vehicle foundations, Slice 3 campaign/creative metadata, Slice 4 campaign zones/geofences, Slice 5 campaign assignment/activation, Slice 6 trip tracking/GPS ping ingestion, Slice 7 route analytics/fraud flags, Slice 8 impression estimation, Slice 9 payout calculations/driver earnings ledger, Slice 10 advertiser dashboard/reporting APIs, Slice 11 heatmap/geospatial aggregation APIs, and Slice 12 seed/demo data and API docs hardening have been accepted by Pro review. Build on the existing repo foundation. Do not replace the stack, restructure the project unnecessarily, or introduce speculative scope.

Before starting implementation, confirm Slice 12 has been committed or that the working tree contains only the accepted Slice 12 state. If the repo has uncommitted unrelated changes, stop and report them.

PROJECT CONTEXT

Product:
Mobility AdTech & Audience Attribution Platform.

Backend goal:
Build the backend for a platform where advertisers run campaigns on shared ride vehicles, drivers and vehicles activate campaigns, GPS movement data is ingested, and analytics support route analytics, impression estimation, payout calculations, advertiser reporting, heatmap-ready geospatial data, and demo-ready frontend integration.

Slice 13 goal:
Perform MVP hardening and contract freeze. This slice should make the backend safe and stable for frontend integration by reviewing and tightening security/privacy boundaries, API consistency, pagination/filter validation, error envelopes, OpenAPI contract stability, database indexes/constraints, test coverage, README runbooks, and build-loop closure. It must not add new product features or expand the MVP scope.

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
- Existing campaign/creative foundation from Slice 3
- Existing campaign zone/geofence foundation from Slice 4
- Existing campaign assignment/activation foundation from Slice 5
- Existing trip/session/location ping foundation from Slice 6
- Existing route analytics/fraud flag foundation from Slice 7
- Existing impression estimation foundation from Slice 8
- Existing payout/earnings foundation from Slice 9
- Existing advertiser reporting foundation from Slice 10
- Existing heatmap foundation from Slice 11
- Existing demo seed/docs foundation from Slice 12
- pytest
- ruff
- Docker Compose

IMPORTANT LOCAL NOTE

The local coding-guidelines file is named `agent.md`, even if other instructions mention `AGENTS.md`. Read and follow `agent.md`.

REQUIRED LOCAL INVESTIGATION BEFORE CODING

1. Inspect the current repo state.
2. Read `agent.md`.
3. Read the accepted Slice 0 through Slice 12 implementation reports under `docs/build-loop/reports/`.
4. Inspect `docs/build-loop/slice-log.md`.
5. Inspect existing app structure, routers, settings, error handling, request ID middleware, DB session setup, Alembic setup, auth dependencies, RBAC patterns, models, schemas, services, tests, README, OpenAPI metadata, and demo seed.
6. Confirm the existing API prefix is `/api/v1`.
7. Confirm the current Alembic head is `0010_payouts_and_earnings`.
8. Confirm no Slice 13 product tables already exist.
9. Review the full route table for:
   - missing auth
   - wrong role dependency
   - accidental public endpoints
   - duplicate/conflicting paths
   - route-order conflicts such as static routes after dynamic routes
10. Review all response schemas for accidental sensitive data exposure:
    - password hashes
    - raw GPS ping exports in advertiser/admin reporting
    - driver PII in advertiser endpoints
    - vehicle plate numbers in advertiser reports/heatmaps
    - ledger entry details in advertiser views
    - payment/settlement fields that should not exist
11. Review pagination/filter behavior across list endpoints.
12. Review standard error-envelope behavior across expected domain errors and validation errors.
13. Review CORS, JWT, password, seed, and environment settings.
14. Review DB indexes and constraints added in prior slices.
15. Specifically review the Slice 9 known hardening item around parent-delete cascade behavior for payout/ledger/accounting-related records.
16. Determine whether any hardening migration is truly needed for indexes/constraints/FK behavior. If needed, it must not add product tables. If not needed, document why.
17. If any local evidence conflicts with this prompt, stop and produce a reconciliation report instead of implementing blindly.

ALLOWED SCOPE

Implement only Slice 13 MVP hardening and contract freeze:

1. Security/RBAC audit fixes for existing endpoints.
2. Privacy redaction fixes for existing response schemas.
3. Error-envelope consistency fixes for expected app/domain errors.
4. Pagination/filter consistency fixes for existing list/report endpoints.
5. Request validation tightening for existing endpoints where clearly missing.
6. CORS/JWT/password/seed production-safety hardening.
7. API metadata/OpenAPI contract snapshot generation.
8. README and runbook hardening for local/dev/frontend integration.
9. Test coverage hardening for security, privacy, pagination, error format, seed safety, OpenAPI, and migration guardrails.
10. Database index/constraint/FK hardening only if local evidence proves it is necessary for existing MVP safety.
11. No-new-product-scope guardrail tests.
12. Build-loop final closure documentation.

POSSIBLE BUT OPTIONAL SCOPE

Only if straightforward and useful:

1. Add `GET /api/v1/meta` returning non-sensitive API metadata such as:
   - app name
   - environment
   - API version
   - build/version string if available
   - current OpenAPI title/version
   - database readiness should remain in readiness endpoint, not meta
2. Add API contract snapshot file under `docs/api/openapi.json` or `docs/api/openapi.snapshot.json`.
3. Add a deterministic test that generated OpenAPI contains the expected major endpoint groups.

If adding `/api/v1/meta`, keep it non-sensitive and public or low-risk. Do not expose secrets, database URLs, Redis URLs, JWT configuration, file paths, commit hashes unless already intentionally configured, or internal hostnames.

DO NOT IMPLEMENT

- New product features
- New product tables
- New campaign, driver, trip, analytics, impression, payout, reporting, heatmap, billing, settlement, or seed features
- New advertiser dashboard metrics beyond existing stored/reporting data
- New analytics formulas
- New impression formulas
- New payout formulas
- New heatmap metrics
- New seed data beyond fixing Slice 12 seed correctness if needed
- New background jobs
- Celery workers
- Scheduled calculations
- WebSockets
- Real payment settlement
- Withdrawals/cash-out
- Payment provider integrations
- Billing/invoicing/tax
- Manual fraud review workflow
- Notifications
- External traffic/map/geocoding/map-matching providers
- Map tiles/vector tiles
- Raw GPS export
- Route polyline export
- Audience identity
- Retargeting
- Anonymous audience pooling
- AI/computer vision
- Frontend/mobile implementation
- GitHub remote/PR setup
- Production cloud deployment
- OAuth/social login
- Refresh-token flow
- Public self-registration

DATABASE/MIGRATION RULES

Default expectation:
- No new Alembic migration.
- No new database tables.
- Existing Alembic head remains `0010_payouts_and_earnings`.

Allowed exception:
- A hardening migration may be added only if local evidence shows a real safety issue that cannot be addressed through service/API constraints.
- Acceptable hardening migration examples:
  - Add or adjust an index needed for already-existing high-use query patterns.
  - Tighten an existing FK delete behavior to prevent accidental cascade deletion of financial/ledger-critical records.
  - Add a missing check constraint consistent with an already-enforced API rule.
- Unacceptable migration examples:
  - New product tables.
  - New reporting/materialized tables.
  - New cache tables.
  - New settlement/billing tables.
  - New job/scheduler tables.

If a hardening migration is added:
1. Name it clearly, for example `0011_mvp_hardening`.
2. Down revision must be `0010_payouts_and_earnings`.
3. It must be documented in the build report.
4. It must include focused migration tests.
5. It must not introduce new product scope.
6. It must preserve existing seed/demo flow.

If no migration is added:
1. Add/update a migration guard test proving no new migration/table was introduced in Slice 13.
2. Confirm Alembic head remains `0010_payouts_and_earnings`.

SPECIAL HARDENING ITEM: PAYOUT/LEDGER DELETE SAFETY

Review the Slice 9 known issue: ledger append-only behavior is enforced through no public update/delete endpoints, but future destructive parent deletes should review cascade policy before settlement/accounting work.

For Slice 13:

1. Inspect FK delete behavior involving:
   - `earnings_ledger_entries`
   - `payout_calculations`
   - `campaign_payout_rules`
   - `impression_estimates`
   - `trip_analytics`
   - `trip_sessions`
   - `campaigns`
   - `driver_profiles`
   - `vehicles`
2. Confirm whether any existing public/API delete endpoint can delete parent rows that would cascade-delete payout calculations or ledger entries.
3. If no destructive API path exists, document the current risk as non-blocking and add tests proving no public delete endpoints exist for payout/ledger-critical parents where applicable.
4. If a destructive API path exists or FK cascade would be dangerous through existing API behavior, fix narrowly:
   - Prefer service-level delete restriction if delete endpoint exists.
   - Prefer FK `RESTRICT`/`SET NULL` migration only where clearly necessary.
5. Do not add settlement/accounting workflows.
6. Do not add ledger update/delete endpoints.

SECURITY HARDENING REQUIREMENTS

Audit and fix where necessary:

1. Every non-health/auth-login/demo-doc endpoint that should be protected has an auth dependency.
2. Admin endpoints require admin.
3. Advertiser endpoints require advertiser and organization scoping.
4. Driver endpoints require driver and ownership scoping.
5. Cross-organization campaign/report/heatmap access is non-leaking where practical.
6. Cross-driver trip/assignment/vehicle/analytics/earnings access is non-leaking where practical.
7. Password hashes are never returned.
8. JWT settings do not have production-dangerous defaults.
9. Suspended/disabled users remain blocked from auth/current-user flows where appropriate.
10. Demo seed is not available through API.
11. Demo seed refuses production-like environments.
12. CORS does not use wildcard in non-local environments.
13. Error responses do not leak stack traces or raw DB errors.
14. Request ID continues to appear in responses/errors.
15. OpenAPI docs do not contain real secrets.

PRIVACY HARDENING REQUIREMENTS

Audit and fix where necessary:

1. Advertiser reporting and heatmap responses must not expose:
   - driver full name
   - driver email
   - driver phone
   - driver license number
   - driver profile id unless intentionally opaque and already accepted; prefer not exposing
   - vehicle plate number
   - raw GPS point rows
   - idempotency keys
   - ledger entry ids/details
   - payment account data
2. Driver endpoints must not expose other drivers’ data.
3. Admin endpoints may expose operational details appropriate for admin, but still must not expose password hashes or secrets.
4. Demo docs may list demo credentials only as local-only fake credentials.
5. Logs should not intentionally print passwords, bearer tokens, or raw secrets.

API CONSISTENCY REQUIREMENTS

Audit and fix where necessary:

1. List endpoints use consistent pagination shape:

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}

List endpoint limits are bounded, normally max 100 unless intentionally different for daily metrics/heatmap.

Date ranges are validated consistently.

Decimal values follow existing serialization conventions.

Expected domain errors use standard envelope.

404/not-found and forbidden behavior is consistent with prior accepted patterns.

Existing endpoint response shapes should not change unless required to fix a bug or privacy leak.

Do not rename accepted endpoints.

Do not remove accepted fields unless they are clearly sensitive and should never have been exposed.

Do not add new required request fields to existing frontend-facing endpoints unless necessary for safety.

OPENAPI CONTRACT FREEZE REQUIREMENTS

Add an API contract snapshot unless there is a local reason not to.

Preferred output:

docs/api/openapi.snapshot.json

Rules:

Snapshot should be generated from the app’s OpenAPI schema.

Snapshot should not include environment-specific secrets.

Add test that the OpenAPI schema generates successfully.

Add test that the major MVP endpoint groups exist:

health

auth

me

admin users/orgs

driver profiles/vehicles

campaigns/creatives

campaign zones

assignments

trips/pings

analytics/fraud

impressions

payouts/earnings

advertiser reports

heatmaps

Add README note that the snapshot is the MVP frontend contract baseline.

If snapshot churn is too large, still include it; this is the contract-freeze slice.

Do not generate client SDKs.

README/RUNBOOK REQUIREMENTS

Update README or docs with:

MVP backend status.

Stack summary.

Local setup.

Migration commands.

Seed command and demo credentials.

Test commands.

Docker commands.

PostGIS test commands.

Frontend integration base URL and auth flow.

Core frontend endpoint map.

API docs/OpenAPI snapshot location.

Security notes:

demo credentials local-only

no production seed

no real payments/settlement

no frontend/mobile included

Operational notes:

no background jobs required for MVP

analytics/impressions/payouts are triggered by APIs for now

reporting/heatmap endpoints aggregate stored data only

Known limitations:

no production cloud deployment

no settlement

no retargeting/audience layer

no AI/CV counting

no map tiles/vector tiles

no automated scheduled rollups

TEST REQUIREMENTS

Add/extend tests for:

Security/RBAC:

Route audit or focused tests verify protected endpoint groups reject unauthenticated users.

Admin endpoints reject advertiser/driver users where applicable.

Advertiser endpoints reject admin/driver users where applicable.

Driver endpoints reject admin/advertiser users where applicable.

Cross-organization campaign/report/heatmap access remains blocked.

Cross-driver assignment/trip/earnings access remains blocked.

Disabled/suspended users cannot use protected endpoints if existing dependency should block them.

Password hashes are absent from representative admin/advertiser/driver responses.

Privacy:

Advertiser campaign trips/reporting responses do not expose driver PII or vehicle plate numbers.

Advertiser heatmap responses do not expose raw points, ping ids, idempotency keys, driver PII, or plate numbers.

Advertiser cost summaries do not expose ledger entry details.

Driver earnings endpoints do not expose other drivers’ ledger entries.

Demo README/docs mark credentials local-only.

API consistency:

Representative list endpoints return standard pagination shape.

Pagination limit bounds are enforced.

Invalid date ranges return standard error envelope.

Representative expected domain errors use standard error envelope and request id.

OpenAPI schema generates successfully.

OpenAPI snapshot is present and valid JSON.

OpenAPI snapshot includes major endpoint groups.

Existing accepted endpoint paths still exist.

Seed/demo safety:

Seed command still refuses production-like environments.

Seed command remains idempotent.

Seed command still creates useful reporting/heatmap/earnings data.

Seed does not run at app startup.

Database/migration:

Alembic upgrade head passes.

If no migration is added, Alembic head remains 0010_payouts_and_earnings.

If a hardening migration is added, Alembic current shows the new hardening head and tests verify no new product tables.

No new product tables are added.

Existing demo seed still works after any migration.

Performance/index sanity:

Representative reporting/heatmap queries have indexes available for their major joins/filters where inspectable.

No obvious N+1 loops in high-level reporting/heatmap endpoints where easy to detect by service code review or focused tests.

Regression:

Existing Slice 0-Slice 12 tests continue to pass.

Ruff passes.

Docker Python 3.12 tests pass.

Postgres/PostGIS tests pass.

Testing implementation guidance:

Reuse existing fixtures and auth helpers.

Keep tests deterministic.

Do not require external network access.

PostGIS-backed tests should run with real Postgres/PostGIS as in prior slices.

If plain host tests skip PostGIS checks without a DB URL, ensure PostGIS/Docker checks run and are reported.

Avoid brittle tests that depend on exact OpenAPI operation ordering.

Prefer checking endpoint path presence and schema validity rather than huge exact snapshot equality, unless snapshot tooling is already in place.

CHECKS THAT MUST WORK

The final implementation should support:

python -m pytest
python -m ruff check .
alembic upgrade head

Also verify Python 3.12 through Docker as in prior slices:

docker compose run --rm api python --version
docker compose run --rm api python -m pytest
docker compose run --rm api python -m ruff check .

Postgres/PostGIS migration, full-test, and seed verification are required:

$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic current
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; $env:ALLOW_DEMO_SEED='true'; python -m app.seeds.demo

If a hardening migration is added, include both upgrade and current output for the new head.

If any command cannot be run locally due to missing external runtime or local environment issues, report that honestly with exact evidence.

FRONTEND CONTRACT NOTES

After Slice 13, the MVP backend contract should be considered frozen enough for frontend implementation.

Frontend developers should rely on:

API base:

/api/v1

API docs:

/docs

/openapi.json

docs/api/openapi.snapshot.json, if implemented

Auth:

POST /api/v1/auth/login

Bearer token for protected routes

GET /api/v1/me for route guards

Advertiser:

campaign CRUD

creative metadata

zones

impression summary

cost summary

dashboard summary

campaign summary

daily metrics

trip summaries

bundled report

heatmap

Driver:

profile

vehicles

assignments

trips/pings

trip analytics summary

earnings summary/ledger

Admin:

users/orgs

drivers/vehicles

campaign oversight

assignments

analytics/fraud

impressions

payout rules/calculations

heatmap

Do not break these accepted contracts in Slice 13 unless fixing a clear bug or privacy/security issue.

STANDARD ERROR BEHAVIOR

Use the existing Slice 0-Slice 12 error envelope for expected errors:

JSON
{
  "error": {
    "code": "SOME_CODE",
    "message": "Human-readable message",
    "details": {},
    "request_id": "..."
  }
}

Expected errors to keep consistent include:

Missing token

Invalid token

Forbidden role

Missing advertiser organization

Campaign not found

Driver profile missing

Trip not found

Analytics not found

Impression estimate not found

Payout rule not found

Invalid date range

Invalid pagination/filter value

Invalid bbox/resolution/metric

Demo seed disallowed

Do not return raw stack traces or raw DB errors.

ACCEPTANCE CRITERIA

Slice 13 is acceptable only if:

No new product features are added.

No new product tables are added.

No new Alembic migration is added unless it is strictly hardening-only and justified by local evidence.

Existing MVP endpoints remain present and stable.

Security/RBAC audit issues found in existing endpoints are fixed or documented as non-issues.

Privacy audit issues found in advertiser/driver/admin responses are fixed or documented as non-issues.

Demo seed remains production-safe and idempotent.

OpenAPI schema generates successfully.

OpenAPI contract snapshot is added or a clear local reason is documented if not.

README/runbook documents MVP setup, seed, tests, API docs, frontend integration, and limitations.

Error envelope consistency is preserved or improved.

Pagination/filter/date validation consistency is preserved or improved.

Payout/ledger parent-delete cascade risk is reviewed and either safely fixed or explicitly documented as non-blocking because no destructive API path exists.

Existing Slice 0-Slice 12 tests continue to pass.

New hardening tests pass.

Ruff passes.

Alembic upgrade head passes against Postgres/PostGIS.

Demo seed command still succeeds and is idempotent against Postgres/PostGIS.

Python 3.12 verification is performed through Docker or explicitly reported if impossible.

No deferred/future scope is implemented.

STOP CONDITIONS

Stop and report instead of implementing if:

Slice 12 accepted foundation is missing or materially different from the packet.

The existing project uses a materially different stack than the approved stack.

agent.md conflicts with this prompt.

Hardening reveals a security/privacy issue that requires a product decision rather than an obvious fix.

Hardening requires a new product table or product feature.

OpenAPI snapshot generation requires unstable environment-specific secrets that cannot be removed cleanly.

Payout/ledger cascade hardening requires a destructive data migration or accounting policy decision.

You are tempted to add new product features, settlement, withdrawals, billing, frontend, deployment, background jobs, seed automation, retargeting, audience identity, AI/CV, map tiles, or external provider integrations.

Otherwise, stop after Slice 13. Do not start any new slice.

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
Security/RBAC hardening approach:
Privacy hardening approach:
API consistency/contract approach:
OpenAPI snapshot approach:
Payout/ledger cascade review approach:
README/runbook approach:
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
API endpoints implemented/changed:
Security/RBAC hardening implemented:
Privacy hardening implemented:
API consistency/contract implemented:
OpenAPI snapshot implemented:
Payout/ledger cascade review result:
README/runbook implemented:
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
API endpoints implemented/changed:
Security/RBAC hardening implemented:
Privacy hardening implemented:
API consistency/contract implemented:
OpenAPI snapshot implemented:
Payout/ledger cascade review result:
README/runbook implemented:
Tests/checks run:
Exact command outputs or concise failure excerpts:
Known issues:
Out-of-scope confirmation:
Acceptance criteria checklist:
Codex questions:
Orchestrator recommendation: PASS_CANDIDATE | NEEDS_FIX | BLOCKED
