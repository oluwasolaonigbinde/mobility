# Prompt 1 — end-to-end system-flow audit

## Provenance

- Reviewer: Claude Opus 5, High effort
- Audited source: `5f84194df6e9527fcdcbc25b3cb66c9c58697d07`
- Mode: isolated-worktree, read-only source audit
- Controller capture: 9 September 2026

This is a structured capture of the completed reviewer report, not a new
implementation authority. The controller independently checked the highest-impact
claims against the same accepted source before admitting them to the reconciliation
below.

## Executive result

The central commercial chain is connected and strongly governed: advertiser
campaign creation, review, creative approval, frozen targeting and offer terms,
driver acceptance, installation evidence, activation, trip evidence, sealing,
payout calculation, earnings ledger and payout-batch authority all exist. The
review nevertheless found several user or operator transitions where the backend
authority exists but the next required product surface does not.

## Material findings

1. A self-registered driver is created with an intentionally unreachable password
   hash. The public flow promises a later invitation, but the source contains no
   corresponding driver-invitation notification or account-activation path and the
   frontend has no password-reset UI even though reset APIs exist. This does not
   mean seeded or separately provisioned drivers cannot sign in.
2. Post-seal GPS batches can be quarantined and the backend exposes audited admin
   apply/discard routes, but there is no admin quarantine worklist or resolution
   screen. The durable evidence is preserved; the operational transition is
   missing.
3. Measurement-run creation exists as an admin API and synthetic script/test
   capability, but no operator product surface starts or monitors a run. Advertiser
   reporting can therefore remain empty unless staff use a non-product channel.
4. Driver person/payee and vehicle evidence support governed new revisions, but the
   signed-in driver product does not expose a normal renewal/resubmission journey.
5. `COMPLETED` campaign and assignment states are represented in types and seed
   data, but no production service or job was found that performs the normal
   completion transition. Payout-window enforcement still limits money exposure;
   the gap is principally lifecycle, reporting and removal guidance.
6. Other API-only or unlinked internal capabilities include budget-policy resume,
   invoice issuer-profile setup, segment-delivery approval, external quotation
   acceptance, manual contact/phone worklists, payout remediation and report
   issuance. These are not all automatically defects: Prompt 4 determines which
   are required for the staffed operations workflow, while Prompt 8 retains any
   missing owner or external decisions.
7. `/landing` is not the normal product entry: `/` routes by authentication state,
   landing calls to action are enquiry links, and `/apply` is otherwise discoverable
   mainly by direct URL. Whether to change this remains tied to the advertiser and
   driver acquisition decisions.

## Calibration

- The report's P0 labels are not accepted verbatim. Missing self-service entry or
  an operator worklist is normally a P1 launch blocker unless it creates immediate
  safety, privacy or financial harm.
- “Quarantined earnings are stranded” is too broad without proving that the late
  batch changes a sealed payout. The accepted claim is the missing resolution
  surface and the resulting inability to adjudicate preserved evidence.
- “Measurement is always empty” is also narrowed: the capability can be invoked
  outside the GUI, but the staffed product workflow is incomplete.
- An endpoint without a browser page is not inherently defective. Admission
  depends on the documented operating model and Prompt 8 responsibility boundary.
