---
schema_version: 1
program_id: cardvert-audit-remediation
program_status: EXECUTING
plan_revision: 10
controller_generation: 1
controller_owner: 01a05de2-0b5d-73f0-ae3d-0e979b734658
controller_nonce: car-remediation-g1-20260901
authoritative_root: /Users/oluwasolaonigbinde/Projects/mobility
authoritative_ref: master
source_revision: 38094d605830ccce111bcb0773ec1a249fed2d58
authoritative_output: shared master checkout
approval: owner delegation from 01a001ce-d025-7531-a84c-7498cd819eda, 1 Sep 2026
approved_writer_capacity: 2
last_event_sequence: 25
---

# Cardvert audit remediation programme

## Reviewed baseline and authority

The owner authorized execution of the unchanged Pro-admitted remediation graph:
86 `FIX` candidates in 60 dependency-safe slices, with 9 `DEFER`, 12 `OWNER
DECISION`, and 8 `EXTERNAL INPUT` candidates retained as non-executable. The
approved shape uses rolling dispatch and at most two simultaneous implementation
owners only when their file and domain leases are demonstrably disjoint.

Authority and precedence:

1. `AGENTS.md` and `docs/progress.md` remain repository execution authority.
2. `issues/planning/remediation-order.md` is the admitted dependency, risk,
   path, review, and verification map.
3. `issues/planning/consolidated-findings.md` preserves the 115-candidate
   inventory and provenance.
4. `issues/findings/high-risk-verification.md` and
   `issues/findings/product-release-verification.md` preserve pinned
   current-source truth and disposition evidence.
5. `.codex/delivery/cardvert-audit-reconciliation/pro-admission-review.md`
   records the GPT-5.6 Pro `SIGNED OFF` verdict.

Source identities at controller claim:

| Source | SHA-256 |
| --- | --- |
| `issues/planning/remediation-order.md` | `b688b92cf2baa52324d972b0a6a0f0137c32f4ae80589aaa96ba92429cd6a1eb` |
| `issues/planning/consolidated-findings.md` | `063c38864d4759242fd1d43aeb5953c4933530effa03e8cdbea172efe9cec2c2` |
| `issues/findings/high-risk-verification.md` | `3e01ab20e841c3f163d3f8873ae1ae0dfb3e1d8cd40ce6b7728f7d004770aac5` |
| `issues/findings/product-release-verification.md` | `7a09242a6edc2ef6e56448a1bec6a2f0f1f51f88be83cfb432e237ecc916b475` |
| Pro admission receipt | `42d7299ebece3e57fd3f508753a886a044233395282eeecf651fba48b3f37d8d` |
| Closed reconciliation ledger | `90adf8c316cb6625a9a810062ef41dec12d1d47d91f5567b03d5c056dffc94fc` |

Reviewed graph amendment after controller claim:

| Revision | Edge | Reason | Review | Updated source SHA-256 |
| ---: | --- | --- | --- | --- |
| 8 | R04 → R02 | DB-005 consumes R04's clean exact-head schema authority and shared migrated-PostgreSQL fixture. Candidate ownership and outcomes are unchanged. | R02-P PASS; GRAPH-CP-CONTROL PASS | `3abb14ff71bfb41da8eb4a047e0973d12e75b14bbfaafbe7ae14ec719fb51605` |

No deployment, live payment, provider action, external publication, legal
approval, credential invention, or external/live evidence claim is authorized.
The UI/product-flow prompt suite remains paused. `COM-008` remains open and
non-executable until the owner supplies the complete policy named below.

## Checkout reconciliation

- `master` and `HEAD` matched the source pin at generation claim.
- There were no active subagents and no competing active Mobility task.
- Existing uncommitted state consists of the prior reconciliation programme's
  `issues/**`, `.codex/delivery/cardvert-audit-reconciliation/**`, four audit
  ZIP archives, and three direct-owner rows in `docs/progress.md`.
- The existing `docs/progress.md` rows are valid prior controller work to adopt.
  They do not yet authorize product edits because the controller still says
  `COMPLETE`.
- The audit ZIP archives are retained untouched as prior programme artifacts.
  No remediation packet owns or commits them by association.
- No unrelated product-code change was present at controller claim.

## Execution rules

- The controller alone edits this ledger and `docs/progress.md`.
- Central configuration, migrations, generated contracts, shared fixtures,
  route registries, package manifests, and overlapping services are serialized.
