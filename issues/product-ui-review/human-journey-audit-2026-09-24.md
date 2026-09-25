# Human-journey audit and guide reconciliation — 24 September 2026

Authority: `docs/progress.md` → "Direct owner requests outside the package
queue" → *Human-journey UX audit and bounded copy/flow fixes (24 Sep 2026)*.
The executable queue is unchanged (`PAUSED — EXT-PAYMENT-PROVIDER`).

## 1. What was tested

| Stack | Code | Database / config | Used for |
| --- | --- | --- | --- |
| `cardvertmain` (web :3001, api :8001) | main checkout: `21a5981` + uncommitted CV-01–CV-17 + this batch | migrated `0001→0090`, demo + F7 seed, **default pre-approval privacy config** (`PRIVACY_DISCLOSURE_LIVE_AUTHORIZED=false`, no synthetic mode), driver registration enabled | every "current" observation below |
| `cardvertlivecheck` (:3000) | isolated clone at `21a5981`, clean | E2E override (`ENVIRONMENT=test`, synthetic disclosure mode), QA leftovers from 23 Sep | comparison with the demo/synthetic experience only |

Signed-in screens were captured with a headless Playwright script (the
repository's own E2E approach) using the seeded local demo accounts; nothing was
typed into a real browser session. Evidence (text + full-page screenshots) is
in the session scratchpad `out/` folders; the before/after pairs cited below
are reproducible by re-running the capture against the same stack.

Legend — **Fixed now**: changed in this batch (uncommitted) and verified as stated in §3 (unit tests for every item; live on the main stack for every item except where §3 says unit only).
**(1)** fix we can make now, not done in this batch. **(2)** client decision or
credential needed for live use. **(3)** product choice needing owner input.

## 2. Top findings, in priority order

1. **Retargeting page crashed** in the configuration every real deployment
   starts in (privacy not yet approved): `/advertiser/planning-sources` and
   `/admin/planning-sources` rendered "Something broke… contact Cardvert
   support" because `GET …/retargeting-sources` returns 503
   `PRIVACY_LIVE_USE_BLOCKED` and the pages did not handle it. **Fixed now.**
2. **Notification read controls never worked** (QA-18): every request sent
   `content-type: application/json`, and the BFF boundary refuses a media type
   on bodyless commands (415). Only the first 50 notices were reachable
   (QA-17). **Fixed now**; live: 20 of 35 shown, "Show older" loads the rest,
   Mark read / Mark all read return 200 and the badge clears.
3. **An invited driver applicant could be activated** from Users → Reactivate,
   bypassing D28 account setup (QA-15). The first fix was reviewed and a second
   route (role flip → password recovery) was closed. **Fixed now** (server +
   UI; security review adopted).
4. **Reports claimed data corruption** when no report had been issued (QA-02),
   and said "report data could not be verified" when results were simply not
   yet approved. **Fixed now.**
5. **Screens offered actions the server refuses**: change requests and "Add
   missing creatives" on completed campaigns; Accept on offers without pay
   terms (QA-16); create and company forms for viewers (QA-03). **Fixed now**; campaign-detail write controls are still shown to viewers (residual).
6. **Contradictory status messages**: a completed or live campaign said "Next
   action: Request the custom quotation"; artwork chip said READY while the
   summary said "Not ready"; Track said "No active campaign" while Home showed
   one (QA-13). **Fixed now.**
7. **Engineering language on customer and driver screens** ("Backend
   onboarding, vehicle, offer and activation authority are current",
   "Aggregate-only retargeting inputs", "Evidence <sha256>", "Frozen offer
   terms", emoji tab icons). Largest offenders **fixed now**; remaining list in
   §4.
8. **Demo data cannot tell a coherent story** (QA-10): every live campaign has
   no quotation, funding or approved artwork; the Demo campaign runs
   2016→2036; no driver has a verified payout account; all seeded trips are
   legacy per-km. A client walkthrough of quote → report → payout is not
   possible on the seed. **(1)**
9. **The client guide overstates several "Built and working" items** — see §5.
10. **Admin navigation**: 16 flat items clipped the sign-out control at laptop
   heights (QA-04). Now grouped and scrollable. **Fixed now.**

## 3. Changes made in this batch (UX-01…UX-11)

| ID | Screen | Before (exact) | After (exact) | Verified |
| --- | --- | --- | --- | --- |
| UX-01 | Notification centre | list capped at 50; read POSTs → 415 | "Showing 20 of 35 · Mark all read includes older ones" + **Show older**; bodyless requests send no media type | unit + live (Amina: 20→35, both read actions 200) |
| UX-02 | Advertiser nav / page | "Planning sources" · "Aggregate-only retargeting inputs" · "Record aggregate source" · "Website traffic" · "Evidence a3f…" | "Retargeting" · "Follow up online where your campaign drove" · 3-step explainer · "Describe an audience" · "Website visitors" · fingerprint under collapsed "Technical reference"; gated state "Retargeting isn't available yet" | unit + live |
| UX-03 | Admin planning page | crash; title "Campaign analysis governance" | "Planning sources aren't available yet"; title "Planning sources" | unit + live |
| UX-04 | Report / coverage map | "This report failed its integrity check… Cardvert needs to reissue" (no run) · "report data could not be verified" (gated) · tab "Governed coverage map" | "No report is available yet" · "Campaign results aren't switched on yet — …once privacy approval for campaign results is complete" · "Coverage map" | unit + live + e2e spec updated |
| UX-05 | Campaign detail | "📊 🔥 🗺" · "Next action: Request the custom quotation" on completed/live · "CAMPAIGN REVIEW: completed" · change form on every status · "Add missing creatives" · chip "READY" · "security scan: clean" · "This campaign has not been submitted for review." on live | no emoji · lifecycle next action ("This campaign has finished…") · human status · change form only when scheduled/live/paused · "Add artwork" (hidden when completed/cancelled) · "Older file" · "file check passed" · "No review history is recorded…" | unit + live |
| UX-06 | New / edit campaign | "DAILY CAP (NGN)" · "Set the basics — targeting zones come next" · "Created as a draft — Submit the completed campaign for admin review…" · recovery "you can create the campaign without creatives" · Attach enabled with none | "Daily budget (NGN)" · "Set the basics, then add creatives — campaign areas are set on the campaign page" · "Saved as a draft — Nothing is sent for review yet…" · recovery copy · Attach disabled, explanation linked with `aria-describedby` | unit + live (empty recovery on the seeded draft) |
| UX-07 | Viewer role | "+ New campaign", editable company form; 403 → "result is not yet confirmed. Retry…" | "View only — company owners and managers create campaigns"; read-only company form; explicit permission message | unit + live |
| UX-08 | Driver journey / Track | "Backend onboarding, vehicle, offer and activation authority are current." · "Person & payee" · "Ready for explicit Start / Start remains subject to the live PWA capability and server checks." · Track "No active campaign" (with one active) | "You're ready to drive." · "Identity & bank details" · "Ready to start / Press Start on the Track page when you begin driving." · "F7 Lagos Commuter Reach can't start yet" | unit + live |
| UX-09 | Admin sidebar | 16 flat items, sign-out off-screen at 695–768 px | grouped (People & cars · Campaigns · Trips & money · Reports & records), nav scrolls | unit + live at 1366×695: sign-out at y=661 and hit by a pointer; nav 786 px content in 516 px |
| UX-10 | Users → status | "REACTIVATE" on invited applicant; server accepted | "Activated through driver account setup"; server refuses activation *and role change* until setup is completed (`DRIVER_ACTIVATION_REQUIRES_SETUP`) | backend 40/40, red/green on all bypass paths |
| UX-11 | Driver jobs | "This legacy assignment has no complete frozen offer terms." + **Accept job** · "Frozen offer terms" · creative checksum · "Evidence <sha>" | Accept withheld: "This offer can't be accepted because its pay terms are incomplete." · "Pay and job terms" · hashes under "Technical reference" | unit + live |

## 4. Screen-by-screen review — remaining items

### Public

| Screen | Current wording | Proposed | Why | Cat. |
| --- | --- | --- | --- | --- |
| Landing hero / drivers | "drivers earn from the miles they already drive"; "Participate without changing everyday driving habits" | "approved drivers earn for eligible campaign driving time"; "Earn from driving you already do — keep the Cardvert app open while you drive" | Pay is hourly on verified time (D2/D12/D18), and tracking needs the app on screen (D3). The landing contradicts the guide p.8. | (1) copy, confirm tone with owner |
| `/apply` | One long page with five forms, "Application receipt is not work approval", "Submit person/payee evidence", "NO PASSWORD, WORK ACCESS, ASSIGNMENT, PAYOUT OR DOCUMENT ACCESS IS CREATED BY THESE FORMS", "EXISTING VEHICLE ID (ONLY WHEN REVISING)", "Live onboarding remains unavailable until Terrax Media supplies approved legal/privacy wording and adopts the production storage, scanner, key-custody and bank-provider gates." | Three steps shown one at a time: Apply → Your details (with the emailed code) → Your car (after approval). Replace the vehicle-ID field with a chooser of the applicant's cars by plate. Move the provider/legal status to one line: "Document upload opens once Terrax Media switches on driver onboarding." | A first-time driver cannot tell which form applies to them; a raw internal ID cannot be known by the applicant (guide p.23 promises "choose an existing car"). | (1) flow + small API; legal wording (3)/FOD-001 |
| `/driver-account-setup` without token | "This administrator-authorized action only sets your password… This setup action is incomplete. An administrator must issue a new setup action after the required reviews are current." | "This setup link is incomplete or has expired. Ask the Cardvert team that approved your application to send a new one." | Plain recovery step. | (1); support contact (2)/G-39 |

### Advertiser

| Screen | Current wording | Proposed | Why | Cat. |
| --- | --- | --- | --- | --- |
| Overview | "Campaign results unavailable — Available once privacy approval for campaign results is complete." (only card) | Keep, and add "Meanwhile you can prepare campaigns, request quotations and upload artwork." with links | A gated page with nothing to do next. | (1) |
| Campaign → Commercial | "NOT REQUESTED / Request custom quotation" shown on **completed** campaigns; accepted receipt "NGN 100000000.00", "INCLUDED TAX 0.000000 · NGN 0.00", "BUDGET POLICY blocked external policy" | Hide the request on completed/cancelled; money as "₦100,000,000.00"; "VAT 0% · ₦0.00"; "Budget alerts: not set up yet" | Same terminal-state and raw-format issues fixed elsewhere. | (1) |
| Campaign → Cancel | "Cancellation is permanent. New assignments and trip starts stop at one server-recorded cutoff. Verified driver earnings before that cutoff remain payable. Refund eligibility is determined from accepted terms and production evidence; cancellation does not itself prove that money was transferred." + "I understand this records a permanent cancellation cutoff." | "Cancelling can't be undone. Drivers stop from the moment you confirm and are still paid for work already done. Any refund depends on your accepted terms and whether production had started; the refund position appears here afterwards." + "I understand cancelling can't be undone." | Same facts, readable. | (1) |
| Campaign → changes (QA-14) | After Preview, editing the budget leaves the older preview confirmable | Clear the preview on any edit and require a new preview | The form shows one amount while the button confirms another. | (1) |
| Campaign → review history | "Submission reference: <sha256>" | Collapse under "Technical reference" | Same G-37 treatment as elsewhere. | (1)/(3) G-37 |
| Billing | "Billing details" link opens the company profile; "ONLINE PAYMENT ISN'T AVAILABLE YET. PLEASE PAY BY BANK TRANSFER." | Rename link "Update billing contact"; until approved instructions exist: "Pay by bank transfer using the instructions Terrax Media gives you with your invoice." | No destination is shown anywhere (QA-06). | copy (1); instructions (2) G-19 |
| Company | error text rendered from `?error=` query | Keep message in action state | NX-18 class. | (1) |
| Notifications | "Your campaign has been approved." (no name, no link) | "PalmPay Wuse Blitz was approved" + Open campaign | QA-08; needs payload/link contract (§9 baselines). | (1) |
| Retargeting forms | `datetime-local` values converted with `new Date()` in the server action | Reuse CV-17's Lagos converter | Same time-zone bug class as NX-14/CV-17. | (1) |
| New campaign (validation) | "basics.name: …" from `new/actions.ts:42` | Use the field label | CPY-003 confirmed in code. | (1) |
| Time labels | "(Lagos time)" in an Abuja pilot | "(Nigeria time, WAT)" | Lagos is the zone name, not the city. | (3) G-30 |

### Driver

| Screen | Current wording | Proposed | Why | Cat. |
| --- | --- | --- | --- | --- |
| Home / Earnings status words | Home "AVAILABLE", Earnings "RELEASED"; "₦26,175 pending · ₦0.00 owed, taken from your payouts"; "Pending ledger total ₦26,175; not a held-only total"; "This page: 0 held · 4 other pending · 5 released · 0 paid"; stray "₦" line | One vocabulary: Being checked · Ready for payout · On hold · Paid · Taken back. Headline: "Being checked ₦26,175 · Ready for payout ₦29,260 · Paid ₦0" | Same money, two names on two screens. | labels (1); layout (3) FUD-001 |
| Track | "Cardvert captures only while the installed app is visible and every live safety check remains held."; "EARNINGS ACCRUE FROM VERIFIED DRIVING TIME" | "Keep Cardvert open on screen while you drive. Recording pauses if you switch apps or lock the phone."; "You earn for eligible driving time" | Plain safety instruction. | (1) |
| Phone diagnostics | "R14-A · CONTRACT R14-A-V2 · Production PWA capability probe", status codes, JSON report | Driver-facing "Phone check" with five yes/no checks and a Copy-for-support button; move the probe behind a support flag | Engineering instrument linked from the Track page. | (3) G-35 |
| Jobs | "Installation evidence is waiting for the operations policy to be configured."; "Base: 1500/hr" | "Installation photos can't be uploaded yet." ; "₦1,500 per hour" | Plain, formatted. | copy (1); policy (2) G-21a |
| Profile / renewal | Journey sends rejected/expired drivers to Profile, which has no resubmission | Real renewal path | QA-12 / NX-05 (privacy packet). | (1) packet; legal (2) |

### Terrax Media admin

| Screen | Current wording | Proposed | Why | Cat. |
| --- | --- | --- | --- | --- |
| Overview | "Fleet & Trust Operations · OPERATIONS · AGGREGATE MEASUREMENT", four counts | "Waiting for you": applications, approvals, trip reviews, late data, payout approvals, each linking to its queue | Counts don't say what to do. | (3) FUD-004 |
| Users / Drivers / Vehicles | "REACTIVATE" (users, vehicles) vs "REINSTATE" (drivers); user ACTIVE while driver onboarding SUSPENDED, unexplained; Suspend offered on the signed-in admin's own row | One verb ("Restore"); column "Driver approval"; hide Suspend on your own account (verify server rule) | Vocabulary drift; two status axes. | (1) |
| Assignments | column "ACTIVITY OPERATIONS: Clear" | "Activity checks: OK" | Unclear header. | (1) |
| Approvals | "APPROVAL RECORDS THE REVIEWED SUBMISSION ONLY. SCHEDULING AND ACTIVATION REMAIN UNAVAILABLE." | "Approving records your decision on this submission. Drivers are offered and started from Assignments." | "Unavailable" is false — activation exists under Assignments. | (1) |
| Fraud | "13 FLAGS — OPEN, ACKNOWLEDGED AND CONFIRMED FLAGS HOLD AFFECTED MONEY; ONLY DISMISSAL RELEASES THE HOLD"; raw evidence "Demo true · Seed Version f7_rich_v1 · Threshold Mps 55 · Max Observed Speed Mps 539.9865"; "TRIP DCCFB6BE"; physical check needs pasted Assignment ID + Trip ID | "Trip reviews — earnings stay on hold until a review is dismissed"; "Top speed 1,944 km/h (limit 198 km/h)"; hide seed keys; "Request physical check" as a row action | Readable evidence; QA-05 discoverability. | (1) |
| Payouts | "Runs the full pipeline: route analytics → impression estimate → payout calculation + ledger entry. Idempotent — safe to re-run." + TRIP ID box; columns "FORMULA payout_v1 · QUALITY × · FRAUD ×"; "AVAILABLE EARNINGS MOVE THROUGH FROZEN MAKER-CHECKER BATCHES…" | Move "Process a trip" to a support tool / row action; "Pay basis: Legacy per-km"; three links "Prepare a payout batch · Pay rules · Corrections" | Engineering console as the main payouts page. | (1) |
| Payout batches | "SELECT CREDITS, REVIEW FROZEN INSTRUCTIONS, THEN OBTAIN INDEPENDENT APPROVAL"; every row "Destination unavailable — The current bank-account version has no authorized payout verification" | "Choose earnings to pay. Cardvert rechecks holds, debt and bank details when you create the batch."; "Bank account not verified yet" | Readable; demo has no payable driver (QA-10). | (1) |
| Pay rules | "How drivers earn on each campaign — rates, zone bonuses, caps and fraud multipliers" | "Standard and premium hourly rates and the daily cap for each campaign" | Zone bonuses and fraud multipliers are retired v1 concepts (D2/D18/D21). | (1) |
| Corrections | "RETROACTIVE DAY RECOMPUTES — PROJECTED, INDEPENDENTLY APPROVED, EXECUTED ONCE"; "LAGOS DAY"; "CREATOR ≠ APPROVER" | "Correct a day's driver pay. One person proposes, a different person approves, and it runs once." | Plain. | (1) |
| Traffic | "The analytics engine's assumptions — density, dwell and time-of-day weights behind every impression estimate" | "Traffic inputs used to estimate how many people could see a vehicle" | Plain. | (1) |
| Driver contact | Tasks can only complete for a verified phone, but no screen verifies a phone | Phone-verification worklist | NX-11. | (1) packet; operator (2) G-06/G-23 |
| Page titles | Nav vs page: Fraud/"Fraud console", Billing/"Commercial billing", Audit/"Audit trail", Traffic/"Traffic profiles", Measurement & reports/"Campaign Performance Analysis"; three pages titled "Cardvert — Aggregate Mobility Measurement" | Match page titles to nav labels; add missing metadata | Orientation. | (1) |
| Top bar | "Network · Admin / Ops", "Workspace" | "Terrax Media operations" | Meaningless labels. | (1) |

## 5. *How Cardvert Works* (17 Sep 2026) versus observed behaviour

"Observed" below is the main checkout; "at `21a5981`" means the committed code
the client guide describes, which is what the client would see today.

| Guide (page · section) | Guide says | Observed | Guide correction |
| --- | --- | --- | --- |
| p.1 legend | "Built and working … does what this document says it does." | Several "Built and working" items did not work at `21a5981` (rows below). | Re-issue after the fixes are committed and re-verified. |
| p.3–4 advertiser journey | "Campaign approval means the details and artwork are accepted"; the advertiser "supplies campaign dates, budget, geography and artwork" before submitting | A name-only campaign can be submitted and approved (QA-01). Artwork is reviewed separately; offers require approved artwork. | "Campaign approval reviews the submitted details. Artwork is reviewed separately and must be approved before any driver can be offered the campaign." |
| p.6 "Before activation, Cardvert checks" | "Operating requirements: required permits or other launch evidence are present ✓" | No permit or launch-evidence check exists in activation code. D19 makes permits a Terrax Media pre-launch responsibility. | Move permits to "Terrax Media confirms before launch", or build the gate. |
| p.16 public landing | "Explains the advertiser and driver pathways." | Landing tells drivers they earn "from the miles they already drive" — pay is hourly. | Fix landing copy (§4). |
| p.18 overview dashboard | **Built and working** | Until privacy approval, results show "Campaign results unavailable". | Label **Built · needs approval**. |
| p.18 driver application | a driver "can start an application" | Intake is off unless `DRIVER_REGISTRATION_ENABLED` is switched on. | Add "applications open when Terrax Media opens the intake". |
| p.21 campaign changes | **Built and working**; "Stops an old preview from being used if the campaign has changed" | True on the server; but after editing the form, the older preview stays confirmable (QA-14). | Keep claim after fixing QA-14. |
| p.21 billing | "Uses manual bank transfer as the current payment route." | No settlement account or instructions are shown anywhere (G-19). | "Bank-transfer instructions are provided by Terrax Media until approved instructions are loaded." |
| p.22 campaign results | "Explains when a result is missing … instead of showing a misleading zero." | At `21a5981`: no issued report → "This report failed its integrity check"; privacy gate → "report data could not be verified". **Fixed now.** | Accurate after commit. |
| p.22 planning & retargeting | "Records descriptions of grouped information from a website, …" | At `21a5981` the page crashed without privacy approval. **Fixed now.** "Website traffic" read as an integration. | "Describes audiences the advertiser already has (for example website visitors). Cardvert does not connect to websites or ad accounts." |
| p.23 application | "Can add a first car or choose an existing car when updating information." | The applicant must type an internal "Existing vehicle ID". | Build a chooser, or remove "choose". |
| p.23/p.26 documents | "Submits or updates … documents using their application-access code." | Works for applicants only; an active driver with rejected/expired evidence has no path (QA-12). | Add "after activation, renewals are handled by Terrax Media" until NX-05 ships. |
| p.24 setting up the phone | **Built and working**: "Guides the driver through adding Cardvert to the home screen…" | One sentence on Track plus an engineering probe (R14-A codes and JSON). | Label accurately, or build a driver-grade phone check (G-35). |
| p.24 campaign jobs | "Accepts or declines an offer." | At `21a5981` Accept was shown for offers the server refuses (QA-16). **Fixed now.** | Accurate after commit. |
| p.25 earnings | "Explains each trip's normal-rate time, premium-rate time…" | True for hourly trips; legacy per-km trips show only an amount (QA-07). All seeded demo earnings are legacy. | Add "for trips under hourly pay rules"; fix the demo seed. |
| p.26 / p.33 notifications | **Built and working**: "unread count, mark one as read and mark all as read"; "Opens earlier messages across easy-to-browse pages." | At `21a5981` both read actions failed (415) and only 50 were listed (QA-17/18). **Fixed now.** | Accurate after commit. |
| p.33 advertiser notices | Lists approval, funding, budget alert, pause, resume, cancellation | CV-12 (uncommitted) adds campaign rejected, artwork approved/rejected, quotation ready. Notices name no campaign and have no link (QA-08). | Add the new events once committed; don't imply links. |
| p.27 users | "Suspends active users and restores invited, suspended or disabled users." | Restoring an **invited driver applicant** bypassed D28 (QA-15). **Fixed now**: applicants can only be activated by account setup. | "…restores suspended or disabled users. Invited drivers are activated only through account setup." |
| p.29 physical checks | "Creates a physical check for a specific branded car." | Requires pasting full assignment and trip IDs that no screen displays (QA-05). | Keep, after adding a row action/picker. |
| p.30 pay rules | "Creates new pay rules with a start date for future offers." | Works; page subtitle still describes "zone bonuses … fraud multipliers". | Guide fine; fix page copy. |
| p.32 driver contact | "Allows completion only while the phone is verified…" | No screen can verify a driver's phone (NX-11); tasks can't complete from the product. | "Needs phone verification, which is not yet available in the workspace." |
| p.2 payment approval | Three separate people prepare, approve and re-check | Enforced (`PAYOUT_RECONCILER_SEPARATION_REQUIRED`). | ✓ |
| p.16 enquiries | "Advertiser enquiries open a prepared email." | `mailto:` CTAs present. | ✓ |
| p.17 sign-in | Temporary passwords must be changed; sign-out everywhere | Matches (`must_change_password`, D26). | ✓ |

## 6. `issues.md` recheck (main checkout)

| ID | Status now | Evidence |
| --- | --- | --- |
| QA-01 name-only approval | Open — product rule | no completeness rule in submit/approve |
| QA-02 absence shown as corruption | **Fixed now** | UX-04 unit + live |
| QA-03 viewer write flows | **Fixed now** for create/company; campaign-detail and edit write controls still visible to viewers (residual) | UX-07 |
| QA-04 admin rail clipping | **Fixed now** | UX-09 |
| QA-05 pasted UUIDs | Open | fraud/payout forms unchanged |
| QA-06 bank-transfer destination | Open — G-19 | billing unchanged |
| QA-07 legacy trip detail | Open — seed/legacy | |
| QA-08 notification context | Open — contract change | |
| QA-09 wizard steps copy | **Fixed now** | UX-06 |
| QA-10 incoherent demo data | Open | §2 item 8 |
| QA-11 empty attach | **Fixed now** | UX-06 |
| QA-12 driver renewal | Open — NX-05 privacy packet | |
| QA-13 Track vs Home | **Fixed now** | UX-08 live |
| QA-14 stale preview | Open — re-read in code | `campaign-change-panel.tsx` preview not cleared on edit |
| QA-15 invited → Reactivate | **Fixed now** | UX-10, security review adopted |
| QA-16 Accept without terms | **Fixed now** | UX-11 live |
| QA-17 notifications > 50 | **Fixed now** | UX-01 live |
| QA-18 read actions 415 | **Fixed now** | UX-01 live |

## 7. High-impact improvements for a coherent journey

1. **One golden-path demo campaign** (seed): quotation → accepted terms →
   confirmed funding → approved artwork → offer with frozen hourly terms →
   installation evidence → activation → hourly trips → frozen measurement run
   → issued report → payable payee → payout batch. Every screen the guide
   describes would then show real, consistent data. **(1)**
2. **Campaign page as a checklist**, not a stack of panels: one ordered list
   (Details → Quotation → Artwork → Areas → Submit → Funding → Drivers → Live →
   Report) with each step's status and single action, and panels collapsed
   under their step. **(1)/(3)**
3. **One status vocabulary per role**, enforced in `lib/*/status.ts` maps
   rather than `replaceAll("_", " ")` (36 renderers remain). **(1)**
4. **Hide engineering evidence by default** (hashes, run IDs, formula versions,
   seed keys) behind "Technical reference" everywhere until G-37 decides. **(3)**
5. **Admin home as a work queue** linking to each list. **(3)**
6. **A driver money page with three numbers** and a consistent status word per
   ledger row. **(1)** labels, **(3)** layout.
7. **A guided driver application** (three steps, chooser not IDs). **(1)**

## 8. Client decisions and credentials needed for live use (2)

G-01/G-02 payment and payout providers; G-05 email provider; G-06 phone/WhatsApp
operator; G-08–G-11 key vault, storage, scanner, basemap; G-12/G-14 legal and
privacy approvals (these gate retargeting, maps, reports and driver
onboarding); G-15 report methodology; G-17/G-18 invoice and commercial values;
G-19 settlement account and advertiser payment instructions; G-20/G-21a budget,
installation-photo and activity policy; G-23 message copy; G-25 device
validation; G-26 environment; G-29 Abuja permit evidence; G-39 support contact.

## 9. Owner decisions (3)

G-30 naming ("Cardvert" vs "Terrax Media" as the actor; "Lagos time"); G-35
phone-diagnostics exposure; G-37 whether hashes/run IDs are customer features;
QA-01 what makes a campaign complete enough to submit; admin home as a work
queue (FUD-004); driver earnings hierarchy (FUD-001); FOD-001 required
applicant/driver disclosures before rewriting `/apply` legal lines.

## 10. Verification record for UX-01…UX-11

- Reviews: independent plan review `FIX` (7 amendments adopted); security
  review of UX-10 `FIX` (role flip → password recovery route; adopted);
  consolidated post-build review `FIX` (3 blocking: live evidence for
  UX-03/06/09, QA-03 wording, changed-line coverage — all adopted, plus most
  non-blocking points, including restoring the lawful-basis status line on the
  retargeting form in plainer words).
- Frontend: Prettier on the explicit file list; `tsc --noEmit` and ESLint pass;
  full Vitest suite with coverage 156 files / 1,024 tests pass. Changed-line
  coverage of the 30 frontend files this batch touched, measured against
  `21a5981` (so it also counts CV hunks in shared files): **94.6 % lines
  (141/149), 82.8 % branches (275/332)** before the final `labels` test was
  added. This is a direct LCOV computation, not the official D32 checker, which
  needs a full backend LCOV.
- Backend: `ruff check` and `ruff format --check` pass on changed files;
  `tests/test_admin_users.py` 33/33 and with `test_driver_account_setup.py`
  40/40. Red checks: with the guard disabled the four activation-bypass cases
  fail; with the role clause disabled the role-change case fails.
- Live (main stack): retargeting and admin planning gated states, report/map
  privacy state, finished-campaign summary, viewer read-only screens, wizard
  copy and empty-attach guard, driver journey copy, Track paused-campaign
  message, offer without terms, admin sidebar at 1366×695, and UI-driven
  notification paging and read actions. UX-10's UI label was not seen live (no
  invited applicant in the seed).
- E2E specs updated but **not run** in this session: `analytics.spec.ts` and
  `campaign-flow.spec.ts` need the E2E synthetic stack;
  `w401c-campaign-journey.spec.ts` needs its mock-API mode.
- Not changed: OpenAPI/§9 baselines, migrations, provider code, coverage
  baselines. Nothing committed or pushed.
