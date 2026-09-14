# Cardvert Product Requirements Document

**Product:** Cardvert (a Terrax Media product)
**Document type:** Product Requirements Document (client-readable)
**Date:** 14 September 2026
**Status of this document:** Describes the product as currently built and the
boundaries that still apply. It is not a statement that the product is
deployed, that a pilot has started, or that any live provider, legal approval,
or physical evidence exists.

---

## 1. Purpose, audience and how to read this document

### 1.1 Purpose

This document states what Cardvert must do, for whom, and under which
conditions. It is written so that Terrax Media's business, operations, legal
and commercial reviewers can confirm that the product matches their intent,
see exactly which parts work today with test data, and see which parts wait on
information, accounts, approvals or real-world evidence that only the client
or its partners can supply.

### 1.2 Audience

- Terrax Media leadership and product sign-off owners.
- The operations team that will run the planned pilot.
- Legal, privacy and finance advisers who must approve wording, retention,
  invoices and payment arrangements.
- The delivery team, as the reference for acceptance.

### 1.3 How to read the requirement statements

Each requirement has a stable identifier and a status tag. Identifiers are
local to this document:

| Prefix | Area |
| --- | --- |
| `A-` | Advertiser |
| `D-` | Driver |
| `O-` | Operator / administrator |
| `M-` | Money (billing, earnings, payouts) |
| `R-` | Measurement and reporting |
| `P-` | Privacy and security |
| `X-` | Recovery and resilience |
| `S-` | Screen quality |
| `G-` | External gate or owner decision (listed in Section 13) |

### 1.4 Status legend

| Tag | Meaning |
| --- | --- |
| **Implemented** | Built and demonstrable end to end with test (synthetic) data and local stand-in services. This does not mean deployed or used with real people, money or vehicles. |
| **Gated** | Built, but live use is switched off or refused until a named external input exists. The gate is named in brackets, for example *(G-07)*, and explained in Section 13. |
| **Pilot** | Belongs to the controlled pilot: real-world operation, physical activity or evidence that can only happen once the pilot runs. |
| **Post-pilot** | Deliberately outside the pilot. Not built for the pilot unless stated. |
| **Not confirmed** | A requirement the client decided or the product needs, whose current behaviour this document could not confirm in the built product. Treat it as outstanding until demonstrated. |
| **Owner decision** | The product cannot settle this; Terrax Media must decide. |

A requirement may carry two tags, for example **Implemented · Gated (G-01)**:
the software behaviour exists, and live use waits on the named gate.

---

## 2. Product overview and roles

### 2.1 What Cardvert is

Cardvert is a mobility advertising platform. Advertisers place campaigns on
branded private cars. Approved drivers carry the branding and record their
campaign driving through an installable phone web app. Terrax Media's
operations team reviews campaigns, artwork, drivers, vehicles and evidence,
assigns vehicles, reviews suspicious activity, and pays drivers. Advertisers
receive a Campaign Performance Analysis that separates verified vehicle
movement from clearly labelled estimates.

### 2.2 Recorded pilot shape (decisions and targets, not results)

The client has recorded the following pilot decisions. They are targets and
rules, not achieved outcomes; no pilot has launched.

- City: Abuja.
- Scale: 10 vehicles, 5 paying advertisers, 3 months.
- Success measures: Campaign Performance Analysis, offline-to-online targeting,
  and a target-area coverage measure of at least 60%. The exact definition of
  that coverage measure still needs client approval (G-15).
- Business name: Terrax Media. Product and app name: Cardvert. How the name is
  presented across the platform and the driver app is an owner decision
  (G-30).
- Operations: the developer supports initial pilot operations while training
  the Terrax Media operations team; the receiving operations owner must be
  named (G-27).

### 2.3 Roles

Cardvert has three account types. Separation of duties is enforced per action,
not by creating extra account types.

| Role | Who | What they do |
| --- | --- | --- |
| **Advertiser** | A person working for one advertiser company. Company members can be owners, managers or viewers. | Maintain the company profile, request quotations, accept terms, create campaigns, upload artwork, request changes, cancel, view billing and reports. |
| **Driver** | An owner-driver whose car is registered to them and who receives their own payouts. | Apply, submit identity, payee and vehicle evidence, accept or decline offers, upload installation photos, track campaign trips, view earnings and holds, dispute holds. |
| **Administrator (operator)** | A Terrax Media staff member. | Create advertiser accounts, review applications and evidence, approve campaigns and artwork, assign vehicles, activate work, review fraud, run measurement, make and approve payouts, reconcile outcomes. |

**Separation of duties within the administrator role:**

- **Maker:** the administrator who creates a payout batch or proposes a
  payout correction.
- **Checker:** a *different* administrator who approves it. A maker can never
  approve their own batch or correction.
- **Reconciler:** where a payout outcome is recorded manually, the reconciling
  administrator must be different from both the maker and the checker.
- Driver application review is deliberately a single-administrator trust
  boundary: one administrator may verify the bank account and approve both
  the person/payee and the vehicle evidence for the same driver, and each of
  those actions is individually attributed.

---

## 3. Scope boundaries

Everything in this document falls into one of four categories. The same
categories are used in every section.

### 3.1 Implemented, provider-neutral

These capabilities work end to end with test data and local stand-in services
(local email catcher, local file storage, local malware scanner, simulated
payment and payout outcomes). They are ready for acceptance testing but are not
live:

- Operator-led advertiser onboarding, company profile and single sign-in.
- Custom quotation, exact-terms acceptance, expedited-production waiver,
  funding and credit authority, budget evaluation, cancellation and
  settlement records.
- Campaign draft, submission and approval; artwork upload, security scan,
  review, rejection and replacement; governed mid-campaign changes with
  preview and separate confirmation.
- Public driver application, status reference, onboarding-code renewal,
  identity/payee/vehicle evidence, administrator review, administrator-started
  account setup, active-driver password reset.
- Offers with frozen terms, installation evidence, activation readiness and
  final activation, one active campaign per vehicle.
- Screen-on trip tracking in the installable driver web app with a durable,
  encrypted offline queue and visible recovery.
- Hourly earnings with base and premium rates, daily caps and parked-time
  exclusion; fraud assessment, holds, disputes and release; corrections with
  separate approval; post-payment debt.
- Payout selection, maker/checker batches, provider-neutral submission,
  per-line outcomes, failed-line replacement and campaign closeout position.
- Frozen measurement runs, Campaign Performance Analysis, CSV/PDF issuance and
  reissue, disclosure protection.
- In-app notifications, advertiser email preference, manual driver contact
  tasks, audit trail, data-subject request workflow, retention controls.

### 3.2 Conditional — external gates

Built behaviour that stays off, refuses, or uses test values until the named
input exists. Each gate is listed with what it blocks in Section 13. The main
gate families are:

- **Provider credentials:** online payment gateway, automated bank-transfer
  (payout) provider, transactional email provider, phone-verification operator
  and WhatsApp/voice account, production object storage, malware scanner, key
  custody, basemap, ad platforms.
- **Legal and privacy approvals:** privacy notices and consent wording, driver
  agreement, retention periods and data-subject request rules, disclosure
  thresholds for advertiser outputs, retargeting and export approval.
- **Company, bank and commercial facts:** registered issuer details and tax
  identification for invoices, settlement bank details, quotation components,
  commissions, driver base and premium rates, budget policy values, evidence
  and upload policy values, approved message copy.
- **Measurement method:** client approval of the estimate methodology and
  labels; any financial return-on-investment method.
- **Physical-device evidence:** representative Android and iPhone testing of
  installation, permissions, offline behaviour, route accuracy and battery.
- **Deployment:** the client-owned cloud account, domain, budget and access,
  plus an approved staging environment.
- **Pilot permits:** Abuja vehicle-advertising permit evidence.

**Built does not mean live.** No real invoice may be issued, no real payment
recorded as received from a live gateway, no real driver tracked, no real
advertiser report issued, no retargeting data exported or activated, and no
real money transferred until the corresponding gate is cleared.

### 3.3 Controlled pilot scope

Once gates are cleared, the pilot covers: real advertisers and drivers in
Abuja at the recorded scale; physical printing, installation and removal
coordinated by Terrax Media through approved vendors; permit evidence;
operations-run manual WhatsApp or voice contact with drivers; real
screen-on tracking; weekly automated bank-transfer payouts through an approved
provider; live Campaign Performance Analysis under an approved method;
aggregate controlled export and aggregate geographic, time and contextual
ad-platform activation once legally approved and accounts exist; operator
training and handover.

