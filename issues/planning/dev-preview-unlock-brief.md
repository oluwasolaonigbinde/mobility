# Brief for Codex: show built pages in development (REQ-072)

Owner request, 2026-10-02. Claude reviews the finished change; you implement it.
Follow the root `AGENTS.md` and your delivery skill as usual, including the plan
review. This brief gives the facts and the intended outcome, not a substitute
for those gates.

## The rule, in the owner's words

Cardvert is in development. There are no real users and no real data, and the
clients who review the demo know it is demo data. Pending legal and approval
items must not hide built pages. **Take the locks out, and seed demo data that
shows every page in its range of states, so the client can click around the
whole system and give feedback.** The campaigns list is the model: no real
campaigns exist, yet eight seeded campaigns in different states (draft, live,
paused, completed and so on) make the page real. Every other page should feel
like that.

Do not add a new setting, demo mode, banner or approval process. The owner
will decide what protection production needs when they move off demo data.

## What blocks pages today

Every lock below checks server settings, not whether the data is real, so a
demo server holding only seed data is locked just like production would be.

| Lock | Where | What it hides | Opens today only when |
| --- | --- | --- | --- |
| Disclosure gate `PRIVACY_LIVE_USE_BLOCKED` | `app/services/disclosure.py:70` (`ensure_disclosure_live_gate`) and its callers in `reports.py`, `heatmaps.py`, `impressions.py`, `audience.py` | Advertiser overview figures, campaign summary, daily figures, trips, report, impressions, heatmaps, zone insights and retargeting suggestions; the matching admin views | `PRIVACY_DISCLOSURE_LIVE_AUTHORIZED=true` and three approved references, or `PRIVACY_DISCLOSURE_SYNTHETIC_TEST_MODE` |
| Stale measurement-run lock `SAFE_MEASUREMENT_RUN_REQUIRED` | `disclosure.py:87`; default `requires_measurement_run=True` in `require_governed_advertiser_output` (`disclosure.py:101`), reached through `build_dynamic_campaign_report` (`reports.py:1305`) | The live-calculated campaign report | Never outside synthetic mode. Its message says "until immutable measurement runs are implemented", but those runs now exist (`reports.py:1185-1220`, `report_issuances.py`). This lock is out of date |
| Report issuance `REPORT_LIVE_ISSUANCE_BLOCKED`, `REPORT_SYNTHETIC_ISSUANCE_BLOCKED`, `MEASUREMENT_LIVE_ISSUANCE_BLOCKED` | `report_issuances.py:113-143`, `reports.py:1213-1220`, `measurement.py:386` | Issuing and showing a stored campaign report | The privacy references above plus `MEASUREMENT_LIVE_ISSUANCE_AUTHORIZED` and an approved `MEASUREMENT_REPORT_METHOD_REFERENCE` (EXT-REPORT-METHOD), or synthetic mode with `ENVIRONMENT=test` |
| Collection gate `PRIVACY_COLLECTION_BLOCKED` | `app/services/privacy_authority.py:9` | Driver GPS trip recording and ID-document collection | `PRIVACY_COLLECTION_LIVE_AUTHORIZED=true` plus the legal reference, or `PRIVACY_COLLECTION_SYNTHETIC_TEST_MODE` |
| Synthetic modes limited to tests | `app/core/config.py:1008-1011` | All of the above on any dev or demo server | `ENVIRONMENT=test` only |

The frontend turns these errors into "isn't available yet" panels
(`frontend/src/lib/advertiser/page-data.ts:18`,
`frontend/src/components/ui/data-unavailable.tsx`,
`frontend/src/app/advertiser/campaigns/[campaignId]/report/measurement-authority.tsx:310`).

## Intended outcome

