# W4-04B-P1 support, SLA, and escalation template

Status: **PREPARATION ONLY**. No support rota, production SLO, response time,
availability target, recovery target, or escalation promise is approved. Every
target below remains proposed until recorded owner approval.

## Support ownership placeholders

| Support function | Role placeholder | Boundary |
| --- | --- | --- |
| Intake and record hygiene | `<SERVICE_SUPPORT_COORDINATOR_ROLE>` | Records sanitized references only; does not diagnose by copying payloads. |
| Operational triage | `<OPERATIONS_OWNER_ROLE>` | Remains unresolved until `EXT-OPERATIONS-OWNER`. |
| Incident command | `<INCIDENT_COMMANDER_ROLE>` | Contains first; cannot close privacy/money/security decisions alone. |
| Security and custody | `<SECURITY_OWNER_ROLE>` | Uses the protected access/custody system, never Git. |
| Privacy/legal | `<PRIVACY_DECISION_ROLE>` | Supplies notification/retention/live-use decisions only after approval. |
| Money | `<MONEY_CHECKER_ROLE>` | Preserves maker/checker/reconciler separation and ledger authority. |
| Reporting/method | `<REPORT_METHOD_AUTHORITY_ROLE>` | Keeps live issuance closed without current method/privacy authority. |

## Proposed SLA fields

| Target | Proposed placeholder |
| --- | --- |
| Support coverage window | `<PROPOSED — OWNER APPROVAL REQUIRED>` |
| Initial acknowledgement | `<PROPOSED — OWNER APPROVAL REQUIRED>` |
| Triage target | `<PROPOSED — OWNER APPROVAL REQUIRED>` |
| Status-update cadence | `<PROPOSED — OWNER APPROVAL REQUIRED>` |
| Escalation target | `<PROPOSED — OWNER APPROVAL REQUIRED>` |
| Service restoration target | `<PROPOSED — OWNER APPROVAL REQUIRED>` |
| Recovery-point target | `<PROPOSED — OWNER APPROVAL REQUIRED>` |
| Recovery-time target | `<PROPOSED — OWNER APPROVAL REQUIRED>` |
| Availability objective | `<PROPOSED — OWNER APPROVAL REQUIRED>` |
| Evidence-retention target | `<PROPOSED — OWNER APPROVAL REQUIRED>` |

Do not replace a placeholder in Git. A future approved operating record must
capture the target, unit, measurement source, coverage/calendar rules,
exclusions, approver, effective revision, and review date. Local load ceilings
and test timeouts are regression controls, not production SLOs.

## Qualitative severity template

| Severity | Qualitative trigger | Immediate boundary | Required escalation roles |
| --- | --- | --- | --- |
| Critical | Active or suspected sensitive exposure, money-finality disagreement, unrecoverable release authority, or continuing unauthorized processing. | Contain affected paths; keep traffic, payout, report, or integration action stopped. | `<INCIDENT_COMMANDER_ROLE>`, `<SECURITY_OWNER_ROLE>`, and the affected privacy/money owner. |
| High | Material service degradation, failed recovery evidence, worker/storage backlog, or bounded integrity mismatch without confirmed continuing exposure. | Preserve authority and evidence; block the affected workflow. | `<OPERATIONS_OWNER_ROLE>`, affected domain owner, and `<EVIDENCE_CHECKER_ROLE>`. |
| Standard | Bounded user-impacting defect with intact authority and a safe unavailable path. | Record, reproduce safely, and route without overriding gates. | `<SERVICE_SUPPORT_COORDINATOR_ROLE>` and affected service owner. |
| Request | Question, access request, or planned change with no incident evidence. | Keep it out of incident state unless evidence changes. | `<SERVICE_SUPPORT_COORDINATOR_ROLE>` and the owning decision role. |

Severity does not supply a clock, legal deadline, notification decision,
financial authority, or permission to bypass a fail-closed path.

## Support record template

- record reference: `<PROTECTED_SUPPORT_POINTER>`
- environment classification: `<APPROVED_ENVIRONMENT_CLASSIFICATION>`
- affected release revision: `<SANITIZED_REVISION_REFERENCE>`
- first/last observed time: `<UTC_TIME_PLACEHOLDER>`
- affected domain: `<DOMAIN_PLACEHOLDER>`
- sanitized correlation references: `<SANITIZED_CORRELATION_POINTERS>`
- authority checked: `<AUTHORITATIVE_STATE_POINTER>`
- containment state: `<CONTAINMENT_PLACEHOLDER>`
- escalation roles: `<ROLE_PLACEHOLDERS_ONLY>`
- recovery evidence: `<PROTECTED_EVIDENCE_POINTER>`
- closure authority: `<PLACEHOLDER — NOT ASSIGNED>`

Never include names, contacts, credentials, account identifiers, private URLs,
raw logs/payloads, KYC/bank values, precise GPS, fraud evidence, object keys,
presigned URLs, report contents, or backup plaintext.

## Escalation flow

1. Intake records only sanitized references and current authority.
2. Triage classifies the affected domain and applies its documented stop rule.
3. Containment precedes diagnosis when sensitive exposure, money integrity,
   report integrity, or release authority is uncertain.
4. Escalate to the distinct role placeholders. Missing roles keep the case open;
   they never justify silent closure.
5. Recover through existing request/job/release identities and the owning
   runbook; never create replacement state to hide uncertainty.
6. Require an independent evidence check before an authorized closure decision.

| Domain | Stop/escalate condition | Required roles | Authoritative source |
| --- | --- | --- | --- |
| Privacy | Suspected unauthorized processing, missing retention/DSR authority, or breach uncertainty. | `<PRIVACY_DECISION_ROLE>`, `<SECURITY_OWNER_ROLE>`, `<INCIDENT_COMMANDER_ROLE>` | [Privacy operating model](../privacy-operating-model.md#breach-register-and-escalation) |
| Security/credentials | Exposure, custody uncertainty, failed rotation/revocation, or unsafe secret location. | `<SECURITY_OWNER_ROLE>`, `<CREDENTIAL_CUSTODIAN_ROLE>`, `<CREDENTIAL_CHECKER_ROLE>` | [Release incident playbooks](../w4-03a-release-operations.md#incident-playbooks) |
| Money | Identity/value/currency drift, failed conservation, role collapse, or absent provider finality. | `<MONEY_MAKER_ROLE>`, `<MONEY_CHECKER_ROLE>`, `<MONEY_RECONCILER_ROLE>` | [Payout replay preparation](../pilot-operations/operations-pack.md#domain-payout-replay) |
| Reporting | Frozen-authority mismatch, privacy/method revocation, partial pair, tamper, or storage failure. | `<REPORT_METHOD_AUTHORITY_ROLE>`, `<PRIVACY_DECISION_ROLE>`, `<EVIDENCE_CHECKER_ROLE>` | [Report replay preparation](../pilot-operations/operations-pack.md#domain-report-replay) |
| Release/recovery | Revision/config mismatch, failed readiness/restore/compatibility, or uncertain traffic state. | `<RELEASE_OPERATOR_ROLE>`, `<INCIDENT_COMMANDER_ROLE>`, `<SECURITY_OWNER_ROLE>` | [Release recovery](../w4-03a-release-operations.md#recovery-never-downgrade) |
