# Cardvert live QA — first pass

**Observed:** 23 September 2026. **Tested version:** committed `21a5981d631c1ae1667993381a1d4fda350e29cf` in the isolated `mobility-livecheck-20260923` clone, with a synthetic local Docker stack and Chrome on Windows. The main checkout has separate uncommitted CV work; none of these findings claims that work is still affected. This is an exploratory product and workflow pass, not a production, real-device, payment-provider, or legal approval sign-off.

The visible states below were reproduced through the running UI. Source and product documents were checked to distinguish a defect from an intentional gate. For the consequential status and offer actions, the exact unpressed boundary is stated; one status transition was also verified in a transaction that was rolled back. Priorities are suggested for triage, not authorization to change the delivery queue.

## W2-D local recheck — 7 October 2026

Verified in the isolated `mobility-w2d` worktree on `w2/polish`, based on
`ec267529`, with a synthetic local stack and unchanged demo seed source.
These findings are fixed locally; master integration and combined CI remain
owner work. The dated September table below remains historical evidence.

| ID | Local status | Evidence |
| --- | --- | --- |
| QA-08 | Fixed locally (REQ-121 / D68) | Current-access campaign names and canonical Open links for advertiser, driver and admin; malformed, conflicting or unauthorized context remains generic. Focused scope tests plus real navigation at 375px and 1440px; [receipt](issues/testing/w2d-polish-2026-10-07.md). |
| QA-14 | Fixed locally (REQ-122 / D68) | All form edits invalidate preview; late responses cannot restore confirmation. Five-field/delayed-response tests plus real edit/repreview/confirm at both widths; [receipt](issues/testing/w2d-polish-2026-10-07.md). |

## Recheck on the main checkout — 24 September 2026

Rechecked on a separate stack built from the main checkout (`21a5981` + the
uncommitted CV-01–CV-17 work + the UX-01…UX-11 batch recorded in
`docs/progress.md`), migrated to `0090`, demo seed, **default pre-approval
privacy configuration**. Full screen-by-screen review, before/after wording and
the *How Cardvert Works* comparison:
[`issues/product-ui-review/human-journey-audit-2026-09-24.md`](issues/product-ui-review/human-journey-audit-2026-09-24.md).
"Fixed" means changed in the working tree and verified by unit tests plus a live check on the main stack (for QA-15 the server rule is covered by backend tests with red checks; its UI label was not seen live). Nothing is committed.

| ID | Status on 24 Sep | Note |
| --- | --- | --- |
| QA-01 | Open | Product rule (what makes a campaign complete) still undecided. |
| QA-02 | Fixed (UX-04) | No run → "No report is available yet"; privacy gate → "Campaign results aren't switched on yet". |
| QA-03 | Fixed for create/company (UX-07) | Campaign-detail and edit write controls are still visible to viewers (the server still refuses them). |
| QA-04 | Fixed (UX-09) | Live at 1366×695: sign-out at y=661 and reachable by pointer; sidebar grouped and scrollable. |
| QA-05 | Open | Pasted assignment/trip IDs unchanged. |
| QA-06 | Open | Needs approved payment instructions (G-19). |
| QA-07 | Open | Legacy seed data. |
| QA-08 | Open | Needs a notification link/payload contract. |
| QA-09 | Fixed (UX-06) | |
| QA-10 | Open | Demo seed cannot show quote → report → payout end to end. |
| QA-11 | Fixed (UX-06) | Attach disabled with nothing to attach. |
| QA-12 | Open | NX-05 privacy packet. |
| QA-13 | Fixed (UX-08) | Track: "F7 Lagos Commuter Reach can't start yet". |
| QA-14 | Open | Re-read in code: the preview is not cleared when the form is edited. |
| QA-15 | Fixed (UX-10) | Server refuses activation and role change for an applicant until account setup; security review adopted (role flip → password recovery route closed). |
| QA-16 | Fixed (UX-11) | Accept withheld with a reason; Decline kept. |
| QA-17 | Fixed (UX-01) | Live: 20 of 35 shown, "Show older" reaches all. |
| QA-18 | Fixed (UX-01) | Live: Mark read / Mark all read return 200; badge clears. |

