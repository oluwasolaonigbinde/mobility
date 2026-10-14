# Waves 3 and 4: preparation and delivery boundary

Owner authorization: 13 October 2026, current worktree and
`w3/cleanup-refactor-ops`. Initial fetch succeeded; HEAD and origin/master
both equal `870740531a8625b9350b030fe05107276e0f345a`. Working tree was clean.
Scope source: only Wave 3, Wave 4 and the must-not-forget list in the owner's
5 October batch plan, amended by the current instructions.

## Request mapping

Plan REQ-115/116/117/118/119 map by subject to newly registered
REQ-161/162/163/164/165. Existing rows with the old numbers concern different
work and remain intact. REQ-166 covers obsolete hosting files, REQ-168 the
integrated delivery. Report wording and demo phones already map to
REQ-141/145; the shared bank picker remains REQ-159. REQ-167 records the
owner's answered squash question; REQ-169 records its implementation.
W3a allocates D80, architecture v1.135 and migration 0103. Later waves and the squash allocate fresh numbers in their own commits.

## Proposed contract and order

1. W3a: remove old payout engines and evidence-v1 runtime paths and consumers;
   retain v4 daily-rate/correction/financial integrity and exact signed v2
   evidence. Remove SQLite application branches and use PostgreSQL tests.
   Record the live-data-only accepted-work preservation decision; there is
   no live data. Update the three API baselines and R14-B fixtures together
   when contracts change. Retain meaningful financial and evidence regressions
   when replacing old fixtures.
2. W3b: split payout and billing services by domain, update actual callers,
   refactor measured hotspots, and replace application file-wide C901 ignores
   with exceptions on existing offenders. Preserve the shared bank picker.
   Ping ingestion uses a shared campaign lock in campaign-before-trip order;
   cancellation and terms mutation retain exclusive authority. Deterministic
   PostgreSQL tests must cover different-trip readers, same-trip serialization,
   waiting writers and both cancellation/ingestion orderings without upgrades.
3. Coverage: require 85% branches separately for the combined money group and
   the combined privacy group (not 85% per individual file). Money includes
   `services/payouts/`, `services/billing/`, `payout_corrections.py`,
   `payout_debt.py`, `payout_eligibility.py`, `payout_operations.py`,
   `payout_rule_serialization.py`, `automatic_payouts.py`, `disbursements.py`,
   `paystack_disbursements.py`, `earnings_release.py`, `payees.py`,
   `campaign_cancellations.py`, and all Python modules under
   `adapters/payments/`, `adapters/disbursement/`, `adapters/budget/`.
   Privacy includes `services/disclosure.py`, `data_subject_inventory.py`,
   `data_subject_requests.py`, `data_lifecycle.py`, `file_kyc_lifecycle.py`,
   `stored_files.py`, `stored_object_deletions.py`, `kyc.py`,
   `core/observability.py` and `adapters/crypto/`. Paths are beneath `app/`.
   The checker enumerates tracked source under these directories; absent
   expected modules and missing executable coverage fail closed. Empty package
   files contribute no executable branches. Preserve existing D32/D36/D41
   ratchets and frontend eligibility; optional narrowing is declined because
   frontend account, evidence, authorization and queue logic is consequential.
   Add unconditional deterministic tests for the reservation refusal and trip
   rejection path identified in prior CI. No local coverage measurement.
4. W4: monitor every scheduled job using Sentry Cron check-ins; add the
   five-minute seven-condition business-health sweep and runbook. Use the
   concrete operational predicates below, active-admin notifications and the
   existing Finance alert surface. No local external delivery/provider calls.
5. Trim: inventory every proposed deletion, preserve validator-consumed
   progress state and meaningful behavioral tests, archive completed history,
   delete proven unused scripts and replaced Render/AWS/Mapbox assets.
   REQ-049 is already on master. Keep Hetzner's S3-compatible integration.
6. Squash LAST in a separate commit, as explicitly approved by the owner
   ("squash yes"). First upgrade a clean PostgreSQL database through the
   completed W3/W4 chain and dump its full schema. Compare a fresh upgrade
   from the single baseline using the same dump procedure: identical except
   alembic_version value. Preserve tables, types, defaults, constraints,
   indexes, sequences, enums, functions/triggers, partitions and management
   objects, extensions, grants and RLS. Preserve bootstrap data too, including
   0093's disabled automatic-payout actor and matching fingerprint. Retain
   current DB-behavior tests in baseline-focused tests before deleting old
   per-migration tests. Exactly one head/root, update operational revision
   references, and run the existing demo seed once. Security/privacy review
   explicitly verifies no protection was lost.
