# Prompt 9 — client-facing PRD and system guide

## Capture status

- Reviewer: Claude Opus 5, High effort.
- Source authority confirmed by the reviewer:
  `5f84194df6e9527fcdcbc25b3cb66c9c58697d07`.
- Mode: read-only in the existing `master` checkout; the reviewer reported no
  branch, worktree, commit, or file changes.
- Inputs: the reconciled Prompt 1–8 answers, `outcomes.md`, `reconciliation.md`,
  `packets.md`, the architecture and decision record, and current source.
- Purpose of this file: controller capture of the returned guide and its
  evidence boundary. It is not an implementation authorization and is not yet
  the client-approved document.

## Returned document structure

The reviewer produced a sixteen-section product/system guide covering:

1. the product, business goals, non-goals and recorded pilot shape;
2. the three implemented account roles and object-level separation of duties;
3. the platform modules, system context and module state dependencies;
4. the campaign lifecycle from enquiry through reporting and completion;
5. advertiser, driver and administrator/operations journeys;
6. campaign, creative, assignment, ledger, payout, application and vehicle
   statuses;
7. foreground-only tracking, offline capture and fail-closed boundaries;
8. quotations, billing, earnings, reconciliation, fraud, debt, payouts and
   reporting;
9. privacy, legal, device, provider and live-operation gates;
10. the division between client-supplied inputs and Terrax-operated work;
11. pending, blocked, rejected, unavailable, retry and recovery states;
12. a non-sensitive conceptual data flow;
13. tiered product gaps and proposed improvements;
14. launch-readiness boundaries;
15. support and escalation; and
16. a client-facing glossary.

It also supplied the requested eight Mermaid views: system context, module
dependency map, campaign lifecycle, advertiser journey, driver journey,
operations journey, state lifecycle and conceptual data flow.

## Truth-label contract

The guide explicitly distinguishes:

- `CONFIRMED IMPLEMENTED`: present in the accepted build, not proof of
  deployment, scale or live use;
- `IMPLEMENTED BUT EXTERNALLY GATED`: present but inactive until an approved
  value, provider, legal artefact or real-world process exists;
- `PROPOSED IMPROVEMENT`: a review recommendation, not built or scheduled;
- `VERIFY`: reported but not reproduced on a running system;
- `OWNER DECISION / EXTERNAL INPUT`: business, legal, commercial or operational
  authority the software must not invent; and
- `NO EVIDENCE`: searched for and not found.

The guide repeatedly refuses to claim deployment, live payments, production
tracking, legal/privacy approval, a connected provider or completed pilot
evidence.

## Material product synthesis

The returned guide preserves the accepted safety and authority model:

- no background tracking; the driver starts and ends capture and the app must
  remain foregrounded;
- offline capture is durable, while trip ending and stale-data surfaces remain
  fail-closed;
- campaign activation retains all funding, evidence, assignment, eligibility,
  creative and frozen-term gates;
- measurement and money are not fabricated when authority is missing;
- post-seal evidence is quarantined rather than silently merged;
- payout batches and payout corrections retain distinct-actor maker/checker
  controls;
- route data is not presented as person-level audience data; and
- provider, legal, commercial, support and real-world logistics inputs remain
  external gates.

The guide's highest-priority proposed improvements map back to the reconciled
root causes rather than creating a second backlog: account entry/recovery,
install guidance, foreground-capture warning and return summary, artwork/edit
recovery, rejection visibility, payment instructions, launch readiness,
creative-to-offer discovery, payout-batch assembly, quarantine operations,
measurement operations subject to the operating-model decision, approval-queue
reachability, activation preflight, support destinations and shared error-state
presentation.

## Evidence and uncertainty appendix

The response included a fifty-row internal evidence map. It cites current
symbols or prior reconciled audit evidence for major claims and keeps uncertain
claims labelled `VERIFY`. It also lists twenty-four owner/external inputs,
including commercial values, payment instructions, payout policy, upload and
installation-evidence policy, budget scope, support and recovery targets,
privacy/legal approvals, provider identities, product naming and the decision
on target-area coverage.

No new P0 was accepted. Urgent missing pilot-critical journeys remain P1 unless
an immediate security, privacy, safety or irreversible-money failure is
demonstrated.

## Controller reconciliation before Prompt 10

The guide is a strong synthesis draft, but its statements remain audit claims
until the adversarial review resolves the following:

1. **Completed-state contradiction.** The campaign and state diagrams show a
   normal transition into `COMPLETED`, while the evidence appendix says no
   production transition into completed campaign state was found. The diagram
   must either mark this as a proposed/unknown transition or remove it.
2. **Closed mobile-access gap.** Tier 2 still lists missing mobile account
   controls even though Appendix A acknowledges that `FU-06` closed the gap at
   `a73556c`. Prompt 10 must remove the stale backlog item after confirming it
   remains closed at the source authority.
3. **Activation count and atomicity.** “Roughly fifteen” activation conditions
   and “single locked transaction” are high-weight claims. Confirm the actual
   gates and that no advisory/out-of-transaction check is described as an
   enforced invariant.
4. **Foreground wording.** Source confirms visibility handling, but physical
   handset behavior and the assertion that capture stops “silently” still need
   device/manual evidence. Preserve the foreground-only decision regardless.
5. **Blocked-campaign presentation.** The claim that a blocked campaign appears
   as plain `Approved` depends on how downstream readiness failures and status
   chips interact. It remains a reproduction target, not settled client fact.
6. **Quotation detail omission.** The API schema contains line items, payment
   terms and production scope, while the advertiser panel appears not to render
   them. Confirm the complete current panel before promoting the claim.
7. **Universal audit wording.** “Every administrator action is written to an
   audit trail” is broader than the sampled evidence. Narrow it to the governed
   actions actually substantiated unless exhaustive route coverage proves it.
8. **Platform naming.** The guide openly uses “Cardvert” for the whole platform
   while current product copy calls Cardvert the driver app. This is an owner
   decision, so the client draft must not silently settle it.
9. **Pilot facts.** Abuja, ten vehicles, five advertisers, three months, hourly
   base/premium pay, one campaign per vehicle, prepaid standard terms and weekly
   payouts are recorded decisions, not achieved pilot results. Reconfirm the
   exact decision rows and keep the distinction explicit.
10. **Proposed versus current flow.** Every diagram must visually distinguish
    implemented paths, externally gated paths, verified gaps and proposed
    transitions; prose alone is insufficient where a diagram can imply current
    capability.

## Prompt 10 handoff supplied by the reviewer

The reviewer asked the adversarial pass to attack the activation claim,
foreground behavior, blocked-campaign status, quotation detail rendering,
negative evidence about completion, severity calibration, the already-delivered
mobile-access fix, platform naming, every `CONFIRMED IMPLEMENTED` statement and
the provenance of the recorded pilot facts. These are incorporated into the
controller reconciliation above.

## Disposition

`NEEDS ADVERSARIAL REVIEW`. Prompt 9 is complete and useful. It introduced no
new implementation authority, no justified new P0 and no reason to reopen the
accepted engineering programme. Prompt 10 must correct stale, contradictory or
over-broad client-facing claims before Prompt 11 may treat the PRD as a planning
source.
