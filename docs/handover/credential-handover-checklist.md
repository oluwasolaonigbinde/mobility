# W4-04B-P1 credential handover checklist

Status: **PREPARATION ONLY**. Credential inventory, custody assignment,
transfer, rotation, revocation, recovery validation, and acceptance are **NOT
PERFORMED**. This repository contains no credential, contact, account
identifier, secret-store identifier, private endpoint, or transfer receipt.

Use this checklist only after the release environment, providers, receiving
operations owner, security authority, and protected custody system are
approved. Record values and identifiers only in that protected system. Git may
retain only redacted evidence pointers.

## Custody-family inventory skeleton

| Custody family | Outgoing custodian role | Receiving custodian role | Independent checker role | Repository-safe inventory evidence |
| --- | --- | --- | --- | --- |
| Release, DNS, and image registry | `<CREDENTIAL_CUSTODIAN_ROLE>` | `<OPERATIONS_OWNER_ROLE>` | `<CREDENTIAL_CHECKER_ROLE>` | `<PROTECTED_INVENTORY_POINTER>` |
| Database and broker/cache | `<CREDENTIAL_CUSTODIAN_ROLE>` | `<OPERATIONS_OWNER_ROLE>` | `<CREDENTIAL_CHECKER_ROLE>` | `<PROTECTED_INVENTORY_POINTER>` |
| Object storage, KMS/vault, and scanner | `<CREDENTIAL_CUSTODIAN_ROLE>` | `<SECURITY_OWNER_ROLE>` | `<CREDENTIAL_CHECKER_ROLE>` | `<PROTECTED_INVENTORY_POINTER>` |
| Session signing and application cryptography | `<CREDENTIAL_CUSTODIAN_ROLE>` | `<SECURITY_OWNER_ROLE>` | `<CREDENTIAL_CHECKER_ROLE>` | `<PROTECTED_INVENTORY_POINTER>` |
| Email, phone, and messaging | `<CREDENTIAL_CUSTODIAN_ROLE>` | `<OPERATIONS_OWNER_ROLE>` | `<CREDENTIAL_CHECKER_ROLE>` | `<PROTECTED_INVENTORY_POINTER>` |
| Payment, disbursement, and settlement | `<CREDENTIAL_CUSTODIAN_ROLE>` | `<MONEY_CHECKER_ROLE>` | `<CREDENTIAL_CHECKER_ROLE>` | `<PROTECTED_INVENTORY_POINTER>` |
| Basemap and aggregate ad platform | `<CREDENTIAL_CUSTODIAN_ROLE>` | `<OPERATIONS_OWNER_ROLE>` | `<CREDENTIAL_CHECKER_ROLE>` | `<PROTECTED_INVENTORY_POINTER>` |
| Monitoring and error tracking | `<CREDENTIAL_CUSTODIAN_ROLE>` | `<SECURITY_OWNER_ROLE>` | `<CREDENTIAL_CHECKER_ROLE>` | `<PROTECTED_INVENTORY_POINTER>` |
| Backup encryption and off-host recovery | `<CREDENTIAL_CUSTODIAN_ROLE>` | `<INCIDENT_COMMANDER_ROLE>` | `<CREDENTIAL_CHECKER_ROLE>` | `<PROTECTED_INVENTORY_POINTER>` |

The outgoing and receiving custody functions must be distinct assignments in
the protected record, even when their role labels above differ by responsibility
rather than person. The independent checker must not be the custodian whose
work is checked.

## Preconditions

- [ ] Protected inventory exists outside Git and enumerates every active,
  rollback, recovery, and emergency credential by non-secret identifier.
- [ ] Scope, environment, purpose, issuing system, owner/custodian roles,
  privileges, creation/rotation time, expiry, dependencies, and revocation path
  are recorded in the protected inventory.
- [ ] Least privilege and role separation are reviewed; shared human accounts
  and unmanaged personal custody are rejected.
- [ ] Approved secure transfer/custody channel and receiving authentication are
  verified outside Cardvert.
