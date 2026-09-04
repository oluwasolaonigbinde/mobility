# Controller Opus follow-up audit reconciliation

## Scope and authority

This note reconciles only the three controller-dispatched follow-up audits
listed as CTL-CLD-01 through CTL-CLD-03 in `issues/audit-manifest.md`. It does
not verify their claims, admit work, alter the executable package queue, or
turn suggested wording and designs into product authority. The reports audited
the later `3832cff` working snapshot (with CTL-CLD-03 also reporting
`HEAD 25925e2`), whereas the 115 normalized first-pass candidates audited
`637841d95493bcc24334356da42097fa53a5d16f`.

The later-snapshot normalization pass is now recorded separately in
`../findings/controller-opus-follow-up-findings.md`, with dependency and likely
lease design in `controller-opus-follow-up-remediation.md`. It created 42
provenance-preserving candidates: 28 behavioral/copy corrections, 6 usability
deferrals, and 8 owner decisions. The closed 14-source first-pass set remains
unchanged; none of these candidates is silently inserted into PKG-10 or the
R01-R60 executable queue.

## Existing-candidate and slice overlap

| Follow-up evidence group | Existing finding/slice relationship | Reconciliation |
| --- | --- | --- |
| Reporting caveats, internal measurement vocabulary, raw authority identifiers, synthetic/uncalibrated headline values, and fail-closed report presentation (CTL-CLD-01 F22–F23; CTL-CLD-02 D1–D4; CTL-CLD-03 D12–D14) | Partial overlap with MET-001, MET-004, MET-006 and REP-002; R47 owns frozen caveat/method disclosure and R52 owns the contract-derived advertiser copy guard. | Reuse those IDs only for the exact already-normalized caveat/method/copy-guard boundaries. Presentation dead ends, synthetic ROI visibility, support routing, and in-flight report expectations are distinct unnormalized claims. |
| Cross-format formatting and human-readable report units (CTL-CLD-01 F23–F24 and D10) | Partial overlap with REP-003 / R48. | R48 can consume only parity/formatting evidence already inside its typed-projection contract. It does not own a general UX formatting pass. |
| Planning-source wording and opaque IDs/evidence (CTL-CLD-01 F13; CTL-CLD-03 planning-sources findings) | AUD-006 concerns a specific lifecycle promise; R44/AUD-005 concerns browser idempotency; R40 concerns governed audience inputs. | None of those existing slices owns planning-source information architecture, labels, UUID presentation, or explanatory copy. Treat these as later-snapshot normalization gaps. |
| Mobile sign-out reachability (CTL-CLD-01 F37) | AUT-004 / R11 owns durable global logout and refresh-race safety. | Reachability at mobile widths is adjacent but not equivalent. It needs explicit normalization or a scoped acceptance amendment before being assigned to R11. |
| Advertiser commercial wording and quotation display (CTL-CLD-02 commercial findings; CTL-CLD-03 D7–D10) | COM-003 and COM-005 / R25 own latest quotation and canonical waiver evidence; R47 owns methodology disclosure, not commercial UX. | Quotation itemisation, visible success confirmation, change-preview truthfulness, payment guidance, and zone-copy consistency are not covered by the existing commercial integrity slices. |
| Notification wording and routing (CTL-CLD-01 F42; CTL-CLD-02 E1–E6; CTL-CLD-03 D6 and D15) | GOV-006 / R15 owns job/service authority and retry/terminal transitions. | Neutral subject wording, campaign naming, destination links, and rejection-event coverage are separate product/communications claims and require normalization. |
| Driver assignment/earnings presentation and evidence artefacts (CTL-CLD-01 F29–F34; CTL-CLD-02 C-series) | Existing OFF and MON slices protect capture and money authority; none owns the driver presentation described here. | Do not absorb these into offline or money safety work. Preserve frozen/evidence retrievability while separately deciding what may be relocated or removed from driver screens. |
| Advertiser exposure/coverage promises and driver-payout economics shown to advertisers (CTL-CLD-02 D4; CTL-CLD-03 D11, D13 and trust risks 1–3) | MET-001/MET-004 and R47 are adjacent measurement-disclosure work. | The alleged target-area promise gap, synthetic ROI rendering, map semantics, and advertiser-versus-driver economics are distinct claims requiring current-state verification and product authority. |

## Missing normalization

The follow-up reports contain material claim families with no corresponding
first-pass candidate or remediation slice:

1. Advertiser journey completion: no self-service advertiser entry, payment
   instructions/invoice document, launch-readiness view, support path, or
   completion moment.
2. Campaign and creative repair: no campaign edit route, no add/replace creative
   flow after creation, rejection reasons not surfaced, and rejection events
   allegedly not notified.
3. Operator task completion: unreachable approval rows, evidence hidden behind
   popup-sensitive flows, absent entity detail views, opaque actor/object IDs,
   and audited actions confirmed without record identity.
4. Cross-role interface quality: raw enum/status strings, inaccessible or
   unlabelled controls, measured theme-contrast failure, mobile table/action
   reachability, absent search/sort, and driver assignment request fan-out.
5. Information architecture: payout submodules, password changes, advertiser
   campaign views, notifications, and cross-module records lack persistent or
   contextual navigation.
6. Cross-surface copy system: the HTML report's voice guide, prohibited-term
   list, blocked/error patterns, terminology rules, and mechanical string bugs
   extend well beyond MET-006's advertiser measurement vocabulary guard.

These families are now atomized in the separate follow-up register. Reused
first-pass IDs are explicitly identified there, design/usability proposals are
deferred, and missing owner/legal authority is retained as a decision rather
than converted into implementation work.

## Product, legal, and usability decisions retained as gates

The sources explicitly withhold authority for rewriting compliance negations,
changing legal/privacy disclaimers, deciding whether evidence hashes are a
customer-facing trust feature, removing the driver capability probe, defining
advertiser registration/payment/support ownership, and adopting large
structural redesigns without usability validation. Those are decision inputs,
not fixes authorized by these reports. The copy audit's legal queue and the UX
audit's owner-decision/usability sections remain the evidence pointers.
