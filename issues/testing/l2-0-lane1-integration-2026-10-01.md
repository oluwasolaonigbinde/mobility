# L2-0 local Lane 1 integration verification — 1 October 2026

REQ-054; D45/Q13. This receipt covers the owner-approved local integration
only. The owner rejected new Codex branches, approved retaining the
automatic-payout actor guard alongside Lane 1's async password imports, and
authorized working on latest master and committing after verification.

Source parents: master `4c6c0cc0ad618c8d0d0152d0cb05008cbbf0584f` and Lane 1
`3a2ed931973d919b1f3034f7645461687618fe97`. The pending merge has no unresolved
index entries. One real two-parent merge commit follows final review. Its SHA
is deliberately not embedded in this receipt.

## Contract verification

| Criterion | Local verdict and evidence |
|---|---|
| Preserve both source parents | PASS. Automatic-payout system-account edit protection remains; async request callers use awaited off-loop password helpers. Only synchronous seed helpers retain synchronous hashing. No new branch or worktree. |
| Reconcile integration surfaces | PASS. Authorization/audit denial matrices and admin journey tests retain both sides' entries. `docs/progress.md` has no diff against the master parent; no launch-gate queue change. |
| Regenerate API artifacts | PASS. Runtime generation of both OpenAPI JSON files and frontend API types; snapshot `--check` passes and fresh TypeScript generation matches after line-ending normalization. |
| Auth, concurrency and runtime controls | PASS. Confirmed failures alone increment the alert-only global bucket; IP/account reservations remain atomic blockers, reserve failure stays fail-closed, and alert-storage failures warn without locking out all accounts. PostgreSQL normalized-email serialization covers known and unknown accounts; async Argon2 uses a bounded four-thread limiter. Two observed API workers each have SQLAlchemy pool size 5 plus overflow 10; the separate arq worker remains separate. Local PostgreSQL had 13 connections against its 100 limit. |
| Touched deterministic tests and D32 | PASS. All 277 cases in the final scoped backend catalogue pass; 128 frontend cases in 21 files pass. Changed executable lines: 202/203 (99.5074%); changed branches: 175/184 (95.1087%), calculated with the existing coverage-policy parser and diff functions against `4c6c0cc`. Floors remain 90%/80%. |
| Contract/native fixtures | PASS. Two backend shared trip-evidence golden-vector/canonicalization cases and frontend trip-evidence, capability-contract and PWA-contract fixtures pass. This is R14-B fixture evidence, not physical-device or native release evidence. |
| Live synthetic flow | PASS. Browser admin sign-in; guided Apply steps at desktop and 375px width; own-car chooser missing-code validation and uniform invalid-capability 404; Fraud evidence and per-flag physical-check form; company save returning `saved=1` and saved notice. Corrected live Redis probe: global count 4 stays 4 after successful sign-in, eight unique failed attempts remain 401 and raise exactly one threshold alert, then valid sign-in still returns 200. |
| Scope and records | PASS. REQ-054, D45/Q13, client topics, architecture and runbook updated. No migration, provider call, money-calculation change, new client value, live-use switch, deployment or later-stage implementation. Other open requests and launch-gate queue remain unchanged. |
| Independent reviews | Plan PASS on the approved owner-directed integration route; security/privacy/runtime specialist PASS on corrected source. Consolidated post-implementation minimal-change review PASS on the final integrated diff and stable receipt; no actionable finding remains. |

## Correction found during review

The imported implementation could raise and consume the one-time global alert
on a successful attempt at the threshold. A real-Redis regression reproduced
the failure before correction. Reservation now handles only IP/account limits;
failed authentication/proofs explicitly record confirmed global failures.
Success refunds the IP reservation and clears the account bucket. Tests cover
the success-at-threshold regression, malformed reserve responses and alert-store
outages. No new threshold or product rule was introduced.

## Test and tooling evidence

