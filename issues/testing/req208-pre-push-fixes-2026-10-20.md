# REQ-208 local delivery evidence — 20 October 2026

Candidate on `design/brand-look-mockup`, based on `0a03ca5a`. The owner instructed
the Codex continuation to follow the existing approved handoff. REQ-208 remains
IN PROGRESS until merge; this receipt does not claim full CI, merge or release.
No push, deployment or external provider action was performed.

## Approved outcome and boundaries

The approved contract covers three-car disclosure, always-available Apply and
enquiry forms with rate limits, the built-in five-view/seven-day installation
rule, first-staff CLI, 24-hour approved-driver setup links, plain recovery email
and staff-header wording, and the four specified portal read improvements.
It excludes display-proof policy, driver challenges, payout-rule changes,
Staff Money → Invoices optimization, providers and deployment.

The inherited plan review was Opus 5.5 and its dispositions were already approved.
The continuation independently repeated privacy, security, money and consolidated
source review using `gpt-6.1-sol`, medium reasoning. This changes reviewer
continuity; the earlier Opus verdicts are not presented as Codex verdicts.

## Criterion evidence

| Criterion | Local result and evidence |
| --- | --- |
| A1 — three cars | PASS. Default three-car, single-day heatmap/cohort tests and actual report HTTP cases release three dominant/uneven contributors and suppress two. Frozen authority and source-recomputed manifests retain a three-car floor for every reported day. Date-selected impression, latest-cost and fraud sets each retain the floor; the final focused regression passes. |
| A2 — forms and photos | PASS. Registration/enquiry and installation tests pass. Real Redis atomic rate-limit test passes. Browser Apply opens; enquiry submission reaches the API and succeeds. A driver accepts a seeded offer, uploads exactly five PNG views, the local worker scans them clean, and evidence submission returns 200. Tests cover driver/admin authority, exact views and approval plus 168 hours. Exact removed-setting-token search is empty across app/scripts/tests/frontend/templates. The built-in duration constant is `INSTALLATION_PHOTO_VALIDITY_HOURS`. |
| A3 — first staff | PASS. CLI tests cover active admin, forced password change, normalized duplicate refusal, hash/audit handling and invalid input. Actual module CLI creates a local staff account; browser first sign-in reaches Change password. Temporary password is kept out of this receipt. |
| A4 — setup link | PASS. Persisted expiry equals issue plus 24 hours; delivered email says "This link works once, for 24 hours." Setup delivery, activation and replay test passes with an explicitly configured synthetic public URL. Password reset lifetime is unchanged. |
| A5 — wording | PASS. Recovery-copy and shell tests pass. Browser staff header reads Terrax Media operations without company/currency context. |
| A6 — read improvements | PASS for the specified reads. Driver Home and Earnings each log one `/driver/earnings/days` read and no ledger/summary paging reads. Decimal/status/currency/hold/week and empty-driver tests pass. Company-list parity compares issued invoice obligations/funding with the old per-campaign reads, including draft/cancelled campaigns. Browser Advertisers makes no invoice reads; ordinary link prefetches remain. Advertiser Home makes no creative/zone reads. Corrected isolated hub walk logs exactly one campaign and one commercial read. |
| A7 — verification | PASS for runnable local checks and browser walk; full CI/release-script evidence remains pending as explicitly delegated by the handoff. See limitations below. Both JSON baselines match FastAPI output, freshly generated frontend types match the candidate, and R14-B has 129 passes. |
| A8 — documentation | PASS locally. REQ-208, D106/D107, affected Q rows/client topics, architecture v1.147, installation/release/runbook/privacy documentation and all API baselines are updated together. `docs/progress.md` is intentionally controller-owned and unchanged. |

## Deterministic results

Results are overlapping batches, not an added-up unique-test total:

- Final backend batch: **121 passed** in 1088.98 seconds — authorization denial
  matrix, golden seed privacy, installation evidence, enquiry including Redis,
  reporting flow, campaign assignments and driver earnings days.