1. **Remove every lock in the table.** The analytics and report pages, report
   issuance, heatmaps, zone insights, retargeting suggestions/export and driver
   GPS/ID collection run unconditionally. Pages must render with the existing
   seed data, not an "isn't available yet" panel.

   **Reports have one path only.** Advertisers see issued reports from
   measurement runs (seed them; see item 4). Remove or hide the live-calculated
   report (`build_dynamic_campaign_report`) rather than unlocking it, so the two
   can't show different numbers for the same campaign. Explain the choice in
   your plan.
2. **No setting replaces them.** Delete the gate code, the
   `PRIVACY_DISCLOSURE_*`, `PRIVACY_COLLECTION_*`, `PRIVACY_*_REFERENCE` and
   `MEASUREMENT_LIVE_ISSUANCE_AUTHORIZED` / method-reference settings that exist
   only to drive these locks, the `test_only` versus live issuance split where
   it exists only for the lock, and the now-dead frontend "gated" copy and
   states. Under the repository's replacement policy, do not alias or keep the
   old names. Update every caller, env example, compose file, e2e compose file,
   release/pilot-gate script and test. If a setting or field also does real work
   beyond the lock (for example a method revision recorded on a report), keep
   that part and say so in your plan.
3. **Keep the remaining behaviour intact:** tenant isolation (an advertiser
   sees only their own organisation), minimum-group-size / aggregation rules
   that decide what a result may show, query-history recording, and person-level
   rejection in exports. Those are product logic, not legal locks. If one of
   them is only reachable through a removed lock, keep it working.
4. **Seed every state across the system.** Extend the existing seed
   (`app/seeds/demo.py`, `rich.py`, `demo_authority.py`, run through
   `run_seed`) rather than adding a new mechanism. Walk every advertiser,
   admin and driver page and, wherever a page is empty, says "isn't available
   yet", or only ever shows one state, seed believable demo records that show
   its range. The seed currently covers users, organisations, campaigns,
   zones, drivers, vehicles, KYC, trips, trip analytics, impressions,
   installation evidence, billing and payouts. Gaps found while writing this
   brief (confirm and extend in your plan):
   - campaign reports: measurement runs and issued reports, at least one
     campaign with a full report and one still in progress
   - heatmaps, coverage map and zone insights with enough trips to render
   - retargeting: saved audience descriptions, area-and-time suggestions and an
     export record
   - help/complaints in open, answered and closed states, for advertiser and
     driver
   - quotations, invoices and payments in their different states
   - driver applications at each review stage, and payouts held, released and
     paid
   - notifications and work-queue items for every admin department, so no
     section reads "Nothing waiting" everywhere

   - **Terrax staff, not just "Demo Admin":**
     - about 5 believable staff sign-ins matching the client's departments, for
       example a Finance Officer, a Customer Service officer, a Compliance
       officer, an Operations lead and the CEO;
     - realistic Nigerian names and `@terraxmedia.com`-style demo emails;
     - mostly active, one invited (not yet signed in) and one suspended.

     Record which placeholder names stand in for real people in
     `docs/demo-data.md`; the client hasn't named them yet.
   - **Those staff are the actors across the seed.** Different people approve
     drivers, review artwork, answer complaints, approve corrections and pause
     or resume payouts. Activity logs, review histories and "handled by" fields
     then show real variety instead of one account.
   - **One golden-path campaign** that runs cleanly through every step:
     1. quotation;
     2. accepted terms;
     3. funding;
     4. approved artwork;
     5. a `payout_v4` offer;
     6. installation photos;
     7. activation;
     8. trips;
     9. an issued report;
     10. a payable driver;
     11. an automatic payout batch.

     This takes over L2-3's golden-path item, which is dropped from L2-3.
   - **New pay data uses `payout_v4`** (₦10,000 for 70 miles, proportional, per
     D43), so L2-4's legacy removal doesn't force a reseed.
   - **Enough vehicles, trips and days per area to clear the aggregation
     minimums** (currently 3 vehicles, 5 trips and 2 days per cell).
     Heatmaps, coverage and reports must show real figures, not suppressed
     cells.

   **General rule:** every list and tab in the admin, advertiser and driver
   portals shows several rows in different states. That includes Settings
   (staff, reach estimates, retargeting audiences, activity log, support
   tools), not only the main work pages.

   Use plausible Abuja/Lagos names, routes and amounts, consistent with the
   existing seed.