### 3.4 Post-pilot scope

- Native driver mobile app with true background tracking, secure device
  storage, push notifications and app-store distribution.
- Automated SMS and WhatsApp messaging.
- Fleet owners (a vehicle owner who is not the driver) as payees.
- Person-level exposure retargeting, which additionally requires lawful
  identity data and an approved identity/location-data partner.
- Expanded recurring billing, edge-AI vehicle and pedestrian counting,
  multi-city optimisation.
- Multi-company (agency) advertiser logins.
- Overlapping or multi-brand placements on one vehicle.
- Public self-service advertiser sign-up, unless the owner decides otherwise
  (G-31).

---

## 4. Advertiser requirements

### 4.1 Account and company

- **A-01** Advertiser accounts must be created by an administrator together
  with the advertiser company; there is no public advertiser sign-up.
  **Implemented.** Whether a public or enquiry-led front door is wanted is an
  **Owner decision** (G-31).
- **A-02** An advertiser created by an administrator must change the
  temporary password at first sign-in before using the dashboard.
  **Implemented.**
- **A-03** An advertiser login belongs to exactly one advertiser company;
  multi-company access is not supported. **Not confirmed** — the rule is
  decided, but single-company enforcement for every login could not be
  confirmed in the current build.
- **A-04** An advertiser can view and update the company profile, including
  billing email and operations contact. **Implemented.**
- **A-05** An advertiser can request a password reset from the sign-in page.
  The response must not reveal whether an account exists, requests are
  rate-limited, and the reset link is single-use and time-limited.
  **Implemented · Gated (G-05)** for live email delivery.
- **A-06** An advertiser can change their password and sign out from desktop
  and mobile layouts. Signing out ends the session on every device.
  **Implemented.**

### 4.2 Quotation and accepted terms

- **A-07** Every campaign is priced by custom quotation; there is no package
  catalogue. An advertiser can request a quotation for a campaign with notes.
  **Implemented.** Quotation values and components are client commercial
  facts (G-18).
- **A-08** Before accepting, the advertiser must see the quotation reference
  and revision, every line item with its exact amount, the production cost,
  the net amount, the included tax with rate, the VAT-inclusive total, the
  payment arrangement (standard prepaid or approved corporate credit), the
  production scope, and the payment dates and conditions. **Implemented.**
  Presentation of production scope and payment conditions in plain language
  is a screen-quality requirement (S-02).
- **A-09** Acceptance requires the advertiser to confirm they reviewed those
  terms for that exact revision. Accepted terms become an immutable record
  shown as an accepted receipt. **Implemented.**
- **A-10** Customer-facing prices are VAT-inclusive, with the included net and
  VAT itemised. **Implemented.** Real invoice issuance waits on registered
  company facts (G-17).

### 4.3 Campaign creation and submission

- **A-11** An advertiser can create a draft campaign with name, description,
  dates, total and daily budget, target and exclusion zones, and artwork.
  **Implemented.**
- **A-12** The advertiser submits a completed draft for Terrax Media review.
  While under review the campaign details are frozen. A rejected campaign
  shows the rejection reason and can be resubmitted. **Implemented.** A
  dedicated screen for editing general campaign details after rejection is
  **Not confirmed**.
- **A-13** The campaign page must show a preparation summary with the next
  action and the state of campaign review, quotation, artwork and funding or
  credit. It must state that the summary does not authorise production,
  assignment, installation or launch. If any input is unavailable, it must
  withhold a readiness conclusion rather than guess. **Implemented.**
- **A-14** Approval does not launch a campaign. A campaign becomes active only
  when an administrator activates its first vehicle assignment after every
  launch condition is met (O-15). **Implemented.**
- **A-15** A campaign never enters "completed" automatically; there is no
  product flow that marks a campaign or assignment completed. The completion
  operating model is an **Owner decision** (G-33).

### 4.4 Artwork (creative) upload, review and recovery

- **A-16** An advertiser uploads artwork files inside the platform. Files go
  to private storage, are checked for size and type, and must pass a malware
  scan before they can be reviewed. The upload shows its progress and gives a
  retry path on failure. **Implemented · Gated (G-09, G-10)** for production
  storage and scanner. Allowed file types and sizes await client approval
  (G-22).
- **A-17** Artwork is submitted for Terrax Media review, then approved or
  rejected with a reason. Only approved, clean, platform-stored artwork can
  be used in offers or activation; older linked files are marked as needing a
  private upload. **Implemented.**
- **A-18** Artwork can be added to an existing campaign after creation, and a
  rejected artwork file can be replaced and resubmitted in one step.
  **Implemented.**
- **A-19** The advertiser must see why artwork was rejected. **Not confirmed**
  — the preparation summary shows that changes are required, but display of
  the artwork rejection reason to the advertiser could not be confirmed.

### 4.5 Mid-campaign changes

- **A-20** An advertiser can propose a change to total budget, daily budget,
  start or end date, with a mandatory reason. **Implemented.**
- **A-21** Proposing a change must first produce a read-only preview that
  changes nothing. The preview shows each changed value (before and after),
  the additional driver liability, the recorded liability headroom, and the
  expected outcome: can apply now, needs Terrax Media review, or needs more
  funding. **Implemented.**
- **A-22** The change is recorded only when the advertiser separately confirms
  the previewed change. Confirmation is bound to exactly what was previewed
  and is rechecked. If the campaign changed since the preview, confirmation
  is refused as stale and the advertiser must preview again. Submitting the
  same confirmation twice results in one change, not two. **Implemented.**
- **A-23** Expansions apply immediately only within funded headroom;
  otherwise they wait for funding. Reductions, removals and all date changes
  require an administrator decision with a reason. Accepted driver terms are
  never repriced by a change. **Implemented.**
- **A-24** The advertiser sees each change request's status and any decision
  reason. **Implemented.**

### 4.6 Production timing, cancellation and refunds

- **A-25** Standard production waits until 24 hours have passed from the first
  confirmed payment allocation that authorises production. **Implemented.**
- **A-26** A standard-prepaid advertiser may ask for expedited production by
  accepting a recorded, versioned refund waiver. Refund eligibility ends when
  waived production actually begins, not when the waiver is accepted.
  **Implemented.** Final client-approved waiver wording is not recorded in the
  decision record and must be confirmed (G-24).
- **A-27** An advertiser can cancel a campaign only after an explicit
  permanent-cancellation confirmation. Cancellation records an exact cutoff,
  stops new work, cancels outstanding assignments, releases reserved driver
  liability and records a settlement. Verified driver earnings up to the
  cutoff are preserved. **Implemented.**
- **A-28** Refund rules: before production authority and without a waiver, a
  refund settlement may be recorded; after the 24-hour boundary or after
  waived production starts, no refund is due; corporate-credit work with no
  cash received is settled under its credit terms, not refunded. The product
  must never claim a refund was transferred unless a transfer is recorded.
  **Implemented · Gated (G-01)** for provider refunds.

### 4.7 Billing, invoices and budget

- **A-29** An advertiser can view their payment history (recorded payments,
  their status, and whether each is applied to accepted terms) and, per
  campaign, invoices, corrections, funding and refund history.
  **Implemented.** A downloadable invoice document is **Not confirmed**.
- **A-30** Manual bank transfer is the available payment method; the billing
  page must state that online payment is not yet available. An administrator
  records and confirms received transfers. **Implemented.** The account
  details advertisers pay into are client facts (G-19); the online gateway is
  gated (G-01).
- **A-31** Budget alerts, automatic pause and resume evaluate advertiser
  billing facts, never driver earnings. Without approved policy values, no
  threshold is applied and the product records that the policy is missing.
  **Implemented · Gated (G-20).** Whether printing and fixed costs consume the
  campaign budget is a client decision (G-21).

### 4.8 Reports, maps and planning sources

- **A-32** An advertiser can open the campaign's Campaign Performance Analysis
  and coverage map from the campaign page. The requirements for their content
  are in Section 8. **Implemented · Gated (G-14, G-15).**
