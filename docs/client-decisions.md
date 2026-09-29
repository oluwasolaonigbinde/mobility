# Client decisions — what the client wants now, and how it changed

Start here when the owner says "the client said…". Each topic states the
**current rule** in plain words, links the questions still open, and keeps a
dated **history** so earlier rules are never lost. Work items live in
[requests.md](requests.md); source documents are listed in
[client-documents/README.md](client-documents/README.md).

## How this file relates to the formal record

This file is the plain-language index. The formal record stays in
[decisions-log.md](decisions-log.md): Part 1 is the append-only log of decisions
(`D1`, `D2`, …) and Part 2 holds the questionnaire items `Q1`–`Q34`. Every
current rule below cites the D-row or Q-row that governs it or, where none
exists yet, the dated client answer it comes from. If this file and
the formal record ever disagree, the newest D-row wins; fix this file in the
same change.

## How to record a change

When the client, the PM or the owner changes or adds a rule:

1. Add a row to [requests.md](requests.md) first (see its rules).
2. Find the topic here. Move its current rule into **History** as a dated line
   (what it was, and when it stopped applying), then write the new current
   rule. Add a topic if none fits. Never delete history.
3. If the change affects product behaviour, money, privacy, eligibility or
   security, also add a new D-row to decisions-log Part 1, update the affected
   Q-row in Part 2 (if there is one), and amend `docs/architecture.md`, all in
   the same commit.
4. Put open questions in [requests.md](requests.md) as `NEEDS ANSWER` rows and
   link them under **Still open**; do not copy the question text here.
5. When the work merges, add "Built in `<commit>`" to the history line.

Accepted work is never repriced or silently changed: a new rule applies to new
acceptances unless a D-row says otherwise (D14, D21).

## Topics

