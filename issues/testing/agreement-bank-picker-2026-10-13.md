# Agreement and bank picker delivery evidence

REQ-158/159, D77/78, feature architecture v1.133, migration
0102_driver_agreement_acceptance (parent 0101_document_review_outcomes).
Delivery exception: REQ-160/D79, architecture v1.134. Approved contract:
[agreement-bank-picker-2026-10-13](../planning/agreement-bank-picker-2026-10-13.md).

Implementing commit a349c2e5; corrections 61d77e21, 7957b584 and 41439890;
normal master integrations 3e50fbbb and a84eff23. The latter includes closure
48e4ab51, all 26 closures and Wave 3 notes. Every master request row was
preserved verbatim (111 DONE rows), with feature requests retained separately.

## Criterion evidence

| Criterion | Verdict | Evidence |
| --- | --- | --- |
| 1. Plain agreement, full text, required consent | PASS | Apply at 375x812 displays five plain points, immutable /apply/agreement/1 and one required I agree checkbox. No public draft labels or horizontal overflow. Server rejects false/stale consent; UI sends version and acceptance. |
| 2. Immutable consent and staff view | PASS | First acceptance has server time/version; concurrent/exact retries preserve evidence and reject changed consent. Real PostGIS resolved/fallback submissions retain version 1/time. Authenticated admin Documents shows Agreed to version 1 on 13 Oct 2026. |
| 3. Retire signed path and synchronize contracts | PASS | Current APIs, callers, seeds, fixtures, admin and renewals use two person documents. Historical migrations stay historical. 0102 stages durable private-object retirement, preserves shared references and fabricates no consent; attachment/deletion locks and durable intents block reattachment. Real full migration-chain upgrade and retirement tests pass. All three OpenAPI artifacts moved together, runtime contract 4 PASS and native R14-B 43 PASS. |
| 4. One searchable popular-first picker | PASS | Apply and Profile share BankPicker and one backend catalog. Phone search and fake/unconfigured adapter exercise the approved nine-bank order and full-list filtering. OPay six-digit code survives capture unchanged. Loading/error/retry and selection tests pass. |
| 5. Authoritative check and fallback | PASS | Synthetic HTTP transport resolves TEST DRIVER, confirmation submits. Unconfigured adapter permits typed-name submission. Signed receipt tests reject tampering/expiry/wrong subject/bank/account/name/missing confirmation. Invalid/malformed/mismatched provider results, capability and local limiter failures never grant fallback; only approved unavailability does. UI invalidates stale work on edits. No live Paystack calls. |
| 6. Money, privacy and security authority | PASS source/local | Specialist reassessments PASS. Encryption, scoped reads, staff bank verification and D40b first manual payout to a new account remain. Rewrap preserves consent/bank provenance. Raw fields/query logs are scrubbed. Local lifecycle/retirement tests cover durable audit-before-delete, loss/retry and protected shared objects. |
| 7. Records and consolidated source review | PASS final consolidated round 7 | Requests recorded first; dated topic history, Q26, D77/78 and architecture amended. Pending legal/provider inputs and launch queue remain. Round 5 reviewed 41439890 and documentation-only closure merge a84eff23, correcting inventory/head assertions and shorthand references. |
| 8. Integration and release | PASS pre-merge under owner exception REQ-160/D79 | Closure48e4ab51 integrated, numbers checked. Integrated CI failed five stale fixtures/schema cases; corrections are test-only. REQ-160/D79 permits merge after affected local tests and independent PASS without new pre-merge full CI. Full CI/source-bound coverage evaluation deferred until after Waves 3/4. No false green or coverage claim. Requests close only after implementation reaches master, citing a prior implementing SHA. |

## Verification

Counts below are run totals, with overlaps; they do not claim distinct tests.

- Initial affected backend onboarding/KYC/renewal/bank/agreement: 81 PASS.
- Final focused bank/agreement/retirement/errors/payee/rotation: 66 PASS
  (526.56 seconds); D40b first-payment/current-review regressions 2 PASS.
- Authorization and seed corrections: 20 PASS (690.34 seconds); shared-file
  protection/applicant financial-separation seed cases 2 PASS (509.04 seconds).
- Actual full Alembic chain, retirement and convergence: 8 PASS (185.45 seconds).
- Audit registry, migration-head and full account-setup file: 14 PASS (133.07 seconds).
- Architecture inventory and reverse-phone rollback files: 5 PASS (21.84 seconds).
  Post-closure generated architecture check PASS; final numbering check PASS.
- Existing Paystack/OpenAPI group: 72 PASS, one runner-copy snapshot failure;
  corrected runtime OpenAPI rerun 4 PASS and snapshot check PASS.
- Initial UI: 52 PASS plus one catalog-await fixture correction; final form 1 PASS.
  Native/capability/PWA/admin group 86 PASS (includes R14-B 43). Final bank/form/
  upload 16 PASS; retry/prototype-route cases 10 PASS; BFF/agreement routes 8 PASS.
- Targeted existing synthetic Chromium correction journey: 1 PASS (9.5 seconds).
- Python basedpyright: 0 errors/warnings/notes; TypeScript typecheck and touched
  lint PASS. Touched Python Ruff and diff checks PASS.