- **A-33** An advertiser can register retargeting planning sources (website
  traffic, digital campaign audiences, CRM or upload references, UTM campaign
  sources, manually supplied audience or location insights) as aggregate
  metadata only, and link them to campaigns, target zones and time windows.
  Links are editable while a campaign is draft, pending, approved, scheduled,
  active or paused, and read-only history once completed, cancelled or
  rejected. **Implemented · Gated (G-14).**

### 4.9 Notifications

- **A-34** Advertisers receive in-app notifications with an unread count;
  in-app notifications cannot be turned off. **Implemented.**
- **A-35** Transactional email is on by default for the whole advertiser
  company and can be turned off company-wide by an authorised company manager;
  every change records who changed it. **Implemented · Gated (G-05).**
- **A-36** Notifications exist for campaign approval, confirmed funding, budget
  alert, pause and resume, and cancellation. Advertiser notifications for
  campaign or artwork rejection and for a quotation being ready, each naming
  the campaign and linking to it, are **Not confirmed**.

---

## 5. Driver requirements

### 5.1 Application and access

- **D-01** A prospective driver can apply publicly at the application page.
  Public applications are off by default and must be switched on for the
  pilot. **Implemented.**
- **D-02** Applying returns a private status reference. Submitting a new,
  duplicate or concurrent application with the same email returns the same
  response, so the page never reveals whether someone already applied.
  Application requests are rate-limited per network address and per email.
  **Implemented.**
- **D-03** Anyone holding a status reference can check progress for person
  and payee evidence and for vehicle documents. An unknown reference reveals
  nothing. A reference never grants documents, an account, work or tracking.
  **Implemented.**
- **D-04** The applicant uses an expiring onboarding code to submit evidence.
  If the code no longer works, the applicant can request a new one using the
  application email. The response is identical whether or not an application
  exists, requests are rate-limited, and the code is sent only to the exact
  stored applicant address. **Implemented · Gated (G-05).**
- **D-05** A duplicate application whose national identification number,
  normalised phone number or payout bank account matches an existing driver
  must be rejected without revealing which identity matched. **Not
  confirmed** — decided, but enforcement could not be confirmed.

### 5.2 Evidence

- **D-06** The applicant submits person and payee evidence: driving licence,
  driver photo, signed driver agreement, national identification number and a
  bank account for payouts. **Implemented · Gated (G-12)** for approved
  agreement and consent wording.
- **D-07** The applicant submits vehicle evidence for a car registered to
  them: registration, insurance and vehicle photos. Pilot vehicles are cars.
  **Implemented.**
- **D-08** Uploads survive retry: a repeated upload for the same file binds
  to the same evidence and late or stale uploads are rejected. **Implemented.**
- **D-09** Drivers see their national identification number masked; the full
  number is never shown in lists. **Implemented.**
- **D-10** Renewal of driver evidence after activation (for example when a
  vehicle approval period ends) must be possible through a reviewed
  resubmission. **Not confirmed** for a driver-facing screen; approval expiry
  itself removes work eligibility until a new approval (O-06).

### 5.3 Account setup, sign-in and recovery

- **D-11** Approval does not create a usable account. After both the
  person/payee and vehicle decisions pass, an administrator starts account
  setup. The driver receives a short-lived, single-use setup link and chooses
  their own password. **Implemented · Gated (G-05).**
- **D-12** Completing setup must recheck that the application and evidence are
  still approved and current, then in one step activate the account, consume
  the setup link, invalidate the onboarding code and reset session security.
  Rejected, expired, superseded, stale or reused links fail. A guessed or
  non-existent setup link returns "not found". No administrator ever sets a
  driver's password. **Implemented.**
- **D-13** Password reset is available only to active drivers. A pending or
  invited driver cannot use password reset to bypass account setup; the reset
  page response is the same for eligible and ineligible addresses.
  **Implemented.**

### 5.4 Offers, assignments and installation

- **D-14** A driver receives offers that show the frozen terms before
  acceptance: campaign, campaign window, service area, base and premium hourly
  rates, daily payable-hours cap and artwork. Offers expire. **Implemented.**
  The accepted offer also freezes the premium and exclusion zone boundaries;
  showing those boundaries to the driver in plain terms before acceptance is
  **Not confirmed**.
- **D-15** A driver can accept or decline. An accepted offer is not work until
  Terrax Media activates it; expired and declined offers cannot be activated
  or tracked. The assignments page shows offers, active work and history.
  **Implemented.**
- **D-16** A driver uploads installation photos for an assignment. An
  administrator must approve them before the campaign hours can earn.
  **Implemented · Gated (G-21a)** — the required photo views, uploader roles
  and validity periods await approved evidence policy values.
- **D-17** Recurring display checks and physical spot checks may be issued to
  confirm the branding is still on the vehicle; missed or failed checks feed
  fraud review. **Implemented · Gated (G-21a)** for thresholds and
  windows; spot checks themselves are **Pilot**.

### 5.5 Installing the app and tracking trips

- **D-18** The driver app is an installable web app. Starting a trip requires
  the app to be installed to the home screen; the tracking screen tells the
  driver how to add it from the browser menu. **Implemented.** Behaviour on
  representative Android and iPhone devices is **Pilot** evidence (G-25).
- **D-19** Tracking starts only when the driver presses Start and ends only
  when the driver presses End. There is no background tracking: capture runs
  only while the app is open and visible, and pauses whenever the app is
  hidden, the keep-screen-awake lock or location permission is lost, the
  session ends,
  or device storage or the single-tab lock is unavailable. **Implemented.**
- **D-20** The tracking screen must show the current state in plain words:
  tracking, sending, waiting to send, sent, paused, or needs attention.
  **Implemented.**
- **D-21** Location updates are saved on the device in an encrypted queue the
  moment they are recorded, survive reloads and loss of signal, and are sent
  later using the same identity so nothing is double-counted. **Implemented.**
- **D-22** Only one browser tab can track at a time. If device storage is
  unavailable, tracking does not start. **Implemented.**
- **D-23** If the End response is lost, the app stops capturing, keeps the
  evidence and retries the same End request until the result is confirmed; it
  never restarts capture for that trip. **Implemented.**
- **D-24** Evidence arriving after a trip is sealed is kept for operator
  review rather than rejected (O-18). **Implemented.**
- **D-25** A phone diagnostics page reports device capability checks.
  **Implemented.** Whether drivers should see it is an **Owner decision**
  (G-35).

### 5.6 Earnings, holds, disputes and debt

- **D-26** Drivers are paid a fixed amount per hour of verified campaign time:
  the base rate outside the premium zone and the premium rate inside it.
  Exclusion zones, invalid GPS, time outside the campaign window, and parked
  time beyond the shared allowance are unpaid. A daily payable-hours cap
  applies per campaign per calendar day in West Africa Time (the Lagos time
  zone, which also covers Abuja). **Implemented.** Rate values
  are client commercial facts (G-18).
- **D-27** A driver can open each trip and see how earnings were calculated:
  paid time by tier, excluded time with reasons, rates used and amounts.
  **Implemented.**
- **D-28** The earnings page shows released, pending, held, paid, reversed and
  carried-debt amounts, explains that "paid" appears only after a verified
  transfer, and shows active trip holds. **Implemented.**
- **D-29** A held trip shows its reason and status. The driver can open one
  dispute per hold and see staff replies and the final outcome; internal
  detection evidence and review notes stay private. **Implemented.**
- **D-30** Money already paid that a later correction reverses becomes debt
  deducted from future payouts; the driver sees the carried debt.
  **Implemented.**
- **D-31** When offline, the earnings page must not show previously loaded
  balances or holds as current; it asks the driver to reconnect.
  **Implemented.**

### 5.7 Contact and consent

- **D-32** Drivers receive in-app notices for offers, evidence checks, hold
  outcomes, activity flags and payout release. **Implemented.**
- **D-33** A driver's phone number must be verified through an operator-sent
  code before operations contacts them by WhatsApp or voice, and WhatsApp
  contact requires a separate, withdrawable consent for the exact purpose.
  **Implemented · Gated (G-06)** as system capability. Driver-facing screens
  for phone verification and consent are **Not confirmed**.
- **D-34** Automated SMS or WhatsApp messages to drivers are **Post-pilot**.

---

## 6. Operator requirements

### 6.1 Discovery and identity