- [Product and brand](#product-and-brand)
- [Staff roles and departments](#staff-roles-and-departments)
- [Pricing and quotations](#pricing-and-quotations)
- [Advertiser payments](#advertiser-payments)
- [Invoices and VAT](#invoices-and-vat)
- [Budgets and alerts](#budgets-and-alerts)
- [Campaign lifecycle and changes](#campaign-lifecycle-and-changes)
- [Cancellation and refunds](#cancellation-and-refunds)
- [Artwork](#artwork)
- [Matching, offers and activity](#matching-offers-and-activity)
- [Drivers and vehicles](#drivers-and-vehicles)
- [Installation photos](#installation-photos)
- [Tracking and stopped time](#tracking-and-stopped-time)
- [Driver pay](#driver-pay)
- [Payout approval and timing](#payout-approval-and-timing)
- [Fraud holds and earnings release](#fraud-holds-and-earnings-release)
- [Complaints and support](#complaints-and-support)
- [Notifications and contact](#notifications-and-contact)
- [Advertiser reporting and privacy](#advertiser-reporting-and-privacy)
- [Retargeting and ad platforms](#retargeting-and-ad-platforms)
- [Pilot shape, permits and launch](#pilot-shape-permits-and-launch)
- [Hosting, accounts and providers](#hosting-accounts-and-providers)
- [Legal, privacy and retention](#legal-privacy-and-retention)
- [File uploads](#file-uploads)

---

### Product and brand

**Current rule:** The business is **Terrax Media**; the product and app are
**Cardvert** (Q29). Signed-in screens say "Terrax Media" when a person acts
(reviews, approvals, payments) and "Cardvert" for automatic actions; times read
"Nigeria time (WAT)" (D38a). Advertiser and driver screens never show hashes,
run IDs or fingerprints; staff screens and downloads may (D38c). Four visual
directions remain, with Ivory Ledger as the default (D37).

**History:**
- **2026-08-14** — Client confirmed the names (Q29, D18).
- **2026-09-24** — Client rejected seven of eleven visual directions (D37). Built in `d583829`.
- **2026-09-24** — Owner set the naming, time-label and no-hashes rules (D38a, D38c). Built in `7a9ceb0` (REQ-001).

### Staff roles and departments

**Current rule:** One Terrax admin role; the client's departments (Operations,
Compliance, Finance, Customer Service, Admin) are sections of the admin
"Waiting for you" work queue, not separate logins (D38e). One admin may
complete all driver approval checks; advertiser logins belong to one company
(D29).

**Still open:** [REQ-031](requests.md) — named people for each department.

**History:**
- **2026-09-02** — Owner decision on single-company advertiser logins and one admin for driver checks (D29).
- **2026-09-24** — Client named its departments; owner mapped them to work-queue sections (D38e). Built in `7a9ceb0` (REQ-001).

### Pricing and quotations

**Current rule:** Every campaign gets its own quotation; there is no fixed
package catalogue. Quote lines, terms and revisions are data, and each accepted
campaign keeps an unchangeable copy of its quotation (Q1, D18). Prices such as
the service fee, printing, installation, permits and design are entered per
campaign by Terrax.

**History:**
- **2026-08-14** — Client confirmed custom quotations (Q1, D18).
- **2026-09-24** — Client supplied sample figures (10 % service charge, printing and installation ₦100,000, AMAC permit ₦100,000, optional APCON ₦50,000, optional ads ₦300,000/month, optional design ₦70,000, professional services ₦700,000; sample total ₦1,000,000). Treated as Terrax's own quotation inputs, not a price list (client answers item 2).

### Advertiser payments

**Current rule:** Standard advertisers pay in full before printing or
installation; approved corporate advertisers may use invoice/credit terms (Q2).
Advertisers can pay by bank transfer reconciled by an admin or through an
online gateway, in one payment history (Q3). The gateway is **Paystack** in
Terrax Media's name (card and bank transfer), settling to OPay; refunds are made
by the Finance officer (client answers item 7). The Paystack adapters are built
but stay off until keys are supplied (REQ-004).

**Still open:** [REQ-025](requests.md), [REQ-027](requests.md), [REQ-035](requests.md).

**History:**
- **2026-08-14** — Client confirmed payment timing and methods (Q2, Q3, D18).
- **2026-09-24** — Client chose Paystack with OPay settlement (client answers item 7).
- **2026-09-28** — Paystack adapters built from the public docs, disabled without keys. Built in `dbd41e1` (REQ-004).

### Invoices and VAT

**Current rule:** Cardvert issues numbered invoices; quotations may be made
outside it and recorded (Q14). Customer-facing prices are **VAT-inclusive
(7.5 %)**, while the invoice still shows net, VAT and gross (Q28). Invoice
details: Terrax Media Company Ltd, 73 Lome Crescent, Wuse Zone 7, FCT Abuja,
07074200080, terraxmediacompany@gmail.com; fields include serial number, RC
number, client and CEO signature lines, campaign duration, quantity and bank
details (client answers item 6). An accountant must confirm before live
invoices.

**Still open:** [REQ-019](requests.md) — RC or TIN. Layout work: [REQ-009](requests.md).

**History:**
- **2026-08-14** — Client confirmed in-platform invoices and VAT-inclusive display (Q14, Q28, D18).
- **2026-09-24** — Client supplied company details and invoice fields (client answers item 6).

### Budgets and alerts

**Current rule:** A **warning at 80 %** of the campaign budget, an **urgent
alert at 95 %**, and the campaign **pauses at 100 %**. Alerts go to every
member of the advertiser company and to Terrax admins. Only a Terrax admin
raises a budget or restarts a paused campaign, after the increase or payment is
confirmed (client answers item 3). The ratios are set per deployment in
configuration (`BUDGET_*_RATIO`) and are blank in the templates. The client
also wants fixed costs to count towards the budget: **agreed, not yet built**.

**Still open:** [REQ-037](requests.md) — fixed costs in the budget.

**History:**
- **Before 2026-09-24** — One alert level (`budget_alert_ratio`) before the pause.
- **2026-09-24** — Client asked for 80 % and 95 % warnings and a pause at 100 %; recipients "everybody" (read as all company members plus Terrax admins); fixed costs to count. The three levels and admin recipients were built in `7a9ceb0` (REQ-001); fixed costs were deferred to a money batch.

### Campaign lifecycle and changes

**Current rule:** Advertisers create a draft and submit it for admin approval
(Q6). A campaign can be submitted only with start and end dates, a total budget
and at least one target area (D38d). Launch needs funding authority, approved
artwork, assigned eligible vehicles and approved installation photos; an admin
activates it (Q15). Changes that expand a campaign apply at once within funded
headroom; reductions, removals and date changes need admin approval and a
reason (Q9).

**History:**
- **2026-08-14** — Client confirmed the lifecycle (Q6, Q9, Q15, D18).
- **2026-09-24** — Owner added the submission requirements (D38d). Built in `7a9ceb0` (REQ-001).

### Cancellation and refunds

**Current rule:** A 24-hour refund window starts at the first confirmed
payment that authorises production; standard production waits until it
closes. An advertiser may ask for earlier production through a recorded
waiver, which ends refund eligibility once production starts. Cancelling stops
new work at a fixed cutoff, and drivers are paid their verified earnings up to
that moment (Q24, D20b).

**History:**
- **2026-08-14** — Client confirmed the window and waiver (Q24, D18, D20).

### Artwork

**Current rule:** Advertisers upload artwork in Cardvert; an admin approves or
rejects it before production or launch (Q18, D7).

**History:**
- **2026-07** — Adopted as an MVP rule (D7); client confirmed 2026-08-14 (Q18, D18).

### Matching, offers and activity

**Current rule:** Cardvert recommends eligible drivers and vehicles; an admin
approves the assignment (Q7). The driver gets a full offer and accepts or
declines (Q8); accepted terms are frozen. One active campaign per vehicle
(Q16). A configurable minimum of verified hours applies, and a driver is
flagged after seven inactive days (Q20).

**History:**
- **2026-08-14** — Client confirmed (Q7, Q8, Q16, Q20, D18).

### Drivers and vehicles

**Current rule:** Drivers register themselves, upload documents and are
approved by an admin before working (Q13); approved accounts are activated by
the driver after admin authorisation (D28). Required: licence, vehicle
registration, insurance, NIN, vehicle photos, a verified bank account and a
legally approved driver agreement and consent (Q26). In the pilot the vehicle
is registered to its driver, who is the payee; no fleet owners (Q23). Vehicle
approval ends on an admin-entered date (D31). Pilot vehicles: roadworthy cars
(Q19).

**Still open:** [REQ-034](requests.md) — motorcycles.

**History:**
- **2026-08-14** — Client confirmed self-registration, requirements, owner-drivers and cars (Q13, Q19, Q23, Q26, D18).
- **2026-09-02** — Owner decisions on activation and vehicle approval dates (D28, D31).
- **2026-09-24** — Client's permit answer mentions SUVs, sedans and motorcycles (client answers item 19). On 2026-09-25 the owner told the client motorcycles are assumed allowed; not yet a D-row.

### Installation photos

**Current rule:** Before campaign hours can earn, installation photos must be
approved by an admin (Q17). Views: **front, back, left, right and close-up**.
The driver or an admin uploads them (there is no installer login); Compliance
reviews; new photos are required **weekly**; Terrax's inspector makes spot
checks on top (client answers item 4). Set in configuration
(`INSTALLATION_EVIDENCE_*`).

**Still open:** [REQ-039](requests.md) — spot-check and display-proof values.

**History:**
- **2026-08-14** — Client confirmed approved installation evidence (Q17, D18).
- **2026-09-24** — Client named the views, uploaders and weekly or twice-weekly renewal. The owner chose weekly and told the client it can change (2026-09-25). Built in `7a9ceb0` (REQ-001).

### Tracking and stopped time

**Current rule:** In the pilot, drivers use the installable Cardvert app with
the screen on, starting and ending each trip themselves; native background
tracking comes after the pilot (Q10). For daily-rate work, **each stop of up to
5 minutes** (traffic, checkpoints, fuel) counts as driving, and a longer
continuous stop adds no distance (D39b).

**History:**
- **2026-08-14** — Client confirmed screen-on tracking with driver Start/End (Q10, D18).
- **2026-08-20** — Owner chose a parked-time detector for hourly pay (120-second windows, 25-metre threshold; D22).
- **2026-09-25** — Client set the 5-minute stop rule (D39b). Built for daily-rate pay in `e14149d` (REQ-002). Hourly (v1–v3) work keeps D22.

### Driver pay

**Current rule:** A driver earns a **daily rate** for covering the **expected
daily distance** in a campaign; covering less earns reduced pay. The client's
figures are ₦10,000 for 70 miles, and "on request" areas may have their own
rate. Rates are set per campaign on an audited revision and frozen when the
driver accepts (D39a). Work accepted under hourly pay keeps its rules (D14,
D21). Daily-rate publishing stays switched off until the open questions are
answered.

**Still open:** [REQ-014](requests.md) short-day rule, [REQ-015](requests.md)
which miles count, [REQ-016](requests.md) ₦10,000 or ₦9,800 and any cap.
Documentation: [REQ-012](requests.md).

**History:**
- **2026-07 to 2026-08-04** — Fixed naira amount **per hour** of verified time, with a daily cap on payable hours (D2, D4); built as `payout_v1` and `payout_v2` (D9, 30 Jul); reconfirmed against the proposal (D12, 4 Aug).
- **2026-08-14** — Client set one platform hourly rate with an admin campaign override, and a higher (premium) hourly rate inside the primary zone (Q4, Q5, D18). Built as `payout_v3`.
- **2026-09-24** — Client's answer gave per-mile figures (₦140 inside the primary zone, ₦50 outside, 70 miles a day) and a ₦10,000 daily rate for special locations (client answers item 2).
- **2026-09-25** — Client moved new work to a **daily rate** for the expected distance, with reduced pay for less (D39a). Built as `payout_v4` in `e14149d` (REQ-002).

### Payout approval and timing

**Current rule:** Drivers are paid by **automatic bank transfer** through an
approved provider (Q27; Paystack Transfers funded from OPay, client answers
item 8). **Payouts are approved automatically** for clean earnings only: no
hold, flag or open dispute; a verified bank account that has **already received
a person-approved payment**; at most one full day's rate per driver per day
across campaigns; within a run limit. Everything else goes to a person. Finance
can pause automatic payouts, sees alerts and reconciles daily (D39c, D40).
Automatic payouts stay off until frequency and limits are set.

**Still open:** [REQ-017](requests.md) daily or weekly, [REQ-026](requests.md)
transfer fee, [REQ-029](requests.md) run limit, [REQ-030](requests.md) alert
recipients. Optional hardening: [REQ-036](requests.md).

**History:**
- **2026-08-14** — Automated bank transfers confirmed (Q27, D18). Every batch was prepared by one person and approved by a different person (maker-checker, architecture §16.3 / RM10).
- **2026-09-25** — Client chose automatic approval with no person approving each batch; Finance monitors and follows up (D39c). Built in `3b6b396` (REQ-003).
- **2026-09-28** — Owner added: the first payment to any new bank account goes to a person (D40b, security review). Built in `3b6b396`.

### Fraud holds and earnings release

**Current rule:** Earnings from flagged trips are held for admin review, with
reasons and a dispute path; thresholds are configurable (Q21). Clean earnings
become available for the next payout. Flagged earnings stay pending with a
seven-day review target and are never released automatically; unresolved cases
escalate after day seven (Q22).

**History:**
- **2026-07** — Hold-and-review adopted (D5); client confirmed 2026-08-14 (Q21, Q22, D18).

### Complaints and support

**Current rule:** Drivers and advertisers raise complaints in the app, with a
category and an optional reference to one of their own campaigns, trips or
payouts; Customer Service answers in an inbox that also appears under
"Waiting for you" (D39d). Until the client decides: categories are a neutral
default (pay or payout, trip or tracking, campaign or job, billing or invoice,
account, other); no reply-time target; replies notify drivers in-app only;
advertiser complaints are visible to the whole company; complaint text is kept
on erasure requests unless staff decide otherwise.

**Still open:** [REQ-020](requests.md) categories, [REQ-021](requests.md) reply
target, [REQ-022](requests.md) driver email/WhatsApp, [REQ-023](requests.md)
company-wide visibility, [REQ-024](requests.md) erasure.

**History:**
- **2026-09-25** — Client asked for in-app complaints handled by Customer Service (D39d). Built in `7e39c66` (REQ-005).

### Notifications and contact

**Current rule:** In-app notifications always; advertiser transactional email
on by default, which an advertiser company can switch off (D24); drivers are
contacted on WhatsApp by operations staff; automated SMS/WhatsApp after the
pilot (Q34). Support phone/WhatsApp 07074200080, run by Customer Service; the
developer drafts short messages for Terrax to approve (client answers item 15).

**History:**
- **2026-08-14** — Client confirmed channels (Q34, D18); **2026-08-24** owner decision on email preferences (D24).
- **2026-09-24** — Client supplied the support number (client answers items 14–15).

### Advertiser reporting and privacy

**Current rule:** The standard report is a **Campaign Performance Analysis**:
verified operations, clearly labelled estimated exposure and target-area
coverage. Financial ROI appears only when an advertiser supplies conversion or
revenue data and an approved method exists (Q12, Q30, D20c). Advertisers do not
see driver names or profiles.

**Still open:** [REQ-018](requests.md) — confirm no driver identity in reports.

**History:**
- **2026-08-14** — Client confirmed the report shape and ROI rule (Q12, Q30, D18, D20).
- **2026-09-24** — Client's answer mentioned "admin officer & driver profile and the car", which conflicts with the privacy boundary; asked to clarify (client answers item 5).

### Retargeting and ad platforms

**Current rule:** Retargeting uses anonymised exposure segments, controlled
export and optional Meta/Google targeting by area, time and context — never
person-level audiences (Q11, D20a). **Off for the pilot**; Meta Business and
Google Ads accounts are to be created in Terrax's name later (client answers
item 18).

**History:**
- **2026-07** — Retargeting entered the MVP (D6); shape confirmed 2026-08-14 (Q11, D18, D20).
- **2026-09-24** — Client: off for the pilot (client answers item 18).

### Pilot shape, permits and launch

**Current rule:** Abuja; 10 vehicles; 5 paying advertisers; 3 months (Q30).
Terrax Media owns permit confirmation, and no pilot campaign launches until
permit evidence is recorded and approved (D19). The developer supports early
operations while training Terrax's operations team (Q33).

**Still open:** [REQ-032](requests.md) — permit references, legal pack, pilot
drivers, vehicles and advertisers.

**History:**
- **2026-08-14** — Client confirmed pilot shape, permits ownership and operations (Q30, Q33, D18, D19).
- **2026-09-24** — Client: AMAC permit and APCON approval in progress; installer Kromatiks Ltd (client answers item 19).

### Hosting, accounts and providers

**Current rule:** Terrax owns the cloud accounts and domain, with developer
access (Q32). Hosting on **Render**; file storage and encryption on the hosting
provider's services (AWS); **ClamAV** file checking; **Postmark** email from
support@terraxmedia.com; **Mapbox** maps now, Google Maps later; domain
**terraxmedia.com** (client answers items 9–16).

**Still open:** [REQ-028](requests.md) accounts, [REQ-033](requests.md) domain.
Templates: [REQ-010](requests.md).

**History:**
- **2026-08-14** — Client confirmed ownership (Q32, D18).
- **2026-09-24** — Client chose the providers and domain (client answers items 9–16).

### Legal, privacy and retention

**Current rule:** Terrax Media's legal/compliance adviser approves the privacy
policy, consent wording and retention (Q31). Live GPS, onboarding documents,
reports and retargeting stay gated until the legal pack arrives. Retention is
configurable; the client's "keep old files 6 months" must be reconciled with
legal retention for KYC and money records (client answers items 11 and 17).

**Still open:** [REQ-031](requests.md) lawyer's name, [REQ-032](requests.md) legal pack.

**History:**
- **2026-08-14** — Client confirmed the approval owner (Q31, D18).
- **2026-09-24** — Legal pack in progress; 6-month file retention requested (client answers items 11, 17).

### File uploads

**Current rule:** Limits per purpose: identity documents 10 MB, vehicle photos
20 MB, installation photos 20 MB, artwork 25 MB. File types and sizes follow the
developer's recommendation; files are virus-checked (client answers item 12).

**Still open:** [REQ-038](requests.md) — client confirmation of these limits.

**History:**
- **Before 2026-09-26** — One shared 25 MB limit.
- **2026-09-24** — Client accepted the developer's recommendation; limits set per purpose and told to the client for information. Built in `7a9ceb0` (REQ-001).