5. **Values the client has not given yet.** Some screens need a value the
   client still owes us (open rows in `docs/requests.md` and the MISSING
   external inputs in `docs/progress.md`). Examples:
   - how estimated impressions are worked out and labelled (EXT-REPORT-METHOD),
     which the report pages need
   - custom quotation components, commissions and premium payout rates
     (EXT-COMMERCIAL-VALUES)
   - budget warning and pause thresholds (EXT-BUDGET-POLICY)
   - Terrax's OPay bank details and invoice number prefix (REQ-041, REQ-042)
   - complaint categories and reply targets (REQ-020, REQ-021)
   - installation spot-check and display-proof values (REQ-039)

   For the demo, put a sensible placeholder into the **seed data only**, for
   example a plausible bank name and account number on a demo invoice, or a
   reasonable impression figure on a demo report. Never put placeholders into
   product settings, code defaults, `docs/client-decisions.md` or the decision
   log, which must keep these values unset until the client answers. Record
   each placeholder in the internal note in item 7, so the owner can see what
   to replace when going live.
6. **Keep internal decisions internal.** The product must read like a finished
   product to a human, not like a list of internal decisions. Do not show
   approval, lock, gate, placeholder or policy explanations anywhere in the
   UI. Remove the copy that exists only to explain a lock, for example
   "Available once privacy approval for campaign results is complete." and "Results, maps and reports become available once privacy
   approval for campaign results is complete." On every page you touch, also
   rewrite wording that narrates internal rules instead of helping the user,
   such as "This checklist shows what has been recorded so far. It does not
   authorize production, assignment, installation or launch." (campaign
   detail) and "Pending ledger total ₦0.00; not a held-only total" (driver
   earnings). Use plain, short wording a client or driver would expect; list
   other examples you find outside your pages for the owner rather than
   widening scope.
7. **Document it once, internally.** Write one internal note (suggested
   `docs/demo-data.md`) listing: the locks removed, every seeded placeholder
   and which client answer replaces it, and what to decide before real users.
   This is the owner's go-live checklist; it never appears in the product.

   Its **first item** is "Restore legal/privacy protections for GPS, ID
   collection and advertiser results before real users". When you remove the
   lock settings from the release and pilot-gate scripts, add that same line as
   one launch-gate row in `docs/progress.md`. That way the launch checklist
   can't pass without it.
   Beyond that note, keep the records `AGENTS.md` requires to a sentence each:
   one dated line in the client-decisions topic "Legal, privacy and retention"
   (the current rule no longer says these pages are gated), the decision row
   and architecture note for a privacy-behaviour change, and
   `docs/privacy-operating-model.md`. No other process.

## Content quality (strict; the owner will reject slop)

**Names.** Every seeded record must look like real Terrax business data.
- Never use these words: test, demo, sample, UAT, Codex, Claude, seed,
  fixture, placeholder, lorem, "example".
- Never use numbers as names ("Driver 3", "Campaign B").
- Never put a state in a name ("Paused Campaign", "Rejected Driver").
- Rename existing seed records that break these rules, for example
  "F7 Mainland Retail Pause", "Demo Advertiser", "Demo Driver" and
  "DEMO-101" plates. Keep the demo sign-in accounts working and update the
  docs and tests that name them.

**People.**
- Realistic Nigerian full names with a natural mix (Yoruba, Igbo, Hausa,
  other), with no repeats.
- Staff emails look like `firstname.lastname@terraxmedia.com`. Drivers and
  advertiser contacts have ordinary-looking addresses.

**Companies and campaigns.**
- Use believable but **fictional** Abuja and Lagos businesses, for example
  "Mama Cass Kitchens — Wuse Lunch Rush", "Zenith Gadgets — Maitama Store
  Opening" or "Royal Crest Paints — Lugbe Rainy-Season Push".
