# Role-task inventories

Use one active session for the participant's assigned role. The frontend role
layouts redirect a mismatched role for usability, while the API repeats the
authorization check and remains authoritative. A visible page never grants an
operator a wider purpose, tenant, or data-access right.

The public `/apply` journey is an applicant intake surface, not an authenticated
driver workspace. Driver exercises below begin only after the relevant synthetic
account and onboarding state already exist.

## Admin

Admin means the Cardvert admin/operations role. It is not the privacy adviser,
business approver, provider custodian, or unrestricted raw-data role.

| Role | UI route | Permitted task | Forbidden boundary | Source |
| --- | --- | --- | --- | --- |
| admin | /admin | Review operational counts and queues. | A dashboard count is not acceptance, settlement, or incident closure. | [Admin overview](../../frontend/src/app/admin/page.tsx) |
| admin | /admin/users | List/filter users and apply shipped account-status controls. | Do not impersonate a user or share/reset credentials as training evidence. | [Users page](../../frontend/src/app/admin/users/page.tsx) |
| admin | /admin/driver-applications | Review synthetic person/payee and vehicle submissions, using masked values and governed file reads. | Do not copy NIN, bank, document, filename, or object details into notes; approval needs complete current evidence. | [Driver applications](../../frontend/src/app/admin/driver-applications/page.tsx) |
| admin | /admin/drivers | Inspect driver records and reach the existing create flow when authorized. | A driver record does not bypass onboarding, KYC, vehicle, or payee gates. | [Drivers page](../../frontend/src/app/admin/drivers/page.tsx) |
| admin | /admin/vehicles | Inspect and manage vehicles through the shipped state controls. | A vehicle status does not activate a campaign or prove installation. | [Vehicles page](../../frontend/src/app/admin/vehicles/page.tsx) |
| admin | /admin/assignments | Create offers, observe acceptance, activate only after independent gates, or cancel. | Admin cannot accept an offer for a driver; accepted is not active. | [Assignments page](../../frontend/src/app/admin/assignments/page.tsx) |
| admin | /admin/approvals | Review campaign, creative, installation-evidence, and mid-flight change queues. | Reject incomplete evidence; never infer approval from an empty queue or prior state. | [Approvals page](../../frontend/src/app/admin/approvals/page.tsx) |
| admin | /admin/planning-sources | Monitor aggregate planning-source links and governed zone insights. | No raw route, person-level audience, or unapproved live activation is exposed. | [Admin planning](../../frontend/src/app/admin/planning-sources/page.tsx) |
| admin | /admin/fraud | Review flags, holds, disputes, and physical-check results through current transitions. | Never auto-release an overdue hold or treat location alone as display proof. | [Fraud console](../../frontend/src/app/admin/fraud/page.tsx) |
| admin | /admin/payouts | Inspect/process synthetic trip calculations and ledger state. | Never rewrite historical money or force a stale calculation through. | [Payouts page](../../frontend/src/app/admin/payouts/page.tsx) |
| admin | /admin/payouts/rules | Review immutable revisions and create a future-effective rule only with current authority. | Never reprice accepted work or invent a production rate. | [Payout rules](../../frontend/src/app/admin/payouts/rules/page.tsx) |
| admin | /admin/payouts/corrections | Project, submit, separately approve/reject, and execute correction orders. | Creator and approver must differ; no self-approval or unaudited adjustment. | [Correction orders](../../frontend/src/app/admin/payouts/corrections/page.tsx) |
| admin | /admin/payouts/batches | Draft and reserve synthetic payout batches and inspect debt allocation. | No provider submission, settlement-bank detail, or paid claim without approved live authority. | [Payout batches](../../frontend/src/app/admin/payouts/batches/page.tsx) |
| admin | /admin/billing | Review quotation, invoice, receipt, allocation, refund, and settlement lineage. | Never invent statutory issuer facts, payment-provider evidence, or cash receipt. | [Admin billing](../../frontend/src/app/admin/billing/page.tsx) |
| admin | /admin/audit | Filter the append-only audit trail by shipped query fields. | Do not paste sensitive payloads into searches/notes or edit audit history. | [Audit trail](../../frontend/src/app/admin/audit/page.tsx) |
| admin | /admin/traffic | Review provider-neutral traffic-density profiles used by measurement. | A local/default profile is not an approved live methodology. | [Traffic profiles](../../frontend/src/app/admin/traffic/page.tsx) |

## Advertiser

Advertiser access is tenant-scoped. Organization membership remains relevant:
owner/manager authority is required for governed changes such as report
issuance, while visibility never grants another organization's data.

