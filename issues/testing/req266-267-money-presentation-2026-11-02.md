# Money presentation corrections — REQ-266/267

Owner instruction, 2 November 2026: fix the two known Money issues before
pushing. Continue in the existing `integrate/req252-264` checkout, from
`6d39fe45`. No commit, push, merge, deployment or provider call is authorized.

## Reviewed contract

1. Show the original earnings credit on reserved rows, separately from current
   payable authority. Keep reserved rows unselectable and preserve all payout,
   preview and selection calculations, including partially settled credits.
2. Identify blocked-submission alerts by the actual driver, frozen payment
   amount/currency and payment run; link to the exact payment. Enrich existing
   sparse alerts from their source records without a migration or stored-row
   mutation. Recorded context, including zero, takes precedence. Missing source
   remains unset; other alert kinds retain their current meaning.
3. Preserve staff-only access, no bank-detail disclosure, alert deduplication,
    ordering, filters, counts and bounded pagination.
4. Refresh all three API baselines for `ledger_amount`, run preserved R14-B
   fixtures, focused behavioral and rendered-screen verification, and complete
   the money/privacy/security specialist and final minimal-change reviews.

The independent plan reviewer (gpt-6.1-sol, medium) returned PASS. Its refinements
were adopted: restrict alert enrichment to blocked submissions; preserve recorded
identity and explicit zero; include the exact line in navigation; verify real
producers, stored-row invariance, pagination and accessible amount labels.
The owner already approved this concrete corrective scope; no new payment rule
or product choice is introduced.

## Verification

Before the implementation, two PostgreSQL regressions failed on the old code:
the reserved row had no `ledger_amount`, and the sparse blocked alert returned
null driver/amount/run despite its real payout line.

| Criterion | Verdict and actual evidence |
| --- | --- |
| 1 — earnings vs payable | PASS. Eight PostgreSQL payout-projection/API cases. A real reserved credit retains its original amount with zero selectable payable; a credit of 100.07 with 25.03 recovery still previews/reserves exactly 75.04, while its earnings remain 100.07. Sixteen form tests plus ten form-state tests verify labelled amounts, disabled reserved selection and unchanged selection/preview actions. |
| 2 — alert context | PASS. Two PostgreSQL alert-context/seed tests and three selected automatic-payout producer/filter tests (69 unrelated cases deselected). Both blocked-alert producers return their actual line context; recorded zero/identity/currency/run takes precedence. The demo fixture now creates its provider alert linked to its own reserved line; the seed helper test verifies line fields and repeat-call idempotence. Eight automatic-screen tests include two distinguishable drivers/amounts/runs and exact payment links. |
| 3 — read/access invariants | PASS. Real sparse-alert tests compare stored alert rows before/after reads, counts, ordering, filters and pagination; unrelated kinds and missing source remain unchanged. Driver requests return 403; API output contains no bank-account details. Existing producer tests retain deduplication/progression and no provider-attempt assertions. |
| 4 — contracts and verification | PASS for technical checks: all three API baselines regenerated with only the required `ledger_amount` addition; runtime drift check, TypeScript, scoped ESLint/Prettier, Ruff and `git diff --check` pass. Preserved R14-B capability/queue/evidence/tracker files pass 161 tests. Two additional API-to-React simulations pass. Plan, MONEY and PRIVACY/SECURITY reviews PASS; consolidated final minimal-change review PASS. |

The end-to-end simulation uses the current application in-process against the
existing local demo PostgreSQL database, then renders its actual serialized API
responses through the current Money React components. It verified 52 reserved
rows and all 51 blocked alerts with linked payment lines. It is not a new browser,
physical-device or production-build test. The running preview services were not
rebuilt or restarted. The in-process revision label identifies base `6d39fe45`;
the dirty-source SHA-256 values for both changed read services and schema were
checked against this worktree. No claim that uncommitted changes ran at a Git SHA
is made.

One old synthetic provider alert in that existing demo database has a recorded
driver/run but no payment-line link or amount. Reads preserve that recorded
context instead of inventing an amount. New fixture creation now links the real
line, and its focused database test passes. No backfill or demo reset was done.

Repeatable harness scripts/logs and captured API data are under
`C:\Users\Dell\.t3\worktrees\mobility\live-e2e-20261026-tools\req266-267`:
`verification.log`, `followup.log`, `final-checks.log`, `seed-and-contract.log`,
`live-api-capture.json`, and the corresponding scripts. Earlier logs retain a
corrected new-test UUID-order assumption, test typing/lint fixes and harness
command/revision-label errors; final successful results above supersede those
attempts. Existing Starlette deprecation and preserved tracker React `act`
warnings remain; there were no final test failures or skips.

The independent specialist returned MONEY and PRIVACY/SECURITY PASS on the
application/API/UI change. The consolidated reviewer separately assessed the
late fixture-only correction and returned supplemental MONEY and
PRIVACY/SECURITY PASS. All reviews used gpt-6.1-sol, medium; reviewers read code
and evidence and did not claim to have executed the controller's tests.

Full GitHub CI and owner-authorized commit/push/merge remain separate gates.

Final consolidated review (gpt-6.1-sol, medium): **PASS**, all four criteria
adequately evidenced; no actionable findings. The reviewer independently matched
the API capture hashes to current source and checked the integrated diff.

Later final-source verification and the REQ-268/269 artwork/type corrections are
recorded in [the pre-push sweep](prepush-sweep-2026-11-02.md).