New on 24 Sep (main checkout, default pre-approval configuration):

- **QA-19 · Retargeting pages crashed before privacy approval** — high. `/advertiser/planning-sources` and `/admin/planning-sources` showed "Something broke" because the list reads return 503 `PRIVACY_LIVE_USE_BLOCKED`. Fixed (UX-02/UX-03).
- **QA-20 · Campaign page offered refused or contradictory actions** — medium. Completed campaigns showed the change form, "Add missing creatives" and "Next action: Request the custom quotation"; a legacy artwork chip read "READY" beside "Artwork: Not ready". Fixed (UX-05). A completed campaign still offers "Request custom quotation" in the commercial panel (open).
- **QA-21 · Retargeting date inputs use the server time zone** — low. `planning-sources/actions.ts` converts `datetime-local` with `new Date()` on the server (UTC in the container), unlike CV-17's Lagos conversion. Open.
- **QA-22 · Guide claims without software backing** — medium. *How Cardvert Works* p.6 lists "required permits or other launch evidence" as an activation check; no such check exists (D19 makes it a Terrax Media responsibility). p.32 driver contact needs phone verification that has no screen (NX-11). Open; guide corrections in the audit.
- **QA-23 · Landing page promises mileage pay** — low. "drivers earn from the miles they already drive" contradicts hourly pay (D2/D12/D18). Open.

## Verified issues

### QA-01 · A name-only campaign can pass review — medium; product rule to settle

- **Journey:** Advertiser creates a campaign with a name only, leaving description, window, budget, zones and artwork empty; submits it; admin approves it in `/admin/approvals`.
- **Observed:** Campaign `a098c011-df85-4b5f-9858-8d2883e78359` is `approved`, yet its detail page still says “No window set,” shows no total or daily budget, zero zones and zero creatives. The admin review card disclosed the missing description/window/budget and still offered Approve.
- **Expectation:** [A-12](docs/product-requirements.md) calls for a *completed draft* before review, but [architecture §18](docs/architecture.md) specifies lifecycle integrity without a minimum-content rule. The client/product owner should define which campaign facts make a draft complete for this approval, or distinguish a preliminary concept approval from completed-campaign approval. Do not assume that artwork or an agreed price must be present at this stage; they have later gates.
- **Scope:** This does **not** show that the campaign can launch. [A-14](docs/product-requirements.md) says activation has separate gates, and the detail page correctly says approval does not authorize scheduling or activation.

### QA-02 · Missing measurement is presented as report corruption — high

- **Journey:** Open the Campaign Performance Analysis and coverage map for the approved name-only campaign. The same report state was observed for seeded active “Demo Lagos Mobility Campaign,” active “F7 Lagos Commuter Reach,” and completed “Airtel Lagos Commute” before a measurement run existed.
- **Observed:** Both pages say “This report failed its integrity check” and “Cardvert needs to reissue the analysis.” The report API returned no `measurement_run` or `measurement_result`; this is absence, not evidence of mismatched issued data. A synthetic admin attempt to prepare a run for the seeded active campaign was correctly rejected because activation proof did not bind creative and installation evidence.
- **Expectation:** Show the already-defined “No report is available yet” / measurement-required state until a run exists; reserve integrity failure for a present run/result that fails verification. See [`report/page.tsx`](frontend/src/app/advertiser/campaigns/[campaignId]/report/page.tsx), [`map/page.tsx`](frontend/src/app/advertiser/campaigns/[campaignId]/map/page.tsx), and [`measurement-authority.tsx`](frontend/src/app/advertiser/campaigns/[campaignId]/report/measurement-authority.tsx).
- **Impact:** The current message tells advertisers there is a data integrity incident and a reissue action when no report has been issued.

### QA-03 · Viewer is invited into write flows that the server denies — medium

