# PKG-05 delivery contract and plan

Status: FRONTIER CLOSED — PASS. W3-00A/D/C and W3-01A/B are complete;
remaining checkpoints are dependency-blocked and PKG-06/W3-03A is NEXT.

Base: `feat/pkg-04` / `2309947dbfe91553a5c0243f3a5091dfa9cbdd25`

Delivery branch: `feat/pkg-05`

Upstream dependency-hold release (25 Aug 2026): Package 4's reviewed repair
head `2bc94356f03c76900585de71b6a0189be9e9666c` is released and adopted by a
non-fast-forward merge into this delivery branch. The adoption preserves the
four Package 5 commits through `a81cdf5`, the parked W3-01B candidate, both
histories, and Package 4's fail-closed `0044` authority. Only the migration-head
fixture overlap is resolved in favour of Package 5's later `0046` head; the
merged Package 4 progress evidence is retained. This releases the upstream
repair hold without changing the reviewed Package 5 slice order or external
live-use gates.

Authority: `docs/progress.md` PKG-05, checklist rows 44–54; architecture
§1/§22/§24/§27/§30/§35; decisions D11/D18/D20/D23 and Q11/Q12/Q30/Q31.

## Feature / goal

Deliver the dependency-safe portion of PKG-05 as one governed privacy,
measurement, and retargeting chain. Establish the privacy operating model and
measurement terminology first; then route every advertiser-visible heatmap and
future audience output through one disclosure boundary; then add typed,
tenant-safe planning sources and their campaign/zone/time linkages. Preserve
the blocked descendants and all live-use gates without inventing client,
legal, evidence, activation, or methodology facts.

## Context, scope, and non-goals

- Package 5 owns W3-00A through W3-02B only. Packages 1–4 are not reopened.
- W3-00A and W3-00D are independently runnable. Shared authority-document
  surfaces are serialized.
- W3-00C becomes runnable after W3-00A. W3-01A becomes runnable after W3-00A
  and W3-00D; W3-01B follows W3-01A.
- W3-00B remains transitively blocked by incomplete W2-02E.
- W3-00E remains transitively blocked by incomplete W2-03C and W2-03D.
  W3-01C, W3-01D, W3-02A, and W3-02B therefore remain blocked by W3-00E
  (and their other named dependencies) until those Package 4 facts exist.
- The client document sent for review proves the owner requested the inputs in
  sections 5, 17, and 18; it does not supply them. `EXT-REPORT-METHOD`,
  `EXT-LEGAL-PRIVACY`, and `EXT-AD-PLATFORM` remain MISSING.
- No real GPS, live advertiser output, report issuance, export, activation,
  provider call, identity resolution, person-level audience, new raw-ping
  consumer, or legal approval is in scope.
- Existing money, fraud, commercial, campaign-review, notification, storage,
  and activation behavior is not changed.

## Assumptions

- D23 permits deterministic synthetic build evidence while unavailable live
  legal/provider/physical evidence stays explicitly incomplete.
- Legal/basis/retention rows may name accountable organizational roles and
  provisional build-time controls, but named people, approved wording, final
  retention decisions, and live authority remain external and fail closed.
- The current heatmap raw-ping reader is the one grandfathered reader. W3-00C
  may wrap and constrain it; no additional raw-ping reader may be introduced.
- Thresholds are configuration, not invented pilot facts. A safe synthetic
  test configuration proves behavior; live outputs remain disabled until
  legal approval and density-derived values exist.

## Success criteria and verification

| Criterion | Verification method |
|---|---|
| W3-00A records DPIA, ROPA, controller/processor roles, purpose/basis/retention/recipient matrix, subprocessors/regions, notices/withdrawal, breach responsibilities, external approvals, and a synthetic tabletop | Schema/content contract test plus documented tabletop transcript and cross-check |
| W3-00D defines measured/modelled hierarchy, modelled potential contacts, provenance/vintage, uncertainty, missing data, correction/reissue, prohibited claims, Campaign Performance Analysis, and conditional ROI | Golden performance-only fixtures plus a synthetic test-only ROI method/input manifest; missing-input/method tests; terminology audit. No fixture is a production approval. |
| W3-00C is the only advertiser heatmap/report/audience disclosure path and enforces fixed/coarse buckets, minimum vehicles/trips/days, contributor caps, complementary suppression, restricted filters, atomic cross-endpoint query history, and differencing defense | Endpoint-inventory guard, unit/property fixtures, PostgreSQL endpoint tests, tenant and concurrent adversarial differencing tests; every current advertiser output defaults denied while the legal/privacy gate is absent |
| W3-01A accepts only five typed planning-source kinds with allowlisted structured metadata, provenance, basis, expiry, and DSR fields; identity-like, nested/free-text, cross-tenant input rejects | Migration, API/service validation, RBAC, lifecycle, retry, contract, frontend and live synthetic role journey |
| W3-01B links only owned compatible sources/campaigns/zones/time windows without raw-data joins and with immutable audit history | Compatibility, overlap, ownership, lifecycle, retry/race, audit, frontend and live synthetic setup journey |
| Blocked descendants remain visibly incomplete with exact dependency/external gates | Progress validator and dependency reconciliation |
| Public contracts stay synchronized | OpenAPI generation, snapshot drift, TypeScript generated client, and R14-B contract fixtures whenever the API baseline changes |

