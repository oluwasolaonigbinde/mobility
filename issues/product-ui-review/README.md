# Cardvert UI and product-review programme

This folder is the single home for the eleven UI/product-review prompts, their
verbatim answers, normalized outcomes, decision boundaries, and proposed future
implementation packets. It is deliberately separate from the original 14-source
engineering audit corpus.

## Programme status

| # | Review | Status | Answer |
| ---: | --- | --- | --- |
| 1 | End-to-end system flow | Answered and reconciled | [captured answer](answers/prompt-01-system-flow.md) |
| 2 | UI ergonomics and information architecture | Answered and normalized | [verbatim answer](answers/prompt-02-ui-ergonomics.md) |
| 3 | Human-facing language and AI residue | Answered and normalized | [verbatim answer](answers/prompt-03-copy-voice.html) |
| 4 | Admin and operations workflow | Answered and reconciled | [captured answer](answers/prompt-04-admin-operations.md) |
| 5 | Advertiser journey | Answered and normalized | [verbatim answer](answers/prompt-05-advertiser-journey.md) |
| 6 | Driver journey | Answered and reconciled | [captured answer](answers/prompt-06-driver-journey.md) |
| 7 | Errors, gates and state transitions | Answered and reconciled | [captured answer](answers/prompt-07-errors-states.md) |
| 8 | Client-owned approvals versus system-owned UX | Answered and reconciled | [verbatim answer](answers/prompt-08-external-boundary.md) |
| 9 | Client-facing PRD and visual-system guide | Answered and reconciled | [captured answer](answers/prompt-09-client-prd.md) |
| 10 | Adversarial PRD review | Answered and reconciled | [captured answer](answers/prompt-10-adversarial-prd-review.md) |
| 11 | Consolidated implementation backlog | Ready — GPT-6 Pro via GitHub plus evidence packet | — |

The complete, copyable wording for all eleven reviews is in [prompts.md](prompts.md).

## What prompts 1–8 produced

The first three completed reports reduced their overlapping observations to 42
traceable outcomes:

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

Prompts 1, 4, 6 and 7 were then run concurrently on accepted source
`5f84194df6e9527fcdcbc25b3cb66c9c58697d07` with disjoint scopes. Their
controller captures preserve the reports' material source-backed findings and
severity calibration. The cross-report reconciliation in `outcomes.md` groups
these additions by root cause and explicitly reuses the existing 42 outcomes
where applicable; it does not treat every missing browser consumer as a defect.

## Proposed packets and execution authority

[packets.md](packets.md) groups the 28 potentially buildable candidates into 14
cohesive future packets. Those groups are planning aids, not automatically approved
R-slices. Each still requires current-state reproduction, an explicit queue
admission, a disjoint lease, proportional red/green evidence and normal review.

Only `FU-06` has been separately authorized, implemented and accepted: mobile
administrator/advertiser access to the existing password-change and sign-out
controls, commit `a73556c`. All other proposed packets remain unimplemented.

## Prompt 9 reconciliation

Prompt 9 produced a substantial client-facing PRD/system-guide draft with all
eight requested diagrams, a fifty-row evidence map, explicit truth labels and a
twenty-four-item owner/external-input appendix. The controller accepted it as a
useful synthesis source, not as a client-ready artifact. Its capture records ten
targets for the adversarial pass, including a completed-state diagram/text
contradiction, a stale mobile-access backlog item already closed by `FU-06`, and
several claims that must be narrowed or reproduced before they reach a client.

## Prompt 10 reconciliation

The adversarial review returned `NEEDS REVISION` and a sealed Prompt 11 handoff.
It accepted fifteen truth corrections, retired delivered `FUX-007`, promoted
`ADV-006` from `VERIFY` to a confirmed P1 commercial-consent gap, confirmed the
live naming contradiction while preserving the owner decision, and rejected
several duplicates and design preferences. Its P0 labels concern client-document
truthfulness; it found no new P0 software defect.

## Continuation order

1. Run Prompt 11 in GPT-6 Pro against GitHub commit `5f84194` and the exported
   local evidence packet.
2. Reconcile its proposed backlog into the existing outcome families before
   admitting any implementation package.
3. Admit implementation packets only after the active R01–R60 remediation frontier
   is stable and exact dependencies are revalidated.

Raw audit claims are provenance, not product authority. Independently created user
sessions are outside this programme unless the owner explicitly adds a specific
result.