- **Journey:** Sign in as the seeded advertiser **viewer**. `/advertiser/campaigns` shows “+ New campaign”; complete the name-only wizard and press “Create campaign.” `/advertiser/company` also shows editable fields and “Save company profile.”
- **Observed:** Campaign `POST` returned **403** and created no campaign, but the wizard reported “The campaign result is not yet confirmed. Retry to safely check the same request.” Company save correctly returned “Owner or manager access is required,” after allowing the viewer to edit and submit the form.
- **Expectation:** Hide or disable owner/manager mutation controls for viewers and explain role limits before they spend time filling forms. Map a definite 403 to a permission message, not an uncertain-result retry. Backend authorization **worked**; this is a UI and error-mapping defect.
- **Evidence:** [`campaigns/page.tsx`](frontend/src/app/advertiser/campaigns/page.tsx), [`new/actions.ts`](frontend/src/app/advertiser/campaigns/new/actions.ts), and the live 403 response.

### QA-04 · Desktop admin rail clips lower navigation and sign-out — medium

- **Journey:** Use `/admin/measurement` or another long admin page at the normal 695px high Chrome viewport.
- **Observed:** The 695px sidebar has 823px of content with `overflow-y: visible`; its Sign out button sits about 789–805px below the viewport. Pointer clicks on the off-screen button did not sign out. On a long page, scrolling the document kept the sticky rail at the top and did not reveal the button. Keyboard focus plus Enter did activate it. On a short page, document scrolling sometimes exposed it, so this is a viewport/page-dependent reachability defect rather than an unconditional inability to sign out.
- **Expectation:** The rail should scroll internally or otherwise keep its lower controls reachable by pointer at ordinary laptop heights. See [`app-shell.tsx`](frontend/src/components/shell/app-shell.tsx).

### QA-05 · Operator trip commands require IDs the adjacent lists do not provide — medium

- **Journey:** Open `/admin/payouts` and `/admin/fraud`.
- **Observed:** “Process a trip” requires a pasted full trip UUID, while 330 payout rows display only eight characters plus an ellipsis, with no row link or title containing the full ID. “Queue physical spot check” requires full assignment and trip IDs, while fraud flags show only shortened trip IDs and no trip/assignment navigation. The named `/admin/assignments` list links to assignment readiness, but its active-assignment detail showed no trips or full trip IDs.
- **Expectation:** Give staff a contextual action, full copyable reference, or a searchable trip/assignment picker. This is a workflow discoverability issue; it does not establish an API authorization problem. See [`payouts/page.tsx`](frontend/src/app/admin/payouts/page.tsx) and [`fraud/page.tsx`](frontend/src/app/admin/fraud/page.tsx).

### QA-06 · Bank-transfer instruction has no usable destination — medium; client input required

- **Journey:** Open `/advertiser/billing` with no recorded payments and follow “Billing details.”
- **Observed:** Billing says “Online payment isn't available yet. Please pay by bank transfer.” “Billing details” leads to the advertiser's own company-contact form, with no settlement account or approved instructions.
- **Expectation:** Give a clear approved payment route when the client supplies and verifies it, or say how the advertiser should request instructions. [A-30 and G-19](docs/product-requirements.md) explicitly make bank-account details and approved advertiser instructions a Terrax Media input. Do not invent them or enable live settlement from the local example.

### QA-07 · Legacy trip detail does not fulfil the earnings-page promise — low

- **Journey:** On `/driver/earnings`, open the seeded “Demo Lagos Mobility Campaign” ₦7,158.90 entry. Repeat with Amina Bello's ₦2,496.19 “F7 Lagos Commuter Reach” entry.
- **Observed:** The list page promises “verified time, rate, cap progress, exclusions, and ledger trail” for a trip. Both detail pages show only amount, “Computed under the previous per-km formula,” and one ledger entry. Even the rich F7 seed therefore cannot demonstrate the current hourly breakdown.
- **Expectation:** Qualify the promise for legacy `payout_v1` history, or show the explainable historical inputs that are actually available. Do not reconstruct missing history or imply hourly terms applied to it.

