# W4-04A role training preparation

These provider-neutral materials prepare a later facilitator to introduce
Cardvert's built admin, advertiser, driver, and operator tasks. They describe
repository truth at the Package 9 preparation boundary; they are not attendance,
approval, user feedback, or operational evidence.

W4-04A remains incomplete: facilitated rehearsal, user acceptance, and live operation have not occurred.

`EXT-RELEASE-ENV`, `EXT-STAGING-APPROVAL`, and `EXT-OPERATIONS-OWNER` remain unresolved live-only gates.

No named person, provider, account, domain, credential, production value,
approval, or real evidence is supplied here. A future facilitator must replace
role placeholders only in the protected operating record after the applicable
authority exists; repository examples must remain synthetic.

## Audience and ownership placeholders

| Placeholder | Responsibility | This preparation does not establish |
| --- | --- | --- |
| `<FACILITATOR_ROLE>` | Guides the role tasks and records later observations. | A trained facilitator, rehearsal result, or acceptance. |
| `<OPERATIONS_OWNER_ROLE>` | Receives operational escalation after `EXT-OPERATIONS-OWNER` is resolved. | A named owner or on-call rota. |
| `<PRIVACY_DECISION_ROLE>` | Makes approved privacy/legal decisions outside the platform-operator role. | Legal advice, notice wording, retention authority, or breach-notification decisions. |
| `<MONEY_REVIEW_ROLE>` | Reviews payout/fraud/correction exceptions under separation of duties. | Permission to change formulas, approve one's own work, or submit funds. |
| `<SECURITY_INCIDENT_ROLE>` | Coordinates technical containment and recovery. | Provider access, credential custody, or authority to declare closure. |

## Prepared materials

- [Role-task inventories](role-task-inventories.md) maps each role to actual
  browser entry paths, permitted tasks, forbidden boundaries, and source files.
- [Operator procedures](operator-procedures.md) covers privacy/DSR, KYC, fraud,
  payout, reporting, and incidents with fail-closed ordering and synthetic-only
  rehearsal notes.
- The existing [operations runbook](../runbook.md),
  [DSR runbook](../data-subject-request-runbook.md),
  [privacy operating model](../privacy-operating-model.md), and
  [release operations](../w4-03a-release-operations.md) remain authoritative for
  their owned procedures. These training notes summarize entry points; they do
  not replace those sources.

## How a later facilitator uses this pack

1. Confirm the release, staging approval, and receiving-operator gates in the
   protected operating record. If any is unresolved, use synthetic data only and
   do not record user acceptance.
2. Assign participants by role placeholder. Never share credentials or use one
   participant's session to demonstrate another role.
3. Work through the inventory for one role at a time. Record observations
   outside the repository using non-sensitive task identifiers.
4. Exercise an operator procedure only in an explicitly approved disposable or
   release-candidate environment. Apply every listed stop condition.
5. Route unresolved results to the named role after its external gate is
   satisfied. Preparation alone never turns a placeholder into an owner.

## Focused audit

Repository command: `python3 scripts/validate_w404a_training.py`

The command checks required role/domain coverage, actual role-scoped page
routes, the common procedure schema, local links, repository command targets,
the three live-only gates, and prohibited completion/live claims. It reads
files only and does not exercise product, provider, or deployment state.