- Each meaningful fix packet uses `$verified-feature-delivery`; a genuinely
  cohesive complex packet may use `$orchestrated-feature-delivery` only within
  the admitted outcomes and an isolated reviewed contract.
- Every implementation packet records intended behavior, break cases,
  unchanged behavior, exact candidates and slices, dependency state, allowed
  paths, leases, model gate, verification, required reviews, and stop rules.
- The controller runs on GPT-5.6 Sol/medium by the owner's 1 Sep adjustment.
  Model selection remains explicit before every delegated dispatch: Luna only for bounded read-only
  inventory; Terra/high for ordinary implementation or review; Sol/high or
  Sol/xhigh for money, security, migrations, PostgreSQL concurrency,
  privacy/offline, deployment, or cross-package authority.
- Candidate results remain provisional until the controller inspects the
  integrated diff, tests, red/green evidence, required specialist verdicts,
  and actual checkout state.

## Executable slice map

State began `QUEUED` for every slice. A slice becomes `ACTIVE` only
after repository authority, dependencies, reviews, capacity, and leases agree.

| Slice | Candidate IDs | State | Dependencies / lane | Accepted evidence | Next action |
| --- | --- | --- | --- | --- | --- |
| R01 | GOV-001 | ACCEPTED | control opener | R01-P; R01-M; R01-CP-CONTROL; red/green validator evidence | complete |
| R02 | GOV-003, TST-001, DB-005 | WAITING | R01, R04; control | R02-P; GRAPH-CP-CONTROL | wait for R04 acceptance |
| R03 | GOV-004 | QUEUED | R02; control | — | wait |
| R04 | DB-004 | ACTIVE | database opener | R04-P | implementation attempt 1 |
| R05 | DB-001, TST-012, ONB-010 | QUEUED | R02, R04 | — | wait |
| R06 | DB-002 | QUEUED | R02, R04, R05 | — | wait |
| R07 | DB-003 | QUEUED | R02, R04, R06 | — | wait |
| R08 | GOV-005 | QUEUED | security opener | — | wait for R01 |
| R09 | GOV-007, AUT-001, AUT-002 | QUEUED | R10 | — | wait |
| R10 | AUT-005 | QUEUED | R08 | — | wait |
| R11 | AUT-004 | QUEUED | R09 | — | wait |
| R12 | AUT-003, REL-003 | QUEUED | R11 | — | wait |
| R13 | SEC-001, PRV-008 | QUEUED | sensitive-metadata opener | — | wait for R01 |
| R14 | SEC-002, TST-004 | QUEUED | R12 | — | wait |
| R15 | GOV-006 | QUEUED | worker opener | — | wait for R01 |
| R16 | GOV-008 | QUEUED | provider-boundary opener | — | wait for R01 |
| R17 | TST-007 | QUEUED | R02, R03 | — | wait |
| R18 | MON-005, MON-006 | QUEUED | R04, R06, R07 | — | wait |
| R19 | MON-002 | QUEUED | R18 | — | wait |
| R20 | MON-001, DB-007, MON-008 | QUEUED | R05, R18 | — | wait |
| R21 | MON-003 | QUEUED | R20 | — | wait |
| R22 | MON-004, MON-007, MON-009 | QUEUED | R20, R21 | — | wait |
| R23 | COM-001, COM-004 | QUEUED | R08; commercial opener | — | wait |
| R24 | COM-002 | QUEUED | R08, R23 | — | wait |
| R25 | COM-003, COM-005 | QUEUED | R08, R24 | — | wait |
| R26 | COM-006 | QUEUED | R08, R25 | — | wait |
| R27 | COM-007 | QUEUED | R08, R26 | — | wait |
| R28 | CAM-001 | QUEUED | campaign opener | — | wait for R01 |
| R29 | CAM-002 | QUEUED | R04, R08, R28 | — | wait |
| R30 | CAM-003 | QUEUED | R29 | — | wait |
| R31 | CAM-004 | QUEUED | R18, R19, R30 | — | wait |
| R32 | ONB-002 | QUEUED | onboarding opener | — | wait for R01 |
| R33 | ONB-006 | QUEUED | R05, R32 | — | wait |
| R34 | OFF-001 | QUEUED | R04; offline opener | — | wait |
| R35 | OFF-002, OFF-003 | QUEUED | R34 | — | wait |
| R36 | OFF-005 | QUEUED | R35 | — | wait |
| R37 | OFF-006 | QUEUED | R36 | — | wait |
| R38 | PRV-001, PRV-002 | QUEUED | R13; privacy opener | — | wait |
| R39 | PRV-003 | QUEUED | R38 | — | wait |
| R40 | PRV-004, AUD-001, AUD-002 | QUEUED | R16, R39 | — | wait |
| R41 | PRV-009, AUD-004, TST-010 | QUEUED | R40 | — | wait |
| R42 | PRV-005, PRV-006 | QUEUED | R41 | — | wait |
| R43 | PRV-007 | QUEUED | R42 | — | wait |
| R44 | AUD-005 | QUEUED | R16, R40 | — | wait |
| R45 | MET-003 | QUEUED | R04, R41; reporting opener | — | wait |
| R46 | REP-001 | QUEUED | R45 | — | wait |
| R47 | MET-001, MET-002, MET-004, REP-002 | QUEUED | R41, R46 | — | wait |
| R48 | REP-003 | QUEUED | R47 | — | wait |
| R49 | REP-004 | QUEUED | R47, R48 | — | wait |
| R50 | REP-005 | QUEUED | R47, R49 | — | wait |
| R51 | REP-006 | QUEUED | R43, R49, R50 | — | wait |
| R52 | MET-006 | QUEUED | R51 | — | wait |
| R53 | REL-005 | ACCEPTED | release opener | R53-P; R53-M; R53-RELEASE; R53-CP-RELEASE; real Docker red/green | complete |
| R54 | REL-006 | QUEUED | R12, R16, R53 | — | wait |
| R55 | REL-004 | QUEUED | R03, R18, R48, R51, R54 | — | wait |
| R56 | TST-005 | QUEUED | R09, R11, R14, R40 | — | wait |
| R57 | TST-008 | QUEUED | R19, R27, R49, R55 | — | wait |
| R58 | TST-011 | QUEUED | R15, R20, R21, R43, R49, R51 | — | wait |
| R59 | TST-002 | QUEUED | R22, R31, R33, R37, R41, R44, R48, R50, R51, R56, R57, R58 | — | wait |
| R60 | GOV-009 | QUEUED | R03, R17, R18, R22, R27, R31, R33, R37, R43, R44, R52, R55, R56, R59 | — | wait |