7. Only touched tests locally, at most two test containers; no changes to the
   port-3100 demo, account-access document or tmp. Sequential reviewable commits
   under configured identity, explicit path staging and normal hooks. Named
   money/privacy/security reviews plus consolidated minimal-change PASS on the
   final implementation; final full CI covers squash and D79 agreement/bank
   integration. Nontrivial agreement/bank defects are reported; small fixes get
   their own REQ-158/159 commit. Merge only green without squashing, then close
   requests; preserve both request sets if newer master must be merged.

## Alert predicates and verification

Operational defaults are monitoring sensitivity, not client money, eligibility,
retention or GPS acceptance rules. Each query uses an injected UTC clock and
bounded/indexed counts; the sweep never mutates payments or trip authority.

| Check | Unhealthy predicate |
| --- | --- |
| Stuck payouts | Nonterminal submitted/submitting payout lines or unresolved submission intents older than 60 minutes; use latest durable progress timestamp where present. |
| Unprocessed webhooks | Unprocessed payment or payout provider events older than 15 minutes, including failed retryable events. |
| Paused payouts | Control is paused and its recorded changed_at is strictly older than 24 hours. |
| GPS rejection spike | At least 20 authenticated ingestion attempts during the preceding 15 complete UTC minutes, with at least 25% wholly or partially rejected for GPS validation. |
| Stale trips | Active trips with no accepted ping/start activity for 30 minutes, or ended unsealed trips past the configured evidence grace whose evidence_adjudicated_at is null. Terminally adjudicated incomplete trips are settled evidence outcomes, never stale. |
| Partitions | Existing partition-coverage service reports less than its required now-plus-one-month coverage. |
| Email failures | Terminal failed deliveries in the last 24 hours or pending deliveries older than 15 minutes. |

GPS metrics use aggregate minute counters with a one-hour TTL in the existing
Redis substrate, recorded independently from the ingestion transaction so an
all-rejected batch remains observable. Store no driver, trip, IP, coordinates,
payload or free text. Count attempts (including rejected retries), not unique
trips. Partial and full GPS rejection use the same denominator; idempotent
successful retries do not create new evidence. Counter failure is logged safely,
does not change ingestion authority, and the sweep must report unavailable
telemetry rather than a healthy GPS result. Test with fake Redis; real PostgreSQL
tests cover durable predicates and concurrent deduplication.

Extend the existing Finance alert kind with a business-health kind and allowlist
the check key/count in detail. On counter-write failure, the same daily Finance
item also retains an identifier-free `counter_incomplete_until` UTC time;
concurrent failures extend it under the alert row lock, through the failed
minute leaving the 15-complete-minute window. This operational failure evidence
is retained with the manually resolved alert, not with the expiring Redis
counters. The sweep reads it across workers/restarts and UTC midnight even
after manual resolution. Counter and failure-signal writes have separate
one-second limits and never change ingestion authority; simultaneous Redis/DB
failure produces a distinct safe log event and cannot durably record a signal.
Reuse `raise_alert` and `create_active_admin_notices`:
all active admins are Finance recipients under D38e/REQ-030 (no separate roles).
One alert/notification per unhealthy check per UTC date, transactionally deduped.
Persistent failures may recur on the next date; recovery emits no new alert and
never silently resolves a human-owned Finance item. Finance explicitly follows
up existing items. Boundary, healthy, unhealthy, repeat and missing-telemetry
tests are required; Cron tests cover success, exception and cancellation without
external calls. Sentry telemetry contains only stable monitor slug/status.
Stale-trip tests must prove overdue unresolved evidence alerts and terminally
adjudicated trips do not, including on the next UTC date; existing Finance items
remain manually resolved.

## Independent plan review and reconciled findings