### QA-08 · Notifications give no actionable event context — low

- **Journey:** Read the advertiser notification after the test campaign was approved, and the driver notification center after seeded earnings release.
- **Observed:** The approval says only “Your campaign has been approved.” Four driver entries repeat “Verified earnings are available for the next payout batch.” None names the campaign/trip, amount or a destination link in the notification center. The separate email for campaign approval also used generic copy.
- **Expectation:** Identify the relevant record and offer an authorized destination where possible, so a user can tell which campaign or earning changed. The approval and earnings events **were delivered**; this is a context/navigation issue, not a missing-notification claim.

### QA-09 · Campaign wizard describes steps it does not contain — low

- **Journey:** Open `/advertiser/campaigns/new`, then open “Add missing creatives” from an existing campaign.
- **Observed:** The new-campaign heading says “targeting zones come next,” but the next wizard steps are Creatives and Review; zones are managed after creation from the campaign detail. In existing-campaign artwork recovery, the page still says “you can create the campaign without creatives and add them later,” although the campaign already exists.
- **Expectation:** Tell users where zones are actually set and use recovery-specific artwork copy. The zone and artwork recovery routes exist; this is misleading guidance, not a claim that the features are absent.

### QA-10 · Active demo fixtures bypass the commercial and report story — low; fixture scope

- **Journey:** In the seeded “Demo Lagos Mobility Campaign,” open the advertiser report, then as admin prepare a synthetic measurement run for September 2026. Also inspect the active “F7 Lagos Commuter Reach” advertiser detail, admin billing and settlement pages, and report.
- **Observed:** The Demo Lagos campaign is active with driver earnings, but its report has no frozen measurement run. The preparation command rejected the run with “Activation proof must bind creative and installation evidence”; its detail marks artwork not ready and installation policy missing. F7 Lagos is also live with five assigned vehicles and ₦694,141 in calculated driver pay, yet its preparation card says quotation “Not requested,” artwork “Not ready,” and funding “Not yet recorded.” Admin billing confirms no quotation request or accepted terms; its report has no issued analysis. The settlement page shows driver earnings while correctly saying no verified transfers occurred.
- **Expectation:** Keep explicitly historical/legacy fixtures for migration tests if needed, but provide a coherent synthetic campaign with quotation, accepted terms, funding, approved creative/installation proof and a frozen measurement run for a real-stack commercial-to-report walkthrough. The run rejection and transfer distinction are **correct safety gates**; the issue is the coverage value and apparent chronology of seeded demo data.

### QA-11 · Empty artwork recovery reports an attachment action that did nothing — low

- **Journey:** From an existing campaign with no artwork, open “Add missing creatives,” leave the optional list empty, continue to Review, and press “Attach creatives.”
- **Observed:** The review screen explicitly says “Creatives: none” yet enables “Attach creatives.” Pressing it returns to the campaign with “Creatives · 0” and no explanation that nothing was attached.
- **Expectation:** In recovery mode, require at least one creative before enabling the attachment action, or label the action as a deliberate skip and report that no changes were made. The path itself exists and a creative row without a cleared file is correctly blocked.

### QA-12 · Active driver has no in-app path to restore missing evidence — medium; known open requirement

- **Journey:** Sign in as seeded `driver.wuse@demo.mobility.local`. The journey says person/payee evidence was not submitted, vehicle evidence is not approved, and tracking is locked. Follow the person/payee step to `/driver/profile`.
- **Observed:** Profile offers only licence number, city and country fields plus a vehicle summary; it has no person/payee or vehicle evidence resubmission. The guidance says to use an expiring code from the application email, but the public code renewal service is restricted to invited users with pending applications, not an already active account. The active driver has no visible self-service recovery route.
- **Expectation:** [D-10](docs/product-requirements.md) requires a reviewed renewal/resubmission after activation; it is already marked **Not confirmed** for a driver-facing screen, and [progress](docs/progress.md) parks this journey pending the dedicated privacy/legal packet. Keep tracking locked, but give the driver and operator a real next action. This is a known product gap, not evidence that the safety lock failed.