- **O-01** Operator queues (users, drivers, vehicles, driver applications and
  other work lists) support search by name, email and operational reference,
  filters and pagination. Search must never match national identification
  numbers, bank details, raw evidence or raw GPS. **Implemented.**
- **O-02** Operator screens identify records by human names and references,
  not bare internal identifiers (S-03). **Implemented** for the reworked
  queues; complete coverage across every operator screen is **Not
  confirmed**.
- **O-03** An administrator can create advertiser users with their company,
  drivers and vehicles (operator-led onboarding remains available alongside
  public driver applications), and view an advertiser company profile.
  **Implemented.**

### 6.2 Driver application review

- **O-04** The default application queue shows pending applications; an
  administrator can include approved and rejected history, which opens
  read-only. **Implemented.**
- **O-05** Application detail shows named review context and history without
  bulk-revealing sensitive data. To view a national identification number,
  an evidence document or bank details, the administrator must select the
  review purpose and confirm; the revealed value clears after 60 seconds or
  on leaving the page, is marked not to be cached, and the access is
  audited. **Implemented.**
- **O-06** Evidence reads and decisions apply only to the current submission.
  Superseded or unlinked documents are refused before any download link is
  issued. Vehicle approval requires the administrator to choose an approval
  end date, which may be later than document expiry; when it passes, the
  vehicle stops qualifying until approved again. **Implemented.**
- **O-07** After both approvals, an administrator starts driver account setup
  (D-11). Retries of that action converge on one setup link. **Implemented.**

### 6.3 Campaign, artwork, evidence and change approvals

- **O-08** One approvals area lists pending campaigns, artwork, installation
  evidence and campaign change requests. Rejections require a reason. The
  campaign and artwork queues are paginated so later pending items remain
  reachable. **Implemented.**
- **O-09** Campaign approval binds to the exact submission reviewed; artwork
  approval rechecks that the file is still clean. **Implemented.**
- **O-10** An administrator records quotations and revisions, confirmed
  payments, reversals, invoices and corrections, credit approvals, refunds and
  settlements for a campaign. **Implemented · Gated (G-17, G-19).**

### 6.4 Assignment, offers and activation

- **O-11** An administrator creates an offer by selecting a named campaign,
  driver, vehicle and approved artwork, with an expiry. The system can
  recommend eligible cars (by city, lower current load and activity) but never
  assigns on its own. **Implemented.**
- **O-12** Before activation, an assignment shows a readiness view built from
  the same checks as activation. Viewing readiness changes nothing: no
  reservation, audit or business record is written. An assignment that is
  already active is reported as already active, with no activation control,
  rather than as needing preparation. **Implemented.**
- **O-13** One vehicle may have only one active campaign, and one driver may
  have only one active assignment. **Implemented.**
- **O-14** Competitor-category separation is a tunable business policy not yet
  defined. **Owner decision** (G-36).
- **O-15** Final activation is administrator-only and rechecks, at the moment
  of activation: approved campaign, accepted offer and frozen pay terms,
  approved clean artwork, funded driver liability, production authority
  (standard wait, expedited waiver or approved credit), approved installation
  evidence for that assignment, and vehicle exclusivity. If any condition
  changed after readiness looked good, activation is refused.
  **Implemented · Gated (G-29)** for real pilot campaigns, which also require
  approved permit evidence.

### 6.5 Fraud review, holds and activity

- **O-16** The fraud queue shows flags with bounded evidence. An administrator
  acknowledges, then confirms or dismisses with a note. Only dismissal
  releases a hold. Flags on already released or paid earnings recommend a
  reversal that a named administrator must confirm. **Implemented.**
- **O-17** Flagged earnings stay pending for a seven-day review target and
  escalate if unresolved; they are never released automatically.
  Copied-route detection across trips and accounts, activity flags after seven
  consecutive inactive days, and a configurable weekly verified-hours floor
  feed review. **Implemented.** The weekly floor value is an operations
  parameter (G-21a).

### 6.6 Late evidence

- **O-18** A late-evidence worklist shows trip evidence received after sealing.
  An administrator applies or discards it with confirmation and a note;
  repeated or stale submissions are refused safely. Applying never reprices
  earnings or edits an issued report; any correction follows the separate
  correction or reissue path. **Implemented.**

### 6.7 Measurement operations

- **O-19** An administrator can list measurement runs by campaign and status,
  see whether each is current or superseded, complete or incomplete, and
  whether a report has been issued, and can request report issuance.
  Incomplete, suppressed or gated results must never appear as zero or as
  complete. **Implemented · Gated (G-14, G-15).**
- **O-20** Traffic profiles used by the estimate model are managed by
  administrators with version history. **Implemented.**

### 6.8 Contact

- **O-21** A contact worklist shows manual driver contact tasks with the
  driver's name and masked phone. A task can be completed only while the phone
  is verified and consent matches the task's purpose; a withdrawn or mismatched
  task stays in history but leaves the actionable list and cannot be
  completed. No automated message is sent from this screen.
  **Implemented · Gated (G-06).** An operator screen for sending phone
  verification codes is **Not confirmed**.

### 6.9 Payouts, corrections and closeout

- **O-22** Payout operations are specified in Section 7.
- **O-23** Payout rules are managed as effective-dated revisions; a change
  never reprices work already accepted. **Implemented.**
- **O-24** A campaign closeout view is read-only. It shows the cancellation
  record, per-driver campaign money position and recorded settlements, and
  states that these records do not confirm physical removal, operational
  completion or unverified cash. It offers no action that completes a
  campaign. **Implemented.**

### 6.10 Audit and planning sources

- **O-25** An administrator can search the audit trail of record-changing
  actions. **Implemented.**
- **O-26** An administrator can monitor advertiser planning sources and their
  campaign links. **Implemented · Gated (G-14).**

---

## 7. Money requirements

### 7.1 General rules

- **M-01** All amounts are exact decimal values with their currency. Totals
  of different currencies are never combined. Screens label page, filtered and
  selected totals distinctly, and no total computed in the browser is treated
  as authoritative. **Implemented.**
- **M-02** Money history is append-only. Issued invoices, receipts, payout
  calculations, paid lines and audit facts are never edited; corrections are
  new records. **Implemented.**
- **M-03** Advertiser price and driver cost are separate: advertiser spend is
  computed from billing facts; driver earnings never enter it.
  **Implemented.**

### 7.2 Money in

- **M-04** Standard advertisers must be fully funded by confirmed payment
  allocations before production; approved corporate advertisers may proceed
  under recorded credit terms with an approved limit and due date.
  **Implemented.**
- **M-05** One external transfer can fund only one obligation: each receipt is
  unique, allocations are separate records, and a reversal withdraws funding
  authority at a recorded time so new work cannot start from reversed cash.
  **Implemented.**
- **M-06** Invoices are numbered, itemise net, VAT and gross, and become
  immutable when issued; corrections use credit or debit notes, and repeating
  a correction does not duplicate it. **Implemented · Gated (G-17).**
- **M-07** Online checkout and manual transfer converge on the same payment
  record. **Implemented · Gated (G-01)** for online checkout.

### 7.3 Earnings

- **M-08** Earnings are calculated automatically once a trip's evidence is
  complete and sealed, using the terms frozen when the driver accepted the
  offer. **Implemented.**
- **M-09** Earnings become available for the next weekly payout when the trip
  has a current successful fraud assessment and no active hold. Held
  earnings follow O-16 and O-17. **Implemented.**
- **M-10** Historical earnings can change only through a correction proposed
  by one administrator and approved by a different administrator, rechecked
  for staleness and applied once. **Implemented.**

### 7.4 Payout selection

- **M-11** An administrator selects payouts from eligible available credits.
  Each candidate shows the named driver and payee, a masked destination,
  individual credits, any debt deductions, exact per-currency totals, and the
  reasons a credit is ineligible. **Implemented.**
- **M-12** General selection never decrypts bank details. Viewing a masked
  destination is an explicit, audited action. **Implemented.**
- **M-13** A selection preview is advisory. Reserving credits into a batch
  rechecks eligibility, fraud assessment, holds, debt and payee details at
  that moment, reserves all selected credits or none, and allows one winner
  when two administrators reserve the same credit. **Implemented.**
- **M-14** If the response to creating or reserving a batch is lost, retrying
  the same draft and selection returns the same batch and frozen lines rather
  than creating another; the draft can be recovered from another tab.
  **Implemented.**

