# Final in-house batch verification

REQ-171–178; approved contract in
`issues/planning/final-inhouse-fixes-2026-10-14.md`. Source starts at fetched
master `966abd3a97873ed741f2cd714e5a8a928c5c2905`. No local coverage measurement,
provider calls, deployment, account-access/tmp reads or client-demo changes.

Ordered implementing commits: `2428011f` (A09), `01dd46ca` (A01), `faa4bb19`
(A02), `9bd21ecb` (A03/A10/A11), `13171ea6` (A04), `e2655df1` (request tidy-up).
Specialist correction: `dfa5f1c3` (A10 disclosure transaction boundary).

## Criterion evidence

| Ask | Criterion and actual evidence | Verdict |
| --- | --- | --- |
| A09 / REQ-171 | Both webhook endpoints reject declared, missing-length and false-length oversize before authentication/persistence. Streaming reader counts before accumulation. Exact-cap original-byte HMAC succeeds; bad signatures, normal payment/transfer events and durable replays retain existing behavior. Full fake-only `test_paystack_webhook_api.py`: 16 passed. Oversize reproduction failed on original master, then passed. Caddy 2.8.4 validates the current edge cap configuration. | PASS |
| A01 / REQ-172 | Tracker Flush rejection preserves durable batches and keys and continues capture under existing authority; recovery sends the same identity. End/authority rejection preserves its frozen manifest and pauses capture for reconciliation. Genuine queue quota/authority/writer/seal failures remain closed. Full tracker file: 57 passed; corrected watch-callback Flush regression fails against original master, passes current implementation. | PASS |
| A02 / REQ-173 | Both process-death-before-dispatch and provider-accepted/local-save-failed scenarios reconcile the original saved reference through fake I/O. Unknown/not-found recovery never mints a replacement; ambiguous/duplicate/malformed replies retain uncertainty. Canonical verified events keep exact reference/org/terms/amount/currency binding and audit authority. Checkout files: 7 + 36 distinct tests passed. Separate-session barriers prove initialization/recovery/explicit verification serialize across commits and intervening webhook confirmation wins. Crash regressions fail original master. Billing BFF terminal confirmed/failed recovery: full file 6 passed, two cases fail baseline. | PASS |
| A03 / REQ-174 | Unseeded source→link→measurement→scheduled worker reaches ready and empty-cell suppressed in both creation orders, without fixture materialization. Durable cursor batch 2 progresses beyond three invalid candidates and wraps after lost dispatch; repeat sweeps converge. Reissued runs redact old readers and delayed old jobs cannot restore them. Actual migration 0107 upgrade/pair constraint tested in isolated schema; one head, no restored history. | PASS |
| A10 / REQ-175 | Planning ready/suppressed/stale/unavailable views show governed area/coarse cell, Nigeria-time hours, rationale, human provenance, uncertainty and disclaimer without fingerprints. Exact-run internal export v3 freezes deterministic linked-source context; shared CSV/PDF rendering includes it. Fake-storage issuance→publication→download, cross-tenant denial, artifact tamper refusal and historical integrity after parent edits pass. Both disclosure writes now remain in the issuance transaction; seven two-session parent/access cases and two ordinary-reader cases pass, preserving fresh history and endpoint defaults. | PASS |
| A11 / REQ-176 | Africa/Lagos instant formatters construct under UTC and America/Los_Angeles and cross Nigerian midnight correctly; date-only values retain dates. Two meaningful regressions fail baseline. Final formatter/planning files: 24 passed. | PASS |
| A04 / REQ-177 | Exact-File/context/purpose/request identity independently retains intent, uploaded stage, confirmed ID and scan stage. Scan-poll retry skips completed work, one-of-two failure reuses its successful sibling, continuing siblings coalesce, and edits/access/logout/unmount fence stale responses. Apply person/vehicle and renewal callers covered. Full helper/Apply/renewal files: 17 + 22 + 20 = 59 passed. Profile supplies driver identity; integrated frontend typecheck passes. | PASS |
| REQ-178 | Thirteen specified historical rows close DONE using ancestry-verified triage commits; REQ-044/055 explicitly SUPERSEDED with replacements. Row comparison verifies every other existing row unchanged, including NEEDS ANSWER and external dependencies. No new coverage/design acceptance claim for REQ-063. | PASS |

