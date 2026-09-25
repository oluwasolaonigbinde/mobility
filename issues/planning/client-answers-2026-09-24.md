# Client answers ("Cardvert DOC Answer 2", received 24 Sep 2026)

Source: Terrax Media's answers to the 20-item client-requirements document,
relayed by the project owner. This register maps each answer to the open inputs
in `docs/product-requirements.md` §13 and says whether it can be used as given.
It records inputs; it does not by itself change any decision, formula or gate.

**Security note:** the document contained a Paystack username and password in
plain text. They are deliberately **not** recorded here or anywhere in the
repository, and must not be used. Terrax should change that password and invite
the developer as a team member instead (item 7).

Status: **Usable** — can be configured or built as given. **Clarify** — answer
is ambiguous or incomplete. **Conflict** — contradicts a recorded decision or
control; needs an explicit owner/client decision before any change.
**Pending** — the client says it will follow.

| # | Topic (PRD gate) | Client answer (summary) | Status | Note |
| --- | --- | --- | --- | --- |
| 1 | Stopped/parked time (D22) | Agreed. Short stop stays payable for 5 min; at most 5 min of stopped time paid per trip or day; special cases "on request"; approver: Operations Department | **Conflict / Clarify** | D22 uses 120-second detection windows and a 240-second whole-trip grace. Adopting 5 min is a new effective policy revision for later acceptances only (never repricing accepted work, D14/D21). "Per trip or per day" must be one rule; "on request" needs a defined exception process. |
| 2 | Prices and driver pay (G-18, D2/D12/D18) | ₦140 per **mile** in the primary zone, ₦50 per mile outside, 70 miles/day ⇒ ₦9,800/day; a ₦10,000 daily rate for "special request" locations; 10% service charge; printing + installation ₦100,000 (Kromatiks: print 65,000 + install 35,000); AMAC permit ₦100,000; APCON ₦50,000 (optional); Meta/Google ads ₦300,000/month (optional); graphic design ₦70,000 (optional); professional services ₦700,000; sample total ₦1,000,000 | **Conflict** | Every recorded decision (D2, D12, D18, D21) and the built payout engine pay a fixed naira amount **per hour** of verified time (base/premium). Per-mile pay and a flat daily rate are a new pay model requiring a new formula version (`payout_v4`), and the answer itself says "hourly pay … per mile". The ₦1,000,000 split lists two different figures per line (450,000/380,000 and 550,000/620,000). Commercial figures are usable once the split is confirmed. |
| 3 | Budget alerts (G-20, G-21) | 80% / 95% warnings, pause at 100%, resume after approved increase or payment; recipients "everybody"; fixed costs count toward the budget; only Admin may raise a budget or restart | **Usable / Clarify** | Values fit the built policy port (`BUDGET_*` settings). "Everybody" needs a definition (all advertiser members and all Terrax admins?). |
| 4 | Installation photos (G-21a) | Uploaded by the installer (printing company) and the driver; approved by the Compliance Department; required views: front, back, both sides, close-up; new photos weekly or twice weekly; spot checks by the company inspector (the marketer) | **Usable / Clarify** | There is no installer or inspector login today; uploads are by driver (and admin). Choose weekly or twice weekly. Compliance/inspector are departments, not system roles (see D38(e)). |
| 5 | Advertiser report (G-15) | Approves a Campaign Performance Report; no financial return; answer to "report name/wording" reads "Admin officer & driver profile and the car" | **Usable / Conflict** | Omitting ROI matches D20. Showing driver identity/profile to advertisers conflicts with the privacy boundary (§22, PRD §8.3); needs clarification of what they meant. |
| 6 | Invoice details (G-17, G-19) | Terrax Media Company Ltd; number 2521515778093; 73 Lome Crescent, Wuse Zone 7, FCT Abuja; 07074200080; terraxmediacompany@gmail.com; VAT 7.5% inclusive; invoice fields listed (serial number, RC number, client and CEO signature, campaign duration, quantity, bank details…); payment via Opay account and Paystack | **Usable / Clarify** | Confirm whether 2521515778093 is the RC or the TIN (both are needed), the invoice-number format, and the Opay account details for advertiser instructions (not supplied). An accountant confirmation is still required for live invoices. |
| 7 | Advertiser payments (G-01) | Paystack Business account in Terrax Media's name; card and bank transfer enabled; settle to Opay; refunds by the finance officer (admin) | **Usable** once the developer is invited | Credentials must come through a team invitation and test/live keys, not a password. Unblocks `EXT-PAYMENT-PROVIDER` (the paused PKG-03 / W2-01C) once keys exist. |
| 8 | Driver payouts (G-02, RM10) | Paystack Transfers, funded from Opay; approvals: "Automatic (no human interference) — the system should approve it"; customer service handles issues | **Conflict** | The built and documented control is maker-checker: one person prepares, a different person approves, a third can re-check (RM10, PRD §7.5, guide p.2). Removing human approval is a money-control decision; if accepted it needs limits (per-driver and per-batch caps, automatic holds) and a new decision row. |
| 9 | Test website (G-26) | Render, as recommended; developer creates the staging address; billing contact: Opay account officer / finance office | **Usable** | Needs a Terrax-owned Render account with the developer invited. |
| 10 | Public domain and hosting (G-26) | Domain **terraxmedia.com**; developer chooses region; CEO owns billing | **Usable / Clarify** | Earlier planning assumed a Cardvert domain; confirm the product lives on terraxmedia.com (e.g. app.terraxmedia.com). |
| 11 | File storage (G-09) | Developer's recommendation; region developer's choice; keep old files 6 months | **Usable / Clarify** | 6-month retention must be reconciled with legal retention for KYC/money records (item 17, D34). |
| 12 | File checking (G-10, G-22) | ClamAV as recommended; file types and sizes as recommended | **Usable** | |
| 13 | Encryption (G-08) | Hosting provider's key service; business owner: CEO Mr Somtochukwu | **Usable** | |
| 14 | Email (G-05, G-23) | Postmark; support@terraxmedia.com; domain access approved | **Usable** | Needs the Postmark account invite and DNS access. |
| 15 | WhatsApp / phone (G-06, G-23) | 07074200080; customer service (no named person); manual codes first; developer drafts the short messages | **Usable / Clarify** | Message wording drafted by us still needs Terrax approval (`EXT-MESSAGE-COPY`). Also the support contact G-39. |
| 16 | Maps (G-11) | Mapbox now, Google Maps later; allowed domain terraxmedia.com | **Usable** | Needs a Mapbox account with billing and the developer invited. |
| 17 | Legal and privacy (G-12, G-14) | In process; documents to follow; PM to provide a lawyer | **Pending** | Still blocks real GPS, onboarding documents, reports and retargeting in live use. |
| 18 | Meta/Google (G-16) | Off for the pilot; company Meta Business later; developer to create a Google Ads account; budget ₦1,000,000 approved by the finance-budget officer; live activity approved by the "Control Online" department; legal approval by lawyer | **Usable (off)** | The developer should not own the client's Google Ads account; create it in Terrax's name and invite the developer. |
| 19 | Permits and installers (G-29) | AMAC permit / APCON approval, reference pending; covers SUVs, sedans and motorcycles; 1-year validity; installer Kromatiks Ltd (contact supplied) | **Pending / Clarify** | Launch stays blocked until reference numbers exist (D19). Motorcycles are a new vehicle type for the pilot. |
| 20 | Brand files (G-28) | Delivered to the developer separately | **Usable** | Final approver not named. |