### 7.5 Approval and submission

- **M-15** One administrator makes a batch; a different administrator must
  approve its frozen instructions. Self-approval is refused. Batch lists show
  maker and checker names. **Implemented.**
- **M-16** Submission is provider-neutral: no live payout provider is
  connected. Submitting queues work first; queued work has not been submitted.
  **Implemented · Gated (G-02).**
- **M-17** Each payout line shows its own outcome, kept distinct: queued,
  provider result unknown, submitted, verified paid, and failed. A batch-level
  statement never marks cash as paid; only verified success on an individual
  line records payment. Line detail shows the line's history.
  **Implemented.**
- **M-18** An ambiguous submission (for example, no response from the
  provider) is retried with the same payment reference, so the provider
  recognises the repeat as the same payment rather than a new one.
  **Implemented.**
- **M-19** Where an outcome is recorded manually, the reconciling
  administrator must differ from the maker and the checker. **Implemented.**

### 7.6 Failed lines and replacement

- **M-20** A terminally failed line is never retried in place.
- **M-21** A replacement requires a newer verified bank destination that is
  genuinely different: a different bank code or account number. The same bank
  code and account number captured again, re-encryption of the same details,
  or a changed account name alone does not count. **Implemented.**
- **M-22** Every trip affected by a replacement must still have a current
  successful fraud assessment; if any one does not, the whole replacement is
  refused and nothing is created. **Implemented.**
- **M-23** A replacement is a new batch and line linked to the failed one and
  requires its own independent approval. If the original line later succeeds,
  a replacement that has not yet been submitted is cancelled; one already
  submitted, or whose result is unknown, stays tracked as possible duplicate
  exposure. **Implemented.**

### 7.7 Debt

- **M-24** When already-paid money is later reversed or confirmed as fraud,
  or when a provider verifies a second successful transfer for a credit that
  was already paid (a duplicate success), the excess amount becomes
  carry-forward debt linked to its paid source. No negative transfer is ever
  attempted. **Implemented.**
- **M-25** Debt is driver-wide (across campaigns, per currency) and is
  cleared by consuming future available credits in a fixed order, leaving one
  exact residual credit when debt clears. **Implemented.**

### 7.8 Campaign closeout position

- **M-26** The campaign closeout view shows, per driver: active reserved
  instructions, unresolved provider exposure (reserved or in-flight),
  economic ledger paid, verified provider transfers, and driver-wide
  carry-forward debt. **Implemented.**
- **M-27** Economic ledger paid and verified provider transfers are shown
  separately. Verified provider transfers can exceed the ledger amount if a
  late or duplicate provider success occurs, for example when an original
  line later succeeds after a replacement was created. **Implemented.**
- **M-28** Closeout never claims physical removal, lifecycle completion or
  unverified cash (O-24). **Implemented.**
- **M-29** No credit may be paid twice by the product's own actions: each
  credit can be reserved into only one active line, and replacement requires
  the conditions in M-21 and M-22. Duplicate successes reported by a provider
  remain visible rather than hidden (M-27). **Implemented.**

---

## 8. Measurement and reporting

### 8.1 Report content

- **R-01** The standard advertiser deliverable is **Campaign Performance
  Analysis**. **Implemented.**
- **R-02** Verified vehicle movement is presented as system evidence that a
  campaign vehicle moved. It never proves a person saw an advert.
  **Implemented.**
- **R-03** Estimated exposure is a formula output, clearly labelled as an
  estimate with its model, traffic-density source and calibration state, and
  an estimate-quality factor that is a diagnostic, not a statistical interval.
  It must never be described as verified views, unique reach, people exposed
  or attribution. **Implemented.** The screen label ("Estimated ad exposure")
  and the download label ("Modelled potential contacts") differ; the screen
  explains the relationship. Final labels require client method approval
  (G-15).
- **R-04** Every metric states its coverage and completeness. A metric with no
  qualifying data, or missing a required input, is omitted and marked, never
  shown as zero. A period with incomplete trips says so. Suppressed values are
  marked as suppressed. **Implemented.**
- **R-05** Target-area coverage (the recorded 60% pilot measure) is not
  presented in advertiser reports today. Its qualifying rule and label await
  client approval, and whether to deliver or relabel it is an **Owner
  decision** (G-15, G-32).
- **R-06** The report may show campaign driver cost as an operational
  financial fact, never as revenue or return. Whether advertisers should see
  driver cost at all is an **Owner decision** (G-34).
- **R-07** High-exposure zone insights and the coverage map show only
  disclosure-cleared target zones ranked from the same frozen measurement run.
  **Implemented · Gated (G-14, G-11).**

### 8.2 Frozen runs and issuance

- **R-08** A report reads from an immutable measurement run that freezes its
  source records, method versions and provenance. Changed inputs create a new
  run linked to the earlier one; issued results are never rewritten.
  **Implemented.**
- **R-09** If no suitable run exists, or the run fails its integrity check,
  the report page shows a clear unavailable state instead of partial or
  invented figures. **Implemented.**
- **R-10** An authorised advertiser owner or manager, or an administrator, can
  request CSV and PDF files. The screen, CSV and PDF publish the same frozen
  decisions. Files become available only after both are stored and verified;
  retries converge; reissue is an explicit, append-only action.
  **Implemented · Gated (G-14, G-15).**
- **R-11** A financial return-on-investment section appears only when the
  advertiser supplied defined conversion and revenue inputs **and** an
  approved reproducible method exists. Otherwise the report omits ROI and any
  ROI wording entirely. **Implemented · Gated (G-15).**

### 8.3 Disclosure protection

- **R-12** Every advertiser-visible or exportable location output is
  aggregated. Cells are suppressed when they fall below minimum distinct
  vehicles, trips or days, or when one contributor dominates, and repeated or
  overlapping requests cannot be combined to reveal a suppressed value.
  **Implemented · Gated (G-14)** — current thresholds are test values, not
  approved values, and meeting them is not described as anonymity.
- **R-13** In production configuration, advertiser report and map outputs are
  refused until legal, threshold and history-retention approvals are recorded.
  **Implemented · Gated (G-14).**
- **R-14** No driver identity, trip identifier or precise timestamp appears in
  audience or exposure outputs. Route data is never offered as a person-level
  audience. **Implemented.**
- **R-15** Controlled export of aggregate exposure segments and aggregate
  geographic, time and contextual ad-platform activation accept only
  aggregate fields and reject identifiers. They remain disabled until legal
  approval and ad-platform accounts exist. **Implemented · Gated (G-14,
  G-16).** Person-level retargeting is **Post-pilot**.

---

## 9. Privacy and security

### 9.1 Sensitive data

- **P-01** National identification numbers and bank account details are
  stored encrypted per record. Plain values never appear in lists, logs, audit
  records, exports, error messages or fallback storage. **Implemented · Gated
  (G-08)** for production key custody.
- **P-02** Sensitive reveals are purpose-selected, confirmed, short-lived,
  marked not to be cached and audited (O-05, M-12). **Implemented.**
- **P-03** All files are private. Access uses short-lived signed links issued
  after role and purpose checks. Report files cannot be read through generic
  file access. **Implemented.**

### 9.2 Retention and data-subject requests

- **P-04** Raw location data is retained for a configurable period and purged
  automatically; the current setting is a build value, not an approved
  retention period. **Implemented · Gated (G-12).**
- **P-05** Rejected and expired identity and vehicle evidence is purged only
  after an approved retention period is configured; with no approved value the
  purge stays visibly disabled. Pending and approved evidence is never
  purged. **Implemented · Gated (G-12).**
- **P-06** The pilot build's default backup settings keep at most the newest
  14 copies and none older than 35 days. These are configuration defaults,
  not an approved retention policy. **Implemented · Gated (G-12).**
- **P-07** Data-subject access, rectification and erasure requests follow a
  recorded operator workflow that verifies identity and checks six locations
  (database, stored files, devices, logs, backups and processors) before a
  case can be completed. Erasure never rewrites money, invoice, payout, fraud
  review or audit facts; retained exceptions need an approval reference.
  **Implemented · Gated (G-12).** This workflow has no operator screen; it is
  run by authorised staff following the runbook.
- **P-08** Minimal disclosure-protection history is kept for as long as its
  source data remains queryable; elapsed time alone does not delete it.
  **Implemented.**