## Entry points

- Privacy operations: repository runbook/operating-model artefacts used by the
  named admin/legal/incident roles; no public product entry point.
- Measurement methodology: advertiser campaign report and future issued
  Campaign Performance Analysis labels; no live report issuance in this package.
- Disclosure control: every current advertiser reporting/metric route plus both
  heatmap APIs, then every new Package 5 audience query. The current inventory
  is `/advertiser/dashboard/summary`,
  `/advertiser/campaigns/{id}/summary`, `.../daily-metrics`, `.../trips`,
  `.../report`, `.../impressions/summary`, `.../heatmap`, and
  `/admin/heatmap`. Each inventory row must either call the central disclosure
  decision or fail closed pending W3-00E/W4 safe-run reporting. A static route
  coverage test rejects any current or new advertiser report/metric route that
  is absent from this inventory.
- Retargeting sources/linkage: advertiser campaign/source management and admin
  monitoring through the existing BFF and role navigation.

## Internal dependency plan

| Slice | Checklist | Objective | Dependency / boundary | Acceptance and focused verification |
|---|---|---|---|---|
| P5-S1 | W3-00A | Publish and rehearse the fail-closed privacy operating model | Runnable now; authority docs only | Content contract + synthetic withdrawal/breach tabletop; privacy specialist review |
| P5-S2 | W3-00D | Freeze the build-time measurement/claims contract and conditional ROI gate | Runnable now; serialize shared docs after S1 | Performance-only goldens plus synthetic test-only ROI method/input manifest, missing method/input cases and copy audit; measurement/legal/commercial specialist review |
| P5-S3 | W3-00C | Add central disclosure control; inventory and migrate or fail closed every current advertiser report/metric route and both heatmap APIs | Depends W3-00A; shared default-deny live gate, config/service/query-history migration/API | Route-coverage guard, suppression/differencing/RBAC/PostGIS endpoint evidence, concurrent mixed-endpoint query sequences; privacy/security/architecture specialist review |
| P5-S4 | W3-01A | Add typed aggregate planning-source registry and role surfaces | Depends W3-00A + W3-00D; serialized migration/public contract | Migration/API/UI/e2e, validation/expiry/provenance/tenant tests; privacy/security review |
| P5-S5 | W3-01B | Add owned source-to-campaign/zone/time linkage and history | Depends W3-01A; serialized schema/service/public contract | Compatibility/RBAC/retry/race/audit/API/UI/e2e; privacy/authorization review |
| P5-B1 | W3-00B | Preserve the retention/DSR obligation | BLOCKED transitively by W2-02E | No implementation or DONE claim; record exact dependency |
| P5-B2 | W3-00E | Preserve immutable measurement run/proof-manifest obligation | BLOCKED transitively by W2-03C + W2-03D | No implementation or DONE claim; `EXT-REPORT-METHOD` remains live-issuance gate, not invented input |
| P5-B3 | W3-01C | Preserve governed segment materialization obligation | BLOCKED by W3-00E (also needs W3-00C/D and W3-01B) | No implementation or DONE claim |
| P5-B4 | W3-01D | Preserve recommendation/export/activation obligation | BLOCKED by W3-01C + W3-00E; live push also `EXT-AD-PLATFORM` | No implementation or DONE claim; no adapter call |
| P5-B5 | W3-02A | Preserve exposure-score obligation | BLOCKED by W3-00E | No implementation or DONE claim |
| P5-B6 | W3-02B | Preserve high-zone insight obligation | BLOCKED by W3-00E | No implementation or DONE claim |

Integration order is strictly S1 → S2 → S3 → S4 → S5. Migrations, public
contracts, shared disclosure configuration, API baselines, and authority docs
are controller-owned and serialized. After S5, if all remaining items are
blocked/transitively blocked, mark PKG-05 BLOCKED with the concrete dependency
and external state. Repository control then promotes the first later runnable
package without claiming Package 5 DONE or starting that later package.

