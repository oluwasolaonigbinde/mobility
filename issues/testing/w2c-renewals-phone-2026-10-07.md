# W2-C local delivery — document renewals and reverse phone verification

Owner brief: `Cardvert_W2C_Renewals_Phone_Brief_2026-10-07.md`.
REQ-119/120, D66/67, architecture v1.124; branch `w2/renewals-phone`.
Base: `ec267529d26688bb18d72d41ac3ced4a68221a5a` (combined Wave 1).
This is local evidence. Requests remain IN PROGRESS until owner merge and
combined CI. No push, GitHub CI, provider call or deployment was performed.
No launch-gate queue change, source baseline or dependency change.

[Reviewed contract](../planning/w2c-renewals-phone-contract-2026-10-07.md).
Implementation retains private scanned upload, encrypted NIN/bank capture,
immutable revisions, audited staff reads and current-revision review. Active
signed-in accounts renew rejected/expired person/bank and owned car documents
from Profile. Staff Documents handles current renewals without restoring public
application access or activating suspended drivers. Driver-only phone issuance
replaces operator-send/driver-enter verification; staff records received code
and sender, with no code/hash readback. Migration 0100 replaces obsolete send
fields/statuses, parent `0099_automatic_payout_scan_cursor`.

## Criterion-by-criterion evidence

| ID | Local result | Evidence |
|---|---|---|
| C1 | PASS | `test_w2c_renewals.py`: rejected and expired staff-created accounts renew; standalone KYC bypass denied; exact retry returns one revision; stale ID/review and cross-owner car denied. Real PostgreSQL distinct/exact/review races converge without orphan bank capture. A pre-build run against the base reproduced missing signed-in documents (404) and missing driver-response code: two expected failures. Existing applicant/account/review convergence checks also pass. |
| C2 | PASS | `test_kyc.py`, person/payee and vehicle review files cover protected owned/scanned files, encrypted capture, bank/NIN/read authority, stale decisions and work eligibility. Browser submitted all six private files, performed audited NIN, bank and six document reads, then approved current person revision and rejected current car revision. No approval expiry was invented; current car remains a work blocker. |
| C3 | PASS | Seven renewal component cases plus profile/hub/review cases; browser forms, waiting and reviewed states at 375px and 1440px. Driver sees actual reason, file names and only recorded dates, recoverable upload error and stable retry identity. Screenshots below. |
| C4 | PASS | `test_driver_can_request_a_code_that_staff_cannot_read` compares actual issued code with staff contact reads, validation/forbidden/wrong-code errors, successful recording, audits/logs and storage; only keyed hash is stored. Driver BFFs are no-store; staff action tests exclude code in responses. Browser checks actual staff action response text on success and each of five wrong-code failures against the issued code. Blank staff inputs are not prefilled. |
| C5 | PASS | 21 reverse-phone cases cover durable attempt exhaustion, expiry, saved-phone changes, replay, foreign challenge, inactive driver, account-wide limits across versions and real PostgreSQL request/record/account-edit races. Browser reload recovers the same live code; phone edit, expired reload, exhaustion and verified refresh clear it. Delayed issuance/status and unmount/hide resets have component coverage. |
| C6 | PASS | Missing/configured destination and production/staging operator/wording gates, API denial and hidden driver button tested. Contact completion requires current verified saved phone, active driver and exact purpose/version consent; withdrawal and account-edit races pass both UUID/lock orders. Completed exact retries preserve their receipt. REQ-032 wording and named operator remain external inputs. |
| C7 | PASS | Migration 0100 upgrades actual prior schema and passes Alembic model check. Head seed and rerun pass with immutable guards; exact reserved demo phone mapping, six scanned fictional documents and rejected/expired renewal example checked. Legacy Start fixtures contain no fabricated approved KYC/car snapshots; existing synthetic encrypted bank/payout fixtures and money metadata survive reruns. Three API baselines regenerated and checked; Python golden-vector and affected R14-B browser/PWA contract fixtures pass. |
| C8 | PASS | 211 unique backend cases / no final failures or skips; 170 frontend cases in 18 files pass. Ruff check/format of 34 owned Python paths, scoped basedpyright of 20 application modules (0 errors), scoped ESLint/Prettier, frontend TypeScript and schema consistency pass. Changed-line/branch floors pass on fresh valid measurements below. The same independent consolidated reviewer returned final PASS on the complete staged source and evidence before the authorized local commit. |

## Coverage and runtime integrity

Changed executable lines: **572/602 = 95.0166%**.
Changed branches: **287/347 = 82.7089%**.
Required floors remain 90% / 80%. Calculated against the full base SHA using
unchanged `scripts/check_changed_coverage.py` eligibility, diff-line, LCOV and
metric functions; new files include all source lines in the staged diff, so every LCOV branch
point is included. The preliminary unstaged policy fallback had a smaller
branch denominator; the complete staged counts above are authoritative. Details:
[changed coverage](w2c-renewals-phone-2026-10-07/changed-coverage.json),
[test results](w2c-renewals-phone-2026-10-07/test-results.json),
[source hashes](w2c-renewals-phone-2026-10-07/source-provenance.json).