Reviewer: `codex-fresh-20261012`, `gpt-6.1-sol`, high reasoning, priority.
Task: `node:delegated-task:command%3Amcp%3Ab10cc452-1217-49d9-b8c0-380e2a77edda%3Adelegate-task%3Aw34-plan-review-20261013-r1`.
Verdict: FIX. Accepted findings: preserve bootstrap data and migration-defined
protections; require concrete alert predicates, lock interleavings and explicit
85% scope; incorporate the approved squash parity requirements. Those details
must be completed and reviewed before implementation, not claimed passed here.

The original blocking finding was procedural: `check_changed_coverage.py:839` rejects
changed inventory/policy without D33 refresh. Final CI measurement produces
the input to the reviewed receipt; committing that receipt creates a different
candidate that D41 requires full CI to verify. Exactly one run cannot satisfy
both. The orchestrator continuation now directs two end-of-batch runs under
REQ-170: final-source measurement, independently reviewed canonical D33 receipt
commit, full verification of that commit, then green-only non-squash merge.
No per-wave CI, waiver, CI-generated receipt or local measurement is assumed.
The owner approved this sequence on 13 October, as relayed by the orchestrator.
The measurement and reviewed receipt also cover REQ-158/159 changed code;
any additional agreement/bank tests have their own labelled commit. Their
previous coverage-policy-only CI failure is superseded by final green batch CI. A fresh
independent plan review must return PASS before application changes.

Round 3 (`w34-plan-review-20261013-r3`) returned independent **PASS** on the
complete revised plan, including the terminal-adjudication exclusion. Existing
owner implementation approval covers this unchanged scope; implementation may
proceed. This plan verdict does not claim implementation or final-review PASS.

Round 2 (`w34-plan-review-20261013-r2`) accepted the prior refinements and
returned FIX only for terminally adjudicated trips being included in the
stale-trip predicate. Accepted and corrected above; round 3 reassessment returned PASS.

## Actual preparation evidence

- Master run 38390542839 completed: all six backend shards, e2e, R59, static checks and frontend lint/types/unit/contract/build passed; only changed-code coverage policy failed. Runs 38390436639 and 38390315083 also concluded failure. The orchestrator confirms the repair run was coverage-policy-only; the owner-approved batch D33 refresh/final verification supersedes that failure. Master run:
  https://github.com/oluwasolaonigbinde/mobility/actions/runs/38390542839.
- Radon 6.0.1, `radon cc app -a`: 3,299 blocks; mean complexity
  3.7356774780236437 (A). Raw pre-change JSON is ignored local evidence at
  `coverage/w34/radon-before.json`. No after measurement yet. jscpd 4.0.8 on a pristine HEAD archive, `app frontend/src --ignore "**/*.test.*,**/schema.d.ts" --format python,typescript,tsx`: 788 sources, 110,697 lines, 245 clones, 2,861 duplicated lines (2.58%), 30,683 duplicated tokens (2.86%). Raw report: ignored `coverage/w34/jscpd-pristine-before/jscpd-report.json`.
- W3a implementation is in progress. Schema parity, seed run, commits, push and merge remain outstanding. Squash: approved, not done. Deletions are listed below.
- Two isolated containers are retained during the task and their removal at
  completion is now explicitly authorized: `cardvert-w34-postgres` (localhost
  55434) and `cardvert-w34-runner`. Existing containers/demo remain untouched.

## Deleted inventory

Obsolete hourly/distance rule editors and their dedicated test (daily-rate editor retained):
- `frontend/src/app/admin/payouts/rules/rule-form.tsx`
- `frontend/src/app/admin/payouts/rules/revisions-panel.tsx`
- `frontend/src/app/admin/payouts/rules/revisions-panel.test.tsx`

Retired payout engine suites (current acceptance, correction, daily-cap ordering and API boundaries transferred to daily-rate tests):
- `tests/test_payouts_v2.py`
- `tests/test_payouts_v3.py`

W3a fresh database `w34_validate`: complete chain to 0103 upgraded successfully and `alembic check` reported no new upgrade operations. This is migration/model alignment evidence, not the final squash parity comparison.

W3a checkpoint (14 October): legacy runtime/schema/API/editor removal and
PostgreSQL fixture conversion are implemented. Ruff and diff whitespace pass;
API snapshots and TypeScript schema regenerated. The focused daily payout, debt,
frozen acceptance, publication, ordering and API batch passed 67 tests. Four
payout UI files passed 14 tests. Additional worker/trip/privacy/seed verification
is still running after fixture corrections; this is not final verification or
review acceptance. No coverage measurement, branch CI, push or merge has run.

