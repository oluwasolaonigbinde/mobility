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

Live accepted work is never repriced or silently changed (D14, D21, D80).
There is no live data yet: D80 removes obsolete development payout v1?v3 and
evidence v1 instead of preserving their old formats (REQ-161).

The owner approved a single development database baseline on 13 October 2026
("squash yes", D83/REQ-167/169). There are no live users or customer data.
Current database protections and bootstrap facts are preserved and verified;
disposable old development databases are recreated from the baseline.
Built in `54ddc893`; exact full schema parity, bootstrap, seeds and protection
reviews pass, with full branch verification `38539599622` green.

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
- [CI dependency security](#ci-dependency-security)
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
The public website uses **Request a Quote** for its on-site advertiser
enquiry, **Apply to drive** for `/apply`, and **Sign in** for `/login` (D52,
REQ-070). Advertiser account setup remains operator-led; the enquiry creates
neither an account nor a campaign. `/` is the only public landing route.
The enquiry keeps the notice explaining use of contact details and that no
account or campaign is created; the separate ID/bank warning is removed under
the owner's 8 October review brief (D64, REQ-122). Sign-in welcomes people with
"Welcome to Cardvert". Shared portal controls use readable sentence case and
visible selected states (REQ-120–REQ-124); the driver Home shows current work
and pay, while Profile contains personal details and lifetime totals.
REQ-127/D65 supersedes the earlier driver presentation: Home has one next
action, Jobs shows frozen rate/car/dates and actionable photos, Track owns
the live trip, Earnings lists days with one evidence-based payment status,
and Help alone explains daily pay. The header keeps the bell and Help;
Sign out stays in Profile. Driver headings and labels use sentence case.
D66/REQ-128–132 refines the review preview: the driver opens ready and idle,
Home leads with the latest payment when today's earnings are zero, badges and
small labels use sans, and past jobs do not repeat their dated status. Demo
work days use realistic qualifying mileage and separate next-day payments.

**History:**
- **2026-10-10** — Owner review replaces D65's seeded live trip with idle Start and the zero Today headline with latest payment; requires realistic daily amounts and next-day reconciliations, sans labels and nonrepeated job status (REQ-128–132, D66). Earlier D65 demo history had small trips paid together. Built in `b807d341`, with API projections in `affa641c`; final verification in `8f64cdb8` and full branch CI passed on 2026-10-12.
- **2026-10-10** — Owner replaced the text-heavy driver screens with one job per screen (REQ-127, D65), direct safe Start, honest daily payment labels and settled demo history. D39/D40/D43 money and eligibility rules remain. Built in `b807d341`, with API projections in `affa641c`; final verification in `8f64cdb8` and full branch CI passed on 2026-10-12.
- **2026-10-08** — Owner approved one consolidated portal clarity pass (REQ-120–REQ-125), including "Request a Quote", the contact-use notice without the separate ID/bank warning, and simpler sign-in/onboarding copy (D64). Built in `b807d341`, with API projections in `affa641c`; final verification in `8f64cdb8` and full branch CI passed on 2026-10-12.
- **2026-10-06** — Reviewed client-facing report/map/copy polish is integrated (REQ-104). Built in `6eb5ab9`; full CI passed before closure.
- **2026-08-14** — Client confirmed the names (Q29, D18).
- **2026-09-24** — Client rejected seven of eleven visual directions (D37). Built in `d583829`.
- **2026-09-24** — Owner set the naming, time-label and no-hashes rules (D38a, D38c). Built in `7a9ceb0` (REQ-001).
- **2026-10-02** — Owner replaced varied campaign/driver CTA labels and “Open Cardvert” with explicit next steps, approved an on-site enquiry form and removed the obsolete `/landing` redirect (D52, REQ-070). Previously advertiser buttons opened a prepared email. Built in `c2ab2d9`; full CI passed on 2026-10-06. Live email readiness remains a separate setup obligation.
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
Public payment callbacks are bounded to 1 MiB at the edge and during app
streaming before authentication; original signed bytes remain unchanged (D84,
REQ-171). Payment confirmation still requires canonical verified evidence.
An interrupted online checkout is reconciled using its saved reference under
serialized audited recovery; one ambiguous not-found reply never permits a new
reference (D85, REQ-173).

**Still open:** [REQ-051](requests.md) Paystack activation and developer admin
access, [REQ-025](requests.md) password and two-step verification,
[REQ-027](requests.md), [REQ-035](requests.md).

**History:**
- **2026-08-14** — Client confirmed payment timing and methods (Q2, Q3, D18).
- **2026-10-14** — Owner approved bounded public callback buffering (D84/REQ-171); earlier callbacks authenticated only after an unbounded body read. Local declared/chunked/exact-byte regressions pass; batch delivery gates remain pending.
- **2026-10-14** — D85/REQ-173 recovers saved uncertain checkouts; the earlier implementation refused all initialization retries even after a pre-dispatch interruption. Recovery reuses the exact reference and canonical verification, retaining uncertainty after ambiguous/duplicate responses. Fake-I/O and separate-session checks pass; money review and full batch CI remain pending.
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
details (client answers item 6). Advertiser and driver amounts use grouping and two decimal places; VAT shows
its percentage and amount (D71, REQ-142). The invoice leads with the VAT-inclusive
total; staff still enter prices before VAT. Real invoice bank details stay
unset until Terrax supplies them, and a real invoice cannot be issued without
them or without the accountant's sign-off (D42). Demo/staging sample invoices
may use registered seed-backed bank placeholders under D46; these never
become verified issuer facts or real payment instructions.

**Still open:** [REQ-041](requests.md) OPay bank details;
[REQ-042](requests.md) accountant's confirmation and [REQ-052](requests.md) someone to check the sample invoice.

**History:**
- **2026-10-07** — Owner W2-D brief requires advertiser/driver money grouped with two decimal places and VAT shown as "VAT 7.5% · ₦…"; stored values and issued invoices remain unchanged (D71, REQ-142). Earlier display precision varied by amount. Built in `78ad5580` and real integration `21239a6d`.
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
also wants fixed costs (printing, installation, permits, design and any other
quoted fixed line) to count towards the budget together with media, for the
80 %, 95 % and 100 % levels (REQ-037). This already worked; W1-B added tests
that prove it. Accepted prices never change.



**History:**
- **Before 2026-09-24** — One alert level (`budget_alert_ratio`) before the pause.
- **2026-10-05** — W1-B added tests proving that printing, installation, permits, design and any other quoted fixed line already count towards the budget together with media, for the 80 %, 95 % and 100 % levels. Accepted prices never change (REQ-037). Owner review requested this plain wording (REQ-116 (renumbered at merge from wording REQ-112)). Built in `308f04a8`, with wording in `81de2f54`.
- **2026-09-24** — Client asked for 80 % and 95 % warnings and a pause at 100 %; recipients "everybody" (read as all company members plus Terrax admins); fixed costs to count. The three levels and admin recipients were built in `7a9ceb0` (REQ-001); fixed costs were deferred to a money batch.

### Campaign lifecycle and changes

**Current rule:** Advertisers create a draft and submit it for admin approval
(Q6). A campaign can be submitted only with start and end dates, a total budget
and at least one target area (D38d). Launch needs funding authority, approved
artwork, assigned eligible vehicles and approved installation photos; an admin
activates it (Q15). Changes that expand a campaign apply at once within funded
headroom; reductions, removals and date changes need admin approval and a
reason (Q9). Campaign changes waiting for approval show "Needs staff review";
changes waiting for funding show "Waiting for funding", reusing the existing
staff status labels without changing their authority (D63, REQ-113).
Editing any change-form field clears its preview; confirmation requires a fresh
preview of those inputs (D71, REQ-140). Completed and cancelled campaigns no
longer offer a new custom-quotation request (D71, REQ-142).

**History:**
- **2026-10-07** — Owner W2-D brief replaces retained previews after edits with fresh-preview confirmation, and removes terminal-campaign quotation requests (D71, REQ-140, REQ-142); existing funding and approval rules remain. Built in `78ad5580` and real integration `21239a6d`.
- **2026-08-14** — Client confirmed the lifecycle (Q6, Q9, Q15, D18).
- **2026-09-24** — Owner added the submission requirements (D38d). Built in `7a9ceb0` (REQ-001).
- **2026-10-06** — Owner approved the existing staff labels for advertiser campaign-change states that previously showed "Status unavailable". Reuse the shared labels; funding and reasoned independent staff approval remain unchanged (D63, REQ-113). Built in `1f91b8a`; browser typing alignment in `097382c`.

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

**7 Oct owner correction (D72, REQ-144):** Renewals show each document’s own result and ask only for replacements; retained NIN/bank details and accepted documents are reused. Bank choice uses names, uploads match the app, and copy describes the actual new-trip pause while existing trips may finish.



**Current rule:** Drivers self-register through Apply (`/apply`), or staff create
a driver login on `/admin/drivers/new` using the existing fixed-role form
(D62, REQ-112). Staff-created logins must replace their temporary password;
creating a login does not approve documents or activate driving. Drivers upload documents and are
approved by an admin before working (Q13); approved accounts are activated by
the driver after admin authorisation (D28). Required: licence, vehicle
registration, insurance, NIN, vehicle photos, a verified bank account and a
legally approved driver agreement and consent (Q26). The driver reads the agreement and gives one required in-app acceptance, replacing the signed-file upload (D77, REQ-158). The application records its version and acceptance time; staff see the version/date. The displayed version-1 wording is internally a draft awaiting Terrax's lawyer under REQ-032; screens use normal agreement wording. Apply and renewals share one searchable bank picker, with popular banks first and provider bank codes or a built-in fallback (D78, REQ-159). Apply checks the account name through the adapter and asks the driver to confirm it; an unavailable provider permits a typed name. Staff bank verification and the first-payout-to-a-new-account rule (D40b) remain. In the pilot the vehicle
is registered to its driver, who is the payee; no fleet owners (Q23). Vehicle
approval ends on an admin-entered date (D31). Pilot vehicles: roadworthy cars
(Q19) **and motorcycles** (D43h).

Signed-in active driver accounts can renew rejected or expired identity, bank
and vehicle documents in Profile, with the same scanned uploads and audited
staff review. Work remains blocked until the current reviews pass. Unknown
renewal periods stay unset (D69, REQ-137). Mark expired retains the recorded outcomes, dates and review history. Actually expired driver or vehicle documents require new clean uploads and audited current approval before work resumes; accepted retained documents remain reusable (D76, REQ-152).

**History:**
- **2026-10-12** - Owner chose in-app versioned agreement/privacy acceptance in place of a signed-file upload, plus the shared searchable bank picker and confirmed adapter account-name check with unavailable-provider typed-name fallback (D77/D78, REQ-158/159). The previous signed agreement was a required KYC file and Apply asked for a typed 3-digit bank code and account name. Legal wording remains a draft internally (REQ-032); existing payout authority remains. Built in `a349c2e5`, with final repairs/evidence in `9e7f6147`; non-squash master merge `f77870fd`. Final local verification and independent reviews PASS. Under the one-off REQ-160/D79 exception, full CI/source-bound coverage evaluation is deferred until after Waves 3/4; the accepted integrated run failed, not green.

- **2026-10-12** — Owner-delegated orchestrator requires correction of the wave staff-expiry bug: retain original document facts/history and append the expiry event, refuse reuse of an actually expired file, and restore eligibility only after new upload approval (D76, REQ-152). This implements the existing rule; prior staff expiry incorrectly replaced document facts with empty values. Built in `7f374c39`; integrated verification and accepted master CI [38376171034](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38376171034) pass.

- **2026-10-07** — Owner's Wave 2 C brief opens signed-in renewal for rejected/expired current documents (D69, REQ-137), replacing the later-stage deferral recorded on 1 Oct. Approval and activation remain separate; unknown renewal periods remain unset. Built in `2e29b096` and `74cdb314`; integrated verification and accepted master CI [38376171034](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38376171034) pass. Earlier local evidence: `issues/testing/w2c-renewals-phone-2026-10-07.md`.
- **2026-08-14** — Client confirmed self-registration, requirements, owner-drivers and cars (Q13, Q19, Q23, Q26, D18).
- **2026-10-05** — Owner restored staff-created driver logins beside the existing-profile form on `/admin/drivers/new`; self-registration remains `/apply`, and password, document approval and activation rules remain unchanged (D62, REQ-112). D51 removed the obsolete shared `/admin/users/new` page; it is not restored. Built in `1f91b8a`.
- **2026-09-02** — Owner decisions on activation and vehicle approval dates (D28, D31).
- **2026-09-24** — Client's permit answer covers SUVs, sedans and motorcycles (client answers item 19). Recorded as motorcycles allowed on 2026-10-01 (D43h, REQ-034).
- **2026-10-01** — Owner requested Lane 1's guided applicant flow and own-car chooser (D45, REQ-054). Approval, activation and live-use gates remain unchanged; active-driver renewals are later-stage work. Built in `bf2d92c`; CI repairs in `f172ab3` and `e498147`.

### Installation photos

**Current rule:** Before campaign hours can earn, installation photos must be
approved by an admin (Q17). Views: **front, back, left, right and close-up**.
The driver or an admin uploads them (there is no installer login); Compliance
reviews; new photos are required **weekly**; Terrax's inspector makes spot
checks on top (client answers item 4). Set in configuration
(`INSTALLATION_EVIDENCE_*`).

**Still open:** [REQ-039](requests.md) — spot-check and display-proof values.

**History:**
- **2026-10-06** — The registered temporary development installation/proof values (REQ-094) are integrated. Built in `6879c95`; unanswered client replacement inputs remain REQ-039.
- **2026-10-02** — Owner authorized temporary installation/proof values in development and preview configuration only (REQ-094); unanswered client values remain REQ-039, with the inventory in `demo-data.md`.
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
- **2026-10-14** — REQ-172 corrects browser-to-server transport failures being mistaken for durable-storage failure. Healthy Flush capture retains current session/offline authority and exact v2 batches; End uncertainty retains its frozen manifest and pauses capture until server reconciliation. Existing genuine queue, identity, visibility and writer-lock failures remain closed. Local tracker tests pass; independent money/consolidated review and batch CI remain pending.
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
accepts; "on request" areas may have their own rate (D39a, D43a–c). D80 removes the obsolete hourly engines: there is no live accepted hourly work. Switching daily-rate pay
on for real campaigns: [REQ-048](requests.md).

**History:**
- **2026-10-13, completed 14 October** - Owner approved removal of obsolete development payout v1-v3/evidence v1 and SQLite paths, with no live data; current daily-rate and frozen-evidence protections remain (D80, REQ-161). Built in `18192019`, with daily-rate Jobs completion in `8840fc10`.
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

**Terrax pays Paystack's transfer fee** (D67, [REQ-053](requests.md)). Drivers
receive their full earnings. Cardvert neither computes nor stores nor displays
fees, and has no fee setting or fee-setup submission gate. Paystack's own
dashboard and statements show fees. Accepted work and the short-day calculation
remain unchanged. Requested hardening: [REQ-036](requests.md), [REQ-040](requests.md).

**History:**
- **2026-10-05** — Client reversed the 1 Oct driver-deduction rule: Terrax bears the transfer fee and the driver receives full earnings, with no fee calculation, storage, display or setting in Cardvert (D67; REQ-053; owner W1-P brief; renumbered at merge from D59 on 6 Oct 2026). Locally verified on `w1/payouts`; evidence: `issues/testing/w1p-payouts-2026-10-05.md`. Built in `54662367`, with CI corrections in `f4261af4`; combined exact R branch CI and accepted master CI [38376171034](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38376171034) pass. The owner's one-time Wave 1 D41 exception remains historical in REQ-053.
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
- **2026-10-07** — Owner Claude polish review clarifies the earnings presentation: Ready to pay, Waiting for review and Paid consistently, no repeated page-count summary and one short explanation (REQ-142); amount and payment authority are unchanged. Superseded by the later D65/D66 driver design: Paid with its date, Paying tonight, Being checked and On hold – contact support; the pay explanation lives only in Help. Built in `78ad5580`; the superseding master design is retained by `21239a6d`.
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

**7 Oct demo correction (D73, REQ-145):** Nigerian-format synthetic driver phones; the owner’s +2347068369842 is the temporary local/preview Terrax destination. The PM’s real preview WhatsApp number is [REQ-143](requests.md). Live operator/wording gates remain.



**Current rule:** In-app notifications always; advertiser transactional email
on by default, which an advertiser company can switch off (D24); drivers are
contacted on WhatsApp by operations staff; automated SMS/WhatsApp after the
pilot (Q34). Support phone/WhatsApp 07074200080, run by Customer Service; the
developer drafts short messages for Terrax to approve (client answers item 15).
The notification panel is an unread inbox: Mark read removes that item and
Mark all read clears current unread items, including older pages. Read records
remain stored; notifications arriving afterward appear normally (D54, REQ-075).
Campaign notices name the campaign and offer Open only when the recipient can
currently access its campaign or driver assignment; inaccessible context stays
generic without a name or link (D71, REQ-139).

For phone verification, only the signed-in driver sees a one-time code and
sends it by WhatsApp or SMS to the configured Terrax number. Customer Service
records the received code and sender number; Cardvert verifies the current
phone once, limits attempts and logs the staff action. No configured number
means no driver button. Live use waits for approved wording (REQ-032) and a
named operator (D70, REQ-138).

**History:**
- **2026-10-07** — Owner Claude polish review requires sentence-case notification titles/body in the body font, retaining capitals for small labels (REQ-139); notification content and access checks are unchanged. Built in `78ad5580` and real integration `21239a6d`.
- **2026-10-07** — Owner W2-D brief replaces generic campaign notices with currently authorized campaign names and Open links (D71, REQ-139); immutable notification payloads and delivery channels remain. Built in `78ad5580` and real integration `21239a6d`.
- **2026-10-06** — The earlier Mark read investigation, accessible panel close/focus and simpler company-preference wording are integrated (REQ-073/074/076). Built in `c2ab2d9`; full CI, including the real preference-change browser case, passed. REQ-075 retains its separate unread-inbox walkthrough obligation.
- **2026-08-14** — Client confirmed channels (Q34, D18); **2026-08-24** owner decision on email preferences (D24).
- **2026-09-24** — Client supplied the support number (client answers items 14–15).
- **2026-10-07** — D70 replaces the earlier operator-send/driver-enter verification with driver-send/staff-record. The code is visible only to its driver; live wording and operator gates remain open. Built in `2e29b096` and `74cdb314`; integrated verification and accepted master CI [38376171034](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38376171034) pass. Earlier local evidence: `issues/testing/w2c-renewals-phone-2026-10-07.md`.
- **2026-10-02** — Owner clarified that read notifications must disappear from the panel (D54, REQ-075), replacing its earlier history-list presentation. Built in `c2ab2d9`; the separate unread-inbox browser walkthrough remains open under REQ-075.

### Advertiser reporting and privacy

**Current rule:** The standard report is a **Campaign Performance Analysis**:
verified operations, clearly labelled estimated exposure and target-area
coverage. Financial ROI appears only when an advertiser supplies conversion or
revenue data and an approved method exists (Q12, Q30, D20c). Advertisers do not
see driver names or profiles.
New CSV/PDF issuances say "Not enough data" for unavailable totals. Existing
issued reports, stored snapshots, bytes and integrity hashes retain their original
wording; the export snapshot version changes for new issuances (D71, REQ-141).

**Still open:** [REQ-018](requests.md) — confirm no driver identity in reports.

**History:**
- **2026-10-07** — Owner W2-D brief replaces "Omitted - insufficient frozen evidence" in new export snapshots only; old issuance content and verification remain unchanged (D71, REQ-141). Built in `78ad5580` and real integration `21239a6d`.
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

**7 Oct demo correction (D73, REQ-125):** Seeded campaigns, routes, zones and GPS use real Abuja areas and consistent geometry.



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
[REQ-043](requests.md) domain connection; [REQ-033](requests.md) which address (for example app.terraxmedia.com); [REQ-032](requests.md) residency and legal prerequisites.

**History:**
- **2026-08-14** — Client confirmed ownership (Q32, D18).
- **2026-09-24** — Client approved ClamAV, Postmark, Mapbox ("short run", Google Maps later) and terraxmedia.com, and left hosting, storage and region to the developer's recommendation (client answers items 9–16). The recommendation was Render with AWS storage and encryption.
- **2026-09-29** — Deployment templates for Render, AWS and Mapbox written, with every secret blank and nothing applied (REQ-010). Built in `0b53eab`.
- **2026-09-30** — Owner chose Hetzner instead of Render and AWS, and MapTiler instead of Mapbox (D44). The Render, AWS and Mapbox templates are superseded (REQ-049).
- **2026-10-05** — Owner authorized W1B replacement templates using the existing Compose/Caddy release, Hetzner Object Storage and MapTiler, plus private ClamAV and configurable API workers (REQ-049/117). Templates only; secrets and regions remain unset, with residency under REQ-032. Built in `308f04a8` and `81de2f54`, with MapTiler preflight correction in `7f374c39`; consolidated integration review and accepted master CI [38376171034](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38376171034) pass. Templates only; no provider action or deployment is claimed.

### Legal, privacy and retention

**Current rule:** Built GPS, ID collection, results and reports are accessible during development without legal approval switches; tenant isolation, aggregation limits and query recording remain, and legal/privacy plus overlap/differencing protections must be restored before real users (D56, REQ-072/089). For driver-application and vehicle-document review, the View click is the staff acknowledgment; each read keeps its application or vehicle purpose-scoped audit and one-minute/leave-page hiding, and NIN has its separate reveal (D58, REQ-105). Complete canonical UUID whole tokens are never phone numbers in any audit field or free text; phones beside them, broken/partial UUIDs and sensitive fields retain redaction (D61, REQ-111, superseding D60).

**Still open:** [REQ-031](requests.md) lawyer's name, [REQ-032](requests.md) legal pack.

**History:**
- **2026-10-05 (superseding decision)** — Owner replaced D60's field-specific exception with one whole-token UUID phone-classification rule after a payout audit approver ID was scrubbed. Real phones and sensitive fields remain redacted; privacy/security and money review are required (D61, REQ-111). Built in `1f91b8a`.
- **2026-10-05** — Owner approved exact whole-field stored-file review UUID preservation after phone redaction was shown to corrupt valid review evidence. No broader UUID exemption or phone disclosure is permitted (D60, REQ-109). Built in `69655e2`; replaced by `1f91b8a` under D61.
- **2026-10-04 (vehicle extension)** — Owner extended D58/REQ-105 to driver-page vehicle documents. The earlier separate vehicle purpose/need confirmation ended; each View keeps the existing vehicle-review purpose/reason and individual audit, minute/leave hiding and record isolation. Commit is approved after verification and review. Built in `6eb5ab9`.
- **2026-10-04** — Owner made each driver-application View click the review acknowledgment instead of a separate need checkbox (D58, REQ-105), preserving individual audit and hiding. The prior checkbox control ended for this staff surface; other privacy and launch controls remain. Built in `6eb5ab9`.
- **2026-10-02** — Owner replaced the prior rule gating GPS, documents, reports and retargeting until legal approval with D56 development access and seed-only client-input substitutes; actual legal/retention answers remain open. Built in `5fdf6ec`; complete preview seed states in `6879c95` (REQ-072/089).
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
- **2026-10-01** — Owner requested integration of Lane 1's availability and password-work controls, preserving automatic-payout account protection (D45, REQ-054). Built in `bf2d92c`; CI repairs in `f172ab3` and `e498147`.

### CI dependency security

**Current rule:** CI fails on every high or critical dependency advisory except exactly GHSA-vfj7-8cjw-p6xm in the exclusively dev-only eslint-config-next lint chain, through 2026-11-04 UTC (D59, REQ-107). Reason: no patched braces release is available and exposure is confined to the development lint chain. The exception stops applying on 2026-11-05 UTC; malformed reports, audit errors and broader exposure fail closed. It does not change application behavior or authorize deployment.

GitHub CI pins every Python setup location, including composite actions, to
exactly 3.12.14 (owner instruction 2026-10-08, REQ-134). Exact shard and
aggregate runtime provenance and all coverage gates remain unchanged.

**History:**
- **2026-10-08** — Owner required the exact 3.12.14 pin after the combined run
  produced Python 3.12.14 and 3.12.15 shard manifests. Previously selectors used
  floating 3.12; the existing mismatch refusal correctly blocked aggregation.
  REQ-134 records this delivery-only correction; no production runtime change. Built in `526acddd`; exact runtime provenance and full CI pass.
- **Before 2026-10-05** — The frontend audit rejected every high or critical advisory without exceptions.
- **2026-10-05** — Owner approved this one expiring advisory exception while finishing REQ-106, preserving all other high/critical checks and prohibiting npm's forced lint-package downgrade (D59, REQ-107). Built in `69655e2`.

### Money and privacy verification

**Current rule:** D81 adds separate 85% branch-coverage floors for the money
and privacy modules. Existing changed-code and backend/frontend/global gates
remain. D33 refreshes require independent review; this batch uses an approved
measurement run, receipt commit and final green verification run before merge
(REQ-163/170). The shared bank picker remains one implementation under D78.

**History:**
- **2026-10-13, completed 14 October** - Owner approved Waves 3/4 and the two-run D33/D41 sequence. The earlier policy had no separate 85% money/privacy floor. Built in `115fc505`, with independently reviewed receipt `40e39f4c` and full green verification [38539599622](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38539599622). Whole-range qualification includes REQ-158/159; shared bank picker retained. Non-squash merge `4bbb689d`. Structural refinement Built in `30eadf27`; progress archive/process trim and hosting-scope verification Built in `0b0be762`.

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
- **2026-10-06** — Reviewed complete preview seed states, fictional-company ownership, chronology, active-driver-only earnings, synthetic contacts, exports and report histories are integrated (REQ-072/090–103). Built in `6879c95`; preserved thresholds, immutable reruns and seed-only values are verified. Historical preview reseeding does not authorize or claim a new application deployment.
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
One advertiser login per company remains the current scope (D47). Review driver-application and vehicle documents directly with View: the click acknowledges each individually logged application or vehicle review read, without a separate need checkbox (D58, REQ-105). Keep the one-minute/leave-page hiding, current-record resets and separate Show NIN reveal. Existing server decisions still govern activation, funding, pay and report issuance.

Staff Resume is permitted only for a recorded operational pause, classified on the server. Budget-related and unknown pauses are refused with a plain explanation; current start requirements are rechecked and the actor, reason and pause identity are logged (D55, REQ-081). Staff list totals, oldest-first paging and row names are approved to bound badges, work lists and Trip checks (D55, REQ-077/078/083/085).

Staff driver-login creation belongs on `/admin/drivers/new`, alongside attaching
a profile to an existing login; company logins use `/admin/advertisers/new` and
staff logins use Settings. D51 removed the shared `/admin/users/new` page.
D62 restores the driver-specific form without a legacy alias or a change to
password, profile, document approval or activation authority (REQ-112).

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
- **2026-10-06** — The development replacement rule (REQ-056) Built in `c2ab2d9`. Work queue naming Built in `39eb49c` and `009947c` (REQ-065); physical-check paging and suspicious-trip route/held-pay reads Built in `009947c` (REQ-066/069). The bounded-read, Trip checks, checklist, Pay terms, Resume, copy, grouped-pay, title and Applicants follow-up Built in `046e0dd` (REQ-077–085). Full CI and D33/D41 coverage verification passed; broader design gaps remain open.

- **2026-10-05 (superseding decision)** — Owner replaced D60's field-specific exception with one whole-token UUID phone-classification rule after a payout audit approver ID was scrubbed. Real phones and sensitive fields remain redacted; privacy/security and money review are required (D61, REQ-111). Built in `1f91b8a`.
- **2026-10-05** — Owner approved exact whole-field stored-file review UUID preservation after phone redaction was shown to corrupt valid review evidence. No broader UUID exemption or phone disclosure is permitted (D60, REQ-109). Built in `69655e2`; replaced by `1f91b8a` under D61.
- **2026-10-04 (vehicle extension)** — Owner extended D58/REQ-105 to car documents on the driver page and authorized the verified integrated commit. Vehicle View replaces its separate purpose/need confirmation, with existing `kyc_review` + `vehicle_approval:<submission_id>` read auditing and minute/leave hiding. Vehicle approval decisions remain unchanged. Built in `6eb5ab9`.
- **2026-10-05** — Owner restored the existing fixed-role driver login form on `/admin/drivers/new` after D51's removal of `/admin/users/new` left no staff browser entry point. Company/staff provisioning stays in its own canonical area, and driver self-registration remains Apply (D62, REQ-112). Built in `1f91b8a`.
- **2026-10-04** — Owner replaced the separately confirmed document need checkbox with direct audited View for driver-application review (D58, REQ-105). The earlier 3 October polish retained that checkbox under the existing audited-control rule. Timed hiding, record isolation, purpose and the separate NIN action remain. Local implementation verified by `issues/testing/client-polish-2026-10-04.md`; the original person/bank review passed independent reviews. The owner then extended direct View to vehicle documents and approved the integrated commit, Extension verification, consolidated minimal-change review and implemented privacy/security review PASS. Built in `6eb5ab9`.

- **2026-10-02** — Owner confirmed guarded staff Resume and bounded read options (D55); local implementation and verification completed. Built in `046e0dd`; full CI and coverage verification passed on 2026-10-06.
- **2026-10-02** — Owner approved the two staff reads for suspicious-trip
  recorded routes and actual held pay (D53, REQ-069). Built in `009947c`.
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

W1B identifiers renumbered at merge on 2026-10-06: Compose REQ-108 → REQ-117, wording REQ-112 → REQ-116, D62 → D68, architecture v1.117 → v1.125. Master identifiers retain their meanings.

Combined Wave 1 merge: payout architecture entry renumbered at merge from lane v1.125 to v1.126 because W1-B retains v1.125. Both original lane approvals remain historical; D67/D68 and request identifiers are unchanged.

### 7 October renewal correction history

Before D72, renewal required the complete identity/bank or vehicle capture and displayed filenames (D69). The owner replaced that presentation and complete-input requirement with partial renewal in REQ-144. D73 replaces UK demonstration phone fixtures and Lagos seed geography with Nigerian-format fixtures and Abuja geography. Built in `74cdb314`; [historical correction verification](../issues/testing/w2c-claude-renewals-correction-2026-10-07.md), final integrated review and accepted master CI [38376171034](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38376171034) pass. Screenshots are historical; live operator, wording and preview-destination gates remain separate.

- **2026-10-13** — Reviewed Wave 1 and 2 integration Built in `21239a6d`, with renewal/expiry and MapTiler corrections in `7f374c39`; canonical receipt in `3a9f8b64` and one-time parent correction in `e1716154`, deterministic privacy-test fixture in `1217e4a1`, and payout recovery lock repair in `31997a67`. Exact R branch CI 38334710143, final repair branch CI [38369572447](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38369572447) and accepted master CI [38376171034](https://github.com/oluwasolaonigbinde/mobility/actions/runs/38376171034) pass. Delivery requests close in the register; external launch prerequisites remain open.

## Scheduled operational monitoring

**Current rule (D82 / REQ-164):** Scheduled jobs publish Cron status, and a
five-minute health sweep notifies Finance through the existing active-admin
alert surface. Money/evidence authority is unchanged. Alerts are deduplicated
per check and UTC date; Finance resolves them manually. GPS monitoring keeps
only one-hour aggregate minute counters. The runbook defines the thresholds.

**History:**
- **2026-10-14:** Implements the owner's approved Waves 3/4 operational scope.
  Built in `0b0be762`, with durable privacy-safe counter-failure handling in
  `44ded5ea`. Specialist reviews and full verification `38539599622` pass.
  Earlier jobs exposed logs/errors and partition alarms without a consolidated
  health sweep.
