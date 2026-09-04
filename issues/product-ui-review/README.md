# Cardvert UI and product-review programme

This folder is the single home for the eleven UI/product-review prompts, their
verbatim answers, normalized outcomes, decision boundaries, and proposed future
implementation packets. It is deliberately separate from the original 14-source
engineering audit corpus.

## Programme status

| # | Review | Status | Answer |
| ---: | --- | --- | --- |
| 1 | End-to-end system flow | Not run | — |
| 2 | UI ergonomics and information architecture | Answered and normalized | [verbatim answer](answers/prompt-02-ui-ergonomics.md) |
| 3 | Human-facing language and AI residue | Answered and normalized | [verbatim answer](answers/prompt-03-copy-voice.html) |
| 4 | Admin and operations workflow | Not run | — |
| 5 | Advertiser journey | Answered and normalized | [verbatim answer](answers/prompt-05-advertiser-journey.md) |
| 6 | Driver journey | Not run by this programme | — |
| 7 | Errors, gates and state transitions | Not run | — |
| 8 | Client-owned approvals versus system-owned UX | Answered and reconciled | [verbatim answer](answers/prompt-08-external-boundary.md) |
| 9 | Client-facing PRD and visual-system guide | Waits for 1–8 | — |
| 10 | Adversarial PRD review | Waits for 9 | — |
| 11 | Consolidated implementation backlog | Waits for 10 | — |

The complete, copyable wording for all eleven reviews is in [prompts.md](prompts.md).

## What the three answers produced

The three completed reports contain many overlapping observations. Normalization
reduced them to 42 traceable outcomes:

- 28 potentially buildable product/accessibility/copy candidates: 14 `FUX`,
  11 `ADV`, and 3 `CPY`;
- 6 `FUD` usability or design questions that remain deferred;
- 8 `FOD` owner, legal, or external decisions that cannot be invented.

The exact evidence, deduplication and status of all 42 are in
[outcomes.md](outcomes.md). [reconciliation.md](reconciliation.md) explains
overlap with the original remediation programme and prevents double-counting.

Prompt 8's returned external-boundary review is preserved in
[answers/prompt-08-external-boundary.md](answers/prompt-08-external-boundary.md).
Its 62-row classification remains intact for provenance. Current-base
reconciliation records PB-12 as a current `PRODUCT-DEFECT` and PB-13 as a
partial duplicate of `CPY-002`; the six owner-question groups remain in the
answer. This does not add to the 42-outcome set or authorize implementation.

## Proposed packets and execution authority

[packets.md](packets.md) groups the 28 potentially buildable candidates into 14
cohesive future packets. Those groups are planning aids, not automatically approved
R-slices. Each still requires current-state reproduction, an explicit queue
admission, a disjoint lease, proportional red/green evidence and normal review.

Only `FU-06` has been separately authorized, implemented and accepted: mobile
administrator/advertiser access to the existing password-change and sign-out
controls, commit `a73556c`. All other proposed packets remain unimplemented.

## Continuation order

1. Finish prompts 1, 4, 6 and 7 against one stable accepted snapshot; Prompt 8 is
   answered and reconciled.
2. Reconcile later answers into this same folder and update the 42-outcome set rather
   than creating a parallel register.
3. Run prompt 9 using answers 1–8, then prompt 10 against that PRD.
4. Run prompt 11 last to produce the consolidated backlog.
5. Admit implementation packets only after the active R01–R60 remediation frontier
   is stable and exact dependencies are revalidated.

Raw audit claims are provenance, not product authority. Independently created user
sessions are outside this programme unless the owner explicitly adds a specific
result.