W3b planned source-file replacements (functions move into domain packages):
- `app/services/payouts.py`
- `app/services/billing.py`

W3b checkpoint (14 October): payout and billing domain packages replace the
monoliths; application C901 exceptions are per-function. Shared-reader and
exclusive-cancellation interleavings pass, including different and same trips.
The 37 coverage-policy tests pass without measuring local coverage. The focused
refinement batch passed seven checks, and its remaining exact-millisecond
fixture correction passed separately. Evidence UI: 100/100 tests across the
three touched actions/tracker/queue files. Fresh database upgraded to 0104;
Alembic reports no model differences. Ruff and formatting pass. Final integrated
CI and reviews remain required. The evidence-v1 follow-up removes driver legacy
end/ACK branches and unused trip watermark columns; signed v2 recovery and
encrypted queue ownership protection remain.

W4 deletion inventory before editing: the prose-only
`tests/test_privacy_operating_model.py::test_operating_model_and_tabletop_preserve_external_gates`
and its two unused Markdown path constants. Machine-readable privacy-register
validation is retained. In `tests/test_r59_real_stack_contract.py`, remove only
README/rehearsal prose assertions; retain executable workflow/config assertions.
Render/AWS/Mapbox tracked deployment assets are already absent following
REQ-049 (`308f04a8`); no container or S3-compatible integration is removed.

W4 script inventory: every operational script has a tracked caller, workflow or
runbook reference. `check_frontend_audit.test.mjs` is a discovered Node test, not
an unused operational script; retain it. No unused script was proven, so none
was deleted. Validator-required progress cards/rows remain intact; completed
owner history moved to `docs/archive/progress-history-2026-10.md`.

W4 checkpoint: all 16 new business-health tests pass across the initial and
focused corrective runs. The 13-test API/prose-trim follow-up passed; terminal
email timestamp verification passed. Finance copy passed 5 UI tests. Ruff,
formatting and the progress validator pass. Migration 0105 upgraded successfully
and `alembic check` reports no new operations. D82 / architecture v1.137 record
monitoring and Finance escalation. No external monitoring/provider call ran.
The next step is the separately approved squash, starting with a fresh complete
chain upgrade and full schema dump; parity and specialist acceptance are not
yet claimed.

## Approved squash deletion inventory (before deletion)

The following chain/test files are replaced by the single baseline and current
schema/behavior verification. Required helpers and current protection tests
are transferred before deletion.