- Don't use real brands (MTN, Indomie, Chicken Republic…). The client could
  read them as real advertisers.
- A description is one plain sentence an advertiser would write, for example
  "Lunchtime visibility around Wuse II offices".

**Places, plates, routes and amounts.**
- Real Abuja and Lagos districts and roads.
- Nigerian plate formats, for example ABJ-482-KD or LSR-219-XY.
- Amounts that fit the client's prices: ₦10,000 day rate, quotations around
  ₦1,000,000, VAT 7.5%.

**Text written by people** (complaint messages, review notes, rejection
reasons, contact outcomes, pause reasons) must read like a real person wrote
it: short, specific and varied.
- Good: "Back sticker is peeling at the corner, please re-shoot in
  daylight."
- Not acceptable: "Rejected for testing purposes."

**No explanatory text.** Nothing in the UI or the seed may explain the
system, the demo, a state or a rule.

**Handover.** Before handing over, list every seeded name, company, campaign
and free-text field in one table, so the owner can scan it.

## Also fix while you are on these pages

1. **Seed a recorded pause reason for every paused campaign,** for example
   "Advertiser asked to hold the campaign during the Sallah holiday". The
   campaign page then shows why it's paused, and staff can resume it. Today it
   says "The reason for this pause was not recorded".
2. **Remove the line "Oldest five items from each work list."** from the Work
   queue. It narrates a rule.
3. **Fix the admin layout so the rendered page sits inside `<main>`.** After
   loading, the `<main>` landmark still holds only the "Loading…" fallback,
   and the real content sits outside it. Screen readers and text tools then
   read only "Loading…".

## Out of scope

- Real outbound calls to Meta or Google (`AD_PLATFORM_LIVE_ACTIVATION_BLOCKED`
  in `audience_delivery.py:1037`) stay blocked. That is an external action, not
  a legal display lock.
- Payments, payouts and email providers: untouched.
- No "demo data" banners or labels, and no new setting or mode.
- Visual directions and theme files: Claude is changing those at the same time
  (REQ-071). Do not edit `frontend/src/app/globals.css`,
  `frontend/src/lib/themes.ts` or `docs/design/**`.

## Sequence and commits

- Start only after the L2-1 follow-up fixes are committed.
- Deliver two commits, each reviewed by Claude before it's committed:
  - **(a)** remove the locks and their settings, and rewrite the wording;
  - **(b)** seed every state.

## Working-tree caution

`master` has a lot of uncommitted work from other requests (REQ-063 to REQ-070).
Some of it touches `app/core/config.py`, `.env.example`, `docker-compose.yml`,
`docs/architecture.md`, `docs/client-decisions.md` and `docs/decisions-log.md`.
Do not overwrite or revert those edits. Work in a separate worktree or branch
from `master`, or wait until REQ-070 is committed, and say which in your plan.

## Verification expected

- Focused backend tests: each formerly locked endpoint returns data with
  default settings; tenant isolation, aggregation thresholds and person-level
  export rejection still hold.
- A local run of a fresh seed with default settings: list every advertiser,
  admin and driver page with what it shows. No page may show "isn't available
  yet", and pages with states (campaigns, reports, payouts, applications,
  complaints, invoices, work queue) show several. A driver trip records GPS on
  the demo server.
- Include in the walkthrough evidence a list of every screen and tab with its
  row count and the states it shows, including Settings.
- Heatmaps, coverage maps and reports show real figures with the default
  aggregation minimums.
- Seed tests still pass, and the seed still re-runs without duplicating
  records.
- Run only the test files you touch locally; the full suite runs in CI.

## Handover to Claude

When your change is verified, give the owner the diff (including new files),
the test commands and results, and the walkthrough evidence. Claude reviews it
before commit. No commit, push or deployment without the owner's explicit
approval.