The initial default thread-only coverage dataset was discarded: it contained
impossible cross-file async line mappings. Coverage 7.16 explicitly requires
[greenlet concurrency configuration](https://coverage.readthedocs.io/en/7.16.0/config.html#run-concurrency)
for programs using greenlet. Fresh final-source measurement uses the CLI option
`--concurrency=thread,greenlet` and a separate data file; corrupted data is not
combined with it. Repository policy, configuration, exclusions, baselines and
dependencies are unchanged. This is a scoped local changed-code check; full CI
and global/critical ratchets remain the owner's combined Wave 2 checks.

The functional result merges each test's latest result across the initial
201-case run, corrected race/golden/phone/seed reruns and seven seed tail cases.
Retired failures: one lock-impossible barrier in an old race fixture (corrected
to command-entry synchronization while preserving convergence/conflict checks),
one missing immutable vector file in `/verify` (copied, unchanged), obsolete
empty-phone fixture assertion (updated to exact reserved mapping), and invalid
direct synthetic approved seed snapshots (removed without weakening guards).
An external Docker restart interrupted an earlier run; interrupted results are
not evidence. Only this lane's owned containers were resumed; W2-D was untouched.

## Browser evidence and bounded environment

Real local PostgreSQL, authenticated driver/staff UI and production routes;
actual multipart uploads/private byte reads. Storage and scanner are explicit
synthetic local fixtures, and bank confirmation is an internal synthetic
fixture. No MinIO/ClamAV/provider/live-message or real-bank proof is claimed.
[Browser results](w2c-renewals-phone-2026-10-07/browser-results.json) records
response exclusion, states and persisted audit counts. The proof database was
retained when a separate clean screenshot database was seeded.

| Screen | Phone | Desktop |
|---|---|---|
| Driver renewal form | [375px](w2c-renewals-phone-2026-10-07/renewal-form-375.png) | [1440px](w2c-renewals-phone-2026-10-07/renewal-form-1440.png) |
| Driver waiting for review | [375px](w2c-renewals-phone-2026-10-07/renewal-waiting-375.png) | [1440px](w2c-renewals-phone-2026-10-07/renewal-waiting-1440.png) |
| Driver reviewed outcome | [375px](w2c-renewals-phone-2026-10-07/renewal-reviewed-375.png) | [1440px](w2c-renewals-phone-2026-10-07/renewal-reviewed-1440.png) |
| Driver Verify my phone | [375px](w2c-renewals-phone-2026-10-07/driver-phone-code-375.png) | [1440px](w2c-renewals-phone-2026-10-07/driver-phone-code-1440.png) |
| Staff blank Record phone verification | [375px](w2c-renewals-phone-2026-10-07/staff-phone-blank-375.png) | [1440px](w2c-renewals-phone-2026-10-07/staff-phone-blank-1440.png) |
| Expired code cleared | [375px](w2c-renewals-phone-2026-10-07/driver-phone-expired-375.png) | [1440px](w2c-renewals-phone-2026-10-07/driver-phone-expired-1440.png) |
| Exhausted code cleared | [375px](w2c-renewals-phone-2026-10-07/driver-phone-exhausted-375.png) | [1440px](w2c-renewals-phone-2026-10-07/driver-phone-exhausted-1440.png) |
| Verified code cleared | [375px](w2c-renewals-phone-2026-10-07/driver-phone-verified-375.png) | [1440px](w2c-renewals-phone-2026-10-07/driver-phone-verified-1440.png) |

Owned panels fit both widths and were visually inspected. Existing shared
375px header overflow belongs to W2-D and was not edited. Installed Next 16.3.6
differs from manifest 16.4 and native SWC is absent, so the bounded browser
preview used webpack development mode without dependency changes. No production
build, physical-device or deployed-preview acceptance is claimed.

## Independent reviews and remaining owner actions

| Role | Verdict | Reported model |
|---|---|---|
| Clean-context plan review | PASS after corrections | GPT-6 family; configured `gpt-6.1-sol`, medium; exact runtime ID not exposed |
| Privacy specialist | Final integrated PASS, including source, evidence and screenshots | Codex / GPT-6 family; exact runtime ID not exposed |
| Security specialist | Final integrated PASS, including current-account contact completion, seed correction and evidence | GPT-6; exact variant not exposed |
| Same consolidated minimal-change reviewer | Final integrated PASS; all prior FIX corrections resolved | GPT-6 family; configured `gpt-6.1-sol`, medium; exact runtime ID not exposed |

The same consolidated reviewer reassessed every valid correction and returned
final PASS after independently checking the integrated staged diff, canonical
coverage, latest test results, all 40 source/contract hashes and all 16 screenshot
hashes, plus visually inspecting both widths. No implementer delegation was
used. Owner Claude acceptance, shared-baseline regeneration if this lane merges
second, combined full CI, merge and any preview deployment remain owner actions.
Live use stays off until approved REQ-032 wording and named operator/destination
inputs exist. No expiry/renewal policy was invented. Account-access, tmp,
unrelated lanes, money calculation, notifications, CI and dependencies were not
edited or read where prohibited. Requests remain IN PROGRESS; this receipt does
not contain the implementing commit's own SHA.