### QA-13 · Driver pages disagree about a blocked active assignment — medium

- **Journey:** With the same Wuse driver, compare Home, Jobs and Track without changing account state.
- **Observed:** Home says “Active campaign: PalmPay Wuse Blitz,” Jobs lists its assignment as Active, and the journey marks admin activation complete. Track says “No active campaign” because the missing evidence prevents Start. The latter reads as an assignment-state claim even though it is an eligibility decision.
- **Expectation:** Track should say that the active campaign exists but is temporarily ineligible to track, with the governing evidence reason and recovery path. See [`trip-tracker.tsx`](frontend/src/app/driver/(portal)/track/trip-tracker.tsx). The seeded state is legacy/incomplete; this pass does not claim a new activation can bypass evidence gates.

### QA-14 · Edited campaign form leaves an older preview confirmable — medium

- **Journey:** On live “F7 Lagos Commuter Reach,” enter a synthetic total budget of ₦5,000,000 and a reason, then press “Preview change.” After the preview appears, edit the total budget field to ₦5,500,000 without confirming.
- **Observed:** The form shows ₦5,500,000 while “Review before confirming” still shows `4800000.00 → 5000000`, “Can apply now,” and an enabled “Confirm this change” button. The confirm form contains the frozen ₦5,000,000 proposal. No change was confirmed during this check.
- **Expectation:** Any edit to budget, dates or reason should invalidate or clearly separate the preview and require a fresh preview before confirmation. The present screen can make a user believe the edited amount is being confirmed. See [`campaign-change-panel.tsx`](frontend/src/app/advertiser/campaigns/[campaignId]/campaign-change-panel.tsx).

### QA-15 · Invited driver applicant is offered “Reactivate” — high; status-path risk

- **Journey:** As admin, open `/admin/users` after a synthetic public driver application is received. Its account row is `INVITED` but presents a “REACTIVATE” action.
- **Observed:** This is a first-time applicant, not a suspended former account. The client maps every non-active status to `active`; the admin PATCH calls `update_user`, whose status transition has no driver-application approval or evidence check. A controlled service call against this synthetic applicant moved the account to `active` and made it password-recovery-eligible inside a transaction; rollback left the persisted status `invited`. No UI reactivation or password reset was performed, so this does not claim a completed sign-in or trip-start bypass.
- **Expectation:** Keep invited drivers in the governed application → evidence review → vehicle approval → account setup path. The generic admin status control should not offer activation for an invited applicant, and the server should reject that transition outside approved setup. See [`user-status-menu.tsx`](frontend/src/app/admin/users/user-status-menu.tsx), [`users.py`](app/services/users.py), and [`driver_account_setup.py`](app/services/driver_account_setup.py).

### QA-16 · Driver can attempt to accept an offer the page says lacks terms — medium

- **Journey:** As seeded Amina Bello, open `/driver/assignments` and inspect the offered “F7 Airport Launch Draft” job.
- **Observed:** The page says “This legacy assignment has no complete frozen offer terms,” yet enables “Accept job.” The acceptance service rejects incomplete frozen terms with `FROZEN_OFFER_TERMS_REQUIRED` and HTTP 409. I did not press Accept because that action records a driver work decision; the visible offer state and server guard establish the UI mismatch.
- **Expectation:** Show an unavailable offer with a specific operations remedy, and enable acceptance only once the driver can review complete frozen terms. The backend guard is correct. See [`campaign_assignments.py`](app/services/campaign_assignments.py).

### QA-17 · Notifications beyond the first 50 cannot be opened — medium

- **Journey:** As seeded Amina Bello, open the notification centre with 57 unread notifications.
- **Observed:** The popover lists 50 notifications, with no next page or “load more” control. Its “Mark all read” button could clear the seven unseen notifications. The API defaults to `limit=50` and supports `offset`, but the frontend always fetches `/api/notifications` without pagination.
- **Expectation:** Expose the remaining notifications before offering to clear them all, or make the count and limited window explicit with a path to the full history. See [`notification-center.tsx`](frontend/src/components/notifications/notification-center.tsx) and [`notifications.py`](app/api/v1/notifications.py).

