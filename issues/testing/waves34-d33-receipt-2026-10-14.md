# Waves 3/4 D33 coverage receipt

REQ-163/168/170, including deferred REQ-158/159 verification under D79.
This records measurement and qualification; final receipt-commit CI must still
pass before the D41 non-squash merge. No coverage was measured locally.

## Exact source and complete CI evidence

- Candidate: `6a1c8e6e0c47bf84b583b66f79263226073f7012`.
- Measurement: [38534616984](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38534616984).
  All six backend shards (3,398 tests in 226 files), aggregate verification,
  frontend checks, static checks, ordinary browser tests and R59 passed.
  The only failure was the expected policy refusal:
  `inventory or policy changed; controlled baseline refresh required`.
- Producer: CPython 3.12.14, coverage.py 7.16.0. The aggregate verifies each
  shard's candidate, assigned/executed inventory and coverage artifact hashes.
- Reports: run artifacts `r17-backend-lcov` and `r17-frontend-lcov`.

| Artifact | SHA-256 |
| --- | --- |
| `backend.lcov` | `95e6ee2058b7804c438919ec226b4ae31566016924052bfc7b366ecbf78fe3f2` |
| `backend-provenance.json` | `41473aa6b8fcd3ead7f0424de8aec01295297e00523f9c5aee149fe828d3cb32` |
| `backend-shards.json` | `32ea53de958c8323759aced9d953c101efada89c7296b71416590715b24196bb` |
| frontend `lcov.info` | `2de7c3112aebff5c8ef8db5ff507abdecf88a07f7f896367495eedb011ffae01` |
| Canonical `coverage/baseline.json` | `4d5a9d8f8ceb86ad931fabcee098677d8778c4ad16cd008ac91ba7d5b468e3ff` |

## Qualification and adopted metrics

The unchanged checker qualified the complete range from pre-agreement/bank
ancestor `48e4ab51338dcaf8abde34aee56e91a1a2c40b2c`, with producer verification,
separate sensitive floors and controlled refresh enabled. Exact prior adopted
ratchets passed; no refresh tolerance or eligibility exception was used.

| Scope | Lines | Branches |
| --- | --- | --- |
| Full changed range | 3,180 / 3,393 (93.7224%) | 992 / 1,192 (83.2215%) |
| Global | 38,324 / 41,464 (92.4272%) | 13,462 / 16,900 (79.6568%) |
| Backend | 31,688 / 33,692 (94.0520%) | 6,595 / 7,984 (82.6027%) |
| Frontend | 6,636 / 7,772 (85.3834%) | 6,867 / 8,916 (77.0188%) |
| Money | 5,493 / 5,864 (93.6733%) | 1,692 / 1,970 (85.8883%) |
| Privacy | 2,122 / 2,284 (92.9072%) | 744 / 870 (85.5172%) |

Money and privacy independently exceed 85%; changed code exceeds 90% lines /
80% branches. Global and backend/frontend eligibility remain unchanged under
D32. D81 adds the separate sensitive gates; it does not narrow the global floor.

REQ-158/159 are included in this full changed range and the refreshed inventory:
`app/adapters/banks.py`, `app/schemas/banks.py`, `app/services/bank_capture.py`,
`app/services/driver_agreement.py`, onboarding bank/account-name route handlers,
`application-bank-details.tsx`, `bank-picker.tsx`, `driver-agreement.tsx` and
`frontend/src/lib/driver-agreement.ts`. Existing modified callers are included
by the same ancestor comparison. The shared bank list/picker remains shared.
Additional consent/bank tests are the separately labelled commit `49f84945`.

The prior agreement/bank master run
[38390542839](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38390542839)
failed only changed-code coverage policy; its tests/static/frontend/browser
jobs passed. This receipt qualifies that deferred range; the final green batch
verification is still required to discharge D79's deferred CI obligation.

## Deterministic refusal paths

`test_submit_draft_batch_always_refuses_before_provider_or_intent` directly
asserts `PAYOUT_BATCH_NOT_RESERVED`, unchanged draft state, zero submission
intents and zero adapter calls. The formerly variable disbursement refusal is
now line 558, arc 557 -> 558: both are hit in this measurement and the preceding
complete run 38520447920.

`test_ping_rejection_uses_fixed_time_and_independent_invalid_field` uses a
fixed UTC clock and independently invalid accuracy/speed. `trips.py` rejection
lines 848 and 854 and arcs 847 -> 848 and 853 -> 854 are all hit in both complete
reports. These are explicit path assertions, not inferred per-test attribution
from aggregate coverage. Final verification must confirm those hits again.

## Canonical receipt generation

Reports were evaluated against a clean `git archive` export of the candidate,
with Git metadata and `core.autocrlf=false`; the export matched HEAD exactly.
This prevents Windows checkout conversion from altering source hashes or diffs.
The full-range qualification output has SHA-256
`c58fc10d2840f6c9db9efbc691d087675be55649b97f320ffd2fd557425f69d7`.

After saving that qualification, the committed old baseline was restored and
the canonical refresh rerun with base equal to the measured candidate. Both
canonical refresh and ordinary verification passed against the same reports.
The baseline was copied byte-for-byte, without hand-editing receipt values.

- Source parent: `6a1c8e6e0c47bf84b583b66f79263226073f7012`.
- Previous receipt: `b8d97416cae62122a1b7cd28dece6f7107caaa2072824d5f9d5ff58ae51b869c`.
- Source hash: `89d3ec51a063992b5f43ae425657e70e35e79418df6a60d63545aa69b69f1948`.
- Policy hash: `3dc2898f7e7a09232866464ca276146711f5cd72d626e869f1e829ce79c64f95`.
- Eligible inventory: `903270d02168f56351ecdc189470cb17282dfd60172775f27f7989d4b3f5eeff`.

The canonical receipt records all additions/removals, including the billing and
payout domain packages and the deferred agreement/bank implementation. No
application, test, instrumentation or workflow changes belong in this receipt
commit. Independent receipt review and final full green CI remain merge gates.

Independent `w34-d33-receipt-review-20261014-r1` returned PASS after recomputing
artifact, source, policy, inventory and prior-receipt hashes and checking the
whole-range metrics and deterministic hits. The only remaining merge gate is
full green verification on the receipt commit, including those hit checks.
