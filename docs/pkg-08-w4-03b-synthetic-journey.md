# PKG-08 W4-03B-P2 provider-neutral synthetic journey

## Scope and result

W4-03B-P2 adds one local acceptance command for the build-only Cardvert pilot
path. It does not change product logic, authority, contracts, providers or live
state, and it does not complete W4-03B.

The correlated fixture `w403b-abuja-pilot-001` runs, in order:

1. synthetic advertiser;
2. synthetic admin;
3. screen-on PWA;
4. Abuja synthetic GPS;
5. reproducible measurement;
6. Campaign Performance Analysis;
7. qualified synthetic conditional ROI;
8. aggregate geography/time/context activation through the test-only adapter;
9. one frozen, approved payout instruction without provider submission; and
10. a rejected fabricated-approval incident followed by recovery to the exact
   frozen receipt.

Every exercised identity uses the reserved `.invalid` domain. The acceptance
fixture asserts cross-tenant report access returns `404`. It freezes the
campaign/run identifiers and result fingerprint together with report issuance,
report artifact, aggregate activation, payout instruction and provider-call
counts. The incident cannot change that receipt: there is no report issuance or
artifact, disbursement provider call, live activation adapter call or live GPS
claim.

## Command

Run from the repository root with the repository Python environment:

```sh
python scripts/run_w403b_synthetic_journey.py
```

The command succeeds only when the correlated build path passes and the
unchanged `scripts/evaluate_pilot_gates.py` returns exit `1`, empty stderr and
the exact ordered blocker list below. Exit `0`/PASS, a missing, extra or
reordered blocker, malformed authority, a forged runtime approval, journey
failure, cross-tenant disclosure or changed recovery receipt fails the command.

## Exact live boundaries

```text
G-money: BLOCKED — EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK
G-GPS: BLOCKED — EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, DV-PWA-PHYSICAL-MATRIX, DV-PWA-ROUTE-BATTERY
G-commercial: BLOCKED — EXT-PAYMENT-PROVIDER, EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-EVIDENCE-POLICY, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-UPLOAD-POLICY
G-advertiser: BLOCKED — EXT-BASEMAP, EXT-REPORT-METHOD, EXT-LEGAL-PRIVACY
G-moduleG: BLOCKED — EXT-REPORT-METHOD, EXT-LEGAL-PRIVACY, EXT-AD-PLATFORM
G-pilot: BLOCKED — EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK, EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY, EXT-LEGAL-PRIVACY, EXT-UPLOAD-POLICY, EXT-PAYMENT-PROVIDER, EXT-BUDGET-POLICY, EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-BASEMAP, EXT-REPORT-METHOD, EXT-AD-PLATFORM, EXT-RELEASE-ENV, EXT-STAGING-APPROVAL, EXT-PILOT-PERMITS, DV-PWA-PHYSICAL-MATRIX, DV-PWA-ROUTE-BATTERY, DV-STAGING-LIVE
```

These lines keep automated disbursement, real GPS/device evidence, live report
issuance and conditional ROI, aggregate contextual push, statutory/commercial
facts, permits and external deployment/staging explicitly closed.

## Verification evidence

- Plan review: `REVISE`; reconciled before editing by adding the Abuja-specific
  `.invalid` fixture, mandatory conditional ROI/aggregate activation stages,
  actual command-environment forgery checks and frozen side-effect counters.
- Red: the W4-03B browser proof observed `trip_status: active` after the End
  click and failed its required `sealed` recovery invariant.
- Green: the bounded correction waits for the existing Start-button recovery
  state and polls the simulator receipt; the same proof passed with one
  synthetic ping batch and zero live claims.
- Single journey command: passed one backend acceptance test and one
  mobile-Chrome Playwright proof, then printed the six exact blockers and the
  synthetic PASS receipt.
- Backend conservation red: a safe temporary inversion of the frozen-receipt
  equality failed on the identical before/after receipt; the invariant was
  restored before the green run.
- Runner red: temporarily removing `EXT-SETTLEMENT-BANK` from the expected
  G-money line produced two focused failures; the exact blocker was restored.
- Focused runner tests: eight passed, covering exact order/current blockers,
  real command-boundary forgery, unexpected PASS, missing/reordered blocker,
  malformed evaluator output, child-test failure and preserved shared-helper
  defaults.
- Preserved behavior: the original W4-01C mobile-Chrome proof passed (one
  expected iPhone-profile skip); the default measurement ROI and advertiser
  report helper regressions both passed.
- Focused static checks: Ruff format/check, Python compilation, Prettier and
  ESLint passed for the changed acceptance files.
- Clean-context minimal-change review: `FIX`. One bounded correction restored
  the helper's exact legacy organization/billing/campaign defaults, made
  advertiser-first construction W4-03B-specific and supplied the backend and
  runner red evidence above. No second review was run.

## Remaining gates

No external input or deferred validation changed state. Approved providers,
company/commercial values, privacy and report-method authority, evidence policy,
Abuja permits, representative physical-device/route/battery evidence and an
approved live staging/release environment remain required before live use.
