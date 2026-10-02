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
- [Sign-in security and availability](#sign-in-security-and-availability)
- [Demo and staging external-input placeholders](#demo-and-staging-external-input-placeholders)
- [Admin portal](#admin-portal)

---

### Product and brand

**Current rule:** The business is **Terrax Media**; the product and app are
**Cardvert** (Q29). Signed-in screens say "Terrax Media" when a person acts
(reviews, approvals, payments) and "Cardvert" for automatic actions; times read
"Nigeria time (WAT)" (D38a). Advertiser and driver screens never show hashes,
run IDs or fingerprints; staff screens and downloads may (D38c). Four visual
directions remain, with Ivory Ledger as the default (D37); two new candidates,
Directions 5 and 6, are offered for the client's review (REQ-071).
The public website uses **Request a campaign quote** for its on-site advertiser
enquiry, **Apply to drive** for `/apply`, and **Sign in** for `/login` (D52,
REQ-070). Advertiser account setup remains operator-led; the enquiry creates
neither an account nor a campaign. `/` is the only public landing route.

**History:**
- **2026-08-14** — Client confirmed the names (Q29, D18).
- **2026-09-24** — Client rejected seven of eleven visual directions (D37). Built in `d583829`.
- **2026-09-24** — Owner set the naming, time-label and no-hashes rules (D38a, D38c). Built in `7a9ceb0` (REQ-001).
- **2026-10-02** — Owner replaced varied campaign/driver CTA labels and “Open Cardvert” with explicit next steps, approved an on-site enquiry form and removed the obsolete `/landing` redirect (D52, REQ-070). Previously advertiser buttons opened a prepared email. Local implementation; merge and live email readiness remain pending.
- **2026-10-02** — Owner: the four kept directions look too alike, and the menu text is too small. Added Direction 5 (Route, from the public site) and Direction 6 (Wrap, vehicle-wrap blocks) as candidates, and enlarged the menu text in every direction (REQ-071).

### Staff roles and departments

**Current rule:** One Terrax admin role; the client's departments (Operations,
Compliance, Finance, Customer Service, Admin) are sections of the admin
"Waiting for you" work queue, not separate logins (D38e). The client's
"Finance Officer" is whichever admin handles money. One admin may complete all
driver approval checks; advertiser logins belong to one company (D29).
For now, set up one advertiser login per company; do not add invitations for
additional company staff (D47, REQ-060).

**History:**
- **2026-09-02** — Owner decision on single-company advertiser logins and one admin for driver checks (D29).
- **2026-09-24** — Client named its departments; owner mapped them to work-queue sections (D38e). Built in `7a9ceb0` (REQ-001).
- **2026-09-30** — Owner: no named people per department; everyone uses the one admin role (REQ-031).
- **2026-10-01** — Owner kept one advertiser login per company for the admin redesign; the proposed additional-person invitation is omitted (D47, REQ-060). Existing membership history and access constraints remain.

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
by the Finance officer (client answers item 7). The Paystack adapters and local
Test Mode checkout are built and verified; production use stays off until the
public webhook, transfer and production-provider gates pass (REQ-035).

**Still open:** [REQ-051](requests.md) Paystack activation and developer admin
access, [REQ-025](requests.md) password and two-step verification,
[REQ-027](requests.md), [REQ-035](requests.md).

**History:**
- **2026-08-14** — Client confirmed payment timing and methods (Q2, Q3, D18).
- **2026-09-24** — Client chose Paystack with OPay settlement (client answers item 7).
- **2026-09-28** — Paystack adapters built from the public docs, disabled without keys. Built in `dbd41e1` (REQ-004).
- **2026-09-29** — Existing test-key access was established and one real ₦101 Test Mode checkout completed, verified and applied once by Cardvert; public webhook, transfer and production approval gates remain open (REQ-027, REQ-035).

### Invoices and VAT

**Current rule:** Cardvert issues numbered invoices; quotations may be made
outside it and recorded (Q14). Customer-facing prices are **VAT-inclusive
(7.5 %)**, while the invoice still shows net, VAT and gross (Q28). Invoice
details: Terrax Media Company Ltd, 73 Lome Crescent, Wuse Zone 7, FCT Abuja,
07074200080, terraxmediacompany@gmail.com, **TIN 2521515778093, RC 8688553**
(D43g); fields include serial number, RC number, client and CEO signature
lines, campaign duration, quantity (the number of advert campaigns) and bank
details (client answers item 6). The invoice leads with the VAT-inclusive
total; staff still enter prices before VAT. Real invoice bank details stay
unset until Terrax supplies them, and a real invoice cannot be issued without
them or without the accountant's sign-off (D42). Demo/staging sample invoices
may use registered seed-backed bank placeholders under D46; these never
become verified issuer facts or real payment instructions.

**Still open:** [REQ-041](requests.md) OPay bank details;
[REQ-042](requests.md) accountant's confirmation and [REQ-052](requests.md) someone to check the sample invoice.

**History:**
- **2026-08-14** — Client confirmed in-platform invoices and VAT-inclusive display (Q14, Q28, D18).
- **2026-09-24** — Client supplied company details and invoice fields (client answers item 6).
- **2026-09-29** — Owner approved the invoice layout: bank slots left blank until the real OPay details arrive, prices still entered before VAT (D42, REQ-009). Built in `0b53eab`.
- **2026-10-01** — Client confirmed 2521515778093 is the TIN and gave the RC number 8688553 (D43g, REQ-019).
- **2026-10-01** — Owner's authoritative admin design allows registered bank placeholders only on demo/staging sample invoices (D46, REQ-059); real issuance remains fail closed.

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
(Q19) **and motorcycles** (D43h).

**History:**
- **2026-08-14** — Client confirmed self-registration, requirements, owner-drivers and cars (Q13, Q19, Q23, Q26, D18).
- **2026-09-02** — Owner decisions on activation and vehicle approval dates (D28, D31).
- **2026-09-24** — Client's permit answer covers SUVs, sedans and motorcycles (client answers item 19). Recorded as motorcycles allowed on 2026-10-01 (D43h, REQ-034).
- **2026-10-01** — Owner requested Lane 1's guided applicant flow and own-car chooser (D45, REQ-054). Approval, activation and live-use gates remain unchanged; active-driver renewals are later-stage work.

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
continuous stop adds no distance (D39b, D43d).

**History:**
- **2026-08-14** — Client confirmed screen-on tracking with driver Start/End (Q10, D18).
- **2026-08-20** — Owner chose a parked-time detector for hourly pay (120-second windows, 25-metre threshold; D22).
- **2026-09-25** — Client set the 5-minute stop rule (D39b). Built for daily-rate pay in `e14149d` (REQ-002). Hourly (v1–v3) work keeps D22.
- **2026-09-30** — Client confirmed the 5 minutes apply to **each** stop, not the whole trip or day (D43d).

### Driver pay

**Current rule:** A driver earns a **daily rate of ₦10,000** for covering the
**expected daily miles** (70 in the pilot). A shorter day pays **its share of
the day**: miles counted ÷ expected miles × ₦10,000 (50 of 70 miles =
₦7,143), with **no minimum distance**. **Only miles inside the campaign area
count**. Covering more than the expected miles earns no more than the day rate.
Rates are set per campaign on an audited revision and frozen when the driver
accepts; "on request" areas may have their own rate (D39a, D43a–c). Work
accepted under hourly pay keeps its rules (D14, D21). Switching daily-rate pay
on for real campaigns: [REQ-048](requests.md).

**History:**
- **2026-07 to 2026-08-04** — Fixed naira amount **per hour** of verified time, with a daily cap on payable hours (D2, D4); built as `payout_v1` and `payout_v2` (D9, 30 Jul); reconfirmed against the proposal (D12, 4 Aug).
- **2026-08-14** — Client set one platform hourly rate with an admin campaign override, and a higher (premium) hourly rate inside the primary zone (Q4, Q5, D18). Built as `payout_v3`.
- **2026-09-24** — Client's answer gave per-mile figures (₦140 inside the primary zone, ₦50 outside, 70 miles a day) and a ₦10,000 daily rate for special locations (client answers item 2).
- **2026-09-25** — Client moved new work to a **daily rate** for the expected distance, with reduced pay for less (D39a). Built as `payout_v4` in `e14149d` (REQ-002).
- **2026-09-29** — Architecture §16 and PRD §7 amended for daily-rate pay and automatic payouts (REQ-012). Built in `0b53eab`.
- **2026-09-30** — Client confirmed ₦10,000 a day; the per-mile sheet only shows how the figure was derived (D43a, REQ-016).
- **2026-10-01** — Client chose the proportional share for short days with no minimum, and only in-area miles count (D43b–c, REQ-014, REQ-015).

### Payout approval and timing

**Current rule:** Drivers are paid by **automatic bank transfer** through an
approved provider (Q27; Paystack Transfers funded from OPay, client answers
item 8), **every day** (D43e). **Payouts are approved automatically** for clean
earnings only: no hold, flag or open dispute; a verified bank account that has
**already received a person-approved payment**; at most one full day's rate per
driver per day across campaigns. Everything else goes to an admin. There is
**no run limit**: the setting is at its maximum, so it never binds (D43f).
Admins can pause automatic payouts, get the alerts in the Finance section of
"Waiting for you", and reconcile daily (D39c, D40). The client calls the
person doing this the Finance Officer; in Cardvert it is any admin. Switching
automatic payouts on: [REQ-048](requests.md).

**Paystack's transfer fee is paid by the driver** (deducted from the payout; [REQ-053](requests.md) builds it). Optional hardening:
[REQ-036](requests.md), [REQ-040](requests.md).

**History:**
- **2026-08-14** — Automated bank transfers confirmed (Q27, D18). Every batch was prepared by one person and approved by a different person (maker-checker, architecture §16.3 / RM10).
- **2026-09-25** — Client chose automatic approval with no person approving each batch; Finance monitors and follows up (D39c). Built in `3b6b396` (REQ-003).
- **2026-09-28** — Owner added: the first payment to any new bank account goes to a person (D40b, security review). Built in `3b6b396`.
- **2026-09-30** — Owner: payout alerts go to every admin (as built), not named people (REQ-030).
- **2026-10-01** — Client chose daily payouts and no run limit (D43e–f, REQ-017, REQ-029).
- **2026-10-01** — Client: drivers bear Paystack's transfer fee (REQ-026; build REQ-053).

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
The notification panel is an unread inbox: Mark read removes that item and
Mark all read clears current unread items, including older pages. Read records
remain stored; notifications arriving afterward appear normally (D54, REQ-075).

**History:**
- **2026-08-14** — Client confirmed channels (Q34, D18); **2026-08-24** owner decision on email preferences (D24).
- **2026-09-24** — Client supplied the support number (client answers items 14–15).
- **2026-10-02** — Owner clarified that read notifications must disappear from the panel (D54, REQ-075), replacing its earlier history-list presentation. Local implementation pending commit and merge.

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
access (Q32). Hosting, database and file storage on **Hetzner**; maps from
**MapTiler**; email from **Postmark** (support@terraxmedia.com); **ClamAV** file
checking; domain **terraxmedia.com** (D44, client answers items 9–16). Bank and
NIN encryption keys stay in Cardvert's own key ring, because Hetzner has no
key-management service (D44).

**Still open:** [REQ-050](requests.md) Hetzner, Postmark and MapTiler accounts;
[REQ-043](requests.md) domain connection; [REQ-033](requests.md) which address (for example app.terraxmedia.com). Templates for the new providers:
[REQ-049](requests.md).

**History:**
- **2026-08-14** — Client confirmed ownership (Q32, D18).
- **2026-09-24** — Client approved ClamAV, Postmark, Mapbox ("short run", Google Maps later) and terraxmedia.com, and left hosting, storage and region to the developer's recommendation (client answers items 9–16). The recommendation was Render with AWS storage and encryption.
- **2026-09-29** — Deployment templates for Render, AWS and Mapbox written, with every secret blank and nothing applied (REQ-010). Built in `0b53eab`.
- **2026-09-30** — Owner chose Hetzner instead of Render and AWS, and MapTiler instead of Mapbox (D44). The Render, AWS and Mapbox templates are superseded (REQ-049).

### Legal, privacy and retention

**Current rule:** Built GPS, ID collection, results and reports are accessible during development without legal approval switches; tenant isolation, aggregation limits and query recording remain, and legal/privacy plus overlap/differencing protections must be restored before real users (D56, REQ-072/089).

**Still open:** [REQ-031](requests.md) lawyer's name, [REQ-032](requests.md) legal pack.

**History:**
- **2026-10-02** — Owner replaced the prior rule gating GPS, documents, reports and retargeting until legal approval with D56 development access and seed-only client-input substitutes; actual legal/retention answers remain open.
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

### Sign-in security and availability

**Current rule:** Failed logins may temporarily block an account or IP address;
a rise in failures across the whole platform alerts Terrax instead of locking
everyone out. Redis failure still blocks sign-in safely. Password work runs
outside the API event loop with a four-thread limit per process; same-email
PostgreSQL login attempts queue consistently for known and unknown accounts.
The API image defaults to two configurable workers (D45).

**History:**
- **Before Lane 1 integration** — The global login-failure bucket could block all sign-ins, and password work ran on the request event loop.
- **2026-10-01** — Owner requested integration of Lane 1's availability and password-work controls, preserving automatic-payout account protection (D45, REQ-054).

### Demo and staging external-input placeholders

**Current rule:** Use realistic seed-backed content for missing external inputs
in demo/staging, without sample badges, and list every placeholder, location,
real replacement input and waiting request in `docs/placeholders.md` (D46,
REQ-059). D56 removes legal display/collection switches for development while retaining real provider, money, tenant and aggregation protections.
Never substitute real accepted legal/consent text, real verified invoice or
payment bank details, or pay/payout values. Missing features are built from
seed-backed functionality or omitted; no hard-coded fake UI or nonworking
buttons. The owner expects the registered demo inputs to be replaced before
launch; replacement is a launch checklist task, with no additional runtime
blocker authorized by that clarification.

**History:**
- **2026-10-01** — The earlier L2-1 preview proposed labelled demo cards. The owner's authoritative design section 11 superseded it with realistic registered external-input placeholders (D46, REQ-059).
- **2026-10-01** — Owner clarified that demo inputs will be replaced before launch and questioned a new code gate. Keep the replacement checklist and existing fail-closed checks; no new backend gate is approved.

### Admin portal

**Current rule:** The authoritative 1 October design governs the task-based
admin menu, named search, driver/campaign/company hubs and section drawers
(D48, REQ-058). The latest owner review applies development replacement policy:
remove obsolete admin routes and redirects, and update current callers to the
canonical hubs/work lists (D51, REQ-067). Settings staff logins list Terrax
staff only and hide the automatic-payout account. Driver and advertiser logins
live with their own records; campaign Pay terms belong on the campaign hub.
One advertiser login per company remains the current scope (D47). Review
documents through the existing audited access controls, and use existing
server decisions for activation, funding, pay and report issuance.

Staff Resume is permitted only for a recorded operational pause, classified on the server. Budget-related and unknown pauses are refused with a plain explanation; current start requirements are rechecked and the actor, reason and pause identity are logged (D55, REQ-081). Staff list totals, oldest-first paging and row names are approved to bound badges, work lists and Trip checks (D55, REQ-077/078/083/085).

The task home/menu label is **Work queue** (D50, REQ-065). The owner explicitly
authorized starting L2-1b on the incomplete expedited A checkpoint (REQ-064);
A acceptance remains open; the owner authorized the two source commits while tracked acceptance gaps remain. The four specified read additions, the
company-list move and phone search are approved. Staff in-person-check paging,
actual trip dates/campaign names on the pay list, and the held-pay/recorded-route
staff reads are separately approved (REQ-066, REQ-068, REQ-069; D53).
The route read logs each staff view before returning coordinates and permits
no advertiser sharing or caching; held pay reads existing pending ledger facts
without changing releases or decisions. Other additional reads remain
subject to the owner's decision. REQ-062 records the open pay-summary and
campaign-area gap. A data-read failure must never appear as a confirmed empty
list, completed check or zero balance.

**History:**

- **2026-10-02** — Owner confirmed guarded staff Resume and bounded read options (D55); local implementation and verification in progress.
- **2026-10-02** — Owner approved the two staff reads for suspicious-trip
  recorded routes and actual held pay (D53, REQ-069).
- **2026-10-02** — Earlier explicit old-URL preservation ended: the owner
  requires removal of obsolete route pages and redirects under the development
  policy, plus glossary/failure/performance fixes (D51, REQ-067). Read-only
  physical-check paging and trip-date/campaign-name details were approved
  separately (REQ-066, REQ-068). The owner will perform the browser walkthrough.
- **2026-10-02** — The owner renamed the task home/menu Work queue (D50, REQ-065) and explicitly authorized starting the next batch while A gaps remain tracked (REQ-064).
- **2026-10-02** — Deadline exception: target approximately 70% changed-code coverage locally for L2-1a, document unfinished requirements and proceed to the next batch (D49, REQ-063). Existing correctness/access checks and normal CI policy remain.
- **2026-10-01** — The owner replaced the earlier menu/page preview with the authoritative admin design and its two-batch order (D48, REQ-058).
- **2026-10-01** — The owner moved company search to the first batch, kept one company login and required demo inputs to be replaced before launch through the documented checklist (D47).
- **2026-10-01** — Phone-number matching in the existing driver search was separately approved (REQ-061).

- **2026-10-02** — Core admin source Built in `39eb49c` (L2-1a expedited checkpoint); A-only build, 283 tests and source review passed. Full design acceptance and CI/D33 remain open; B source is delivered separately.