## Non-executable candidate map

These dispositions cannot acquire an implementation lease without their named
trigger and a newly reviewed authority amendment.

### Deferred

| Candidate | State | Activation trigger |
| --- | --- | --- |
| AUD-003 | DEFER | before any live ad-platform adapter |
| CAM-005 | DEFER | reproduced double bind or changed review reachability |
| MET-005 | DEFER | before both live report flags are enabled |
| MET-007 | DEFER | demonstrated lineage harm or approved hardening |
| OFF-004 | DEFER | approved support matrix or reproduced supported-target lock loss |
| OFF-007 | DEFER | approved automatic correction or enforceable operational SLA |
| OFF-009 | DEFER | approved native/background authority and physical evidence |
| ONB-001 | DEFER | deployed timing distributions establish distinguishability |
| ONB-007 | DEFER | reproduced bypass or approved stale-list hardening |

### Owner decisions

| Candidate | State | Required authority |
| --- | --- | --- |
| AUD-006 | OWNER DECISION | allowed campaign lifecycle states for planning-source links |
| AUT-006 | OWNER DECISION | privilege-elevation session/reauthentication policy |
| AUT-007 | OWNER DECISION | explicit tenant selection or one-membership policy |
| COM-008 | OWNER DECISION — OPEN | corporate-credit facility ceiling and recorder/approver policy, including legacy, retry, concurrency, and immutable audit |
| OFF-008 | OWNER DECISION | ambiguous-End capture/resend and sequence-gap policy |
| ONB-003 | OWNER DECISION | duplicate NIN/phone/bank-account policy |
| ONB-004 | OWNER DECISION | maximum vehicle-approval horizon and renewal relation |
| ONB-005 | OWNER DECISION | maker-checker separation for onboarding approvals |
| ONB-008 | OWNER DECISION | global registration abuse/availability policy |
| ONB-009 | OWNER DECISION | account activation and initial credential/session policy |
| REL-007 | OWNER DECISION | bundled-only or managed DB/Redis topology |
| REP-007 | OWNER DECISION | lawful report retention/withdrawal/link policy |

