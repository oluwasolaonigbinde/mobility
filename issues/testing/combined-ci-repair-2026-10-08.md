# Combined CI repair — 8 October 2026 (REQ-132)

Authority: owner integration instruction and subsequent “fix them”. Existing
`w2/renewals-phone`, parent `25dc7ef`; approved [contract](../planning/combined-ci-repair-2026-10-08.md).
Initial [run 37756230483](https://github.com/oluwasolaonigbinde/mobility/actions/runs/37756230483)
failed ten jobs. This receipt records local final-source evidence; full CI on
the new exact commit remains the condition for master acceptance. No deployment,
provider calls, local coverage, test skips/retries, weakened assertions or added
baseline entries. Original request closure list and worktree retention remain.

| Criterion | Local verdict | Actual evidence |
| --- | --- | --- |
| C1 | PASS | The unchanged `CI=true basedpyright` baseline lock passes with 0 errors/warnings/notes. Exactly four obsolete admin/contact entries removed, 384 remain; no additions or policy changes. |
| C2 | PASS | Billing unit 6/6, commercial action unit 6/6, methodology 6/6. Real production billing/change flows 10/10 on desktop/mobile, no mocks, retries or longer timeouts. Exact grouped two-decimal net/production/VAT/gross values, approval, role changes and reload receipt survive. Existing v1 fixture wording stays exact; only current v2 expectation changes. Existing browser assertions exposed a stale preparation summary after accepted quotation: `next/cache` refresh after a successful API receipt fixes it without changing acceptance authority or amounts. A focused red test observed refresh 0; final units prove success/receipt and validation/missing-receipt/API-error paths. |
| C3 | PASS | All 49 changed historical migration files have final passing verdicts on real disposable PostgreSQL databases: 114 distinct cases (111 initially passed; corrected 0019 whole-file 2/2 and 0082 whole-file 4/4 overlap those initial results). Every historical down/up, populated refusal, preservation and re-upgrade assertion remains. Current-head comparisons remain separate: 0019/R20/R22 follow-up 4/4; 0099 head autogeneration and deliberate drift pass. Extended 0100 case passes exact irreversible refusal with 0101 head, columns and complete challenge row unchanged. Inventory/denial follow-up 20/20 includes unchanged deliberate architecture drift detection; generated inventory now 315 operations/282 paths, 101 revisions/head0101. |
| C4 | PASS | Whole queue/lifecycle follow-up 18/18, retention 5/5, renewals 23/23; whole denial-matrix and architecture follow-up 20/20. Unknown directly named driver review returns404; existing incomplete/stale/foreign/purged authority remains denied. Fixtures perform real rejection then Profile renewal and assert supersession while retaining original files, saved bank details, ages, owners, cutoffs and read/audit assertions. Denial fixture enables the approved reverse-verification test number rather than obsolete outbound configuration; all404/no-mutation assertions retained. |
| C5 | PASS | All 68 payout cases have final passing verdicts: 67 initially passed plus corrected fairness case1/1 after distinct longitude3.45 (original BASE_LON3.40) eliminates legitimate route-replay exclusion. Real processing asserts zero fraud flags; scan cap/excluded prefix/exact later ledger remain. R20/R22 PostgreSQL guard/head checks pass. Real R59 journey1/1 passes outage, manifest, exactly-once and ledger assertions using Abuja GPS inside the seed polygon; timeouts/retries unchanged. |
| C6 | PASS | Linux preprod33/33 (including the real static CLI) and CSP8/8 including real browser allowed upload/hostile-origin blocking. Reused synthetic `production_model`, exact missing-value refusals, private ClamAV data+egress networks and configurable2workers. MapTiler exact connect/image origins only; templates/secrets and confinement unchanged. |
| C7 | PASS | Plan reviewer PASS including C2 refinement; money/privacy/security/deployment specialist PASS and the same consolidated minimal-change reviewer final PASS on all source and evidence, no findings. Scoped Ruff check/format63 Python paths, six frontend ESLint/Prettier paths and whitespace checks pass. Final locked Next16.4 production build/TypeScript passes. No schema/native baseline change. |

Local core execution initially reported92/100PASS; its eight failures have
final passing follow-ups: four renewal fixtures (whole files18PASS), R22 guard
(head follow-upPASS), and denial/inventory (whole files20PASS). Initial red
outputs are retained locally rather than represented as green single runs.
The historical0082 fixture does not insert the `write_protocol` column added
by0088; all original fence/tombstone/live-generation assertions remain.

Repeatable runs: Python3.12/pytest in `cv-w2c-tests` with dedicated synthetic
PostgreSQL test databases; Linux preprod/CSP runner with Docker; production
Compose API/frontend and Chromium/mobile Chrome for browser flows. The R59
launcher uses a fresh `cardvert-r59-*` project and exact-project teardown.
Local R59 receipt identified parent25dc7ef with the actual working-source leased
digest; full GitHub CI will bind the committed candidate. Ordinary billing
uses that fresh synthetic stack with its explicit database-container setting.
On Docker Desktop, the live CSP probe needed a runtime-only loopback relay to
its published port; source, browser assertions and waits were unchanged.
A host TypeScript probe found stale ignored `.next/dev` types from the older
installed Next; the final locked Linux production build/typecheck passes.
Raw local outputs: `.w2c/ci-repair-{core,fixtures,historical-head,money,preprod,csp,denial-inventory,0082}.xml`,
`.w2c/ci-repair-r59-final.log`, `.w2c/ci-repair-billing-refresh.log`.
No raw logs, coverage files, screenshots or transient runner files are committed.

## Historical revision map

Only functions exercising a historical cycle/guard use these revisions;
current-head-only catalog/model checks keep head.

| Test file | Historical revision |
| --- | --- |
| `test_migration_0014_partitioning.py` | `0014_location_pings_partitioning` |
| `test_migration_0019_assignment_rule_bindings.py` | `0019_assignment_rule_bindings` |
| `test_migration_0020_payout_correction_orders.py` | `0020_payout_correction_orders` |
| `test_migration_0021_frozen_payout_v3_terms.py` | `0021_frozen_payout_v3_terms` |
| `test_migration_0023_route_replay.py` | `0023_route_replay_signatures` |
| `test_migration_0024_fraud_review_holds.py` | `0024_fraud_review_holds` |
| `test_migration_0025_fraud_disputes_notifications.py` | `0025_fraud_disputes_notifications` |
| `test_migration_0026_frozen_campaign_payment_window.py` | `0026_frozen_campaign_payment_window` |
| `test_migration_0027_earnings_release_sla.py` | `0027_earnings_release_sla` |
| `test_migration_0028_protected_payee_accounts.py` | `0028_protected_payee_accounts` |
| `test_migration_0029_payout_batch_reservation.py` | `0029_payout_batch_reservation` |
| `test_migration_0030_provider_line_reconciliation.py` | `0030_provider_line_reconciliation` |
| `test_migration_0031_carry_forward_payout_debt.py` | `0031_carry_forward_payout_debt` |
| `test_migration_0032_commercial_quotation_terms.py` | `0032_commercial_quotation_terms` |
| `test_migration_0033_advertiser_company_profiles.py` | `0033_advertiser_company_profiles` |
| `test_migration_0034_canonical_receipts_allocations.py` | `0034_canonical_receipts_allocations` |
| `test_migration_0035_vat_itemised_invoices.py` | `0035_vat_itemised_invoices` |
| `test_migration_0036_invoice_authority_hardening.py` | `0036_invoice_authority_hardening` |
| `test_migration_0037_funded_liability_authority.py` | `0037_funded_liability_authority` |
| `test_migration_0038_payment_gateway_events.py` | `0038_payment_gateway_events` |
| `test_migration_0039_billing_corrections_refunds.py` | `0039_billing_corrections_refunds` |
| `test_migration_0041_invoice_correction_retry_identity.py` | `0041_invoice_correction_retry_identity` |
| `test_migration_0042_invoice_number_prefix_sequence.py` | `0042_invoice_number_prefix_sequence` |
| `test_migration_0043_campaign_review_lifecycle.py` | `0043_campaign_review_lifecycle` |
| `test_migration_0044_notification_outbox.py` | `0044_notification_outbox` |
| `test_migration_0045_disclosure_query_history.py` | `0045_disclosure_query_history` |
| `test_migration_0046_retargeting_sources.py` | `0046_retargeting_sources` |
| `test_migration_0047_retargeting_source_links.py` | `0047_retargeting_source_links` |
| `test_migration_0049_assignment_activity_flags.py` | `0049_assignment_activity_flags` |
| `test_migration_0050_driver_applications.py` | `0050_driver_applications` |
| `test_migration_0056_creative_review.py` | `0056_creative_review` |
| `test_migration_0057_installation_evidence.py` | `0057_installation_evidence` |
| `test_migration_0058_campaign_changes.py` | `0058_campaign_changes` |
| `test_migration_0059_campaign_cancellations.py` | `0059_campaign_cancellations` |
| `test_migration_0060_evidence_verifications.py` | `0060_evidence_verifications` |
| `test_migration_0061_email_delivery.py` | `0061_email_delivery` |
| `test_migration_0062_data_subject_requests.py` | `0062_data_subject_requests` |
| `test_migration_0063_measurement_runs.py` | `0063_measurement_runs` |
| `test_migration_0064_budget_notifications_recovery.py` | `0064_budget_notifications_recovery` |
| `test_migration_0066_audience_deliveries.py` | `0066_audience_deliveries` |
| `test_migration_0067_exposure_scores.py` | `0067_exposure_scores` |
| `test_migration_0068_driver_person_payee_review.py` | `0068_driver_person_payee_review` |
| `test_migration_0069_w3_04b_review_authority.py` | `0069_w3_04b_review_authority` |
| `test_migration_0070_driver_vehicle_approval.py` | `0070_driver_vehicle_approval` |
| `test_migration_0071_report_issuances.py` | `0071_report_issuances` |
| `test_migration_0075_governed_audience_delivery.py` | `0075_governed_audience_delivery` |
| `test_migration_0077_stored_object_deletions.py` | `0077_stored_object_deletions` |
| `test_migration_0082_report_publication_intents.py` | `0082_report_publication_intents` |
| `test_migration_0099_automatic_payout_scan_cursor.py` | `0099_automatic_payout_scan_cursor` |
| `test_kyc_retention_authority.py` historical guard | `0087_kyc_payload_retention` |
| `test_r20_disbursement_postgresql.py` historical guard | `0083_payout_submission_intents` |
| `test_r22_conservation_postgresql.py` historical guard | `0084_payout_conservation` |

Migration0100's irreversible replacement is unchanged. No containing commit
SHA is embedded in this receipt.

## Static CLI follow-up

[Run37767080248](https://github.com/oluwasolaonigbinde/mobility/actions/runs/37767080248)
on `f4261af4` passed all six backend test shards, frontend lint/types/unit/contract/build,
the full ordinary browser suite and R59. Its backend aggregate failed because
static verification failed; no aggregate coverage PASS is claimed. Its static
CLI reached Compose's required-value refusal
because W1B intentionally left template secrets blank; the earlier test-helper
correction did not cover the script's own render command. The regression
reproduced missing signing/database/storage values in the actual CLI.
Nine synthetic overrides now apply only to production `compose config`;
development render, shell syntax, Caddy validation, default test command,
production templates and release preflight are unchanged. No export, deployment,
provider action or live default was introduced. The entire touched preprod file
passes33/33 on Linux, including the unmocked `--static-only` invocation and
unchanged required-value refusals. Scoped Ruff check/format and whitespace pass.
Shell CRLF from Windows was normalized in the disposable Linux checkout only.
Raw final evidence: `.w2c/ci-repair-static-preprod.xml`.
The plan refinement, deployment supplement and same consolidated minimal-change
reviewer are PASS on this bounded follow-up, with no findings. Full exact-SHA
CI remains the condition for master acceptance.

## Notification fixture follow-up

[Run37769620815](https://github.com/oluwasolaonigbinde/mobility/actions/runs/37769620815)
on `c43d43c8` passed static verification, frontend checks/build, both real-browser
jobs and five backend shards. Shard1 failed only the driver notification
context test: its `items[0]` selection sometimes chose the legitimate trip
notice when SQLite creation timestamps tied and UUIDs determined feed order.
The existing resolver already rejects contradictory assignment references.
The backend aggregate therefore failed and changed-code coverage did not run.

C4's follow-up inserts immutable notification fixtures with fixed timestamps
and tests both possible feed orders. The existing helper keeps its original
fraud-notice defaults, deriving fingerprints from the selected type/payload.
A deterministic red run retained `items[0]`: legitimate-first failed with
Launch Campaign, while the other30 cases passed. Final selection uses the exact
conflict ID; both feed and successful mark-read responses retain name/link
denials, while the legitimate trip link and foreign-assignment denials remain.
No production source or evidence guard changed. The whole touched file passes
31/31, including the existing creator replay/frozen-evidence test. Scoped Ruff
check/format and whitespace checks pass; no retries, skips or baseline entries
were added. Raw evidence stays local in `.w2c/ci-repair-notifications.xml`.
The plan refinement, privacy/security supplement and same consolidated
minimal-change reviewer are PASS on this final source/evidence, with no findings. Other C1-C6
verdicts and their prior reviews remain unchanged. Full exact-SHA CI remains
the condition for master acceptance.

## Exact CI Python runtime follow-up — REQ-134

[Run37772626527](https://github.com/oluwasolaonigbinde/mobility/actions/runs/37772626527)
on `1ebca813` passed all six backend shards, static checks, frontend
lint/types/unit/contract/build, ordinary real-stack browsers and R59. The
backend aggregate failed with `pytest shard error: shard 2 runtime differs`;
coverage aggregation and changed-code coverage PASS are not claimed. Downloaded
producer manifests show shards0/1 used Python3.12.14, while shards2/3/4/5
used3.12.15. All used CPython3.12 and coverage7.16.0. The exact provenance
guard correctly rejected mixed interpreter patch versions.

The owner explicitly extended scope to pin3.12.14 everywhere CI sets up
Python, including composite actions, and requested the next free request.
REQ-133 is reserved for the unrelated uncommitted demo-start row; this is
REQ-134. The complete .github YAML inventory has exactly four setup-python
selectors (static, shards, aggregate and changed-code coverage), all in ci.yml;
no composite action sets up Python. Pre-change YAML assertion failed because
all four selectors were floating3.12. Final YAML parsing finds all four exactly
3.12.14. A host-side byte comparison proves these four literal replacements
are the workflow's only changes. Exact shard/aggregate runtime comparison,
coverage policies, retries and tests remain unchanged. Whitespace passes.
No local coverage or additional pytest suite was run for these literal edits.

C7's revised plan review, deployment/provenance supplement and the same
consolidated minimal-change reviewer are PASS on this source/evidence, with no findings. Full
exact-SHA CI must provide matching producer/downstream runtime and complete
coverage evidence before master integration. REQ-134 will close with its own
implementing SHA in the original single closing documentation commit.

## Pydantic CI-alignment source checkpoint — REQ-132/136, 10 October

The approved, independently plan-reviewed A1 amendment pins only pyproject's
Pydantic requirement to 2.13.4, matching the unchanged production input/hash
lock (core 2.46.4). Exact failed-Q evidence and controlled substitutions isolate
114 removed Decimal patterns across 31 schemas under 2.14.0; historical passing
CI application versions remain unknown. Prior production-schema and mixed-CI
counterexperiments each established one generation plus HTTP equality, not three.
No FastAPI/Starlette pin, application/schema change or baseline refresh is made.

Bounded local verification uses the existing test container's Python 3.12.14
with isolated public packages in container Temp: FastAPI 0.143.0, Starlette 1.7.0,
Pydantic 2.13.4/core 2.46.4, settings 2.15.0, pytest 8.4.2 and coverage 7.16.0
(no coverage invocation). Inherited configuration is cleared, cwd is external
Temp, and sockets are blocked before app import. No repository .env is loaded.
All four existing `tests/test_openapi.py` cases pass with real TestClient,
including the runtime error envelope and absence of rejected-input echo. One
existing payout malformed-data case and seven existing config secret-validation/
credential-redaction cases also pass: 12 total, no skips, one upstream TestClient
httpx deprecation warning. Sixteen probes against the actual payout-v4 and
audience-approval models preserve valid/scientific-notation Decimal serialization
and malformed, scale, precision, negative, over-bound and non-finite refusals.
These are bounded dependency evidence, not complete financial-workflow equivalence;
the existing patterns' scientific-notation limitation is not fixed by this pin.

The unchanged snapshot generator `--check` passes. Two separate fresh Python
processes regenerate both JSONs into Temp with exact tracked-byte equality:
SHA256 `7f1db411dbbd79acfc403be537f7ac18be6d1eaa2b6bd2d9b8c0702ede78ab4d`.
Temp openapi-typescript 7.13.0 generation is also byte-equal to tracked types:
`a36a221f17e8de40755042b96914cb355f6a296512dd5aeb6b71897723dab636`.
All three §9 baselines stay unchanged. The native baseline-change rerun trigger
is not exercised; exact final CI still owns native fixtures, E2E and R59.
No physical-device claim is made.

`pip check` passes; every project/dev requirement accepts the selected versions,
and the public-package resolver dry-run accepts that installed selection.
Settings 2.15.0 requires Pydantic >=2.7.0. This is not a claim that all transitive
packages equal CI or that a clean complete CI environment was rebuilt. Public
PyPI version records and OSV queries on 10 October return no known advisories for
Pydantic 2.13.4, core 2.46.4 and settings 2.15.0; this is point-in-time evidence,
not proof of absolute safety. Production hashes and the full CI pip-audit gate
remain unchanged, without suppressions. Python pins, coverage options, checker,
eligibility and instrumentation are unchanged; the intentional pyproject policy
content change must naturally enter new-Q receipt hashes.

O1 scope/authority, O2 causal parity, O3 bounded behavior and O4 unchanged
baselines have local source evidence. O5 dependency/provenance evidence and the
required money/security and consolidated source-review outcomes are retained in
external Temp `mobility-pydantic-implementation-20261010`, with exact commands,
XML, model results, public advisory responses, source hashes and O1-O6 matrix.
No review here substitutes for final integrated A6. The testing receipt is
written once after local verification stabilizes and contains no containing SHA.
Both permitted containers are restored to their original stopped state; owner
untracked directories are untouched. Whitespace/TOML checks pass. No full local
suite/coverage, Git publication, account/provider action or deployment occurred.

O6, A3-A5 and final integrated A6 remain pending: fresh new-Q six-shard backend
aggregate/provenance and frontend LCOV; full fixed-M 90% changed lines/80% branches
at Q and R; exact trusted global/backend/frontend/named floors; unchanged checker
canonical LF Q-anchored receipt; normal R-versus-Q provenance; every exact-R full
CI job and final integrated reviews. Failed Q has no complete backend aggregate;
asserted-but-zero LCOV remains unresolved. No old-report reuse, hash patch,
collector fix, coverage-gain claim, waiver or master-readiness claim is made.
