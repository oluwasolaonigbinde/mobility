# W4-04B-P1 external and deferred risk register

Status: **PREPARATION ONLY**. This table transcribes the current
[`docs/progress.md` external register](../progress.md#external-prerequisite-register)
and cannot change programme authority. `PRESENT` means only the registered fact
exists; it does not supply a provider, account, approval, live authority, or
completed handover. Every `MISSING` item remains unresolved.

## Relevant external inputs

| Gate | State | Relevance | Unresolved action or effect |
| --- | --- | --- | --- |
| EXT-STAGING-APPROVAL | MISSING | Direct release/pilot/handover gate | Approve external staging spend and live deployment/restore validation. |
| EXT-RM2-POLICY | PRESENT | Direct pilot fact | Current stationary policy is build-authoritative; it supplies no other live input. |
| EXT-PAYMENT-PROVIDER | MISSING | Direct commercial/live gate | Select and approve payment integration and protected signing custody. |
| EXT-STORAGE-PROVIDER | MISSING | Direct security/live gate | Select production private object storage, account, and region outside Git. |
| EXT-MALWARE-SCANNER | MISSING | Direct security/live gate | Select approved fail-closed scanner/provider. |
| EXT-KMS-CUSTODY | MISSING | Direct credential/live gate | Assign production key/vault custody and rotation authority. |
| EXT-EMAIL-PROVIDER | MISSING | Adjacent communications gate | Select provider and approved sending identity before live email. |
| EXT-BUDGET-POLICY | MISSING | Direct money/live gate | Approve production alert/pause/resume values. |
| EXT-PHONE-OPERATOR | MISSING | Direct pilot/live gate | Select approved verification/manual messaging operator and account. |
| EXT-BASEMAP | MISSING | Direct report/live gate | Select production basemap licence/account and protected key custody. |
| EXT-STORE-ASSETS | MISSING | Post-MVP distribution input | Native signing/listing assets remain Phase 2, not PWA-pilot authority. |
| EXT-RELEASE-ENV | MISSING | Direct release/handover gate | Supply client-owned account/domain/provider/budget/access action. |
| EXT-PILOT-FACTS | PRESENT | Direct pilot fact | Confirmed cohort/goals remain facts; they do not prove pilot execution or ROI. |
| EXT-REPORT-METHOD | MISSING | Direct reporting/live gate | Approve labels/method and any qualified ROI input/attribution method. |
| EXT-Q28-COMPANY | MISSING | Direct statutory/commercial gate | Supply approved issuer facts and accountant confirmation. |
| EXT-COMMERCIAL-VALUES | MISSING | Direct money/commercial gate | Supply approved quotation, commission, payout, and vendor values. |
| EXT-EVIDENCE-POLICY | MISSING | Direct pilot/privacy gate | Approve upload/view/renewal and challenge/spot-check policy. |
| EXT-LEGAL-PRIVACY | MISSING | Direct privacy/live gate | Supply wording, privacy owner, retention/DSR decisions, and approval. |
| EXT-DISBURSEMENT-PROVIDER | MISSING | Direct money/live gate | Select approved transfer provider and protected integration custody. |
| EXT-AD-PLATFORM | MISSING | Direct activation/live gate | Supply approved aggregate contextual activation account, access, and budget. |
| EXT-PILOT-PERMITS | MISSING | Direct pilot gate | Supply approved authority/permit evidence for selected pilot activity. |
| EXT-RM2-CALIBRATION-DATA | MISSING | Optional post-build validation | Field corpora may support a later reviewed revision; current build is not blocked. |
| EXT-BRAND-APPROVAL | MISSING | Direct release/handover gate | Supply final brand assets and approved client review. |
| EXT-CAMPAIGN-BUDGET-SCOPE | MISSING | Direct commercial gate | Decide whether printing/fixed costs consume governed campaign budget. |
| EXT-SETTLEMENT-BANK | MISSING | Direct money/live gate | Supply approved bank details through protected intake and custody evidence. |
| EXT-UPLOAD-POLICY | MISSING | Direct security/live gate | Approve types and maximum sizes for every live upload surface. |
| EXT-MESSAGE-COPY | MISSING | Adjacent communications gate | Approve sender identity and production email/messaging/voice copy. |
| EXT-RM2-APPROVER | MISSING | Optional post-build validation | Name an approver only for a future calibration revision. |
| EXT-OPERATIONS-OWNER | MISSING | Direct training/pilot/handover gate | Assign the receiving operations owner in the protected operating record. |

`EXT-PKG07-OWNER-RELEASE` is deliberately excluded from this handover risk
table because it is a historical Package 7 build-admission record, already
`PRESENT`, and is explicitly not a product or live-use prerequisite. Excluding
it does not change or erase its programme state.

## Deferred validation

| Validation | State | Required evidence before closure |
| --- | --- | --- |
| DV-PWA-PHYSICAL-MATRIX | NOT RUN — DEVICE ACCESS REQUIRED | Representative physical Android/iPhone install, permission, offline, visibility, storage, lock, completeness, and sync-latency evidence before real-driver GPS/pilot acceptance. |
| DV-PWA-ROUTE-BATTERY | NOT RUN — DEVICE/ROUTE ACCESS REQUIRED | Controlled supported-device route accuracy and battery evidence before PWA pilot acceptance. |
| DV-STAGING-LIVE | NOT RUN — EXT-STAGING-APPROVAL | Approved external deployment, public-edge smoke, worker recovery, exact backup/restore, and rollback evidence before release/pilot gates. |

## Risk treatment template

| Field | Placeholder |
| --- | --- |
| Risk/gate | `<REGISTERED_GATE_ID>` |
| Current authoritative state | `<STATE_FROM_DOCS_PROGRESS>` |
| Decision role | `<ROLE_PLACEHOLDER>` |
| Protected input/evidence | `<PROTECTED_EVIDENCE_POINTER>` |
| Affected workflow | `<WORKFLOW_PLACEHOLDER>` |
| Fail-closed behavior | `<STOP_OR_WITHHOLD_PLACEHOLDER>` |
| Closure criteria | `<APPROVED_EVIDENCE_REQUIREMENTS>` |
| Current outcome | `<UNRESOLVED_OR_NOT_RUN>` |

Never replace a missing value with synthetic data, a repository placeholder, a
test result, or inference. Only owner-recorded authority can change a gate;
only the specified physical/external exercise can change a deferred-validation
state.
