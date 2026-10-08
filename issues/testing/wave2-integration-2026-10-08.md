# Wave 2 integration — 8 October 2026

REQ-131; owner-authorized local real merge of `w2/polish` (78ad558) into
`w2/renewals-phone` (74cdb31). No push or external action. Full CI/master acceptance
remains separately gated. Contract: [integration plan](../planning/wave2-integration-2026-10-08.md).

| Criterion | Verification |
| --- | --- |
| C1 | PASS. Fresh migrated base ec267529 and candidate 74cdb31 used the same installed runtime, settings and synthetic private storage/scanner. The unchanged track-tab Chromium spec passed on base and failed on candidate because the trip button was absent. Base returned approved person/car evidence; candidate returned KYC_NOT_FOUND and missing vehicle evidence. The failure is UI readiness, not proof of a backend trip-start denial: the existing no-application/no-KYC guard exemption is unchanged. Normal primary demo submissions now use six owned fictional PNGs, audited NIN/bank/file access, accepted document outcomes and recorded reviews. Fixed candidate passed; merged desktop/mobile tracking passed. A real API Start returned 201 and End 200. The strengthened existing PostGIS start/end test passed, including stable file/review/submission identities and dates after reseeding. Damilola remains rejected for licence and expired for insurance. |
| C2 | PASS for the reviewed merge tree; the authorized final action records its two parents, 74cdb31 and 78ad558. REQ-119–131 and D66–71 occur exactly once; architecture v1.124, v1.125 and v1.126 remain. Q12 retains export wording, Q13 renewals, and Q34 both notification access and reverse verification. Package progress, CI, dependencies, credentials and unrelated files are untouched. |
| C3 | PASS. Actual merged FastAPI source regenerated both JSON artifacts and openapi-typescript regenerated schema.d.ts. Canonical snapshot check passed. The running API matched both JSON artifacts after excluding only the harness's /fixture/file and /fixture/upload routes; there were no extra schemas. Native contracts passed: 46 PWA/trip frontend fixtures and one shared Python vector. |
| C4 | PASS. 191 frontend tests in 21 changed files and 172 additional affected-review/report/native/queue/tracker tests in 10 files passed (363 total). The 314-case touched backend batch completed with 313 passes and one obsolete assertion expecting no primary-driver KYC. That assertion was corrected to require audited approved submissions and accepted document outcomes; its final isolated migrated-head rerun passed. The strengthened primary-driver start/end/idempotency case also passed separately on final source. Including the shared Python vector, all 315 distinct backend cases have final PASS verdicts, with no skips. All 14 driver browser cases passed across the initial run and isolated warm reruns. The initial broad run had three desktop loading/navigation timing failures; warm reruns passed unchanged assertions/timeouts. Source TypeScript, scoped ESLint, Ruff/format, basedpyright against existing baseline and final LF-normalized runtime Prettier passed. No local coverage was run. |
| C5 | PASS. Independent plan review was completed before implementation and its valid corrections were accepted. The consolidated post-build reviewer (gpt-6.1-sol, medium, fresh context) applied minimal-change-review and returned PASS on the final staged source and evidence: no actionable findings. Only the expressly authorized local merge commit follows; no push. |

The harness used lane-owned PostgreSQL databases; no preview database was used.
Ordinary backend fixtures use SQLite and the database-specific fixtures use
PostgreSQL. Synthetic scanning checks PNG bytes and is not live scanner/provider
or physical-device evidence. Runtime source copied from Windows was normalized
to Git LF for formatting checks; repository formatting rules and baselines did
not change. No full CI, deployment or production build is claimed.

[Case results](wave2-integration-2026-10-08/results.json) retain original batch
verdicts and the final two seed reruns separately. The two changed seed tests
were collected before their final assertion updates in the batch; only their
isolated final-source passes are used for those criteria. Other collected tests
and application source were unchanged. [Source hashes](wave2-integration-2026-10-08/source-hashes.json)
cover all 121 integrated changed runtime/test/generated files using Git index
bytes; the final runtime copies matched each hash.

Final reviewer disposition: PASS. Verified the prepared two-parent merge,
preserved lane records, normal audited primary-driver seed correction, unchanged
work guards, generated contracts and all 121 indexed source hashes. The original
obsolete seed assertion and three browser timing failures remain recorded with
passing final reruns. No full CI, production build or deployment approval is
implied.