## Adversarial-boundary matrix

| Boundary | Controlling invariant | Concrete failure case | Prevention / focused evidence |
|---|---|---|---|
| Retry identity | W3-01A/B acceptance; architecture §14.3 and advisory Package 5 | Create/link commits, response is lost, concurrent retry uses same key or changed body | Stable actor-scoped idempotency key + canonical payload fingerprint; same replay returns one fact, conflicting reuse rejects; concurrent PostgreSQL regression |
| Concurrency / lock order | W3-01B ownership/lifecycle; architecture §22.4 | Source expires or campaign/zone changes while a link is created | For create/retry take source row, campaign row, then referenced zone rows sorted by UUID, then existing link row; re-read tenant, current lifecycle, source expiry, campaign window, zone ownership/type and requested window before write. Source lifecycle takes source; campaign mutation takes campaign; zone mutation takes zone. A later parent mutation makes the stored source/campaign/zone fingerprint stale rather than rewriting history. Link removal locks link after its source. Opposing-order barrier tests prove create sees the prior or new canonical state, never a mixed fingerprint; expiry/deactivate/removal races converge safely. |
| Populated migrations/backfills | Root package loop; migration policy §7.2 | New query-history/source/link authority could be silently lost on downgrade | These are new tables with no legacy heatmap history to backfill. Use empty upgrade/head-chain fixtures and no reconciliation machinery. Downgrade is allowed only while new authority tables are empty; populated downgrade fails before destructive DDL. If implementation changes an existing populated table, stop and amend/re-review this row. |
| Immutable history / projections | W3-00D/E, RM16, D20 | Method/source/link metadata changes after a visible result or accepted linkage | S1–S5 never mutate issued result history. Every source/link create/change/deactivate/remove appends immutable audit evidence with prior/new canonical allowlisted state plus fingerprints; a later source/campaign/zone edit cannot rewrite the linkage fingerprint and instead makes the current projection stale. Mutation, history retrieval and tamper tests cover this. Later W3-00E freezes runs and correction lineage. |
| Tenant/RBAC isolation | §22.4, W3-01A/B, advisory Package 5 | Advertiser guesses another organization source/link/campaign or filters admin output into an advertiser response | Service-level organization checks, not router-only checks; cross-tenant API/service tests and sanitized 404/403 behavior |
| Disclosure floor / suppression | RM15, §22.2, W3-00C | Single query, complementary query, overlapping filters, or switching report/heatmap endpoints reveals a small cohort; one vehicle dominates a cell | Canonical query identity binds principal, tenant, endpoint/output class, campaign/org scope, fixed cell/bucket, normalized time window, metric and allowed filters. In one transaction, lock the principal+tenant disclosure-history scope, evaluate live gate and prior served/suppressed overlaps, append the decision, then compute/return only an allowed result. Record both served and suppressed decisions under bounded retention defined by the privacy schedule. Minimum vehicles+trips+days, contributor caps, complementary suppression and restricted shapes apply across the complete endpoint inventory. Test retries and concurrent mixed bbox/date/resolution/metric/endpoint sequences. |
| Reproducibility / provenance | RM16, W3-00D/E | Missing/stale analytics, changed formula, omitted evidence, or selective source vintage is relabelled as measured/ROI | Explicit metric class and formula/source vintage; missing-data/uncertainty rules. Production remains performance-only and omits ROI until `EXT-REPORT-METHOD` supplies required conversion/revenue inputs and an approved method revision. The ROI-enabled golden uses a clearly synthetic test-only method revision and manifest, never production approval. |
| Suppression edges | RM15, §22.2 | Threshold-minus-one, exact threshold, tied contributors, empty windows, or a removed source changes disclosure | Boundary/property fixtures for below/exact/above thresholds, contributor ties, empty/stale windows, and complementary cells |
| Frontend/generated-contract sync | Architecture §9/§27 | Backend narrows payload but stale generated types/UI still exposes or requests forbidden fields | Move all §9 baselines together, regenerate TypeScript, fail contract drift, rerun R14-B fixtures and role UI tests |
| Split/shared-source conservation | Considered; not applicable to S1–S5 | No money, quota allocation, or divisible evidence source is consumed in the runnable slices | Reassess when W3-00E/W3-01C become runnable; provenance link uniqueness still gets retry/concurrency tests |
| Public identity vs storage scope | Considered; not applicable to S1–S5 | No rendered sequential public number is introduced | UUID resource IDs remain tenant-scoped; reassess for issued measurement/report identifiers |
| Changed cross-package seam | §22.2, W3-00C; current Package 4 base | Existing heatmap is the sole sanctioned raw-ping reader; Package 5 must constrain it without changing upstream trip/impression/money facts | Focused heatmap producer/consumer tests only; verify no new raw-ping imports/queries and no mutation of Packages 1–4 data |