- `alembic/versions/0001_enable_extensions.py`
- `alembic/versions/0002_identity_and_organizations.py`
- `alembic/versions/0003_driver_vehicle_foundations.py`
- `alembic/versions/0004_campaigns_and_creatives.py`
- `alembic/versions/0005_campaign_zones.py`
- `alembic/versions/0006_campaign_assignments.py`
- `alembic/versions/0007_trip_tracking.py`
- `alembic/versions/0008_route_analytics_and_fraud_flags.py`
- `alembic/versions/0009_impression_estimation.py`
- `alembic/versions/0010_payouts_and_earnings.py`
- `alembic/versions/0011_user_password_management.py`
- `alembic/versions/0012_audit_event_indexes.py`
- `alembic/versions/0013_payout_v2_hourly_caps.py`
- `alembic/versions/0014_location_pings_partitioning.py`
- `alembic/versions/0015_payout_day_allocation.py`
- `alembic/versions/0016_trip_seal_protocol.py`
- `alembic/versions/0017_seal_review_hardening.py`
- `alembic/versions/0018_payout_rule_revisions.py`
- `alembic/versions/0019_assignment_rule_bindings.py`
- `alembic/versions/0020_payout_correction_orders.py`
- `alembic/versions/0021_frozen_payout_v3_terms.py`
- `alembic/versions/0022_current_fraud_assessments.py`
- `alembic/versions/0023_route_replay_signatures.py`
- `alembic/versions/0024_fraud_review_holds.py`
- `alembic/versions/0025_fraud_disputes_notifications.py`
- `alembic/versions/0026_frozen_campaign_payment_window.py`
- `alembic/versions/0027_earnings_release_sla.py`
- `alembic/versions/0028_protected_payee_accounts.py`
- `alembic/versions/0029_payout_batch_reservation.py`
- `alembic/versions/0030_provider_line_reconciliation.py`
- `alembic/versions/0031_carry_forward_payout_debt.py`
- `alembic/versions/0032_commercial_quotation_terms.py`
- `alembic/versions/0033_advertiser_company_profiles.py`
- `alembic/versions/0034_canonical_receipts_allocations.py`
- `alembic/versions/0035_vat_itemised_invoices.py`
- `alembic/versions/0036_invoice_authority_hardening.py`
- `alembic/versions/0037_funded_liability_authority.py`
- `alembic/versions/0038_payment_gateway_events.py`
- `alembic/versions/0039_billing_corrections_refunds.py`
- `alembic/versions/0040_budget_policy_blocked_state.py`
- `alembic/versions/0041_invoice_correction_retry_identity.py`
- `alembic/versions/0042_invoice_number_prefix_sequence.py`
- `alembic/versions/0043_campaign_review_lifecycle.py`
- `alembic/versions/0044_notification_outbox.py`
- `alembic/versions/0045_disclosure_query_history.py`
- `alembic/versions/0046_retargeting_sources.py`
- `alembic/versions/0047_retargeting_source_links.py`
- `alembic/versions/0048_campaign_assignment_offer_lifecycle.py`
- `alembic/versions/0049_assignment_activity_flags.py`
- `alembic/versions/0050_driver_applications.py`
- `alembic/versions/0051_canonical_impression_authority.py`
- `alembic/versions/0052_stored_files.py`
- `alembic/versions/0053_file_scanning.py`
- `alembic/versions/0054_managed_creatives.py`
- `alembic/versions/0055_kyc_key_custody.py`
- `alembic/versions/0056_creative_review.py`
- `alembic/versions/0057_installation_evidence.py`
- `alembic/versions/0058_campaign_changes.py`
- `alembic/versions/0059_campaign_cancellations.py`
- `alembic/versions/0060_evidence_verifications.py`
- `alembic/versions/0061_email_delivery.py`
- `alembic/versions/0062_data_subject_requests.py`
- `alembic/versions/0063_measurement_runs.py`
- `alembic/versions/0064_budget_notifications_recovery.py`
- `alembic/versions/0065_exposure_segments.py`
- `alembic/versions/0066_audience_deliveries.py`
- `alembic/versions/0067_exposure_scores.py`
- `alembic/versions/0068_driver_person_payee_review.py`
- `alembic/versions/0069_w3_04b_review_authority.py`
- `alembic/versions/0070_driver_vehicle_approval.py`
- `alembic/versions/0071_report_issuances.py`
- `alembic/versions/0072_driver_application_terminal_status.py`
- `alembic/versions/0073_refund_cancellation_provenance.py`
- `alembic/versions/0074_trip_evidence_manifest.py`
- `alembic/versions/0075_governed_audience_delivery.py`
- `alembic/versions/0076_dsr_assessment_truth.py`
- `alembic/versions/0077_stored_object_deletions.py`
- `alembic/versions/0078_campaign_assignment_driver_active.py`
- `alembic/versions/0079_traffic_density_profile_revisions.py`
- `alembic/versions/0080_trip_evidence_partial_disposition.py`
- `alembic/versions/0081_payout_money_authority.py`
- `alembic/versions/0082_report_publication_intents.py`
- `alembic/versions/0083_payout_submission_intents.py`
- `alembic/versions/0084_payout_conservation.py`
- `alembic/versions/0085_disclosure_protection_retention.py`
- `alembic/versions/0086_audit_subjects.py`
- `alembic/versions/0087_kyc_payload_retention.py`
- `alembic/versions/0088_report_publication_writes.py`
- `alembic/versions/0089_driver_account_setup.py`
- `alembic/versions/0090_single_active_advertiser_membership.py`
- `alembic/versions/0091_budget_urgent_threshold.py`
- `alembic/versions/0092_payout_v4_daily_rate.py`
- `alembic/versions/0093_automatic_payout_approval.py`
- `alembic/versions/0094_customer_service_complaints.py`
- `alembic/versions/0095_invoice_issuer_contact_and_bank.py`
- `alembic/versions/0096_payment_checkout_intents.py`
- `alembic/versions/0097_payout_provider_event_queue.py`
- `alembic/versions/0098_paystack_edge_case_evidence.py`
- `alembic/versions/0099_automatic_payout_scan_cursor.py`
- `alembic/versions/0100_reverse_phone_verification.py`
- `alembic/versions/0101_document_review_outcomes.py`
- `alembic/versions/0102_driver_agreement_acceptance.py`
- `alembic/versions/0103_retire_legacy_engines.py`
- `alembic/versions/0104_retire_v1_trip_watermarks.py`
- `alembic/versions/0105_business_health.py`
- `tests/test_migration_0013_payout_v2.py`
- `tests/test_migration_0014_partitioning.py`
- `tests/test_migration_0017_seal_hardening.py`
- `tests/test_migration_0018_payout_rule_revisions.py`
- `tests/test_migration_0019_assignment_rule_bindings.py`
- `tests/test_migration_0020_payout_correction_orders.py`
- `tests/test_migration_0021_frozen_payout_v3_terms.py`
- `tests/test_migration_0023_route_replay.py`
- `tests/test_migration_0024_fraud_review_holds.py`
- `tests/test_migration_0025_fraud_disputes_notifications.py`
- `tests/test_migration_0026_frozen_campaign_payment_window.py`
- `tests/test_migration_0027_earnings_release_sla.py`
- `tests/test_migration_0028_protected_payee_accounts.py`
- `tests/test_migration_0029_payout_batch_reservation.py`
- `tests/test_migration_0030_provider_line_reconciliation.py`
- `tests/test_migration_0031_carry_forward_payout_debt.py`
- `tests/test_migration_0032_commercial_quotation_terms.py`
- `tests/test_migration_0033_advertiser_company_profiles.py`
- `tests/test_migration_0034_canonical_receipts_allocations.py`
- `tests/test_migration_0035_vat_itemised_invoices.py`
- `tests/test_migration_0036_invoice_authority_hardening.py`
- `tests/test_migration_0037_funded_liability_authority.py`
- `tests/test_migration_0038_payment_gateway_events.py`
- `tests/test_migration_0039_billing_corrections_refunds.py`
- `tests/test_migration_0040_budget_policy_blocked_state.py`
- `tests/test_migration_0041_invoice_correction_retry_identity.py`
- `tests/test_migration_0042_invoice_number_prefix_sequence.py`
- `tests/test_migration_0043_campaign_review_lifecycle.py`
- `tests/test_migration_0044_notification_outbox.py`
- `tests/test_migration_0045_disclosure_query_history.py`
- `tests/test_migration_0046_retargeting_sources.py`
- `tests/test_migration_0047_retargeting_source_links.py`
- `tests/test_migration_0048_campaign_assignment_offer_lifecycle.py`
- `tests/test_migration_0049_assignment_activity_flags.py`
- `tests/test_migration_0050_driver_applications.py`
- `tests/test_migration_0051_canonical_impression_authority.py`
- `tests/test_migration_0052_stored_files.py`
- `tests/test_migration_0053_file_scanning.py`
- `tests/test_migration_0054_managed_creatives.py`
- `tests/test_migration_0055_kyc_key_custody.py`
- `tests/test_migration_0056_creative_review.py`
- `tests/test_migration_0057_installation_evidence.py`
- `tests/test_migration_0058_campaign_changes.py`
- `tests/test_migration_0059_campaign_cancellations.py`
- `tests/test_migration_0060_evidence_verifications.py`
- `tests/test_migration_0061_email_delivery.py`
- `tests/test_migration_0062_data_subject_requests.py`
- `tests/test_migration_0063_measurement_runs.py`
- `tests/test_migration_0064_budget_notifications_recovery.py`
- `tests/test_migration_0066_audience_deliveries.py`
- `tests/test_migration_0067_exposure_scores.py`
- `tests/test_migration_0068_driver_person_payee_review.py`
- `tests/test_migration_0069_w3_04b_review_authority.py`
- `tests/test_migration_0070_driver_vehicle_approval.py`
- `tests/test_migration_0071_report_issuances.py`
- `tests/test_migration_0073_refund_cancellation_provenance.py`
- `tests/test_migration_0074_trip_evidence_manifest.py`
- `tests/test_migration_0075_governed_audience_delivery.py`
- `tests/test_migration_0076_dsr_assessment_truth.py`
- `tests/test_migration_0077_stored_object_deletions.py`
- `tests/test_migration_0078_campaign_assignment_driver_active.py`
- `tests/test_migration_0079_traffic_density_profile_revisions.py`
- `tests/test_migration_0080_trip_evidence_disposition.py`
- `tests/test_migration_0082_report_publication_intents.py`
- `tests/test_migration_0085_disclosure_protection.py`
- `tests/test_migration_0086_audit_subjects.py`
- `tests/test_migration_0088_report_publication_writes.py`
- `tests/test_migration_0089_driver_account_setup.py`
- `tests/test_migration_0090_single_active_advertiser_membership.py`
- `tests/test_migration_0091_budget_urgent_threshold.py`
- `tests/test_migration_0092_payout_v4.py`
- `tests/test_migration_0093_automatic_payout_approval.py`
- `tests/test_migration_0094_complaints.py`
- `tests/test_migration_0095_invoice_issuer_contact_and_bank.py`
- `tests/test_migration_0096_0098_paystack.py`
- `tests/test_migration_0099_automatic_payout_scan_cursor.py`
- `tests/test_migration_0100_reverse_phone_verification.py`
- `tests/test_migration_payout_downgrade_guards.py`
- `tests/test_migration_slice1.py`
- `tests/test_migration_slice2.py`
- `tests/test_migration_slice3.py`
- `tests/test_migration_slice4.py`
- `tests/test_migration_slice5.py`
- `tests/test_migration_slice6.py`
- `tests/test_migration_slice7.py`
- `tests/test_migration_slice8.py`
- `tests/test_migration_slice9.py`
- `tests/test_migration_storage_downgrade_guards.py`