Backend catalogue (277 unique cases; automatic-payout tests restricted to the
two system-account protection cases):

- `tests/test_admin_users.py`
- `tests/test_audit_route_coverage.py`
- `tests/test_auth.py`
- `tests/test_auth_command_races_r09.py`
- `tests/test_authorization_denial_matrix.py`
- `tests/test_automatic_payouts.py`
- `tests/test_contacts_and_recovery.py`
- `tests/test_driver_account_setup.py`
- `tests/test_driver_applications.py`
- `tests/test_driver_vehicle_approval.py`
- `tests/test_fraud_assessments.py`
- `tests/test_openapi.py`
- `tests/test_prepare_account_setup_application.py`
- `tests/test_r32_driver_application_terminal_lifecycle.py`
- `tests/test_rate_limit.py`

Additional checks: `tests/test_ci_integration_authority_r02.py` plus
`tests/test_w403a_release_preparation.py::test_production_builds_pin_base_images_and_dependency_graphs`
(74 passed); two selected shared-vector cases in `tests/test_trip_evidence_r34.py`
(2 passed). No full backend suite was run locally.

Frontend selection (21 files, 128 passed):

- `src/app/admin/advertisers/[organizationId]/company/{actions.test.ts,page.test.tsx}`
- `src/app/admin/fraud/{actions.test.ts,dispute-actions.test.tsx,evidence.test.ts,page.test.tsx,review-actions.test.tsx}`
- `src/app/advertiser/company/actions.test.ts`
- `src/app/advertiser/planning-sources/link-actions.test.ts`
- `src/app/api/apply/onboarding/vehicles/route.test.ts`
- `src/app/apply/{actions.test.ts,application-status.test.ts,car-chooser.test.tsx,page.test.tsx,person-payee-form.test.tsx,upload-retry.test.tsx}`
- `src/components/company/company-profile-form.test.tsx`
- `src/components/driver/pwa-contract.test.ts`
- `src/lib/advertiser/company-profile.test.ts`
- `src/lib/pwa/capability-contract.test.ts`
- `src/lib/trips/trip-evidence.test.ts`

Frontend typecheck and lint PASS. Ruff PASS. Basedpyright 1.40.1: 254 files,
0 errors, 0 warnings. Its required download was separately owner-authorized.
One permitted baseline refresh changed Lane 1's 325 findings to 389 (78 exposed
master findings, 14 obsolete entries removed); C901 exemptions added only the
three current-master files containing four previously existing complex functions.
No coverage floor was lowered. Progress validator PASS.

Backend runs used the cached Python 3.12 image, dedicated synthetic databases,
real PostgreSQL for concurrency cases and real local Redis for rate limits.
Existing per-test SQLite fixtures remain where prescribed by touched tests.
The initial host-bridge database connection timed out once; the same case later
passed using the container network. Partial runs were deduplicated against the
final 277-node catalogue: no missing case or unresolved error, failure or skip.
Coverage for the three corrected app files was purged before corrected runs;
only actual coverage records were combined. Two final disjoint whole-file groups
used unique per-test database schemas and separate temporary/output paths.
No backend and frontend coverage runs overlapped. A 256-file normalized SHA256
comparison confirms the tested Python snapshot matches the checkout.

Local raw reports (ignored by Git): `coverage/l20.*.junit.xml`,
`coverage/l20.backend.lcov`, `coverage/frontend/lcov.info`. Deduplicated catalogue,
coverage calculation and browser screenshots are retained under
`C:/Users/Dell/.codex/l20-verification/`. The temporary browser tab, frontend,
relay and live API were stopped after checks; other sessions' containers were
not stopped.

## Pending external gates