- [ ] Break-glass access, audit visibility, recovery dependencies, and provider
  support paths are reviewed without copying values into tickets or Git.
- [ ] External gates in the risk register are current; missing provider/account
  authority keeps that custody family unassigned.

## Transfer and verification sequence

| Step | Required evidence | Current state |
| --- | --- | --- |
| Freeze protected inventory scope and revision. | `<PROTECTED_INVENTORY_POINTER>` | NOT PERFORMED |
| Verify outgoing and receiving custodian authority separately. | `<PROTECTED_AUTHORITY_POINTERS>` | NOT PERFORMED |
| Verify independent checker assignment and least privilege. | `<PROTECTED_REVIEW_POINTER>` | NOT PERFORMED |
| Establish approved protected transfer/custody channel. | `<PROTECTED_CHANNEL_EVIDENCE_POINTER>` | NOT PERFORMED |
| Place values directly into the approved secret/custody system. | `<PROTECTED_CUSTODY_EVENT_POINTER>` | NOT PERFORMED |
| Rotate each transferable value and update dependent services deliberately. | `<PROTECTED_ROTATION_EVIDENCE_POINTER>` | NOT PERFORMED |
| Run scoped readiness, authentication, worker, storage, messaging, money-provider-disabled/live-authority, and recovery checks as applicable. | `<PROTECTED_VERIFICATION_POINTERS>` | NOT PERFORMED |
| Revoke prior interactive/provider access after verified replacement. | `<PROTECTED_REVOCATION_EVIDENCE_POINTER>` | NOT PERFORMED |
| Review audit events for issue, read/use, rotation, denial, and revocation. | `<PROTECTED_AUDIT_POINTER>` | NOT PERFORMED |
| Record exceptions, expiry, follow-up owner role, and unresolved gates. | `<PROTECTED_EXCEPTION_POINTER>` | NOT PERFORMED |

For backup encryption, retain the old key under approved restricted custody
until every protected bundle in its retention window has expired, or each
bundle has been re-encrypted and successfully restore-verified. Revoking it
earlier can destroy recovery authority. Record only the protected evidence
pointer here.

## Revocation and recovery checklist

- [ ] Compromise or custody uncertainty stops the affected integration/path.
- [ ] New value is issued in the protected store; repository/image/log/ticket
  content remains unchanged and value-free.
- [ ] Dependents are updated one boundary at a time and readiness is verified.
- [ ] Old value/access is revoked only after the replacement and recovery path
  are proved, subject to backup-key retention above.
- [ ] Session-signing rotation explicitly accounts for intentional logout.
- [ ] Failed rotation preserves containment and rollback/recovery evidence; it
  never restores a leaked value to active use.
- [ ] Incident, privacy, money, or provider authority is escalated to its
  distinct placeholder role.

## Repository-safe completion record template

- inventory revision pointer: `<PROTECTED_INVENTORY_POINTER>`
- custody authority pointer: `<PROTECTED_AUTHORITY_POINTERS>`
- rotation evidence pointer: `<PROTECTED_ROTATION_EVIDENCE_POINTER>`
- revocation evidence pointer: `<PROTECTED_REVOCATION_EVIDENCE_POINTER>`
- recovery evidence pointer: `<PROTECTED_RECOVERY_EVIDENCE_POINTER>`
- audit evidence pointer: `<PROTECTED_AUDIT_POINTER>`
- unresolved external gates: `<REGISTERED_GATE_IDS>`
- custodian roles: `<ROLE_PLACEHOLDERS_ONLY>`
- independent checker role: `<CREDENTIAL_CHECKER_ROLE>`
- outcome: `NOT PERFORMED`

Do not record names, email/phone contacts, account numbers/IDs, tenant or
subscription IDs, usernames, passwords, tokens, keys, certificates, private
URLs, DSNs, webhook secrets, backup passphrases, recovery codes, raw provider
receipts, or credential fingerprints in this repository.
