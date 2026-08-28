# W4-04B-P1 roles and responsibilities skeleton

Status: **PREPARATION ONLY**. Every role is a placeholder. Assignment, rehearsal,
acceptance, handover, credential transfer, and live operation are **NOT
PERFORMED**.

RACI means responsible, accountable, consulted, and informed. It describes a
future separation of duties after approved assignments exist; it does not grant
permissions or turn a repository role into a legal, financial, security, or
operating authority.

## Role registry

| Role placeholder | Independence requirement | Build-ready duty | External/live boundary |
| --- | --- | --- | --- |
| `<BUSINESS_ACCOUNTABLE_ROLE>` | Separate from technical implementers and checkers. | Reviews prepared scope and unresolved gates. | May accept only after approved evidence, never from this pack. |
| `<OPERATIONS_OWNER_ROLE>` | Distinct named receiving role required by `EXT-OPERATIONS-OWNER`. | Reviews runbooks, queues, stops, and evidence templates. | Owns later operating decisions only after assignment. |
| `<RELEASE_OPERATOR_ROLE>` | Separate from the independent release checker. | Understands exact revision, preflight, backup, recovery, and traffic ordering. | Executes only in an approved client-owned environment. |
| `<SERVICE_SUPPORT_COORDINATOR_ROLE>` | Cannot override domain decision owners. | Routes sanitized support records and preserves status. | Uses only owner-approved coverage, channels, and targets. |
| `<INCIDENT_COMMANDER_ROLE>` | Separate from affected-system implementer where practicable. | Coordinates containment and evidence preservation. | Cannot declare privacy, money, or recovery closure without required authorities. |
| `<SECURITY_OWNER_ROLE>` | Separate from credential custodians when approving access. | Reviews least privilege, rotation, revocation, and recovery evidence. | Authorizes security actions only through the protected operating record. |
| `<PRIVACY_DECISION_ROLE>` | Separate from platform operations. | Reviews privacy gates, DSR, retention, and breach templates. | Supplies legal/privacy decisions only after `EXT-LEGAL-PRIVACY`. |
| `<MONEY_MAKER_ROLE>` | Must differ from checker and reconciler. | Prepares a frozen synthetic correction/batch/instruction. | Cannot approve, reconcile, submit, or mark paid. |
| `<MONEY_CHECKER_ROLE>` | Must differ from maker and reconciler. | Checks identity, value, currency, authority, and conservation. | Cannot self-approve or invent provider/bank evidence. |
| `<MONEY_RECONCILER_ROLE>` | Must differ from maker and checker. | Reconciles immutable provider-neutral evidence. | Cannot manufacture provider finality or rewrite history. |
| `<REPORT_METHOD_AUTHORITY_ROLE>` | Separate from report operator and advertiser requester. | Reviews methodology, provenance, disclosure, and correction templates. | Live issuance remains closed until report/privacy approvals exist. |
| `<EVIDENCE_RECORDER_ROLE>` | Must differ from evidence checker. | Records sanitized pointers, hashes, times, and source authority. | Cannot store protected evidence or credentials in Git. |
| `<EVIDENCE_CHECKER_ROLE>` | Must differ from evidence recorder. | Checks completeness, conservation, classification, and redaction. | Cannot convert missing evidence into closure. |
| `<TRAINING_FACILITATOR_ROLE>` | Cannot accept on behalf of participants or owners. | Guides role-specific synthetic exercises. | Records no attendance, competence, or acceptance until approved rehearsal. |
| `<CREDENTIAL_CUSTODIAN_ROLE>` | Must differ from credential checker. | Prepares protected inventory and custody evidence pointers. | Holds values only in the approved secret/custody system. |
| `<CREDENTIAL_CHECKER_ROLE>` | Must differ from credential custodian. | Verifies least privilege, rotation, revocation, recovery, and redaction. | Cannot receive or approve values through this repository. |
| `<BRAND_RELEASE_APPROVER_ROLE>` | Separate from artifact author. | Reviews neutral asset and release-readiness gaps. | Final brand/release approval remains gated by `EXT-BRAND-APPROVAL`. |

## RACI workstream skeleton