### 9.3 Audit

- **P-09** Record-changing actions across all roles are written to an audit
  trail with actor, subject and request identity; a small number of named
  high-volume actions (such as location batch ingestion) rely on their own
  evidence records instead. Ordinary reads are not audited; purpose-scoped
  sensitive reads are. **Implemented.**

### 9.4 Access and sessions

- **P-10** Roles are enforced on the server for every request. Browser tokens
  are held in secure, script-inaccessible cookies behind the web app's own
  server. **Implemented.**
- **P-11** Sessions slide with activity under an absolute maximum. Password
  change and sign-out revoke sessions on every device; account setup and
  privilege elevation reset session security. Suspended users are blocked.
  **Implemented.**
- **P-12** Sign-in, password reset, driver application and onboarding-code
  renewal are rate-limited and fail safely if the rate limiter is unavailable.
  **Implemented.**
- **P-13** Public account, application, status and setup flows never reveal
  whether an email, application or account exists. **Implemented.**
- **P-14** The driver app's offline cache stores no signed-in pages or data
  responses; location evidence on the device is encrypted to that driver.
  **Implemented.**

### 9.5 Legal preconditions

- **P-15** Live GPS collection, identity checks, advertiser outputs and
  retargeting require approved privacy notices, consent wording, driver
  agreement, retention and data-subject decisions, and a named privacy owner.
  None of these approvals exists yet. **Gated (G-12).**
- **P-16** Legally required disclosures for applicants, drivers, privacy and
  fraud handling must be identified before compliance copy is rewritten.
  **Owner decision** (G-12).

---

## 10. Recovery and resilience

- **X-01** **Lost responses.** Commands that create or change important
  records (campaign change confirmation, quotation acceptance, artwork
  confirmation, uploads, account setup, payout draft and reservation, report
  issuance, contact completion, applying or discarding late trip evidence)
  must converge on one result when retried with the same request, and
  conflict if retried with different content. **Implemented.**
- **X-02** **Double submission.** Pressing a confirm button twice, or two
  administrators acting at once, produces one outcome and a clear conflict for
  the other. **Implemented.**
- **X-03** **Stale data.** Actions based on an outdated view (a campaign change
  preview, an activation readiness view, an application's evidence, a payout
  selection) are rechecked and refused if the underlying facts changed.
  **Implemented.**
- **X-04** **Multiple tabs.** Only one tab can track a trip; a payout draft can
  be recovered in another tab; report issuance keeps its request identity
  before submission. **Implemented.**
- **X-05** **Offline driver use.** Trip evidence is kept and sent later
  (D-21); offline pages show an unavailable state and hide money, hold and
  work actions until a fresh read succeeds; privileged actions cannot be
  submitted offline. **Implemented.**
- **X-06** **Partial failure.** When an optional section of a page fails to
  load (for example campaign labels on earnings), the rest of the page stays
  usable and the failed section offers a retry. When a section that controls
  money, work or authority fails, the page shows it as unavailable and does
  not show a conclusion or action. **Implemented.**
- **X-07** **Failure messages.** Failures tell the user what happened and the
  next safe action in plain language, without internal codes or sensitive
  details, and without carrying error text in the page address. **Not
  confirmed** across every screen: the campaign commercial panel can still
  receive its error message through the page address, and consistent
  handling of expired sessions, permission denials, validation errors,
  conflicts and rate limits on every screen has not been confirmed.
- **X-08** **Background work.** Automated jobs (trip processing, earnings
  release, email dispatch, report publication, evidence purge) are safe to run
  twice, resume after a crash, and surface failures to operators rather than
  inventing an outcome. **Implemented.**

---

## 11. Screen quality requirements

These are requirements for every screen. Where the build does not yet meet
one everywhere, the requirement still applies and is part of acceptance.

- **S-01** **Plain language.** Screens use plain human language describing the
  current state and the next action. Internal status names, codes, hashes,
  formula versions and engineering terms are not shown to advertisers or
  drivers. Whether reproducibility details such as run identifiers and hashes
  are shown to customers, kept for support, or kept for exports only is an
  **Owner decision** (G-37).
- **S-02** **Structured facts.** Commercial terms, production scope and
  payment conditions are shown as readable labelled fields, not raw data
  structures.
- **S-03** **Named context.** Records are identified by names (driver,
  vehicle plate, campaign, company, administrator) and human references, not
  internal identifiers.
- **S-04** **Record-aware confirmations.** Destructive or permanent actions
  name the affected record and require an explicit on-page confirmation with
  any required reason, rather than a generic browser prompt.
- **S-05** **Responsive.** Every screen works on desktop and at a phone width
  of about 375 pixels without page-level horizontal scrolling; wide tables
  scroll within their own panel and action columns remain reachable.
- **S-06** **States.** Every data view has distinct loading, empty, error and
  unavailable states. "Unavailable" is never displayed as empty, zero or
  complete.
- **S-07** **Accessibility.** Form fields have programmatic labels; status
  and error messages are announced; colour is never the only signal; text and
  controls meet contrast requirements; pending indicators name the action in
  progress.
- **S-08** **Truthful success.** A success message appears only after the
  server confirmed the result, and says exactly what happened (for example
  "queued", not "paid").
- **S-09** **Consistent brand.** Screens follow the approved Cardvert brand;
  final logo and asset pack require client approval (G-28).

---

## 12. Acceptance requirements

Acceptance has two layers. **In-repository acceptance** can be obtained now
with test data, local stand-in services, automated tests and real-backend
browser journeys. **External acceptance** needs providers, approvals, devices,
an environment or the pilot itself, and cannot be claimed until those exist.

### 12.1 In-repository acceptance (obtainable now)

| Area | Must be demonstrable |
| --- | --- |
| Advertiser | A browser journey on desktop and phone width: operator-created advertiser signs in, requests a quotation, sees every material term, accepts it, uploads and replaces artwork, submits a campaign, previews a change, confirms it once, sees a stale confirmation refused, and cancels with the correct settlement outcome. |
| Driver | A browser journey on desktop and phone width: application, status check, onboarding-code renewal with identical responses for known and unknown emails, evidence submission, administrator approval, account setup, reused or expired setup link refused, pending-driver reset refused and active-driver reset accepted, offer acceptance, installation evidence, Start, offline capture, reload, recovery, End after a lost response, and earnings with holds and disputes. |
| Operator | Named search that cannot match sensitive fields; purpose-confirmed reveal that clears; stale evidence download refused; readiness that writes nothing; activation refused when a source changes after readiness; late evidence applied and discarded without repricing; measurement runs never showing incomplete data as zero; contact completion refused after consent withdrawal. |
| Money | A two-administrator browser journey: named selection with ineligibility reasons, all-or-none reservation, concurrent single winner, self-approval refused, distinct approval, queued versus submitted, unknown and partial outcomes, same-identity retry, verified-line-only paid status, failed-line replacement refused for unchanged destination and for one stale trip, replacement accepted for a genuinely different destination, late or duplicate success visible in closeout, and database tests for these races. |
| Reporting | Screen, CSV and PDF parity from one frozen run; omission instead of zero; ROI absent without inputs and method; production configuration refusing outputs without approvals. |
| Privacy and security | Encrypted storage inspection, no plain values in logs or audits, rate limits, non-enumeration, all-device sign-out, data-subject workflow refusing completion until all six locations are assessed. |
| Screen quality | Automated and manual checks of S-01 to S-08 at desktop and 375-pixel width. |
| Build integrity | The complete automated test suites, contract checks and continuous-integration run pass on the exact delivered version. |

### 12.2 External acceptance (not obtainable in the repository)

| Area | Must be demonstrated when the gate clears |
| --- | --- |
| Driver devices | Representative Android and iPhone: installation, location permission grant, denial and revocation, app switching, screen lock, calls, reload, offline storage, route accuracy, sync delay, four-hour battery use. |
| Payments | Online gateway sandbox and live checkout; payout provider sandbox, signed provider callbacks, safe repeat of an unanswered submission using the same payment reference, and per-line reconciliation; first real transfer under maker/checker. |
| Email and contact | Verified sender, delivery receipts, approved copy; named phone operator sending codes. |
| Invoices | First real invoice with approved issuer facts and accountant confirmation. |
| Legal and privacy | Approved notices, consent, agreement, retention, disclosure thresholds, data-subject response rules; tabletop breach exercise. |
| Measurement | Client-approved estimate method and labels; approved coverage rule; first live issued report. |
| Environment | Deployment to the client-owned account and domain, public-edge smoke test, backup restore and rollback evidence. |
| Pilot | Permit evidence, physical installation and removal, trained named operations owner, cohort onboarding and pilot success measures. |

