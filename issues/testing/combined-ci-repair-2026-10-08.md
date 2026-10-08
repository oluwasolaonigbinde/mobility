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