### External inputs

| Candidate | State | Required evidence |
| --- | --- | --- |
| DB-006 | EXTERNAL INPUT | production-version PostGIS target and representative data volumes |
| GOV-002 | EXTERNAL INPUT | immutable exact-SHA green CI/check evidence |
| REL-001 | EXTERNAL INPUT | selected live providers/accounts/specifications and sandbox contracts |
| REL-002 | EXTERNAL INPUT | selected production KMS/vault and custody specification |
| REL-008 | EXTERNAL INPUT | approved backup ownership/scope/cadence/RPO/RTO and restore evidence |
| TST-003 | EXTERNAL INPUT | real provider sandbox/live-contract evidence |
| TST-006 | EXTERNAL INPUT | physical Android/iPhone lifecycle and GPS evidence |
| TST-009 | EXTERNAL INPUT | controlled low-value bank settlement artifact |

## Active owners, leases, and capacity

| Owner | Packet / attempt | Model gate | Mutation lease | State |
| --- | --- | --- | --- | --- |
| controller | rolling scheduler | GPT-5.6 Sol/medium — owner-adjusted controller | ledger and `docs/progress.md` | ACTIVE |
| `/root/r04_implementation` | R04 / attempt 1 | GPT-5.6 Sol/xhigh — Alembic/PostgreSQL/PostGIS schema and migration authority | `app/models/**`; `app/db/base.py`; `alembic/env.py`; `alembic/versions/**`; R04 migration/catalog tests; shared DB fixture only if pre-declared | ACTIVE |
| `/root/r53_implementation` | R53 / attempt 1 | GPT-5.6 Sol/high — immutable frontend image and release-build provenance | released after exact three-file handoff | ACCEPTED |

Implementation writers active: **1 / 2**. Review/inventory work may use spare
capacity only when it cannot contend with an implementation owner.

## Accepted evidence

R01 is accepted exactly once with R01-P, R01-M and R01-CP-CONTROL. Evidence
includes the pre-fix terminal-state red, four safe-mutation red failures covering
manifest pinning, active capacity, receipt completion and post-PKG-10 pause,
then 47 green validator tests, Ruff, the repository validator and diff check.
R53 is accepted exactly once with R53-M, the release-specialist PASS and
R53-CP-RELEASE after real Docker 29.5.3 red/green. R04 remains active; R02-P is
accepted but waits for the reviewed R04 dependency.

## Outstanding decisions and waits

`COM-008` is open. It does not block independent ready slices. Every other
owner-decision and external-input row remains non-executable and is not present
by omission.

## Next scheduler action

Monitor R04, pre-review the next ready non-conflicting R08 security packet, and
dispatch it into the released second writer slot only after its exact plan
passes. R02 remains waiting for R04 acceptance.

## Material receipts