---

## 13. Open owner decisions and external dependencies

Values in this table are to be supplied by the client or its partners. The
product does not invent them. Gate numbers are stable references; unused
numbers (G-03, G-04, G-07, G-13) are intentionally left unassigned.

### 13.1 External dependencies

| ID | Dependency | What it blocks | Owner |
| --- | --- | --- | --- |
| G-01 | Online payment gateway provider, account, sandbox and signing credentials | Online checkout; provider refunds | Terrax Media |
| G-02 | Approved automated bank-transfer (payout) provider, account, sandbox, signing and callback credentials, production approval | Any real driver payout submission | Terrax Media |
| G-05 | Transactional email provider and verified sending identity | Live advertiser email, password reset, onboarding-code and setup-link delivery | Terrax Media |
| G-06 | Named phone-verification operator and approved WhatsApp/voice account | Live phone verification and manual driver contact | Terrax Media |
| G-08 | Production key custody (key vault) and custodian | Production storage of identity and bank data | Terrax Media |
| G-09 | Production object-storage provider, account and region | Production file storage | Terrax Media |
| G-10 | Malware scanner provider | Production upload scanning | Terrax Media |
| G-11 | Production basemap provider, licence and key | Live maps | Terrax Media |
| G-12 | Legal and privacy approvals: named privacy owner, notices, consent, driver agreement, retention periods, data-subject rules, required disclosures | Real GPS, identity checks, advertiser outputs, retargeting | Terrax Media's legal/compliance adviser |
| G-14 | Legal approval of advertiser disclosure thresholds, history retention and retargeting/export | Live reports, maps, planning sources, export, activation | Terrax Media's legal/compliance adviser |
| G-15 | Client approval of the estimate methodology and labels, the target-area coverage rule, and any ROI inputs and method | First live issued report; coverage measure; ROI | Terrax Media |
| G-16 | Ad-platform accounts, legal approval, API access, credentials and activation budget | Aggregate ad-platform activation | Terrax Media |
| G-17 | Registered issuer name, tax identification number, billing address, invoice wording and numbering, accountant confirmation | Real invoice issuance | Terrax Media |
| G-18 | Quotation components, commissions, driver base and premium rates, production and vendor values | Real commercial and payout use | Terrax Media |
| G-19 | Settlement bank-account details with secure intake and verification; approved advertiser payment instructions | Live settlement; payment instructions shown to advertisers | Terrax Media |
| G-20 | Budget alert, pause and resume values | Live budget policy | Terrax Media |
| G-21 | Whether printing and fixed costs consume the campaign budget | Production commercial configuration | Terrax Media |
| G-21a | Evidence and activity policy: installation photo views, uploader roles, validity and renewal, display-check and spot-check thresholds, weekly verified-hours floor | Pilot evidence and activity enforcement | Terrax Media operations |
| G-22 | Approved file types and maximum sizes per upload | Live upload policy | Terrax Media |
| G-23 | Approved sender name and email/WhatsApp/voice message copy | Live communications | Terrax Media |
| G-24 | Approved expedited-production waiver wording | Live waiver use | Terrax Media's legal adviser |
| G-25 | Physical Android/iPhone device, route and battery validation | Production driver app acceptance; any real driver tracking | Terrax Media with delivery team |
| G-26 | Client-owned cloud account, domain, provider, budget and access; approved staging environment | Deployment and release | Terrax Media |
| G-27 | Named receiving operations owner | Training, operations rehearsal and handover | Terrax Media |
| G-28 | Final Cardvert logo, brand asset pack and named approver | Client-facing release assets | Terrax Media |
| G-29 | Abuja vehicle-advertising permit evidence and approval | Pilot campaign launch | Terrax Media (vendors coordinate) |
| G-38 | App-store and Play accounts and assets | Post-pilot native app only | Terrax Media |

### 13.2 Owner decisions

| ID | Decision needed | Current product behaviour |
| --- | --- | --- |
| G-30 | Canonical presentation of the Cardvert name across platform and driver app, legal-entity presentation, pilot-city wording, locale and spelling | "Cardvert" is used both for the platform and the driver app |
| G-31 | Advertiser front door: operator-led, enquiry-led or self-service | Operator-led; no public advertiser sign-up |
| G-32 | Deliver target-area coverage to advertisers, or remove/relabel any "measured" promise | Coverage is not shown in advertiser reports |
| G-33 | Campaign and assignment completion operating model, including physical removal logistics | No completion action; closeout is read-only |
| G-34 | Whether driver payouts, Terrax delivery cost and fraud signals appear on advertiser surfaces, and with what explanation | Driver payout totals appear in advertiser views |
| G-35 | Whether drivers see the phone diagnostics page, and under what access | Diagnostics page available to signed-in drivers |
| G-36 | Competitor-category separation policy | Not enforced; one active campaign per vehicle and one active assignment per driver only |
| G-37 | Whether run identifiers, hashes, submission references and technical scan or status labels are customer features, support-only or export-only | Some appear on report screens, and the advertiser campaign page shows a submission reference hash and raw file-scan status |
| G-39 | Advertiser and driver support and dispute destinations | No approved support destination has been supplied |
| G-40 | Enforcement priority for two decided rules not confirmed in the build: single-company advertiser logins; rejection of duplicate driver identity, phone or bank account | See A-03 and D-05 |

---

## 14. Glossary

| Term | Meaning |
| --- | --- |
| **Terrax Media** | The business operating Cardvert. |
| **Cardvert** | The product and driver app name (see G-30 for presentation). |
| **Advertiser** | A company member who runs campaigns. |
| **Driver** | An approved owner-driver whose car carries a campaign. |
| **Operator / administrator** | Terrax Media staff using the admin area. |
| **Campaign** | An advertiser's paid placement across dates, zones and budget. |
| **Artwork (creative)** | The advert file printed on vehicles. |
| **Quotation** | The custom price proposal, with revisions, that the advertiser accepts. |
| **Accepted terms** | The immutable record of the accepted quotation revision. |
| **Offer** | A proposed assignment sent to a driver with frozen pay terms and an expiry. |
| **Assignment** | A campaign placed on one driver's vehicle. |
| **Activation** | The administrator's final step that allows an accepted assignment to earn. |
| **Installation evidence** | Photos proving the branding is installed, approved by an administrator. |
| **Verified hours** | Campaign time that passes location, time-window, movement and signal checks. |
| **Base and premium rate** | Hourly rates for valid time outside and inside the premium zone. |
| **Exclusion zone** | An area where campaign time is unpaid. |
| **Daily cap** | Maximum payable hours per driver per campaign per calendar day in West Africa Time. |
| **Sealed trip** | A trip whose evidence is complete, so earnings can be calculated. |
| **Late evidence** | Trip data received after sealing, held for operator review. |
| **Hold** | A pause on earnings while a fraud flag is reviewed. |
| **Dispute** | A driver's response to a hold. |
| **Carry-forward debt** | Money owed by a driver after a paid amount is reversed, taken from future payouts. |
| **Payout batch** | A group of payout lines prepared together. |
| **Payout line** | One payment instruction to one payee, with its own outcome. |
| **Maker / checker** | The administrator who creates a batch or correction, and the different administrator who approves it. |
| **Reconciler** | The administrator recording a payout outcome manually, who must differ from maker and checker. |
| **Provider-neutral** | Built to work with any approved provider, currently using local stand-ins. |
| **Idempotency identity** | The fixed identity a retried request carries so it is processed once. |
| **Replacement** | A new, separately approved payout line for a failed line, requiring a genuinely different bank destination. |
| **Economic ledger paid** | What the earnings ledger records as paid. |
| **Verified provider transfers** | What a payout provider has confirmed as successfully transferred. |
| **Campaign Performance Analysis** | The standard advertiser report. |
| **Measurement run** | A frozen, reproducible calculation that a report is issued from. |
| **Estimated ad exposure / modelled potential contacts** | The labelled formula estimate of advert exposure; not verified views. |
| **Target-area coverage** | A proposed geographic measure of how much of the target area had qualifying movement; definition pending approval. |
| **Suppression** | Hiding a value that could reveal too little aggregated data. |
| **Planning source** | Aggregate online audience or insight metadata linked to campaign planning. |
| **Screen-on tracking** | Tracking that runs only while the driver app is open and visible. |
| **Gate** | An external input or approval that must exist before live use. |