Audience backend first pass: 70 passed / 3 failed (obsolete current-v2 assertions
and synthetic fixture); corrected. Focused follow-up: 75 passed / one existing
real-broker skip; final supersession node: 1 passed. Parent resolved the broker
skip using Redis inside the existing runner: both touched worker files plus the
full webhook file, 67 passed / zero skips. Touched architecture/migration
expectation files: 15 passed. Public API shapes remain unchanged; internal export
versioning does not change §9 baselines or require R14-B.

Privacy correction: seven fresh-history lock cases failed at the first disclosure
on the pre-correction source; fixing that path alone exposed the second premature
commit. Final nine focused cases passed (88.37s), and the existing integrated
linked-source publication/download/integrity journey passed (13.58s). Concurrent
source/user/organization/membership/campaign/zone/link edits remain blocked at
both disclosures and snapshot freeze, then succeed after issuance commits.
Ordinary zone-insight/recommendation readers still commit their served history.
An unnecessary full-file repeat was stopped after 12 passes; no full-file result
is claimed for that interrupted repeat. Scoped Ruff, whitespace and three-file
basedpyright pass on the correction.

## Repeatable focused checks

Only touched test files ran locally. Backend uses
`docker exec cardvert-final-inhouse-runner python -m pytest -q <touched files>`;
worker checks also set `REDIS_URL` and `ARQ_TEST_REDIS_URL` to the runner-local
Redis. PostgreSQL tests run sequentially against `cardvert-final-inhouse-db`.
The two containers use the batch-owned network, without host application ports.

Frontend uses runner-local source copies to avoid mounted Windows dependency
startup timeouts, with the repository's unchanged dependencies and configs:
`npm test -- <touched files>`, or direct Vitest entry point. Separate audience and
upload copies prevent concurrent source edits. Final integrated `tsc --noEmit`
passes. Focused ESLint passes. Prettier checks pass with the repository config;
CRLF conversion is not a source change. Focused Ruff and `git diff --check` pass.
Backend basedpyright 1.40.1, Python 3.12.14, explicit packaged typeshed and Python
interpreter: all 11 touched app files analyzed, zero errors/warnings. The first
direct Node invocation omitted its typeshed path and yielded invalid missing-
builtins diagnostics; the corrected invocation passes without baseline edits.
Package/checklist validation and the runtime OpenAPI snapshot drift check pass.

## Review and CI gates

- Plan reviewer: FIX; all five findings accepted in the amended approved contract
  before implementation.
- Money specialist: PASS, A01/A02 source `01dd46ca` / `faa4bb19`.
- Security specialist: PASS, A09/A04 in integrated source through `13171ea6`.
- Privacy specialist: round 1 FIX on A10's disclosure transaction boundary;
  accepted and corrected. Round 2 PASS on A03/A10/A04 and SECURITY PASS on
  unchanged A09/A04 after inspecting the integrated correction and evidence.
- Consolidated minimal-change review: round 1 PASS on `966abd3a..dfa5f1c3`
  and this criterion receipt; all changed files have an approved scope or
  correctness reason and no actionable finding remains.
- Full branch CI, possible controlled D33 receipt, non-squash master merge and
  new request closure: pending. This receipt does not assert those gates passed.

All delegates use owner-selected `codex-fresh-20261012`, `gpt-6.1-sol`, high,
priority. No actual provider context or handoff error occurred. Batch containers
must be removed before final handoff. A06, G04, external accounts/keys and client
answers remain outside this batch; no package-queue promotion is authorized.
