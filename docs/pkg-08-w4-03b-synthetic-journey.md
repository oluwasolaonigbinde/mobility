# PKG-08 W4-03B-P2 provider-neutral synthetic journey

## Scope and result

W4-03B-P2 adds one local acceptance command for the build-only Cardvert pilot
path. It does not change product logic, authority, contracts, providers or live
state, and it does not complete W4-03B.

The current D115/D118 synthetic sequence is advertiser → admin → screen-on PWA → Abuja GPS → measurement → Campaign Performance Analysis → frozen payout instruction without provider submission → incident/recovery. Retargeting, activation and ROI stages are removed (REQ-214/217).

Every exercised identity uses the reserved `.invalid` domain. The fixture checks tenant isolation and preserves its frozen synthetic receipt through an incident and recovery, with zero provider calls and no real GPS claim. The verification record below describes the original package-close evidence; it does not re-authorize the removed stages.

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
G-GPS: BLOCKED — EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-LEGAL-PRIVACY, EXT-PRIVACY-RESTORATION, EXT-UPLOAD-POLICY, DV-PWA-PHYSICAL-MATRIX, DV-PWA-ROUTE-BATTERY
G-commercial: BLOCKED — EXT-PAYMENT-PROVIDER, EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-UPLOAD-POLICY
G-advertiser: BLOCKED — EXT-BASEMAP, EXT-REPORT-METHOD, EXT-LEGAL-PRIVACY, EXT-PRIVACY-RESTORATION
G-pilot: BLOCKED — EXT-DISBURSEMENT-PROVIDER, EXT-SETTLEMENT-BANK, EXT-STORAGE-PROVIDER, EXT-MALWARE-SCANNER, EXT-KMS-CUSTODY, EXT-LEGAL-PRIVACY, EXT-PRIVACY-RESTORATION, EXT-UPLOAD-POLICY, EXT-PAYMENT-PROVIDER, EXT-Q28-COMPANY, EXT-COMMERCIAL-VALUES, EXT-CAMPAIGN-BUDGET-SCOPE, EXT-BASEMAP, EXT-REPORT-METHOD, EXT-RELEASE-ENV, EXT-STAGING-APPROVAL, EXT-PILOT-PERMITS, DV-PWA-PHYSICAL-MATRIX, DV-PWA-ROUTE-BATTERY, DV-STAGING-LIVE
```

These lines keep automated disbursement, real GPS/device evidence, live report
issuance, statutory/commercial
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
company/commercial values, privacy and report-method authority,
Abuja permits, representative physical-device/route/battery evidence and an
approved live staging/release environment remain required before live use.
