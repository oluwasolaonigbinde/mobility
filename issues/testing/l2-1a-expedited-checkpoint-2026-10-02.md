# L2-1a expedited source checkpoint — 2 October 2026

Full design acceptance remains incomplete. The owner approved proceeding with
L2-1b on this checkpoint and separately authorized committing the two batches.
D49/REQ-063 permits the local A coverage exception; the ordinary CI policy,
trusted baselines, live-use gates and delivery programme are unchanged.

## A-only outcome and verification

Core named search, staff glossary, driver/campaign hubs and section drawers are
implemented. The approved company directory and phone search are in A. Minimal
canonical company and staff pages make the search destinations functional
using existing profile/status operations. Future department navigation is
hidden until B supplies those screens. This A menu/home is an expedited
checkpoint, not the full departmental Work queue.

The nine owner source corrections are retained: obsolete core entity pages
and redirect shim are deleted; current core callers are canonical; moved
content uses plain staff wording; unsupported checklist rows are removed;
each failed section shows one plain failure; applications use exact driver
identity; per-trip/campaign/job fan-out is removed; Support links are absent
until B supplies scoped reads; automatic-account exclusion is server-side.
Driver hub cold reads are 9 normally, 10 only for explicit-application fallback
in A, compared with up to 84 before the fix. Final B adds two scoped Support
reads, making 11/12; these are HTTP counts, not SQL statement counts.

| Criterion | Evidence and verdict |
|---|---|
| Core search, destinations and staff wording | PASS for implemented scope: actual canonical company/staff/driver/campaign destinations, grouped search, debounce/failure behavior, role vocabulary and audited document labels are tested. |
| Driver/campaign correctness and existing authority | PASS for implemented scope: exact application/evidence identity, failed-read activation blocks, current readiness, selected drawer parent identity, actual trip/campaign metadata and honest financial/date labels are tested. Existing financial, audited document/account, activation and report authority remains. |
| A/B source attribution | PASS independent source review: no company-member read, complaint/contact filter or work list, Trip map/held-pay/paging, full company metrics/new-company retry, departmental Work queue, Money or Settings worklist is in A. Business pages retained until B relocates them are implementations, not redirect shims. Root AGENTS.md and unrelated marketing work are excluded. |
| Scoped frontend tests | Final isolated A run: 50 files, 283 tests, zero failures/errors. The earlier single failure was an A-only test still expecting a B contact read; corrected to assert primary phone data stays visible. Production behavior did not change. |
| Local coverage exception | PASS: 504/582 lines = 86.5979%; 839/1071 branches = 78.338%, exceeding the authorized 70% local targets. This is isolated A frontend changed executable coverage relative to e498147, not combined D32 or CI/D33. |
| Build and static checks | Isolated Linux Next 16.3.6 default Turbopack production build and TypeScript passed. Scoped ESLint and final formatting passed. The only production formatting after build sorts the home page's unchanged Tailwind class set. |
| Preserved tracking/native contract fixtures | PASS: 136 cases across seven capability, queue, canonical evidence, tracker and recovery fixture files. Driver/auth source and contracts are unchanged between A and B; the final B fixture run exercises the regenerated contract. |
| Backend and generated contracts | Approved directory/phone changes passed 23 focused cases; exact application identity and metadata projections passed their additional focused checks, including real PostGIS runs. Actor/payout regressions, Ruff and type checks passed. A JSON, snapshot, frontend types and architecture inventory are regenerated without B member/Trip/paging or unrelated marketing changes. |
| Independent review | Approved plan/phone and pay-read amendments reviewed. Same source post-reviewer rechecked owner fixes and isolated source separation with minimal-change PASS; money/privacy/security controls reviewed. Expedited evidence does not waive unresolved full-design criteria. |
| Full design gaps | OPEN: REQ-062 complete driver pay totals and campaign-area read lack permission. Full supported task/readiness coverage, agent screenshots and the owner's section 9 three-click/no-typed-ID walkthrough are not claimed complete. B supplies remaining department source work. |
| CI and baseline | OPEN: full CI after a separately authorized push, then D33 coverage/baseline.json refresh. REQ-054 remains open. |

Local repeatable receipts: C:/Users/Dell/.codex/l20-verification,
l21a-tree-tests.junit.xml, l21a-tree-changed-coverage.json,
l21a-directory-phone-r14.junit.xml, l21-approved-read-postgis.xml,
l21a-tree-manifest.json, l21a-staged-files.json and l21a-isolated-build.log. Candidate source is kept
in l21a-tree; final B source remains separately preserved. No containing commit
SHA is embedded in this receipt.

Owner walkthrough: http://127.0.0.1:3101/admin. Seeded admin login source:
app/seeds/demo.py. Owner will check 1366×695 and 375 px; seed credentials are
demo inputs and do not establish production access or readiness.