- Final CI-repair verification: complete retention-authority, real MinIO report/storage and file/KYC lifecycle files: 25 PASS (492.32 seconds), zero skips. Final retention-authority source with encrypted historical payload/document bindings plus architecture file: 9 PASS (158.35 seconds), zero skips. Ruff, diff and request/D-row checks PASS; no real app, migration or money defect found.
- Earlier failed local runs exposed stale fixture counts/references, route inventory
  and runner-copy defects; all were corrected and their affected reruns recorded.
  No local full suite or coverage run, skipped hooks, weakened tests or floor changes.

## Accepted CI and one-off waiver

Cancelled source: 414398907e2efa877b7f750c014e80d9c821d7c9,
[run 38383022715](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38383022715).
Branch concurrency cancelled it on the closure push before the owner waiver.
It is not green evidence.

Accepted integrated diagnostic source: a84eff23b7ea579ebf7da86acb09108cfea8d739,
[run 38383211511](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38383211511),
FAILED. Shard 1: 692 PASS / 2 FAIL (MinIO lost-delete-reply cases expected three
retirement receipts). Shard 5: 444 PASS / 3 FAIL (two driver-document counts and
current ORM against frozen revision0087). Shards0/2/3/4, frontend quality/build,
backend static, E2E and R59 PASS. Backend aggregate failed on prerequisites;
coverage policy was SKIPPED, not passed. No fully green feature run exists.

Owner's final REQ-160/D79 authorization: correct these stale tests, require all
local affected tests and independent reassessment PASS, then commit/push and
merge without squashing. Do not wait for new pre-merge full CI. Defer full CI
until the Waves 3/4 run; report automatically triggered CI without waiting.
Any real app, migration or money defect stops the exception. D33 baseline,
checker, eligibility, instrumentation and every floor remain unchanged.
Complete source-bound measurement/receipt evaluation remains deferred and
must not be represented as passed. Last accepted fully green prior-master
source31997a67 was [run38376171034](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38376171034);
that evidence predates this feature.

## Independent review dispositions

All reviews ran through T3 with codex-fresh-20261012, gpt-6.1-sol, high, priority.
The provider temporarily timed out; these errors were never counted as PASS.
It recovered for rounds4/5. Authorized fresh read-only CLI fallback was unused.

- Plan1 FIX accepted before implementation: staff-created consent, receipt/retry
  precedence, fallback classification and immutable text/version.
- Money1 FIX -> money2 PASS: rewrap metadata, strict provider boolean and trimmed names.
- Privacy1 FIX -> privacy2 PASS: raw/query log scrub, fresh/reused consent provenance
  and durable signed-object retirement.
- Security1 FIX -> security2 PASS: shared file locking and durable reattachment denial.
- Consolidated1 FIX accepted: singleton seed, inherited object keys, consent/retry/
  expiry/current-view evidence. Consolidated2 FIX accepted: obsolete E2E fixture.
- Consolidated3 PASS source/local1–7. Consolidated4 FIX accepted: inventory/head/
  rollback assertions and shorthand REQ references. Consolidated5 PASS source/local1–7
  on41439890 and closure integrationa84eff23. Consolidated6 accepted the historical payload/binding/lock/downgrade and MinIO corrections and D79 records; its sole FIX identified an overnight renewal retry test whose only expiry date was removed with the signed-agreement fixture. Added expires_on=today to the accepted photo, retaining next-day replay/conflict assertions. Complete affected renewal file: 35 PASS (388.87 seconds), zero skips; restored overnight-expiry replay and conflict case passed. Consolidated round7 final pre-merge PASS covers a84eff23 plus this final working diff and receipt; criteria1–7 satisfied and criterion8 pre-merge gate passes under REQ-160/D79, without a full-CI or coverage PASS claim. Final verification run totals: 25 + 9 + 35 = 69 PASS, with overlap and no distinct-test-count claim.

## Isolated simulation and artifacts

Only agreement-bank-tools and agreement-bank-db were started. Branch Next3210,
FastAPI8210 and own PostGIS database used synthetic bank/storage/scanner adapters.
For the final affected tests, the pinned existing MinIO image's executable runs
inside agreement-bank-tools on9910/9920: no third test container. Real local
MinIO covers unversioned/versioned objects, deletion reply loss and publication
failure recovery. Client mobility containers and port3100 were untouched.

T3 native browser viewport375x812. Saved original screenshots embed duplicate
scaled preview panes; *-crop.png extracts the left phone view234x500 unchanged.
Untracked .tmp-review/agreement-bank/ screenshots, originals plus crops:
picker-search-phone.png, resolved-name-phone.png, agreement-phone.png,
full-agreement-phone.png, fallback-name-phone.png, submission-success-phone.png,
admin-agreement-phone.png. Runtime identities and helper files remain untracked.

Open external inputs: lawyer-approved text REQ-032 and Paystack keys REQ-025/051.
No deployment, live provider call, force push, account-access.md/tmp read or
launch-gate closure. PR28 is linked to this T3 thread:
https://github.com/oluwasolaonigbinde/mobility/pull/28.