- Final dated-disclosure regression: **1 passed** in 13.99 seconds.
- Setup delivery/activation/replay focused rerun: **1 passed**. The other test
  in that two-case invocation exposed a further fixture-authority issue, corrected
  before the final dated-disclosure pass above.
- Earlier backend batches: 525 pass / 35 environment failures; 44 pass / one
  corrected expectation; 46 pass / one corrected empty-driver result; 65 pass /
  13 corrected test issues / seven service-gated skips; 203 pass / one corrected
  notification-channel assertion; 90 pass / two corrected fixture issues.
  The interrupted correction batch completed 43 passes before diagnosis.
- Frontend: **77** touched tests and **39** affected tests pass; R14-B **129**
  passes; TypeScript, ESLint, final Prettier and production Next build pass.
- Final changed Python files: Ruff lint and format checks pass. OpenAPI
  `--check`, deterministic frontend type regeneration comparison, Git whitespace
  check, and both production Compose configurations render successfully.
  The touched rehearsal script passes Bash syntax after checkout CRLF normalization.

Corrections made during continuation were narrowly scoped: frozen fallback daily
floor and Monday–Sunday total bounds (both reproduced failing before correction),
missing existing continuation-route inventory/payload, stale notification/subject
expectations, seed assertions for the new rule, and valid current-authority setup
for the new dated regression. No compatibility path or new dependency was added.

## Runtime and evidence integrity

The production frontend build runs against the migrated, freshly seeded disposable
`cardvert_req180b` database in `cv-req180b`; Edge connects to localhost:3220.
Storage is local MinIO, email is local Mailpit, and the scanner is the pre-existing
local protocol stand-in. Browser storage requests use a real-fetch local proxy
because only the frontend port is published. This verifies application integration,
not production malware detection or external delivery.

The main walk captures 12 screens with zero browser errors, blocked requests,
horizontal overflow or broken images. Its two hub assertions initially failed
because the harness parsed a query/hash suffix as part of the ID. The captured
API calls already showed one of each. A corrected URL-path parser and isolated
hub rerun pass both assertions, with one more screen and zero errors. This is
complementary evidence, not a claim of one all-green main-walk invocation.
Pre-existing small text on staff/Jobs/public screens is outside this copy/read scope.

Raw logs, original JSON results, corrected hub JSON and PNGs are retained in the
chat's local `req208-evidence` artifact directory before disposable resources are
removed. The original failures remain available there.

## Reviews and remaining controller work

- Privacy: final PASS; money: final source/deterministic PASS; security: final PASS.
- Consolidated final evidence review: PASS for the bounded local candidate; full CI and release/Compose checks remain pending. No source or behavioral changes followed that verdict.
- Full GitHub CI has not run. Missing container Docker CLI, checkout CRLF in
  unchanged release scripts and unconfigured recovery-service URLs explain the
  retained release/Compose test failures and seven recovery skips. Host Compose
  rendering is supplementary evidence, not a claim those pytest cases passed.
- API response key is `totals`, rather than the draft contract's `summary`.
  Day grouping runs in Python; lifetime total uses the existing SQL sum. Existing
  per-paying-tonight checks and per-invoice database reads remain within one API
  request. Without a stable transaction snapshot, concurrent writes can make
  lifetime and earlier-read day rows differ; this disclosed limitation remains.
- Trips still require `DISPLAY_PROOF_CHALLENGE_TTL_SECONDS` and
  `DISPLAY_PROOF_VALIDITY_SECONDS`. Staff Money → Invoices remains a non-goal.
- Controller-only progress wording: narrow EXT-EVIDENCE-POLICY to display-proof
  challenge/validity windows and RM9 challenge/spot-check values; installation
  uploaders, five views and seven-day validity are code-defined under REQ-208.
  Do not change its MISSING state or launch gates from this local work.
- The handoff target `import:claudeAgent:05f69b78-3943-4110-b204-595f8de50b57`
  cannot be resolved by this app (Invalid conversation). This receipt and the
  final commit report are available for the controller; no other chat is used
  as an inferred substitute.
