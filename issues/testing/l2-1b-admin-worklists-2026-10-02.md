# L2-1b local implementation checkpoint — 2 October 2026

This receipt records the second local implementation batch. Full design
acceptance remains open: the owner will perform the section 9 walkthrough;
REQ-062 still awaits permission for complete driver pay totals and the campaign
area read. Full GitHub CI and its D33 baseline refresh are pending. No launch
gate, dependency policy or trusted coverage baseline is changed.

## Outcome and scope

The canonical company hub, Trip checks, Money, Support, Settings and departmental
Work queue use existing named records and commands. Old department page routes
are removed, and current callers use the hubs or work lists. Company accounts
remain under Advertisers, driver accounts under Drivers, and Settings staff
reads only Terrax staff. One advertiser login per company remains the scope.

Backend changes are limited to the owner's approved member projection,
complaint/contact filters, in-person-check pagination and the separately
approved actual held-pay and audited recorded-route reads. Existing financial,
activation, consent, document access and report issuance commands retain their
authority and idempotency. No provider, invitation, migration, extra runtime
placeholder gate or unapproved REQ-062 read is introduced.

## Criterion evidence

| Criterion | Local verdict and evidence |
|---|---|
| Company identity, account and independent sections | PASS: company hub/directory/helper tests validate exact company identity, complete invoice reads, currency-separated exact amounts, actual refund records, independent paging, failures, and at most four simultaneous reads. New-company setup retains existing operations with exact partial-create retry; no invitation is shown. |
| Work queue and navigation | PASS for implemented sources: full paging, filtered totals, global oldest items, bounded named context reads and exact destination links are tested. A failed source makes its department unavailable rather than showing partial counts. Known timestamps are honestly labelled Created, Updated or Last message where a waiting-start timestamp is absent. |
| Trip review | PASS: recorded map geometry handles antimeridian and start/end without inventing locations; selected records are independently loaded and validated. Actual held pay comes from existing pending ledger facts. Fifteen focused PostGIS cases pass, including wrong roles, audit/cache boundaries, duplicate flags, mixed currencies, failed audit commit and exact point/batch identity. |
| Support and contact | PASS: driver/company filters, complete staff selections, exact selected complaint identity and current consent/contact authority are tested. Existing complaint and contact commands remain unchanged. |
| Money and Settings | PASS: existing commands, password proof, masks, audit controls and selected batch/line/correction identities are retained. Full invoice and settlement reads, pagination and audience read concurrency are tested. Pay terms remain on the campaign page. |
| Placeholder rule | Registered in docs/placeholders.md under D46/D47. Seeded inputs and their replacement requests are documented; existing live-use checks remain. This is not evidence that external inputs or staging are ready. |
| Read-only backend boundaries | PASS: approved projections/filters/pagination passed ten actual PostGIS cases. REQ-069 passed fifteen additional PostGIS cases and independent money/privacy/security review. Generated API JSON, snapshot, frontend types and architecture inventory are produced from an isolated backend without unrelated marketing changes. |
| Changed frontend coverage | 1,209/1,341 lines = 90.1566%; 853/1,033 branches = 82.5750%, relative to f172ab3. Scope is integrated frontend only, not combined backend/frontend D32, full CI or D33. |
| B-only frontend coverage | 724/779 changed lines = 92.9397%; 907/1,071 changed branches = 84.6872%, comparing the isolated A and B source trees with difflib changed-line mapping. This exceeds the ordinary local frontend targets; it is not CI Git rename analysis or a combined D32 verdict. |
| Preserved tracking/native contract fixtures | PASS: 136 cases across seven capability, ping queue, canonical evidence, tracker and recovery files after final contract regeneration; no real-device claim. |
| Tests | 593 selected integrated frontend cases passed across 81 files, followed by 17 passing targeted cases for actual queue kinds, duplicate work, independent company pagination and section failures. Production source was identical; coverage merged maximum hits only for two records with identical line/branch keys. |
| Production build and static checks | Standard Linux Next 16.3.6 Turbopack build and TypeScript passed on the final integrated source; the additional isolated B build and TypeScript passed without unrelated marketing work. Scoped ESLint has zero warnings. Backend type checking and focused static/schema checks passed. |
| Independent reviews | Approved B plan and read amendments reviewed before implementation. Same consolidated reviewer rechecked valid corrections and returned source minimal-change PASS; money/privacy/security frontend and backend reviews PASS. Added tests and coverage method were independently rechecked with PASS. These are source verdicts, not full design acceptance. |
| Owner browser walkthrough | NOT RUN by agents as final acceptance. Owner will test all tasks in at most three clicks without typed IDs, at 1366×695 and 375 px. Local URL http://127.0.0.1:3101/admin; seeded admin source app/seeds/demo.py. |
| CI, baseline and delivery | Pending a separately authorized push and successful full CI. D33 coverage/baseline.json remains unchanged; REQ-054 remains open. Current owner authorization covers commits only. |

Repeatable local receipts are in C:/Users/Dell/.codex/l20-verification:
l21-integrated-serial-coverage.junit.xml, l21b-extra-coverage.junit.xml,
l21-final-changed-coverage.json, l21-merged-pass.lcov.info,
l21-approved-read-postgis.xml, l21b-trip-review-postgis.xml,
l21-final-build.log and l21b-isolated-build.log. Source scope is recorded in
l21b-staged-files.json. No containing commit SHA is embedded in this receipt.