### QA-18 · Notification read controls are rejected by the request boundary — medium

- **Journey:** On 24 September, press “Mark all read” in the advertiser notification popover on the approved local test campaign. The browser shows “THIS COMMAND DOES NOT ACCEPT A REQUEST BODY” and leaves the notification unread.
- **Observed:** The shared notification client adds `Content-Type: application/json` to every request, including the bodyless `POST /api/notifications/read-all` and individual `POST /api/notifications/{id}/read`. The browser request boundary rejects that media type for both bodyless routes before reaching the API. A local HTTP check with the same header returned `415 BFF_MEDIA_TYPE_DENIED`; without the header it passed the boundary and reached authentication. The individual “Mark read” action has the same client and boundary mismatch, though it was not pressed in this screenshot.
- **Expectation:** Omit `Content-Type` when a request has no body, while retaining JSON headers for mutations that send JSON. Verify both read actions through the UI and confirm unread counts update. See [`notification-center.tsx`](frontend/src/components/notifications/notification-center.tsx) and [`mutation-boundary.ts`](frontend/src/lib/api/mutation-boundary.ts). This is separate from QA-17's missing pagination.

## Checked without raising a new defect

- Public driver registration initially returned `APPLICATION_UNAVAILABLE` because the local default had `DRIVER_REGISTRATION_ENABLED=false`; that is an intentional cohort gate. After enabling it **only in the isolated synthetic stack**, a new application returned a status reference, the status lookup showed pending stages, the admin queue showed the applicant, and an onboarding email arrived at local Mailpit on the scheduled worker sweep.
- Viewer campaign and company writes were denied by the backend; QA-03 concerns the visible controls and misleading campaign error.
- The post-creation “Add missing creatives” route exists. Missing-file validation worked when a creative row was present. The full private upload/scan/attach flow remains **untested** because Chrome's ChatGPT browser extension denied the local file chooser until “Allow access to file URLs” is enabled.
- An advertiser aggregate planning source could be recorded with an expiry. Linking it required a campaign target zone and a bounded period; no live audience export or ad-platform activation was attempted.
- The seeded active campaign lacks bound creative and installation proof for a new measurement run. The admin run command rejected it correctly; this limits report/issuance testing on this fixture.
- A second seeded driver has an active assignment and recorded earnings but lacks current person/payee and vehicle evidence. Start is correctly locked; QA-12/QA-13 cover the missing recovery path and contradictory page labels, while the legacy fixture itself needs cleanup before a coherent pilot walkthrough.
- Driver storage/queue, Web Locks and BFF-session diagnostics passed in the earlier mobile-sized Chrome pass. Windows Chrome is not a representative physical Android/iPhone tracking test; no location permission or real trip was started.
- Password-reset requests for a known seeded account and an unknown address returned the same non-enumerating public message. The known account received a local Mailpit reset email; the unknown address did not. Password change was not attempted.
- Admin late trip evidence showed an empty quarantined queue with distinct pending/applied/discarded filters. The seeded live campaign's settlement page separated economic ledger pay, provider transfers and outstanding exposure; no provider action was attempted.
- Signing out and going Back in Chrome returned to the sign-in page rather than exposing the previous advertiser view.
- The zone editor opens a local, provider-neutral schematic map because no approved basemap URL is configured in this test stack. That is an explicit provider/release gate; a blank geographic background alone was not counted as a code defect. No live zone change or deletion was submitted.

## Test data and follow-up boundaries

The local database contains one disposable approved name-only campaign, one synthetic pending driver applicant, and one synthetic aggregate planning source created by these checks. No real payment, provider submission, physical-spot-check decision, driver trip or file upload was performed. Recheck every fix against the main checkout after its concurrent CV work is integrated; this document records what the committed baseline actually did.