## Integrated checkpoint ? 14 October, squash candidate

W3a `18192019`, W3b `115fc505`, W4 `0b0be762` and the W3b
static/error-path correction `30eadf27` are committed. The squash is the next,
separate commit. Final reviews, D33 receipt, two full CI runs and merge remain
pending; the historical checkpoints above are not completion claims.

- Full fresh PostgreSQL chain through 0105 versus fresh baseline 0106:
  `coverage/w34/schema-before.sql` and `schema-after.sql` are **byte-identical**,
  591,483 bytes, SHA-256
  `5cfe8f76c533f6825a3b5649242974b54766ea0d13f0751fff169db359dfb2ad`.
  `schema-parity.diff` is empty. Separately dumped `alembic_version` data differs
  only from `0105_business_health` to `0106_development_baseline`.
  pg_dump 16.4 used `--schema-only` without exclusions or owner/ACL suppression.
  Thus tables, columns/types/defaults, constraints, indexes, enums/sequences,
  functions/triggers, partition objects, extensions and grants/RLS match.
  Catalog: 141 public tables including partitions/extension tables, 1,214
  constraints, 114 noninternal triggers, zero RLS tables/policies, three explicit
  relation ACLs. Canonical Alembic check and drift/geometry/constraint tests pass.
- Bootstrap verification passes: disabled automatic actor, random Argon2 hash,
  matching SHA-256 fingerprint, singleton controls and money approval guards.
  All 37 current baseline/protection cases pass across focused runs
  (`baseline-protections.xml`, corrected `baseline-protections-final.xml` and
  `baseline-retention-final.xml`). Final retention/R18 run: 28 passed, including
  real interrupted detach recovery/refusal and signed-evidence immutability.