| Workstream | Responsible role | Accountable role | Consulted role | Informed role | Current boundary |
| --- | --- | --- | --- | --- | --- |
| System documentation index | `<EVIDENCE_RECORDER_ROLE>` | `<OPERATIONS_OWNER_ROLE>` | `<EVIDENCE_CHECKER_ROLE>` | `<BUSINESS_ACCOUNTABLE_ROLE>` | Preparation can be checked; acceptance is external. |
| Release and recovery | `<RELEASE_OPERATOR_ROLE>` | `<INCIDENT_COMMANDER_ROLE>` | `<SECURITY_OWNER_ROLE>` | `<OPERATIONS_OWNER_ROLE>` | Provider-neutral rehearsal evidence exists; external run is gated. |
| Training | `<TRAINING_FACILITATOR_ROLE>` | `<OPERATIONS_OWNER_ROLE>` | `<PRIVACY_DECISION_ROLE>` | `<BUSINESS_ACCOUNTABLE_ROLE>` | Materials exist; facilitated rehearsal and acceptance are not performed. |
| Privacy and DSR | `<OPERATIONS_OWNER_ROLE>` | `<PRIVACY_DECISION_ROLE>` | `<SECURITY_OWNER_ROLE>` | `<BUSINESS_ACCOUNTABLE_ROLE>` | Build-only controls exist; legal/live authority is missing. |
| Money preparation | `<MONEY_MAKER_ROLE>` | `<MONEY_CHECKER_ROLE>` | `<MONEY_RECONCILER_ROLE>` | `<OPERATIONS_OWNER_ROLE>` | Synthetic/provider-neutral only; no transfer or settlement. |
| Reporting | `<OPERATIONS_OWNER_ROLE>` | `<REPORT_METHOD_AUTHORITY_ROLE>` | `<PRIVACY_DECISION_ROLE>` | `<BUSINESS_ACCOUNTABLE_ROLE>` | Reproducible build output exists; live issuance is gated. |
| Incident response | `<INCIDENT_COMMANDER_ROLE>` | `<OPERATIONS_OWNER_ROLE>` | `<SECURITY_OWNER_ROLE>`, `<PRIVACY_DECISION_ROLE>`, `<MONEY_CHECKER_ROLE>` | `<BUSINESS_ACCOUNTABLE_ROLE>` | Templates exist; live incident action and closure are not performed. |
| Credential custody | `<CREDENTIAL_CUSTODIAN_ROLE>` | `<SECURITY_OWNER_ROLE>` | `<CREDENTIAL_CHECKER_ROLE>` | `<OPERATIONS_OWNER_ROLE>` | Checklist only; custody and transfer are not performed. |
| Support and escalation | `<SERVICE_SUPPORT_COORDINATOR_ROLE>` | `<OPERATIONS_OWNER_ROLE>` | `<INCIDENT_COMMANDER_ROLE>` | `<BUSINESS_ACCOUNTABLE_ROLE>` | Proposed template only; no approved SLA or rota. |
| Brand/release acceptance | `<BRAND_RELEASE_APPROVER_ROLE>` | `<BUSINESS_ACCOUNTABLE_ROLE>` | `<OPERATIONS_OWNER_ROLE>` | `<EVIDENCE_CHECKER_ROLE>` | Final approval and acceptance remain external. |

## Decision boundaries

- Privacy: only `<PRIVACY_DECISION_ROLE>` may supply approved privacy/legal
  decisions; admin or developer access is not legal authority.
- Security: `<SECURITY_OWNER_ROLE>` governs access/containment decisions, while
  `<CREDENTIAL_CUSTODIAN_ROLE>` and `<CREDENTIAL_CHECKER_ROLE>` remain distinct.
- Money: maker, checker, and reconciler remain three distinct roles; no role may
  manufacture submission, settlement, or paid finality.
- Operations: `<OPERATIONS_OWNER_ROLE>` cannot be inferred from repository
  authorship and remains unresolved until `EXT-OPERATIONS-OWNER` is supplied.
- Acceptance: `<BUSINESS_ACCOUNTABLE_ROLE>` and
  `<BRAND_RELEASE_APPROVER_ROLE>` remain placeholders; build-ready evidence is
  not client acceptance or completed handover.