The owner-directed local master integration overrides D41's pre-master branch-CI
sequence for this stage; it does not satisfy D41. No push or GitHub access was
authorized. Full GitHub CI and the D33 exact-CI coverage baseline/provenance
receipt remain pending a later authorized push; `coverage/baseline.json` is
unchanged. REQ-054 remains IN PROGRESS until those closure gates are satisfied.
No unsupported Lane 1 DONE row was added. Physical-device/PWA field evidence
remains external. Stop after L2-0; later stages require the owner's continuation.

## Changed files

- `.basedpyright/baseline.json`
- `.github/dependabot.yml`
- `.github/workflows/ci.yml`
- `Dockerfile`
- `app/api/v1/auth.py`
- `app/core/rate_limit.py`
- `app/core/security.py`
- `app/schemas/driver_onboarding.py`
- `app/services/account_recovery.py`
- `app/services/auth.py`
- `app/services/driver_account_setup.py`
- `app/services/driver_applications.py`
- `app/services/fraud_assessments.py`
- `app/services/users.py`
- `app/services/vehicle_onboarding.py`
- `docs/api/openapi.snapshot.json`
- `docs/architecture.md`
- `docs/client-decisions.md`
- `docs/decisions-log.md`
- `docs/requests.md`
- `docs/runbook.md`
- `frontend/e2e/admin.spec.ts`
- `frontend/e2e/correction-workflows.spec.ts`
- `frontend/e2e/evidence-verification.spec.ts`
- `frontend/e2e/w401c-campaign-journey.spec.ts`
- `frontend/src/app/admin/advertisers/[organizationId]/company/actions.test.ts`
- `frontend/src/app/admin/advertisers/[organizationId]/company/actions.ts`
- `frontend/src/app/admin/advertisers/[organizationId]/company/page.test.tsx`
- `frontend/src/app/admin/advertisers/[organizationId]/company/page.tsx`
- `frontend/src/app/admin/fraud/evidence.test.ts`
- `frontend/src/app/admin/fraud/evidence.ts`
- `frontend/src/app/admin/fraud/page.test.tsx`
- `frontend/src/app/admin/fraud/page.tsx`
- `frontend/src/app/admin/fraud/spot-check-actions.tsx`
- `frontend/src/app/advertiser/company/actions.test.ts`
- `frontend/src/app/advertiser/company/actions.ts`
- `frontend/src/app/advertiser/company/page.tsx`
- `frontend/src/app/advertiser/planning-sources/actions.ts`
- `frontend/src/app/advertiser/planning-sources/link-actions.test.ts`
- `frontend/src/app/api/apply/onboarding/vehicles/route.test.ts`
- `frontend/src/app/api/apply/onboarding/vehicles/route.ts`
- `frontend/src/app/apply/application-forms.tsx`
- `frontend/src/app/apply/car-chooser.test.tsx`
- `frontend/src/app/apply/car-chooser.tsx`
- `frontend/src/app/apply/page.test.tsx`
- `frontend/src/app/apply/page.tsx`
- `frontend/src/app/apply/person-payee-form.tsx`
- `frontend/src/app/apply/upload-retry.test.tsx`
- `frontend/src/app/apply/vehicle-form.tsx`
- `frontend/src/components/company/company-profile-form.test.tsx`
- `frontend/src/components/company/company-profile-form.tsx`
- `frontend/src/lib/advertiser/company-profile.test.ts`
- `frontend/src/lib/advertiser/company-profile.ts`
- `frontend/src/lib/api/schema.d.ts`
- `issues/testing/l2-0-lane1-integration-2026-10-01.md`
- `issues/testing/pwa-field-test-protocol.md`
- `openapi.json`
- `pyproject.toml`
- `pyrightconfig.json`
- `tests/authorization_matrix.py`
- `tests/test_admin_users.py`
- `tests/test_audit_route_coverage.py`
- `tests/test_auth.py`
- `tests/test_auth_command_races_r09.py`
- `tests/test_authorization_denial_matrix.py`
- `tests/test_driver_vehicle_approval.py`
- `tests/test_fraud_assessments.py`
- `tests/test_rate_limit.py`