## Follow-up answers (25 Sep 2026) — recorded as D39

| Item | Answer | Now |
| --- | --- | --- |
| 1 Stopped time | Each stop up to 5 minutes (traffic, checkpoints, fuel) counts; a longer continuous stop does not count as covered movement | **Decided** (per stop) |
| 2 Driver pay | Paid a daily rate of ₦10,000 for covering the expected 70 miles; less distance → reduced ("subcharged") pay; per-mile figures only explain the derivation; "on request" areas may have a different rate | **Decided in principle**; shortfall formula and counting rules still open |
| 8 Payout approval | Automatic, no human approval; the system decides full or reduced pay; Finance Officer monitors, reconciles and follows up failed/duplicate payments | **Decided**; safeguards are a design responsibility |
| New | Complaints from pilot users are raised in the app and handled by Customer Service | **Decided**; needs an in-app complaint/support inbox |

## Departments named by the client (input to D38(e))

Operations (stopped-time rule, day-to-day), Compliance (installation photos),
Finance officer (refunds, payment problems), Customer Service (driver contact,
payout issues and complaints), Admin (budget increases and restarts), company
inspector/marketer (spot checks), Control Online (live ad activity),
finance-budget officer (ad budget), CEO (account ownership and billing). Cardvert
has a single admin role today; these are used as work-queue sections, not new
permissions, unless the owner decides otherwise.
