# Project Reconciliation

**Status:** current as of 26 July 2026. This document is the project-wide status
map; it does not replace the backend slice ledger or product decision records.

## Canonical Repository

The canonical repository is `/Users/oluwasolaonigbinde/Downloads/mobility` on
`master`. The sibling `mobility-master` directory is an obsolete
Slice-0-only copy and must not be used to determine delivery status.

## Verified Committed Baseline

| Delivery stream | Status | Evidence |
| --- | --- | --- |
| Backend Slices 0–13 | Closed | `docs/build-loop/slice-log.md`, closure commit `0dfb284`, and the final closure response |
| Backend contract | Closure froze 63 API paths; F7 extends it to 66 | `docs/api/openapi.snapshot.json` (current), closure packet (historical 63-path freeze) |
| Frontend F0–F6 | Committed | Git history from `9189fe4` through `a5bcbb6` |
| F7 hardening | Merged to `master` | Git history `f40e0c4` through `236c2e4`; PR #1 |
| Automated trip processing | Merged to `master` | Git history `159b0b1` and `4f69ef6` |
| Pre-production operations | Merged to `master`, not deployed | Git history from `006d94e`; `docker-compose.production.yml`, `docs/runbook.md` |
| Product direction | Decisions recorded, further answers pending | `docs/decisions-log.md` and `docs/Product-Direction-Questionnaire.md` |

The final backend closure states that no Slice 14 is authorized. Any backend work
after that closure is a separately scoped change, not a continuation of the old
slice roadmap.

## F7 Hardening — Merged and Verified

F7 is **complete** and merged to `master`. The delivery comprises:

- Auth/session hardening: current-password-verified changes, forced first-login
  password change, sliding sessions with a 12-hour absolute cap,
  session-version revocation, safe legacy-token handling.
- Redis-backed login rate limiting (account/IP/global buckets, fail-open) with
  429 feedback in the login form and gated trusted-client-IP handling.
- Auth audit events, admin-only filterable audit API, `/admin/audit` UI, and
  audit query indexes (migrations `0011`/`0012`, single Alembic head `0012`).
- Rich deterministic, idempotent demo seed (`f7_rich_v1`) preserving all legacy
  `slice_12_v1` values; staging/production execution denied.
- Backup and revision-gated restore scripts with a rehearsed local drill.
- Sentry hooks on both tiers, inert without a DSN.
- CI: backend job (PostGIS+Redis services, ruff + full pytest), frontend
  quality gates with the contract-drift check, and real-stack Playwright
  (desktop + mobile).

Verification evidence: ruff clean; 267 pytest results passing with PostGIS and
Redis; migration upgrade from an empty database to head `0012`; seed
idempotency and later-date append-only reruns; frontend lint/typecheck/unit/
build green; 45 Playwright tests passing (3 project-scoped skips) including
forced password changes, revoked-cookie login, 429 feedback, and the audit
page; backup/restore drill with truncated-dump rejection.

## Post-F7 Delivery

- The arq worker automates complete-missing-only post-trip processing and uses a
  Postgres-derived recovery sweep. Its payout stage remains transitional
  `payout_v1`; do not enable it for real earnings until D2/Q4/Q5 are resolved.
- The provider-neutral production Compose overlay now keeps only Caddy public,
  isolates PostGIS/Redis, gives application services explicit outbound egress,
  and removes development ports, reload commands, and source mounts.
- The release smoke command and the exact disposable backup/restore rehearsal
  are implemented. The rehearsal has passed valid restore, safety-database,
  exact Alembic-head, and truncated-dump non-replacement checks.

Still true after F7:

- **Nothing is deployed.** Staging is research only
  (`docs/staging-options.md`); pricing requires revalidation at approval time.
- Product-direction items in `docs/decisions-log.md` and questionnaire v2
  remain open; F7 implements none of them.

## Documentation Authority

| Question | Source of truth |
| --- | --- |
| Backend MVP slice completion | `docs/build-loop/slice-log.md` and its linked reports, review packets, and responses |
| Current API contract | `docs/api/openapi.snapshot.json`, generated `openapi.json`, and contract checks |
| Current repository state | `git log`, `git status`, and the checked-out source files |
| Architecture and future boundaries | `docs/architecture.md` |
| Operational procedures | `docs/runbook.md` |
| Product decisions and unresolved choices | `docs/decisions-log.md` and the product-direction questionnaire |

When documentation conflicts, committed source and Git history take precedence.

## Next Documentation Gate

The next status change to this document should come with whichever happens
first:

1. OJ-approved staging deployment (records provider, budget, operator, and the
   trusted-edge design per `docs/staging-options.md`).
2. The next authorized product slice after the blocking questionnaire answers
   land (W1 in `docs/architecture.md` §31).