---

## Appendix A — Traceability

This appendix links requirement areas to the recorded decision authority and
external prerequisite register. It is for reviewers; it adds no requirements.

### A.1 Decision authority

| Requirement area | Decisions and questionnaire answers |
| --- | --- |
| Scope baseline | D11 (proposal baseline) as superseded by D18–D20 |
| Pilot shape and naming | D18, D19, D20; Q29, Q30, Q33 |
| Operator-led advertisers, driver self-registration | D1, Q13 |
| Quotation, payment timing, methods, VAT | Q1, Q2, Q3, Q14, Q28 |
| Campaign approval, changes, activation, installation, artwork | Q6, Q9, Q15, Q16, Q17, Q18 |
| Matching and offers | Q7, Q8, Q19, Q20 |
| Cancellation, refunds, expedited waiver | Q24, D18(d), D20(b) |
| Hourly pay, tiers, cap, parked time | D2, D4, D9, D12, D14, D18(a), D21, D22; Q4, Q5 |
| Fraud holds and release | D5, Q21, Q22, D18(c) |
| Payouts, owner-drivers, payee | Q23, Q27, D18(e) |
| Encryption boundary | D17 |
| Screen-on tracking, native post-pilot | D3, D18(b), Q10, D23 |
| Trip evidence and late data | D15, D16, D25 |
| Retargeting and activation | D6, D11(b), D20(a), Q11 |
| Report naming and ROI | D20(c), Q12, Q30 |
| Notifications | Q34, D24 |
| Sessions and security defaults | D26, D27 |
| Driver account setup | D28 |
| Single-company advertisers; single-admin applicant review | D29 |
| Duplicate driver identity; planning-source link freeze | D30 |
| Vehicle approval end date | D31 |
| Disclosure history retention | D34 |
| Manual contact task invalidation | D35 |
| Legal and privacy sign-off | Q26, Q31 |
| Infrastructure ownership | Q32 |

### A.2 Gate mapping

| PRD gate | External prerequisite register entry |
| --- | --- |
| G-01 | EXT-PAYMENT-PROVIDER |
| G-02 | EXT-DISBURSEMENT-PROVIDER |
| G-05 | EXT-EMAIL-PROVIDER |
| G-06 | EXT-PHONE-OPERATOR |
| G-08 | EXT-KMS-CUSTODY |
| G-09 | EXT-STORAGE-PROVIDER |
| G-10 | EXT-MALWARE-SCANNER |
| G-11 | EXT-BASEMAP |
| G-12, G-14 | EXT-LEGAL-PRIVACY |
| G-15 | EXT-REPORT-METHOD |
| G-16 | EXT-AD-PLATFORM |
| G-17 | EXT-Q28-COMPANY |
| G-18 | EXT-COMMERCIAL-VALUES |
| G-19 | EXT-SETTLEMENT-BANK |
| G-20 | EXT-BUDGET-POLICY |
| G-21 | EXT-CAMPAIGN-BUDGET-SCOPE |
| G-21a | EXT-EVIDENCE-POLICY (plus the weekly verified-hours floor operations parameter) |
| G-22 | EXT-UPLOAD-POLICY |
| G-23 | EXT-MESSAGE-COPY |
| G-24 | Not separately registered; recorded here as an open wording approval |
| G-25 | Deferred physical validation (PWA physical matrix; route and battery) |
| G-26 | EXT-RELEASE-ENV, EXT-STAGING-APPROVAL |
| G-27 | EXT-OPERATIONS-OWNER |
| G-28 | EXT-BRAND-APPROVAL |
| G-29 | EXT-PILOT-PERMITS |
| G-38 | EXT-STORE-ASSETS |
| Not a pilot gate | EXT-RM2-CALIBRATION-DATA and EXT-RM2-APPROVER: optional post-pilot field calibration of parked-time allowances and its named approver; the reviewed current rule stays authoritative for build and pilot |

### A.3 Source conflicts resolved in this document

| Topic | Earlier source | Resolution used |
| --- | --- | --- |
| Driver app | Proposal: native app with background GPS in the MVP | Screen-on installable web app for the pilot; native app post-pilot (D18, D23) |
| Driver pay | Proposal and brief: mileage, traffic density and exposure quality | Fixed hourly base and premium rates with daily cap (D2, D12, D18, D21) |
| Pricing | Working decisions: packages plus custom quotes | Custom quotation for every campaign (Q1) |
| Payment timing | Working decisions: deposit then balance; credit post-pilot | Full payment before production; approved corporate credit allowed (Q2) |
| VAT | Working decisions: VAT-exclusive | VAT-inclusive with itemised net and VAT (Q28) |
| Payouts | Working decisions: seven-day wait for all, manual transfers | Clean earnings join the next weekly batch; flagged earnings held; automated provider transfers (Q22, Q27) |
| Pilot | Working decisions: Lagos, 15–25 vehicles, name "Vantage" | Abuja, 10 vehicles, 5 advertisers, 3 months; Cardvert (D18) |
| Retargeting | Working decisions: no direct platform push | Aggregate geographic/time/context activation allowed when gated inputs exist (D20) |
| Public advertiser sign-up | Proposal lists advertiser registration | Operator-led (D1); front door left as owner decision |
| Estimate label | Methodology contract: "Modelled potential contacts" | Screen uses "Estimated ad exposure"; downloads keep the contract label; final labels need method approval |

## Appendix B — Screen index

| Area | Screen | Route |
| --- | --- | --- |
| Public | Sign in | `/login` |
| Public | Forgot and reset password | `/forgot-password`, `/reset-password` |
| Public | Driver application, status and code renewal | `/apply` |
| Public | Driver account setup | `/driver-account-setup` |
| All | Forced password change | `/change-password`, `/driver/change-password` |
| Advertiser | Dashboard | `/advertiser` |
| Advertiser | Campaign list and new campaign | `/advertiser/campaigns`, `/advertiser/campaigns/new` |
| Advertiser | Campaign detail (preparation, terms, changes, artwork, cancellation) | `/advertiser/campaigns/{campaign}` |
| Advertiser | Zones, report, coverage map | `/advertiser/campaigns/{campaign}/zones`, `/report`, `/map` |
| Advertiser | Company profile, billing, planning sources | `/advertiser/company`, `/advertiser/billing`, `/advertiser/planning-sources` |
| Driver | Home, assignments, track, earnings, trip detail, profile | `/driver`, `/driver/assignments`, `/driver/track`, `/driver/earnings`, `/driver/earnings/trips/{trip}`, `/driver/profile` |
| Driver | Phone diagnostics | `/driver/capabilities` |
| Operator | Overview, users, drivers, vehicles | `/admin`, `/admin/users`, `/admin/drivers`, `/admin/vehicles` (each with `/new`) |
| Operator | Advertiser company | `/admin/advertisers/{organization}/company` |
| Operator | Driver applications and detail | `/admin/driver-applications`, `/admin/driver-applications/{application}` |
| Operator | Approvals | `/admin/approvals` |
| Operator | Assignments, new offer, assignment detail | `/admin/assignments`, `/admin/assignments/new`, `/admin/assignments/{assignment}` |
| Operator | Fraud, late evidence, contact | `/admin/fraud`, `/admin/late-data`, `/admin/contact` |
| Operator | Measurement runs and detail | `/admin/measurement`, `/admin/measurement/{run}` |
| Operator | Billing, campaign billing, closeout | `/admin/billing`, `/admin/billing/{campaign}`, `/admin/billing/{campaign}/closeout` |
| Operator | Payouts, rules, corrections | `/admin/payouts`, `/admin/payouts/rules`, `/admin/payouts/corrections` |
| Operator | Payout batches, batch detail, line detail | `/admin/payouts/batches`, `/admin/payouts/batches/{batch}`, `/admin/payouts/batches/{batch}/lines/{line}` |
| Operator | Traffic profiles, planning sources, audit | `/admin/traffic`, `/admin/planning-sources`, `/admin/audit` |
