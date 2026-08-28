# PKG-08 W4-03A provider-neutral preparation evidence

Date: 2026-08-28

Base: `1715fe53b19972cd6db829a08a9d6cf572fbd656`

Branch: `feat/pkg-08-w4-03a-preparation`
Verdict boundary: repository preparation only; `EXT-RELEASE-ENV` is missing,
`DV-STAGING-LIVE` is not run, and W4-03A is not complete.

## Delivery contract

Intended behavior: a future approved client-owned account/domain can receive
one exact Cardvert revision through fail-closed preflight, private topology,
forward migration, readiness/smoke, encrypted off-host backup, isolated
restore verification, traffic switch, and non-destructive previous-image
recovery.

Break cases: missing/placeholder/weak secrets; mutable or revision-mismatched
images; unsafe host/origin/CORS/test flags; public non-edge services; stale or
conflicting release state; migration response loss or mismatch; worker,
broker, storage, report-schema or smoke failure; corrupt/wrong-key/partial
backup; database/object disagreement; unproven previous-image compatibility;
and any attempt to imply downgrade or live completion.

Unchanged behavior: public API/OpenAPI, model/schema, migrations, frontend
routes, money/report/issuance authority, Package 1–8 behavior, and the three §9
baselines. No provider, account, domain, budget, credential, legal value, or
operations owner was selected.

## Reconciled plan review

The independent clean-context deployment/security/data-loss plan review
returned `REVISE`. The candidate plan was narrowed and strengthened once to:

- bind durable retry-convergent state to exact revision/images/config/previous
  release and require explicit stale-lock recovery evidence;
- prohibit host builds, mutable references, migration downgrade, and automatic
  populated-data replacement;
- quiesce writers and bind database marker/revision plus versioned private
  objects in one authenticated, encrypted, atomically completed bundle;
- inspect the complete production profile and exact edge allowlist;
- add structured correlated redacted edge/API/worker evidence; and
- add focused migration, load, wrong-input, restore-agreement and recovery
  verification.

## Adversarial boundary matrix

| Boundary | Invariant | Failure/retry case | Evidence |
|---|---|---|---|
| Release identity | one release binds exact revision, immutable images, config digest and previous release | conflicting retry or skipped stage fails | state-contract tests and rehearsal |
| Concurrency | one protected release lock | second owner fails; stale recovery needs recorded reference | release script inspection/tests |
| Migration | forward-only exact single head | lost response reconciles only at exact head; mismatch keeps edge stopped | script test and full 0001→0071 rehearsal |
| Topology | only TLS edge public | any app/data port or build/mutable image fails preflight | rendered Compose tests |
| Worker/storage | traffic only after broker, heartbeat and object R/W/delete | stale worker or storage outage stops release | layered readiness and MinIO rehearsal |
| Backup conservation | complete bundle contains exact DB plus DB-authorized versioned objects | interruption has no complete marker; changed inventory/digest fails | manifest tests and isolated restore |
| Restore identity | exact release/config/revision/object agreement in isolation | wrong/corrupt/incompatible bundle fails before traffic | restore script and rehearsal |
| Recovery | previous exact images may run only on proven compatible forward schema | no downgrade/fallback; missing proof keeps traffic stopped | recovery inspection and rehearsal |
| Observability/privacy | useful release/request/job correlation without private facts | sensitive keys/messages scrub; exception body suppressed | log/Sentry scrub tests |
| Money | not applicable | no money/provider action or state changed | §9/API/schema diff checks |

## Verification record

- Red: the new focused suite failed against the pre-implementation image at
  import because the required JSON formatter did not exist.
- Green: `55 passed` in the W4-03A/pre-production gate and `156 passed, 12
  skipped` across preserved settings, health, backup retention, current
  migration/downgrade, report storage and worker suites. The 12 host-side
  service-gated cases lacked `TEST_DATABASE_URL`; the disposable rehearsal
  separately exercised real PostGIS migrations and storage.
- Static/config: targeted Ruff passed; shell syntax passed; standalone
  production Compose rendered with only Caddy 80/443 public, private app/data
  networks, mandatory worker, release-only migrate, immutable images and no
  build directives; pinned Caddy validated the configuration.
- Production-like rehearsal: exact labelled backend/frontend images built;
  fresh PostGIS/Redis/private versioned MinIO started; Alembic upgraded from
  0001 through 0071; API/worker/frontend became healthy; layered readiness and
  storage write/read/delete passed; 100 concurrent health requests passed at
  p95 11.81 ms; writer-quiesced encrypted backup completed; isolated database
  and object restore passed; same-revision recovery passed; the disposable
  project and volumes were removed.
- First rehearsal correction: object snapshot import ordering failed before a
  complete bundle was written; cleanup restarted the prior services and
  removed the disposable project. The import was corrected and the entire
  rehearsal rerun to the passing result above.
- Final rehearsal build red: an open Python dependency range resolved to a new
  incompatible graph, proving the production build was still mutable. The
  production graph is now exact-version and hash locked for Python 3.12, the
  Dockerfile requires every hash, and the complete rehearsal is rerun from a
  fresh build rather than treating the earlier cached image as evidence.
- Final backup-hygiene red: a disposable GPG home under the platform's long
  temporary path exceeded the local agent-socket limit. No complete marker was
  produced; prior services and the disposable project were restored/removed.
  Backup and restore now use separately created short, mode-0700 `/tmp` GPG
  homes and remove them on every exit; the entire rehearsal then passed.

Final lint/tests, §9 byte-stability, secret/exposure scan, and clean-context
post-build minimal-change review are recorded in the final candidate commit
and controller handoff. Live DNS/TLS, public edge, provider backups/alerts,
external restore, previous-release compatibility, and credential rotation are
not run because they require `EXT-RELEASE-ENV` and `EXT-STAGING-APPROVAL`.