| Seq | Revision | Generation | Type | Event | Evidence |
| ---: | ---: | ---: | --- | --- | --- |
| 1 | 1 | 1 | CONTROLLER_CLAIMED | Generation 1 claimed the admitted remediation programme at the exact source pin. | current task `01a05de2-0b5d-73f0-ae3d-0e979b734658`; `HEAD=38094d6` |
| 2 | 1 | 1 | USER_AUTHORIZED | Owner authorized all 86 FIX candidates/60 slices, rolling two-writer dispatch, direct shared-checkout execution, and retained non-executable dispositions. | delegation from `01a001ce-d025-7531-a84c-7498cd819eda`, 1 Sep 2026 |
| 3 | 1 | 1 | SOURCE_RECONCILED | Source/admission digests, dirty checkout, task state, and initial ready fronts reconciled; no drift or competing owner found. | startup snapshot and source hashes above |
| 4 | 2 | 1 | CONTROLLER_MODEL_ADJUSTED | Owner set the running controller to Sol/medium while retaining high/xhigh for delegated high-risk implementation/review. | current task, 1 Sep 2026 |
| 5 | 2 | 1 | PLAN_REVIEW_PASSED | R01's corrected exact contract received independent PASS after preserving the root terminal pointer and pinning slice-state/evidence grammar. | `R01-P`; Terra/high reviewer `/root/r01_plan_review` |
| 6 | 2 | 1 | RED_OBSERVED | The new rejection assertion failed against the pre-fix build-exhausted COMPLETE validator behavior. | targeted pytest: 1 failed as expected |
| 7 | 2 | 1 | IMPLEMENTATION_VERIFIED | R01 authority, PKG-10 register and validator enforcement are green before diff admission. | 47 focused tests passed; progress validator passed; `git diff --check` passed |
| 8 | 3 | 1 | DIFF_REVIEW_FIX | R01 M/CP review found missing ONB-009 durable authority and insufficient adversarial receipt/red proof. | Sol/high reviewer `/root/r01_diff_review` |
| 9 | 3 | 1 | REVIEW_FIX_VERIFIED | Restored ONB-009, added wrong-slice/wrong-CP receipt cases, observed four focused tests fail under smallest safe enforcement mutations, restored enforcement, and reran green. | 47 tests passed; Ruff, progress validator and diff check passed |
| 10 | 4 | 1 | DIFF_REVIEW_PASSED | R01-M passed after correction with no findings or verification gaps. | Sol/high reviewer `/root/r01_diff_review` |
| 11 | 4 | 1 | CHECKPOINT_PASSED | R01-CP-CONTROL passed; executable and non-executable authority remained exact. | Sol/high reviewer `/root/r01_diff_review` |
| 12 | 4 | 1 | SLICE_ACCEPTED | R01/GOV-001 accepted exactly once and unlocked rolling product dispatch. | R01-P, R01-M, R01-CP-CONTROL; 47 tests; validator; Ruff; diff check |
| 13 | 4 | 1 | PLANS_ACCEPTED | Corrected R04 and R53 exact contracts passed their independent plan reviews. | R04-P Sol/xhigh; R53-P Sol/high |
| 14 | 5 | 1 | DISPATCH_RESERVED | R04 attempt 1 reserved the exclusive ORM/Alembic/PostgreSQL schema lease. | Sol/xhigh because migration and PostGIS authority are the hardest boundary |
| 15 | 5 | 1 | DISPATCH_RESERVED | R53 attempt 1 reserved the disjoint frontend Docker/map image lease. | Sol/high because immutable release-image provenance is the hardest boundary |
| 16 | 6 | 1 | DISPATCH_STARTED | R04 attempt 1 acquired its exclusive schema/migration lease. | agent `/root/r04_implementation`; Sol/xhigh |
| 17 | 6 | 1 | DISPATCH_STARTED | R53 attempt 1 acquired its disjoint frontend image-contract lease. | agent `/root/r53_implementation`; Sol/high |
| 18 | 7 | 1 | IMPLEMENTATION_RETURNED | R53 released its exact lease after real-Docker red/green and focused frontend verification; completion remains pending M/release/CP review. | three leased files; Docker 29.5.3; 6 image tests; 434 frontend tests |
| 19 | 8 | 1 | PLAN_REVIEW_PASSED | R02's exact CI/PostgreSQL/PostGIS/Redis/MinIO/ClamAV contract passed after event-matrix and evidence-manifest corrections. | Sol/high reviewer `/root/r02_plan_review`; R02-P held pending graph CP |
| 20 | 8 | 1 | GRAPH_AMENDMENT_APPLIED | Added R04 → R02 because DB-005 consumes R04's exact-head schema authority and central real-DB fixture; ordering only, with candidates/outcomes unchanged. | focused dependency regression red before amendment; CP-CONTROL review pending |
| 21 | 9 | 1 | GRAPH_REVIEW_FIX_VERIFIED | CP-CONTROL found one stale R01-only R02 test fixture; it now uses R01,R04 and the full validator suite is green. | 48 tests passed; Ruff, progress validator and diff check passed |
| 22 | 10 | 1 | DIFF_REVIEW_PASSED | R53-M passed with every changed file and the new image test justified. | Sol/high reviewer `/root/r53_diff_review` |
| 23 | 10 | 1 | CHECKPOINT_PASSED | R53 release-specialist and CP-RELEASE reviews passed with actual immutable-image authority. | Sol/high reviewer `/root/r53_diff_review` |
| 24 | 10 | 1 | SLICE_ACCEPTED | R53/REL-005 accepted exactly once; no deploy, publication or live map action occurred. | 6 Docker image tests; 2 map tests; 434 frontend tests; build/type/lint; R53-P/M/CP |
| 25 | 10 | 1 | GRAPH_CHECKPOINT_PASSED | R04 → R02 ordering-only amendment passed CP-CONTROL after the stale test correction. | Sol/high reviewer `/root/r02_plan_review`; 48 validator tests |