## Review factors and implementation rules

- Privacy and claims safety: outputs remain personal until approved
  re-identification evidence says otherwise; no anonymity claim is inferred
  from vehicle count.
- Legal truth: draft/provisional controls are visibly distinct from approved
  legal wording/owner/retention decisions.
- Default-deny live gate: production defaults leave advertiser and Module-G
  outputs disabled. Enabling requires a non-placeholder legal/privacy approval
  reference plus complete disclosure configuration and approved retention/
  query-history controls; a synthetic test-only setting may enable fixtures.
  The gate runs before query-history evaluation or any source/link mutation,
  adapter call, persistence, or response. Production-config tests prove every
  inventoried advertiser map/report/source/link read or mutation denies with no
  new rows while `EXT-LEGAL-PRIVACY` is missing. Threshold values alone can
  never open the gate.
- Data minimization: positive allowlists reject identifiers, free text, nested
  opaque metadata, routes, trips, precise timestamps, or driver/vehicle identity.
- Failure posture: absent legal/method/platform inputs disable live use; no
  fallback or placeholder approval.
- Scope control: no new persisted field, shared abstraction, or endpoint beyond
  the criterion requiring it; no Package 4 remediation.
- Verification economy: focused tests per slice; one relevant aggregate suite
  and live synthetic journey at the package integration gate; no repeated full
  suite by workers.

## Worker/model/concurrency budget

- All subagents use `fork_turns: "none"` and receive bounded packets only.
- Maximum two active workers; no duplicate discovery or reviews.
- One Terra independent plan reviewer now. Controller remains sole writer for
  S1 and all shared authority/migration/contract/control surfaces.
- Later bounded implementation may use at most one Terra worker with disjoint
  write ownership while one required read-only specialist reviews a different
  completed checkpoint. Luna is reserved for bounded inventory only. Sol/high
  requires a demonstrated new privacy/security/migration/concurrency decision.

## Approval provenance

The delegated owner packet explicitly authorizes Package 5 implementation from
the exact Package 4 checkpoint and directs work to proceed after the one plan
review without another owner approval, provided the reconciled plan stays
inside PKG-05 authority.

## Independent plan review

- Reviewer: clean-context Terra, no inherited conversation history, read-only.
- Initial verdict: FIX. Six findings required complete advertiser-output
  inventory coverage, a default-deny legal/live gate, atomic cross-endpoint
  differencing history, synthetic-only ROI clarification, precise source/link
  lifecycle concurrency and immutable history, and non-speculative migration
  handling.
- Reconciliation: all six corrections are incorporated above.
- Recheck verdict: PASS. No material scope or authority conflict remains.

## Integration evidence (25 Aug 2026)

- Package 4 repair head `2bc94356f03c76900585de71b6a0189be9e9666c`
  is an ancestor through merge commit `d52b0dd`; the post-adoption seam set
  passed 28 with 10 environment skips and the chain is 0044 → 0045 → 0046 →
  0047 with one head.
- W3-01B focused backend/API/contract checks passed. Five real-PostgreSQL
  checks passed against the local isolated-schema/throwaway-database harness:
  the 0045–0047 migration chain plus source/link retry and parent-lock races.
  Frontend link actions passed 2/2, typecheck and lint passed, and
  the production webpack build passed. The default Turbopack build cannot
  traverse this worktree's external `node_modules` symlink.
- Aggregate backend: 722 passed, 244 environment-only skips, two deprecation
  warnings. Aggregate frontend: 40 files / 212 tests passed. Progress validator,
  95 control/migration/measurement fixtures, Ruff and diff checks pass.
- The synthetic API/service lifecycle covers advertiser source creation,
  campaign/zone/time linkage, history/removal, tenant denial, active-admin
  monitoring and fail-closed production gates. No browser/live-stack linkage
  journey exists in the current suite; none is claimed.
- The single consolidated privacy/authorization/minimal-change review returned
  FIX for premature promotion, skipped PostgreSQL evidence and unrelated test
  formatting. Promotion was deferred, five real-PostgreSQL cases passed, the
  formatting hunk was removed, and the same reviewer rechecked PASS before the
  control-plane transition.