- Existing `app.seeds.demo.run_seed` completed on `w34_baseline_after`, with the
  repository's `seed_private_storage` fixture adapters and synthetic local keys,
  no provider calls: 379 rich trips, 13 assignments, four rich campaigns, nine
  rich drivers; basic graph has 1,144 pings, four calculations and four ledger
  entries. The seed output is local ignored evidence at `baseline-seed.log`.
- Lifecycle/authority verification: 89 passed on the first combined run, with
  its 12 stale retention fixtures subsequently corrected and passing above.
  Reference/head/model follow-up: 41 passed. Two recovery-harness checks need
  Docker CLI/daemon or a Linux Git checkout/shell environment unavailable in
  this Windows-bound runner; final full CI must verify them. No extra test
  container was started. Billing not-found/error corrections: 12 passed.
- Security specialist `w34-security-review-20261014-r1`: **PASS**, read-only
  source/artifact review, explicitly confirming no constraints, RLS state,
  grants or audit/immutability triggers lost. Privacy, money and consolidated
  minimal-change acceptance remain pending.

### After metrics and comparable clone scope

Radon 6.0.1, same `radon cc app -a`: **3,256 blocks, average 3.6228501228501226
(A)**, versus 3,299 / 3.7356774780236437 before.

The original jscpd default limit of 1,000 lines silently excluded the old large
monoliths. With that same limit, before/after are 245/244 clones, 2,861/2,831
lines, 2.58%/2.39%, 788/809 sources. For an honest whole-source comparison,
both pristine master and this candidate were also measured with identical
`--max-lines 20000 --max-size 2mb` plus the original language/ignore options:
**347 ? 319 clones; 4,088 ? 3,718 duplicate lines; 2.69% ? 2.52%**.
Total lines: 152,084 ? 147,725; sources: 812 ? 829; duplicated tokens:
42,762 (2.94%) ? 37,439 (2.77%). Reports remain in ignored
`coverage/w34/jscpd-complete-before` and `jscpd-complete-after`.

