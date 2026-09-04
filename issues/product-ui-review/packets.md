# UI/product-review proposed packets

## Authority

This is a dependency and likely-lease design for the 42 candidates in
`outcomes.md`. It does not amend
`docs/progress.md`, authorize implementation, or insert work into R01-R60.
Every executable packet requires current-state reproduction, an approved queue
amendment, disjoint ownership, proportional red/green evidence, and the
repository's normal review gates.

## Proposed future packets

| Packet | Candidate IDs | Dependencies | Likely lease | Evidence target |
| --- | --- | --- | --- | --- |
| FU-01 approval reachability | FUX-001, FUX-013 | Accepted campaign/creative review contracts | approvals page/action components and focused tests; API schemas only if pagination is missing | More than 25 records all reachable; pending state attaches to the invoked action. |
| FU-02 evidence review | FUX-002 | Accepted private-object/signing authority | installation review action/view components and tests | Evidence visible without popup authority; blocked retrieval produces a useful error. |
| FU-03 safe application decisions | FUX-003 | Current onboarding terminal-state authority | driver-applications page, decision components/tests | No horizontal decision loss; reject requires explicit reason and record-aware confirmation. |
| FU-04 operator identity | FUX-005, FUX-014 | Stable tenant/RBAC contracts; API expansion reviewed before UI | named list schemas/services/routes plus admin list surfaces and tests | Search finds off-page records; every addressed actor/object has a human label while ID remains retrievable. |
| FU-05 audited dialogs | FUX-006 | Accepted mutation and audit contracts | shared dialog primitive, named action components/tests | Record and reason are reviewable before commit; no native prompt remains. |
| FU-06 responsive account access | FUX-007 | AUT-004 complete | app shell/account control and responsive tests | Logout/change-password reachable at 375px without altering durable logout semantics. |
| FU-07 driver list efficiency | FUX-008 | Stable installation-evidence read authority | driver assignment aggregation/API if needed, page and tests | Bounded request count and per-card degradation under one-source failure. |
| FU-08 notification usability | FUX-009, ADV-004 | GOV-006/R15 and current notification schema | notification event service/API, notification center/templates/tests | Cached UI remains during refetch; actionable events name and link the campaign without false audits. |
| FU-09 accessibility corrections | FUX-010, FUX-011 | Final accepted theme bytes | audit filters, shared Button usage, theme/a11y tests | Programmatic labels and measured WCAG contrast at supported themes. |
| FU-10 truthful small states | FUX-004, FUX-012 | Stable payout/ledger read contracts | payout-batch page/test; driver home/page test | Batch action reachable at 375px; trip total is exact or omitted, never silently capped. |
| FU-11 advertiser editing | ADV-001, ADV-002, ADV-003 | Current campaign/creative state and private-upload contracts | advertiser campaign edit/creative routes, actions, components and focused API/UI tests | Draft/rejected campaign and creative recovery paths match copy; rejection reason is visible only to its tenant. |
| FU-12 commercial comprehension | ADV-005, ADV-006, ADV-007 | R25-R27 accepted commercial authority | campaign commercial/change components/actions/tests; no service changes unless a proved projection is missing | Success is visible; quotation facts render before acceptance; preview wording matches actual behavior. |
| FU-13 advertiser map/report states | ADV-008, ADV-009, ADV-010, ADV-011 | R47-R52 reporting chain and accepted activation/installation gates | advertiser campaign/map/report summary projections and UI/tests | Map label matches its data; live progress and launch/completion state remain distinct from frozen final authority. |
| FU-14 copy contract | CPY-001, CPY-002, CPY-003 | FOD-001/FOD-008 decisions; R52 copy guard | centralized terminology/field-label map, user-facing components/templates, copy tests | Public strings state condition and next action without leaking raw codes; protected legal text remains intact. |

Packets FU-01-FU-12 are mutually parallel only where their exact leases remain
disjoint after plan review. FU-13 must wait for the reporting chain because R47
and later slices own the same projections and UI. FU-14 follows owner/legal
decisions and should run after surface-specific packets so it does not create
wide merge churn. FU-04 is deliberately broad and should be split by role if
its verified API lease overlaps other active work.

## Non-executable dispositions

- `FUD-001` through `FUD-006` remain a usability-research backlog. They may
  provide acceptance evidence to a later packet but are not implementation
  authority.
- `FOD-001` through `FOD-008` remain owner/legal/external decisions. No default
  wording, bank detail, support destination, public metric promise, evidence
  visibility rule, or instrumentation policy may be invented.
- Existing candidates `AUT-004`, `AUD-006`, `MET-001`, `MET-002`, `MET-004`,
  `MET-006`, `REP-002`, and `REP-003` keep their existing queue ownership; the
  follow-up reports are additional provenance only.

## Admission order

1. Reproduce each `VERIFY` candidate on the then-current accepted SHA and close
   false/stale claims without code.
2. Resolve FOD decisions that gate a packet; retain unresolved decisions rather
   than weakening the packet.
3. Admit small independent packets first (FU-01, FU-02, FU-05, FU-06, FU-09,
   FU-10) when the executable queue permits.
4. Admit campaign/commercial packets after their underlying authority remains
   stable; serialize generated-contract changes.
5. Admit FU-13 only after R47-R52, then FU-14 after final wording authority.
6. Reconcile all 42 IDs to verified `COMPLETE`, `FALSE/STALE`, `DEFER`, or a
   named unresolved decision; do not close them by packet association.