| Role | UI route | Permitted task | Forbidden boundary | Source |
| --- | --- | --- | --- | --- |
| advertiser | /advertiser | Review the tenant's campaign and performance summary. | No other tenant, raw route, driver identity, or operator queue is visible. | [Advertiser overview](../../frontend/src/app/advertiser/page.tsx) |
| advertiser | /advertiser/campaigns | List/filter the tenant's campaigns and enter the create flow. | Campaign presence is not admin approval, funding authority, or activation. | [Campaign list](../../frontend/src/app/advertiser/campaigns/page.tsx) |
| advertiser | /advertiser/campaigns/new | Create a draft campaign with the shipped basic fields. | Draft creation does not approve creative, targeting, budget, or launch. | [New campaign](../../frontend/src/app/advertiser/campaigns/new/page.tsx) |
| advertiser | /advertiser/campaigns/{campaignId} | Inspect one authorized campaign, submit governed changes, and manage creatives where offered. | A changed identifier or cross-tenant campaign must remain undisclosed. | [Campaign detail](../../frontend/src/app/advertiser/campaigns/[campaignId]/page.tsx) |
| advertiser | /advertiser/campaigns/{campaignId}/zones | Draw/edit permitted target or exclusion zones before the governing lifecycle closes them. | Geometry does not authorize live tracking or reveal raw driver routes. | [Zone editor](../../frontend/src/app/advertiser/campaigns/[campaignId]/zones/page.tsx) |
| advertiser | /advertiser/campaigns/{campaignId}/map | View only disclosure-cleared target-zone geometry from a ready frozen report. | Hidden/suppressed/stale results render no map; the local style is not a production provider. | [Governed map](../../frontend/src/app/advertiser/campaigns/[campaignId]/map/page.tsx) |
| advertiser | /advertiser/campaigns/{campaignId}/report | View verified/modelled results and, for authorized owner/manager membership, request the bounded CSV/PDF pair. | Omit ROI without qualified frozen authority; no partial pair, revoked gate, or raw route may be exposed. | [Campaign report](../../frontend/src/app/advertiser/campaigns/[campaignId]/report/page.tsx) |
| advertiser | /advertiser/planning-sources | Record aggregate-only sources and link them to owned campaigns/zones. | Person-level identifiers, raw routes, and live ad-platform push remain unavailable. | [Planning sources](../../frontend/src/app/advertiser/planning-sources/page.tsx) |
| advertiser | /advertiser/billing | Read the tenant's commercial history. | Advertiser cannot reconcile bank transfers, issue receipts, or mutate settlement lineage. | [Billing history](../../frontend/src/app/advertiser/billing/page.tsx) |
| advertiser | /advertiser/company | Maintain allowed company and operational contact fields. | Profile edits do not supply statutory issuer approval or another tenant's facts. | [Company profile](../../frontend/src/app/advertiser/company/page.tsx) |

## Driver

Driver access is self-scoped and designed for the screen-on installable PWA.
Previously displayed content is not fresh authority when the app is offline.

| Role | UI route | Permitted task | Forbidden boundary | Source |
| --- | --- | --- | --- | --- |
| driver | /driver | Review the driver's current journey, recent activity, and next available action. | Summary cards do not activate work or prove payout availability. | [Driver home](../../frontend/src/app/driver/%28portal%29/page.tsx) |
| driver | /driver/assignments | Accept/decline the driver's offers, inspect frozen terms/history, and submit required installation/display evidence. | Driver cannot activate an assignment, approve their own evidence, or act for another driver. | [Driver jobs](../../frontend/src/app/driver/%28portal%29/assignments/page.tsx) |
| driver | /driver/track | Start, keep visible, reconcile when prompted, and end an authorized trip. | No background/live tracking claim; do not start without fresh server, assignment, evidence, and PWA authority. | [Trip tracking](../../frontend/src/app/driver/%28portal%29/track/page.tsx) |
| driver | /driver/earnings | Review the driver's own pending/available/paid ledger projection. | Displayed earnings do not authorize batch submission, correction, or settlement. | [Driver earnings](../../frontend/src/app/driver/%28portal%29/earnings/page.tsx) |
| driver | /driver/earnings/trips/{tripId} | Inspect a frozen trip breakdown, public hold reason, notices, and submit one dispute where offered. | No internal fraud evidence, another driver's trip, or operator transition is available. | [Trip earnings](../../frontend/src/app/driver/%28portal%29/earnings/trips/[tripId]/page.tsx) |
| driver | /driver/profile | Review/update allowed profile fields and inspect owned vehicles/onboarding status. | Driver cannot mark KYC, payee, vehicle, or onboarding approval. | [Driver profile](../../frontend/src/app/driver/%28portal%29/profile/page.tsx) |
| driver | /driver/capabilities | Run the probe-only PWA capability checks when a facilitator requests them. | The probe requests no trip mutation or location before its explicit buttons and is not physical-device acceptance. | [Capability probe](../../frontend/src/app/driver/%28portal%29/capabilities/page.tsx) |

## Cross-role checks for a later session

- Sign out before changing roles; do not reuse a browser session as evidence of
  role isolation.
- A wrong-role browser path should redirect to that participant's home. The
  backend is the final authority and must still reject a direct cross-role API
  call.
- Cross-tenant identifiers should fail without disclosing existence. Record only
  the synthetic task/reference identifier, status, and expected boundary.
- A network or authority failure must show an unavailable/blocked state, not an
  empty success, inferred approval, or cached action authority.
