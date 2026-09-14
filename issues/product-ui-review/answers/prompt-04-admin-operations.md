# Prompt 4 — admin and operations workflow audit

## Provenance

- Reviewer: Claude Opus 5, High effort
- Audited source: `5f84194df6e9527fcdcbc25b3cb66c9c58697d07`
- Mode: isolated-worktree, read-only source audit
- Controller capture: 9 September 2026

## Executive result

The backend contains unusually strong audit, frozen-authority, maker/checker and
money controls. The admin product frequently fails to expose the information and
transitions an operator needs to use those controls. The strongest repeated root
cause is asking staff to type identifiers that no preceding screen reveals.

## Confirmed operational breaks

1. Approved creatives disappear from the only admin creative queue, while the
   assignment-offer form requires a free-text approved creative UUID. This breaks
   the normal campaign-to-offer handoff.
2. Payout-batch creation requires available ledger-entry UUIDs, but the admin
   payout screen does not display them. Debt allocation returns the needed
   `remainder_entry_ids`, which its frontend action discards; the debt-balance read
   endpoint and batch-detail endpoint are also unused. The product cannot assemble
   a normal payout batch without an out-of-product data lookup.
3. Manual driver-contact tasks and phone-verification challenges have complete
   admin APIs precisely to support the current human-provider fallback, but no
   staff worklist exists.
4. Assignment activation enforces roughly fifteen legitimate prerequisites but
   offers no readiness projection or links to the responsible corrective screen.
   Staff discover one failed prerequisite at a time through raw conflicts.
5. Admin approvals and planning-source pages make many dependent reads and allow
   one failed record to replace the whole work queue rather than degrading that
   item.
6. Creating an advertiser user and then failing organization creation leaves an
   account without an organization. The recovery message tells staff to repeat a
   form that will then fail on duplicate email; no standalone organization creation
   flow is linked.
7. Invoice-correction idempotency is undermined by generating the correction
   reference during page render. A lost response or second tab can submit a new key
   and create a second correction instead of replaying the first intent.
8. Operator date formatting omits an explicit timezone, while assignment expiry is
   entered as `datetime-local` and converted on the server. The displayed and
   persisted instant can depend on the server timezone rather than the operator's
   Lagos intent.
9. Billing/invoice reconciliation uses a formatter that rounds values above
   ₦1,000 to zero decimal places even though an exact money formatter exists.
10. Sensitive NIN reveal is a one-click action with a hard-coded purpose; the value
    remains visible in the DOM without a hide control. The backend audit exists,
    but the UI supplies neither meaningful purpose capture nor proportionate
    privacy friction.

## Supported usability and truthfulness findings

- The admin landing page reports entity totals rather than actionable queues, the
  admin notification bell has no observed admin producers, and navigation has no
  work counts. The exact dashboard redesign remains an operator-validation choice.
- Driver, vehicle, assignment, fraud and evidence records often use truncated UUIDs
  instead of names, plates or campaign identity. This reinforces `FUX-005`.
- Approval, submission and suspension copy sometimes describes work the action did
  not perform. These instances reinforce `CPY-002` rather than creating separate
  findings.
- Audit APIs support actor, entity and time-range filters that the audit page omits.
  This extends `FUX-010`/`FUX-014` with a concrete low-cost capability.
- PENDING-only newest-first application review, missing decided history, silent
  100-item caps and missing filters create starvation or discoverability risk.
- Irreversible fraud and money actions need record-aware review/confirmation. This
  reinforces `FUX-006`.

## Not admitted as immediate implementation

- Seventeen documented operational responsibilities do not by themselves prove
  the product needs seventeen RBAC roles. The actual separation-of-duty policy is
  an owner/security decision; existing distinct-actor money checks must remain.
- A browser DSR console is not assumed necessary where the approved operating model
  is an audited runbook/API process.
- Invoice issuance, external acceptance, providers and live deployment remain
  external/owner-gated where Prompt 8 says authority is absent.