### Deleted test fragments alongside the inventoried chain files

- `tests/test_advertiser_reports.py::test_slice10_adds_no_migration_or_reporting_tables`
- Historical migration-file assertions at the tail of `tests/test_heatmaps.py`.
- `tests/test_driver_agreement_retirement.py::test_migration_retires_private_objects_retryably_without_fabricating_consent`
  and its old-revision loader; current retirement/attachment protection remains.
- Historical backfill/downgrade-only cases and the unused `seed_revision_chain`
  fixture in `tests/test_r18_money_authority_postgresql.py`; current money
  immutability and ledger transition assertions remain.
- Downgrade-only assertions in current R20/R22/R32, KYC-retention and transferred
  schema tests; the single baseline has no predecessor. Obsolete migration-test
  duration entries are removed from `scripts/pytest_shard_durations.json`.

Operational old-revision references in tests, seeds, shell fixtures and migration
chain/inventory checks now use the baseline or distinct synthetic test versions.
Append-only historical architecture/progress/build-loop evidence retains its
original revision names as history, not current instructions.


## Post-build privacy correction ? 14 October

Privacy review r1 reproduced an incomplete-counter defect: readable successful
attempts could conceal rejected attempts whose Redis writes failed. A new
regression failed with a healthy result before correction. The existing daily
Finance item now retains the operational invalidation time described above;
no schema change was needed. `tests/test_business_health.py` passed 17 cases
(`privacy-counter-fix.xml`), and the added concurrent older/newer failures,
midnight and manual-resolution boundary passed (`privacy-counter-concurrency.xml`).
Ruff and the progress validator pass. Privacy reassessment
`w34-privacy-review-20261014-r2` returned PASS on the integrated source and
reconfirmed exact schema parity/no lost constraints, RLS, grants or audit and
immutability triggers. Money and consolidated reviews remain pending.

The committed squash is `54ddc8933a78b28980308a71dae932a497ed2c1d`.
The operational correction leaves the baseline and parity dumps unchanged.
Post-correction Radon is 3,259 blocks, average 3.6225836146057073 (A).
The identical full-source jscpd command now reports 829 sources, 147,783 lines,
319 clones and 3,718 duplicated lines (2.52%); 37,439 duplicated tokens (2.77%).
Targeted basedpyright reports zero errors/warnings/notes.

### D33 qualification bases

The complete changed-code qualification range starts at
`48e4ab51338dcaf8abde34aee56e91a1a2c40b2c`, the master ancestor before the
REQ-158/159 agreement/shared-picker merge. After the measurement run, apply the
unchanged checker to its exact downloaded LCOV/provenance against that ancestor,
including the separate 85% money/privacy floors, and retain the result for the
independent receipt review. No local coverage is measured.

This branch has no remote predecessor, so its first push event supplies a zero
base; the measurement run can produce all full-suite/coverage artifacts but its
coverage job cannot resolve that base. The explicit qualification above covers
the complete range. The canonical receipt is then generated against the actual
measurement candidate SHA, matching the next push event's predecessor. That
receipt commit changes no application source. Its full verification must pass
all unchanged gates before merge; a zero source delta on this second event does
not replace the required complete-range qualification from the first run.
