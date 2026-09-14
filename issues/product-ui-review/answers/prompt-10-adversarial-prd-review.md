# Prompt 10 — adversarial review of the client PRD

## Capture status

- Reviewer: Claude Opus 5, High effort.
- Exact source authority: `5f84194df6e9527fcdcbc25b3cb66c9c58697d07`.
- Static, read-only review; no application, device, provider or test execution
  and no repository changes.
- Verdict: `NEEDS REVISION`. The guide is structurally useful but must not be
  shared until its accepted truth corrections are applied.

## Accepted corrections

| ID | Accepted correction | Disposition |
| --- | --- | --- |
| RC-01 | `COMPLETED` is defined and displayed for campaigns and assignments, but no production transition into it was found outside seed data. Diagrams must not present it as working. | `NO EVIDENCE`; owner/operations decision. |
| RC-02 | Remove mobile administrator/advertiser account controls from the backlog. FU-06 remains present at the audited HEAD. | Delivered at `a73556c`; retire `FUX-007`. |
| RC-03 | Replace “roughly fifteen activation conditions.” The reviewer enumerated 29 enforced preconditions and confirmed one request-scoped transaction with row/advisory locks and a single commit. Avoid a brittle numeral in the client guide. | Strengthened `CONFIRMED IMPLEMENTED`; PostgreSQL-specific locking caveat retained. |
| RC-04 | Hidden-page stop, wake-lock release, captured state and automatic resume on visibility return are source-confirmed. Delete “silently.” Driver perception and physical-handset behavior remain unverified. | Split `CONFIRMED` / `VERIFY`. |
| RC-05 | The campaign header can remain `Approved` while downstream readiness is unresolved, but the commercial panel shows readiness after terms acceptance. Narrow the page-wide claim. | Narrowed `CONFIRMED`. |
| RC-06 | The quotation contract returns line items, production scope, production cost and payment terms; the advertiser acceptance panel renders only reference, revision and three totals. | `ADV-006` becomes confirmed P1. |
| RC-07 | Replace “every administrator action is audited” with the evidenced scope: record-changing actions across roles are route-table checked; seven named exceptions have compensating evidence; reads are not covered. | Scope-corrected `CONFIRMED`. |
| RC-08 | “Cardvert” is used both for the driver app and the broader platform. The contradiction is source-confirmed but its resolution belongs to Terrax Media. | `CPY-001`: `OBSERVED / OWNER DECISION`. |
| RC-09 | Abuja, 10 vehicles, 5 advertisers, 3 months, 60% target, base/premium hourly pay, one campaign per vehicle, prepaid terms and weekly payout are recorded decisions/targets, not results. `payout_v3` is implemented; do not describe zone-tiered pay as unbuilt. | Recorded decisions plus external gates. |
| RC-10 | Every diagram must carry its own truth-class legend and distinguish built, externally gated, proposed, verify and no-evidence nodes/edges. | Required document correction, not a software slice. |
| RC-11 | Replace “During the Abuja pilot” with “In the planned Abuja pilot.” No pilot has launched. The same shipped-copy instance belongs to existing `CPY-002`. | Document correction; no new ID. |
| RC-12 | Automatic bank transfer is the approved model, but no provider is registered and no transfer has occurred. | `IMPLEMENTED BUT EXTERNALLY GATED`. |
| RC-13 | Legal/privacy approval is a prerequisite, not an accomplished fact; approved wording and retention periods do not yet exist. | `OWNER DECISION / EXTERNAL INPUT`. |
| RC-14 | Home-screen installation is a confirmed hard Start gate, while no in-product installation guidance was found. | Confirmed gate plus proposed P1 guidance; maps to `NX-02`. |
| RC-15 | The advertiser campaign page displays the verified driver payout total. Whether advertiser users should see Terrax Media's driver-cost base is a commercial decision. | Confirmed behavior plus owner decision; maps to `FOD-007`. |

The review's P0 labels for RC-01, RC-10, RC-11 and RC-12 are
**client-document truthfulness severities**, not new P0 software defects. RC-06
is the highest software/product P1 because a user can accept immutable
commercial terms without seeing material returned terms.

## Unresolved verification

- Physical-handset visibility behavior across Android/iOS app switching,
  screen lock, notification shade and calls.
- Whether the driver perceives that capture stopped and what appears on return.
- Running-system reproduction of an approved-but-unlaunchable campaign before
  commercial terms acceptance.
- Existing candidates not re-examined here: `FUX-003`, `FUX-010`, `FUX-011`,
  `FUX-013`, `FUX-014`, `ADV-002`, `ADV-003`, `ADV-004`, `ADV-008`, `ADV-009`,
  `ADV-011`, and `CPY-003`.

## Owner and external gates

Preserve rather than invent `EXT-PILOT-PERMITS`, `EXT-LEGAL-PRIVACY`,
`EXT-DISBURSEMENT-PROVIDER`, statutory company/invoice facts
(`EXT-Q28-COMPANY`), canonical product naming, advertiser visibility of driver
cost, approved support destinations, installation/removal logistics, commercial
values and the campaign-completion operating model. The existing
`FOD-001`–`FOD-008` and six Prompt 8 owner-question groups remain
non-executable.

## Duplicates and dismissals

- Raw enumerations/internal vocabulary remain `CPY-002`.
- Native confirmations remain `FUX-006`.
- UUID-only identity remains `FUX-005`.
- Mobile account controls are delivered and must not re-enter the backlog.
- Emoji navigation, broad typography preference, dashboard composition, payout
  information architecture and driver earnings hierarchy remain
  `FUD-001`–`FUD-006` evidence questions, not defects.
- “Zone-tiered base/premium pay is unbuilt” is false at this source authority.
- Automatic audit events for every 401/403 remain dismissed.
- Seventeen operational responsibilities do not imply seventeen RBAC roles.

## Required client-document rules

- Never imply deployment, a completed pilot, a live payment, connected provider
  or obtained legal/permit approval.
- Describe pilot numbers as decisions/targets with provenance.
- Identify the source surface behind each `CONFIRMED IMPLEMENTED` claim.
- Name the searched surface behind negative evidence.
- Keep external inputs and owner decisions visibly unsettled.
- Give every diagram an in-figure truth-class legend.
- Show campaign `ACTIVE` only as a side effect of first assignment activation.
- Show `COMPLETED` as `NO EVIDENCE`, not a working edge.
- Remove delivered mobile account access from every backlog.
- Keep engineering vocabulary out of the client-facing body.

The reduced glossary retains only Terrax Media, Cardvert with its naming caveat,
advertiser, driver, campaign, assignment, creative, offer/frozen terms,
activation, installation evidence, verified hours, base/premium rate, exclusion
zone, payout batch, hold, Campaign Performance Analysis, target-area coverage
and modelled exposure. Internal terms such as hashes, snapshots, maker-checker,
fail-closed, quarantine, ledger entries, formula versions, idempotency keys,
advisory locks and canonical receipts belong outside the client body.

## Sealed Prompt 11 handoff

Prompt 11 may consume only the accepted RC-01–RC-15 corrections, unresolved
`VERIFY` list, owner/external gates, explicit duplicate/dismissed list,
pre-existing reconciled outcomes, and source evidence at the immutable baseline.
It must not treat optional editorial improvements as defects, reopen FU-06,
claim zone-tiered pay is missing, create new IDs for duplicate symptoms, or turn
owner/external decisions into implementation.

Controller disposition: `ACCEPTED WITH CORRECTIONS`. Prompt 11 is safe to run
as the final deduplicating backlog synthesis.
