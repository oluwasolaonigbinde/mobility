# Cardvert — Independent UX / IA / Interaction Audit
**Snapshot:** `master @ 3832cff` · 45 routes, 14 tables, 3 roles · read-only, no files edited

---

## 1 · Executive UX verdict

Cardvert is a **correctly-built system wearing a database administration skin**. The engineering is careful — server-rendered pagination, immutable evidence chains, fail-closed states, real a11y wiring in the primitives. But the interface consistently presents *the backend's model of the work* instead of *the user's task*.

Three observations frame everything below:

1. **The team can do this well.** [`app/driver/(portal)/earnings/trips/[tripId]/page.tsx:270`](frontend/src/app/driver/(portal)/earnings/trips/[tripId]/page.tsx:270) — "Time that didn't count", "Paid (after daily cap)", rates explained in words — is genuinely excellent product design. So is `lib/campaigns/status.ts`, a proper label/tone mapping. Both exist in exactly **one** place each. The defect is not capability; it is that good patterns were never generalised.
2. **Identity is the systemic failure.** Across ops surfaces, humans and objects are identified by truncated UUIDs. An admin cancelling a driver's assignment sees `a3f9c2d1…`. A maker-checker payout batch — a financial control whose entire purpose is *who approved this* — shows `created_by_user_id.slice(0, 8)`.
3. **The voice is defensive, not instructional.** The driver recruitment page's primary headline is a negation: *"Application receipt is not work approval."* Nearly every driver-facing string tells the driver what they may **not** do. This is the strongest single "not designed for a human" signal in the product.

**Verdict: not ready for external users as-is.** Admin/ops is usable-but-punishing. The advertiser surface leaks evidence artefacts (SHA-256 hashes, run IDs, error codes) into a commercial reporting product. The driver PWA — the highest-frequency, lowest-tolerance surface — is the weakest, carrying raw JSON dumps and a 10-tile chart of accounts on a phone.

The good news: **the majority of findings are subtractive.** Most fixes delete or relocate, they don't redesign.

---

## 2 · Highest-impact systemic patterns

### S1 · Human identity replaced by machine identity — **Critical**
**Evidence:** [`admin/assignments/page.tsx:80`](frontend/src/app/admin/assignments/page.tsx:80) `driver_profile.id.slice(0,8)…` · [`payouts/batches/page.tsx:58,60`](frontend/src/app/admin/payouts/batches/page.tsx:58) maker/checker · [`admin/fraud/page.tsx:232`](frontend/src/app/admin/fraud/page.tsx:232) `Reviewed by {user_id.slice(0,8)}` · [`admin/planning-sources/page.tsx`](frontend/src/app/admin/planning-sources/page.tsx) three full-UUID columns + a 64-char SHA · [`admin/approvals/page.tsx:282-286`](frontend/src/app/admin/approvals/page.tsx:282) installation review shows `assignment_id` / `vehicle_id` but not the plate.
**Role:** admin/ops. **Why:** the operator cannot perform the task the screen exists for — recognising *who* and *which*. Cross-referencing requires a second window.
**Severity: Critical.** **Recommendation:** render name (or plate/campaign name) as the primary value; expose the id only in a detail view or a copy-id affordance. Where the list endpoint doesn't return the name, that is a required API change — name it as such rather than shipping the id.
**Alternatives considered:** tooltip-on-hover with the name (rejected — hover-only, fails touch and keyboard); id + name both in-cell (rejected — doubles column width across 14 tables).
**Must not change:** the id must remain retrievable for support and audit correlation.
**A11y/responsive:** names wrap; ids don't — this also *reduces* the min-widths driving horizontal scroll.
**Acceptance:** no list cell renders a UUID as its only identifying content; every actor/subject reference resolves to a human-readable label; `.slice(0, 8)` on an id appears nowhere in `src/app/**`.

### S2 · Raw enum strings shown as status — **High**
`lib/campaigns/status.ts` is a correct label+tone mapping. It is used for campaigns only. Everywhere else the enum is printed: `{u.status}` ([users:111](frontend/src/app/admin/users/page.tsx:111)), `{a.status}` ([assignments:86](frontend/src/app/admin/assignments/page.tsx:86)), `{f.severity}`/`{f.status}` ([fraud:185,303](frontend/src/app/admin/fraud/page.tsx:185)), `{batch.status}` ([batches:52](frontend/src/app/admin/payouts/batches/page.tsx:52)), `{source.status}`, `{campaign.status}` ([admin/billing:32](frontend/src/app/admin/billing/page.tsx:32) — same data as the advertiser list, no tone mapping at all).
Three de-underscoring idioms coexist: `.replaceAll("_"," ")`, `.replace("_"," ")` ([campaign detail:313](frontend/src/app/advertiser/campaigns/[campaignId]/page.tsx:313)), and the label map. `CampaignJourneyPanel` humanises step state (`degraded → "Unavailable"`) while printing `standing` raw as `BLOCKED` **in the same component** ([campaign-journey-panel.tsx:47,81](frontend/src/components/driver/campaign-journey-panel.tsx:47)).
**Severity: High.** **Recommendation:** one `statusMeta<Domain>` module per domain exporting `{label, tone, meaning}`; `StatusChip` accepts only mapped values. **Alternative:** a generic humaniser (rejected — "deactivated" and "stale" need real copy, not title-casing). **Acceptance:** no `StatusChip` child is an unmapped API enum.

### S3 · Compliance voice as product copy — **High**
Systemic. `/apply` H2 = *"Application receipt is not work approval"*; footer = *"No password, work access, assignment, payout or document access is created by these forms."* Driver assignment cards carry a permanent paragraph per card ([assignments:274](frontend/src/app/driver/(portal)/assignments/page.tsx:274)) including *"Accepted — waiting for the independent admin activation gate"* and *"Start still rechecks current server and PWA authority."* Journey step details are negations: *"An application receipt is not approval or work access"*, *"Approval is pending; this does not grant work eligibility."* Page footers explain backend architecture: *"The backend serializes every transition and remains the authority"* ([fraud:328](frontend/src/app/admin/fraud/page.tsx:328)); *"Scheduling and activation remain unavailable"* ([approvals:305](frontend/src/app/admin/approvals/page.tsx:305)); *"Online payment checkout is unavailable until an approved provider is configured"* ([advertiser/billing:99](frontend/src/app/advertiser/billing/page.tsx:99)).
**Severity: High** (Critical on `/apply`, a conversion surface). **Recommendation:** lead with the state and the next action; move the legal negation to a single disclosure per screen, below the fold. *"Under review — we'll notify you when operations decides. You can't start campaign work yet."* **Alternative:** keep as-is if legally mandated — see §12. **Must not change:** the substance of what is disclosed. **Acceptance:** no screen's primary heading is a negation; each blocked state states what *will* happen and when.

### S4 · No search, no sort, no bulk, anywhere — **High**
Verified by grep across `src/app/**`: zero `type="search"`, zero `aria-sort`, zero row-selection checkboxes. All 14 tables are offset-paginated only. `/admin/drivers` and `/admin/vehicles` have no filter at all — finding one driver in a network-scale fleet means paging 25 at a time.
**Severity: High.** **Recommendation:** server-side `q=` search on the four entity lists (users, drivers, vehicles, assignments) reusing the existing searchParams pattern; sortable headers on the money tables; defer bulk operations until a real batch task is identified. **Alternative:** client-side filtering (rejected — the server already paginates; client filtering would silently search one page). **A11y:** sortable headers need `aria-sort` + a live region announcing the new order. **Acceptance:** every list ≥ 2 pages offers text search; result count updates and is announced.

### S5 · `micro` (11px uppercase mono, 0.12em tracking) used for prose — **Medium**
[`globals.css:403`](frontend/src/app/globals.css:403). Designed for labels; used for full sentences: the fraud page eyebrow is a 100-character policy statement rendered in it ([fraud:109](frontend/src/app/admin/fraud/page.tsx:109)); `/admin/payouts` footer carries three navigation links inside one uppercase run-on sentence. Uppercase + wide tracking + 11px + mono removes word-shape cues — measurably slower to read, and worse for dyslexic and low-vision users.
**Recommendation:** cap `micro` at ~4 words; sentences use `text-xs text-muted`. **Acceptance:** no `micro` element exceeds one short line at 1280px.

### S6 · Design-system bypass — **Medium (High in one theme)**
Eleven primary buttons are hand-rolled `bg-amber text-bg` instead of `<Button>` (`text-accent-ink`) — users, drivers, vehicles, assignments, advertiser campaigns, audit, not-found, two planning-source forms, two report-issuance buttons. The wizard re-implements `inputClass`/`labelClass`/`errorClass` locally rather than using `components/ui/field.tsx`. Two table-header idioms (`micro text-muted` vs plain `text-muted` in audit + planning-sources).
**This is a real contrast bug, not a style preference.** Measured against the shipped theme tokens:

| theme | amber | hand-rolled `text-bg` | `<Button>` `text-accent-ink` |
|---|---|---|---|
| hi-vis | `#e04e00` | **3.17 : 1 — fails AA** | 4.66 : 1 |
| danfo | `#7d6300` | 5.09 : 1 | 3.18 : 1 *(rescued by an explicit override at [globals.css:565](frontend/src/app/globals.css:565))* |
| others | — | pass | pass |

**Recommendation:** replace all eleven with `<Button>`; keep the danfo override; re-check `hi-vis`'s `accent-ink` after. **Acceptance:** `grep "bg-amber text-bg" src/app` returns nothing; every theme ≥ 4.5:1 for button label on accent.

### S7 · Evidence artefacts rendered to end users — **High**
Full/partial SHA-256 with `break-all` on the advertiser's campaign page and report; `Run {run.id}` plus three hash prefixes in the advertiser performance report footer; `Evidence {offer_terms_sha256}` on a **driver's phone**; and raw `JSON.stringify(…, null, 2)` `<pre>` blocks in three production surfaces — [`admin/assignments:141`](frontend/src/app/admin/assignments/page.tsx:141), [`admin/audit:100`](frontend/src/app/admin/audit/page.tsx:100), [`driver/assignments:268`](frontend/src/app/driver/(portal)/assignments/page.tsx:268).
**Recommendation:** hashes belong behind one "Verification details" disclosure per record, or in an export. JSON dumps belong in the audit export, not in a table cell. The driver never needs a hash. **Must not change:** the evidence must remain retrievable — this is relocation, not deletion.

### S8 · Native `window.confirm` / `window.prompt` for audited actions — **High**
Eight sites. Only [`zones-editor.tsx:242`](frontend/src/app/advertiser/campaigns/[campaignId]/zones/zones-editor.tsx:242) names the record. The other seven say "this account", "this driver", "this vehicle", "this assignment" — a confirmation that cannot confirm. Worst: [`cancel-button.tsx:11`](frontend/src/app/admin/assignments/cancel-button.tsx:11) collects a **permanently recorded audit reason** via `window.prompt` — no length limit, no validation, no review before commit, unstyled, then a second native dialog immediately after.
**Recommendation:** one confirmation dialog component; always name the record; move free-text reasons into it as a real textarea with the same constraints the server enforces. **A11y:** native dialogs bypass the design system's focus styling and can't carry structured content. **Acceptance:** every destructive confirmation states the record's human name; no `window.prompt` in `src/`.

---

## 3 · Screen-by-screen findings

### F1 · `/admin/approvals` — items past 25 are unreachable — **Critical**
[`page.tsx:21-31,53-57`](frontend/src/app/admin/approvals/page.tsx:21). Four queues fetched at `limit: 25, offset: 0`, hard-coded. No `<Pagination>` on the page. The header sums all four totals — *"68 items awaiting review"* — while rendering at most 25 campaigns + 25 creatives. **The remaining items have no navigable path.**
**Role:** admin/ops. **Recommendation:** split into four tabbed queues, each independently paginated, each tab labelled with its own count. **Alternative:** one merged queue sorted by submission age (rejected — the four decisions need different evidence and different forms). **Must not change:** the four review types stay distinct; review history stays available. **Responsive:** tabs collapse to a select < 640px. **Acceptance:** every pending item is reachable; the header count equals the sum of reachable items.

### F2 · `/admin/approvals` — an evidence-review screen that doesn't show the evidence — **High**
[`installation-review-actions.tsx:22-52`](frontend/src/app/admin/approvals/installation-review-actions.tsx:22). Installation photos are `View front` / `View rear` buttons that `POST` for a signed URL then `window.open`. Two problems: (a) the reviewer must open N tabs per record to make one decision — the photos *are* the decision; (b) `window.open` fires after `await`, outside the user-activation window — **Safari and hardened Chrome will block it**, and the code doesn't check the `null` return, so the reviewer sees nothing and no error.
**Recommendation:** render signed thumbnails inline in a photo strip; click opens a lightbox. Keep a fallback link. **Alternative:** pre-sign at render (rejected — leaks URLs into HTML and burns TTL on unopened photos). **Acceptance:** every required view is visible without leaving the page; a blocked popup produces a visible message.

### F3–F5 · `/admin/approvals` — repeated forms, inconsistent rules
- **F3 (Medium):** a "Rejection reason" textarea is permanently open on every card. Twenty-five pending campaigns = 25 always-open textareas. Reveal it on `Reject`.
- **F4 (Medium):** on one screen, four visually identical cards disagree on whether the reason is required — campaign-change is `required` client-side ([campaign-change-review-actions.tsx:25](frontend/src/app/admin/approvals/campaign-change-review-actions.tsx:25)), the other three enforce it only server-side via a discriminated union, so the reviewer types nothing, clicks Reject, and gets a round-trip error. Make requiredness identical and client-visible.
- **F5 (Low):** all four components render `{pending ? "Reviewing…" : "Approve"}` — **click Reject and the progress text appears on the Approve button.**

### F6 · `/admin/driver-applications` — a decision workflow inside a 1500px table cell — **Critical**
[`page.tsx:45`](frontend/src/app/admin/driver-applications/page.tsx:45) `min-w-[1500px]`, eight columns. The last cell contains *two* complete decision forms — five confirmation checkboxes, an approval-expiry datetime, a seven-option rejection-reason select, three buttons, plus document-review links ([vehicle-decision-actions.tsx:100-180](frontend/src/app/admin/driver-applications/vehicle-decision-actions.tsx:100)). At 1440px the reviewer scrolls horizontally to reach the form, losing the applicant's name from view. Rows with nothing to review print literal placeholders — "No person/payee review", "No vehicle review".
**Role:** admin/ops, high-consequence (identity + bank account). **Recommendation:** a queue list (name, city, what's pending, age) → a full-width review page per applicant with documents and forms side by side. **Alternative:** an expanding row (rejected — the form is too tall; it would push every other row off-screen). **Must not change:** the two submissions stay independently decidable. **A11y:** a decision form must not require horizontal scrolling to reach; 12px `text-muted` controls are below comfortable size for this consequence class. **Acceptance:** no horizontal scroll to reach a decision control; applicant identity visible while deciding.

### F7 · `/admin/driver-applications` — approve and reject fields co-visible, reject pre-filled — **High**
Same file, lines 114-146. "Approval expiry" (approve-only) and "Rejection reason" (reject-only) are both always shown, and the reason `select` **defaults to `unreadable_evidence`**. A mis-click on Reject — 8px from Approve, same size — permanently records a specific, wrong reason with no confirmation and no undo.
**Recommendation:** reveal the relevant fields on intent; no default reason; confirm reject with the applicant's name and the chosen reason. **Acceptance:** rejecting requires an explicit reason selection; approve and reject are not adjacent same-weight controls.

### F8 · `/admin/assignments` — the archetypal database screen — **Critical**
[`page.tsx:63-145`](frontend/src/app/admin/assignments/page.tsx:63). Seven columns at `min-w-[900px]`. The Driver column is a truncated UUID. "Activity operations" (meaningless header) stacks flag type + status + `{observed_seconds}s` raw + evidence count + recovery date at 10px. The **Actions column contains two conditional buttons, a 12-char hash fragment, and a `<details>` that dumps the entire frozen offer terms as pretty-printed JSON.**
**Recommendation:** Driver → name; "Activity operations" → a single flag chip with count, details on the row's detail view; seconds → `formatDuration` (already exists); hash + JSON → move to a per-assignment detail page. **Must not change:** frozen terms remain inspectable and the hash remains verifiable. **Acceptance:** min-width ≤ 720px; no JSON in a table cell; every column header is a noun an operator would use aloud.

### F9 · `/admin/assignments` — `window.prompt` for a permanent audit reason — **High**
Covered in S8. **Recommendation:** a proper cancellation dialog naming campaign + driver + plate, with a labelled textarea matching the server's constraints. **Acceptance:** the recorded reason is reviewable and editable before commit.

### F10 · `/admin/payouts/batches` — the maker-checker control is clipped off-screen — **High**
[`page.tsx:34-35`](frontend/src/app/admin/payouts/batches/page.tsx:34): `<Panel className="overflow-hidden">` wrapping `<table className="min-w-[760px]">` **with no `overflow-x-auto`**. This is the only one of 14 tables missing the wrapper — every other table has it. Below 760px the rightmost Actions column, containing batch approve/reject, is clipped with no way to scroll to it.
**Recommendation:** add the `overflow-x-auto` div, matching the other thirteen. One-line fix. **Acceptance:** at 375px the Actions column is reachable.

### F11 · `/admin/payouts/batches` — maker and checker are UUIDs — **High**
Lines 57-61. The entire point of maker-checker segregation is attributable identity; the UI shows `4f2a91c8…`. **Acceptance:** both columns show the approver's name.

### F12 · `/admin/payouts` — three sub-modules exist only as footnote links — **High**
[`page.tsx:122-135`](frontend/src/app/admin/payouts/page.tsx:122). Batches, Rules, and Corrections are reachable only from a run-on uppercase-mono sentence at the page bottom. They are not in the sidebar. Each has its own breadcrumb — so the IA *models* them as children, but the navigation doesn't. Also note the page's top panel is an internal pipeline trigger described as *"Runs the full pipeline… Idempotent — safe to re-run."*
**Recommendation:** a sub-navigation row under the Payouts header (Calculations · Batches · Rules · Corrections); demote "Process a trip" below the calculations list or behind a control. **Alternative:** nested sidebar items (rejected — the admin sidebar is already 13 flat items). **Acceptance:** every payout sub-module is reachable from a persistent navigation element.

### F13 · `/admin/planning-sources` — nav label ≠ page title; four opaque columns — **High**
Sidebar says "Planning sources"; the H1 says **"Campaign analysis governance"** ([page.tsx:47](frontend/src/app/admin/planning-sources/page.tsx:47)). The first table's Organization column is a full UUID and the Evidence column is a full 64-character SHA-256; the second table has *three* consecutive full-UUID columns. No name appears anywhere on this screen.
**Recommendation:** align the two names; resolve org/campaign/zone to names; Evidence → a short verified indicator with the hash behind a disclosure. **Acceptance:** the screen is legible without a database console.

### F14 · `/admin/audit` — filters require memorising enum strings; inputs have no accessible name — **Medium**
[`page.tsx:48-64`](frontend/src/app/admin/audit/page.tsx:48). Two bare `<input>`s with **placeholders and no `<label>`, `aria-label`, or `aria-labelledby`** — a WCAG 4.1.2 failure, and once typed into, the field loses its only identification. The placeholder asks for `auth.login.succeeded` verbatim. No date-range filter — the first thing anyone wants from an audit trail. Dates use an inline `toLocaleString("en-NG")` rather than the shared `formatDateTime`. Metadata is a raw JSON `<pre>` behind a link labelled "View".
**Recommendation:** labelled selects populated from known actions/entity types, plus a date range; render the two or three metadata keys that matter with a "raw" disclosure. **Acceptance:** every filter control has a programmatic name; a date range exists; the audit view uses shared date formatting.

### F15 · `/admin` overview — four counters, no work — **High**
[`page.tsx`](frontend/src/app/admin/page.tsx) renders Users / Drivers / Vehicles / Open fraud flags and nothing else. None is clickable. An ops lead opening this learns four numbers and must guess where the work is — while `/admin/approvals`, `/admin/driver-applications` and `/admin/fraud` all hold queues with real backlogs.
**Recommendation:** replace with a work-first surface: pending approvals by type, applications awaiting review, open fraud flags past SLA, batches awaiting a checker — each linking into the filtered queue. Keep the four counts as a secondary strip. **Alternative:** a personalised "assigned to me" queue (rejected — no assignment model exists; **requires usability validation** before building one). **Acceptance:** every number on the overview links to the list it counts; the top of the page answers "what needs me today".

### F16 · `/admin/billing` — same data, different treatment — **Medium**
[`page.tsx:32`](frontend/src/app/admin/billing/page.tsx:32) prints `{campaign.status}` with `tone="default"` — the `statusTone` map that the advertiser list uses is imported nowhere here. `limit: 100`, unpaginated, no search, no empty state. A per-row "Open billing" button where the row itself should navigate.
**Recommendation:** reuse the campaign status mapping; make the row the link; add pagination + search.

### F17 · `/admin/fraud` — the tool sits above the queue; four chips per card — **Medium**
The "Physical display checks" panel occupies the top of the page, pushing the actual flag queue below the fold. Each flag card carries a severity chip, a status chip, an escalation chip and a dispute chip. Evidence values truncate at 120 chars with the full value only in a `title` — hover-only, invisible to touch and keyboard.
**Recommendation:** flags first, spot-check tool in a secondary panel or behind an action; one status chip plus severity conveyed by card treatment; expandable evidence rather than a tooltip.

### F18 · `/admin/users` · `/admin/drivers` · `/admin/vehicles` — no detail view exists — **High**
None of the three tables links a row anywhere, and no detail route exists for any of them. The table *is* the record, so everything must fit in four columns — which is why status transitions became a bare-text "Actions" column. `/admin/drivers` and `/admin/vehicles` also have no filter of any kind.
**Recommendation:** add detail pages; make the row navigate; move lifecycle transitions to the detail page's status control, leaving the list to listing. This is the change that dissolves the whole "Action column" question rather than answering it. **Alternative:** keep the inline transition and add an overflow menu (rejected as the *primary* fix — it hides the action without giving the operator the context needed to decide). **Must not change:** approve/suspend must stay reachable in ≤ 2 clicks from the list. **Acceptance:** each entity has a detail route; the row navigates; the list has search.

### F19 · Row actions are colour-differentiated only at hover — **Medium (a11y)**
[`onboarding-menu.tsx:50-53`](frontend/src/app/admin/drivers/onboarding-menu.tsx:50), and identically in `user-status-menu`, `vehicle-status-menu`, `cancel-button`. At rest, **"Approve" and "Reject" are the same `text-muted`, the same size, 12px apart**; they diverge only on `hover:text-coral` / `hover:text-green`. Colour alone, and only on hover — invisible to keyboard and touch users, and to anyone with a colour-vision deficiency. Additionally `{pending ? "…" : s.label}` collapses **every** button in the row to "…" during a transition, destroying the accessible name mid-action.
**Recommendation:** give constructive and destructive actions distinct at-rest treatment (weight/border/icon + text), separate them, and scope the pending state to the invoked control. **Acceptance:** destructive vs constructive is distinguishable in greyscale, without hover; a pending action does not blank sibling labels.

### F20 · Confirmations don't identify the record — see S8 — **Medium**

---

## 4 · Advertiser findings

### F21 · `/advertiser/campaigns/[id]` — navigation dressed as actions; audit log above the campaign — **High**
[`page.tsx:118-136`](frontend/src/app/advertiser/campaigns/[campaignId]/page.tsx:118). Three emoji-prefixed pills — `📊 Campaign Performance Analysis`, `🔥 Coverage map`, `🗺 Zones · 4` — sit in the same top-right cluster as `StatusActions` (real state changes), styled identically to secondary buttons. They are *sub-pages*. `micro` uppercases the first into a very long shouted string, and the three labels don't share a naming convention. Page order then buries the campaign's own details and creatives beneath an immutable review-history panel showing full break-all SHA-256 hashes.
**Recommendation:** promote the three destinations to a tab row under the campaign title (Overview · Report · Map · Zones); drop the emoji; keep lifecycle actions alone in the header. Reorder: identity + status → details + creatives → performance → history last. **Alternative:** keep them as buttons but relabel (rejected — they navigate; tabs communicate that and preserve context). **Must not change:** all four views stay one click from the campaign. **Acceptance:** actions and navigation are visually distinct; review history is not above campaign details.

### F22 · `/advertiser/campaigns/[id]/report` — a dead end with a raw error code — **Critical**
[`measurement-authority.tsx:212-224`](frontend/src/app/advertiser/campaigns/[campaignId]/report/measurement-authority.tsx:212). When any integrity check fails, the **entire report is replaced** by a panel headed *"Fail-closed reporting state"* that prints the raw code `MEASUREMENT_RUN_INTEGRITY_FAILURE` in mono, with **no action, no retry, no support path, no way back**. The advertiser — a paying customer — sees an internal error taxonomy and a wall.
This is the correct *behaviour* (don't show unverified numbers) with the wrong *presentation*.
**Recommendation:** keep the fail-closed logic; replace the presentation with plain language ("Your latest results are being re-verified. We'll email you when they're ready."), a link back to the campaign, and a support path. Keep the code in a copyable "Reference" line for support, not as the headline. **Alternative:** show stale results with a warning (rejected — contradicts the deliberate integrity guarantee). **Must not change:** no unverified figures are ever rendered. **A11y:** `role="status"` is too weak for a page-level replacement — use `role="alert"` or move focus. **Acceptance:** every fail-closed state offers a next step and a return path; no bare error code is the most prominent element.

### F23 · report — evidence artefacts and raw units — **Medium**
`{metric.active_tracking_seconds}s` prints raw seconds while the file imports four other formatters and `formatDuration` exists ([measurement-authority.tsx:139](frontend/src/app/advertiser/campaigns/[campaignId]/report/measurement-authority.tsx:139)). Footer carries `Run {run.id}` plus three hash prefixes. A `StatusChip` reads `reproducible`. A synthetic-ROI chip labelled *"synthetic test-only result"* can render beside a real percentage.
**Recommendation:** `formatDuration`; hashes behind one "Verification" disclosure; drop the `reproducible` chip (it's the default, not news).

### F24 · `/advertiser/campaigns/new` — the review step shows unformatted values — **High**
[`wizard.tsx:381-402`](frontend/src/app/advertiser/campaigns/new/wizard.tsx:381). The confirm-before-submit step renders `${currency} ${values.basics.budget_amount}` → **"NGN 5000000"**, and the window as raw `datetime-local` strings → **"2026-09-02T14:00 → 2026-09-30T23:00"**. This is the one screen where formatting carries the most weight — it is the last check before a budget commitment — and it is the only screen that skips it.
**Recommendation:** run review values through `formatMoney` / `formatDateRange`. **Acceptance:** the review step and the created campaign's detail page display identical strings.

### F25 · wizard — internal phase names, DS bypass, no step back-navigation — **Medium**
`` `${phase}…` `` surfaces `hashing…` / `uploading…` / `scanning…` verbatim ([wizard.tsx:344](frontend/src/app/advertiser/campaigns/new/wizard.tsx:344)). Completed stepper items are non-interactive `<span>`s — no jumping back to Basics from Review. Labels/inputs/errors are re-implemented locally rather than using `components/ui/field.tsx`. "Creatives are optional" is disclosed *after* the Add button, at the bottom. Required-field marking is an unexplained `*` used on two of six fields.
**Recommendation:** human phase copy ("Checking the file…"); make completed steps clickable; use `Field`; state optionality at the top of the step; add a required-field convention.

### F26 · `/advertiser/billing` — bank reference as the headline; unbounded page — **High**
[`page.tsx:52`](frontend/src/app/advertiser/billing/page.tsx:52). Each receipt's most prominent element is `external_transaction_id` in mono. The advertiser wants amount, date, and which campaign — the transaction reference is a support artefact. Below the receipts, a `CommercialHistory` panel renders **per campaign, for up to 100 campaigns, each fetched in its own request** (lines 22-30) — an unbounded, unpaginated page with 100+ round trips per load. Unapplied receipts read *"Unapplied — does not authorize production."* The header action "Billing details" links to `/advertiser/company` — the same destination the sidebar calls "Company".
**Recommendation:** amount + campaign lead, reference secondary; paginate or scope commercial history to a selected campaign; one name for `/advertiser/company`.

### F27 · `/advertiser` overview — no afternoon, no next action — **Medium**
[`page.tsx:29`](frontend/src/app/advertiser/page.tsx:29): `getHours() < 12 ? "Good morning" : "Good evening"` — an advertiser logging in at 2pm is greeted "Good evening", while the driver app at the same moment correctly says "Good afternoon" ([driver page.tsx:50](frontend/src/app/driver/(portal)/page.tsx:50)). Six stat tiles, no next action; two carry disclaimers longer than their labels ("Formula diagnostic, not a statistical confidence interval"; "Payout projection — not advertiser spend") duplicated verbatim on the campaign page.
**Recommendation:** share one greeting helper; add "campaigns needing your attention"; move recurring disclaimers to a single methodology link.

### F28 · campaigns list — hover implies row click, only the name is a link — **Low**
[`page.tsx:125-133`](frontend/src/app/advertiser/campaigns/page.tsx:125). `hover:bg-raised/50` on the `<tr>` signals a clickable row; only the name `<Link>` navigates. Make the whole row the target (keeping one real anchor for a11y).

---

## 5 · Driver PWA findings

### F29 · `/driver/earnings` — ten money tiles on a phone — **Critical**
[`page.tsx:84-108`](frontend/src/app/driver/(portal)/earnings/page.tsx:84). Batch-payable · Pending · Released · Available ledger · Cash paid · Paid ledger · Carried debt · Voided · Lifetime earned · Ledger entries. Five are tinted green. Five are near-synonyms with no definition anywhere on the page. This is the backend's chart of accounts rendered as a 2-column grid.
A driver has two questions: **how much am I getting, and when.** Neither is answerable here. Below it, a "Payout journey" panel reads *"Recent page: 3 held · 2 other pending · 5 released · 1 paid"* — leaking pagination into a summary — beside a decorative ₦ circle.
**Role:** driver, daily, on a phone, about their income. **Recommendation:** one hero figure (next payout + expected date), one secondary (pending, with what unblocks it), debt shown only when non-zero, everything else behind "Full breakdown". **Alternative:** keep all ten but group and label them (rejected — nine of ten are internal accounting states the driver cannot act on). **Must not change:** every figure stays retrievable; the ledger stays trip-traceable. **Acceptance:** a driver can state their next payout and its date within five seconds; no undefined financial term appears without an explanation.

### F30 · `/driver/assignments` — raw JSON and a SHA-256 on a driver's phone — **Critical**
[`page.tsx:197-272`](frontend/src/app/driver/(portal)/assignments/page.tsx:197). Each offer card carries: a "Frozen offer terms" grid of eight raw key-value pairs, the **full `offer_terms_sha256`**, a creative **checksum**, and a `<details>` labelled "View complete frozen snapshot" that dumps the entire terms object as 10px JSON.
And the rates — the only thing that matters in an offer — are unformatted: `Base: 1500/hr`, `Daily cap: 8h`. The single most important number in the product is printed as a bare integer.
**Recommendation:** the offer card shows what you earn (formatted), when, where, on which vehicle, and what's expected — nothing else. Terms verification moves behind one "Contract details" link; the JSON dump and hashes are removed from the driver surface entirely. **Must not change:** frozen terms remain viewable and legally accessible. **Acceptance:** no JSON, checksum, or hash on a driver screen; every money value is currency-formatted.

### F31 · `/driver/assignments` — counts that don't filter; decisions buried under history — **High**
Three tiles (Active / Offers / Completed) are static counters, not filters. Below them, up to 50 assignments render in one flat list with no grouping and no sort — **an offer awaiting a decision can sit below months of completed jobs.** Every card also carries a permanent compliance paragraph (S3), including completed ones.
**Recommendation:** make the three tiles the filter (default: anything needing action); group Offers → Active → History; show the status explanation only where a decision is pending. **Acceptance:** an offer requiring a decision is always in the first screenful.

### F32 · `/driver/assignments` — up to 50 sequential API calls before first paint — **High**
[`page.tsx:90-101`](frontend/src/app/driver/(portal)/assignments/page.tsx:90) fetches installation-evidence history per assignment. On a Lagos mobile connection this is the difference between a usable app and an abandoned one. Also, three separate early-return branches replace the *whole page* with near-identical "unavailable" panels, plus a fourth offline state — four distinct full-page dead ends for partial data failures.
**Recommendation:** a batch endpoint; degrade per-card rather than per-page. **Acceptance:** the assignments list renders with a bounded number of requests; a failure in one data source doesn't blank the list.

### F33 · `/driver` home — four doors to one room; a metric capped at 6 — **High**
`/driver/track` is linked four times on one screen: the live-trip banner, the journey panel's tracking step, the "Active campaign" link (which shows three different labels depending on state), and the tab bar. Meanwhile the "Trip entries" tile counts entries from a ledger call limited to **6** ([page.tsx:33,48](frontend/src/app/driver/(portal)/page.tsx:33)) — a driver with 200 trips sees "6". A KPI that silently caps is worse than no KPI.
**Recommendation:** one primary call-to-action per screen state; replace "Trip entries" with a real total or remove it.

### F34 · `/driver` home — a state-machine token as the driver's status — **Medium**
The "Standing" tile prints `READY` / `BLOCKED` / `PENDING` raw, sub-labelled *"server verified"* / *"not work-ready"*, at `text-sm` while its two neighbours are `text-2xl` — a visibly broken 3-up grid. Map the tokens to sentences ("Ready to drive" / "Can't start yet — 1 step left") and size the tiles consistently.

### F35 · `/driver/capabilities` — an engineering diagnostic shipped in the production PWA — **High**
[`capability-probe.tsx:230-289`](frontend/src/app/driver/(portal)/capabilities/capability-probe.tsx:230). A live authenticated driver route headed *"Production PWA capability probe"*, eyebrowed with the internal work-package id **"R14-A · contract …"**, offering buttons like **"Test BFF session"**, printing raw status codes in mono, a `<pre>` report dump, and a note that *"Physical Android/iPhone journeys… are still required post-build before real pilot use."* It uses bare `rounded border` markup — no `Panel`, no `Button`, no tokens — confirming it was never intended as product UI.
**Recommendation:** gate behind an internal role or a build flag, or move to a `/internal` route outside the driver shell. **See §12** — this may be intentional pilot instrumentation. **Acceptance:** no production driver session can reach a screen containing an internal work-package identifier.

### F36 · `/apply` — the recruitment page's headline is a negation — **High**
Covered in S3. This is the top of the driver acquisition funnel; its primary panel heading is *"Application receipt is not work approval"* and its closing line enumerates five things the form does **not** grant. **Recommendation:** lead with what happens next and how long it takes; keep one clear disclosure. **Acceptance:** the primary heading describes the applicant's next step.

---

## 6 · Navigation and information-architecture findings

### F37 · No sign-out on mobile for admin and advertiser — **High**
[`app-shell.tsx:41,57`](frontend/src/components/shell/app-shell.tsx:41). The user block — name, role, **Sign out** — lives in `<aside className="hidden … md:flex">`. The mobile header renders only the logo, notifications, and a static word. Below 768px, **admin and advertiser users cannot sign out.** (The driver PWA has its own logout button and is unaffected.)
**Recommendation:** an account control in the mobile topbar containing identity, sign out, and change password. **Acceptance:** sign-out is reachable at 375px in every role.

### F38 · `/change-password` and `/driver/change-password` are orphan routes — **Medium**
Grep finds no link to either from anywhere in the app. Both exist and work; both are reachable only by typing the URL. Fold into the account control from F37.

### F39 · Admin sidebar: 13 flat items, no grouping — **Medium**
Overview, Users, Drivers, Driver applications, Vehicles, Assignments, Approvals, Planning sources, Fraud, Payouts, Billing, Audit, Traffic. Backend boundaries, not tasks: two review queues sit apart (Approvals, Driver applications); Payouts hides three children (F12); "Traffic" means analytics assumptions, not road traffic; "Planning sources" doesn't match its own page title (F13).
**Recommendation:** group under three or four headings — e.g. *Review* (Approvals, Applications, Fraud) · *Fleet* (Drivers, Vehicles, Assignments, Users) · *Money* (Payouts + children, Billing) · *System* (Audit, Traffic, Planning sources). Rename "Traffic" to what it configures. **Alternative:** flat list with dividers (acceptable, cheaper). **Acceptance:** no group exceeds five items; every label survives being read aloud to a new operator.

### F40 · Breadcrumbs exist on four pages and are hand-rolled four times — **Low**
Present on payouts/batches, payouts/rules, payouts/corrections, campaign detail, campaign report — absent from every other nested page (`/admin/users/new`, `/admin/vehicles/new`, `/admin/billing/[id]`, `/advertiser/campaigns/[id]/map|zones`). One inline instance omits the hover class the others have. Extract a `Breadcrumb` component; apply to every nested route.

### F41 · Topbar carries a decorative label — **Low**
[`app-shell.tsx:88`](frontend/src/components/shell/app-shell.tsx:88): `<span aria-label="Workspace context">Workspace</span>` — a static word that does nothing, plus an `aria-label` on a non-interactive element restating its own text. Remove; give the space to the account control (F37).

### F42 · Notification centre — bookkeeping without destinations, and a flickering badge — **Medium**
[`notification-center.tsx:184-190`](frontend/src/components/notifications/notification-center.tsx:184). Notifications carry no link to the thing they're about, so the only available action is per-row **"Mark read"** — a repeated bookkeeping button on every unread row. Worse: `unread` and `showNotifications` are both forced empty while `isFetching`, and the count refetches every 45 s — **the badge disappears and the open list goes blank on every poll.** Advertiser email preferences are buried in this transient popover (with a hard-coded `ORGANIZATION DELIVERY PREFERENCES` string inside a class that already uppercases), and toggling gives no success feedback. Also three dead `hover:text-fg` classes (`text-fg` is not a defined token) here and in `report-issuance-panel`.
**Recommendation:** make notifications navigable (opening marks read); keep previous data during background refetch; move preferences to Company settings; confirm preference saves; fix or remove `text-fg`.

### F43 · Cross-module workflow requires remembering an id — **Medium**
Approving installation evidence at `/admin/approvals` shows `assignment_id` and `vehicle_id` as UUIDs. To learn which vehicle it is, the reviewer must copy the UUID and search `/admin/vehicles` — which has no search (S4). The workflow is, in practice, not completable within the product. Resolved jointly by S1 + S4 + F18.

---

## 7 · Reusable design-system corrections

| # | Correction | Evidence | Sev |
|---|---|---|---|
| D1 | `StatusChip` accepts only mapped `{label, tone}`; one map per domain | S2 | High |
| D2 | Replace 11 hand-rolled `bg-amber text-bg` buttons with `<Button>` | S6, contrast table | High |
| D3 | `PageHeader` gains a `primaryAction` slot so pages stop hand-rolling it | 5 duplicate copies | Medium |
| D4 | One `<DataTable>` wrapper: `overflow-x-auto`, `micro` headers, row-link, empty state | F10, F44 | High |
| D5 | One `ConfirmDialog` with record name + optional reason field; ban `window.*` | S8 | High |
| D6 | `EntityRef` component: name primary, id copyable, never bare | S1 | Critical |
| D7 | `Breadcrumb` component; apply to all nested routes | F40 | Low |
| D8 | Styled `Checkbox` + `Select` primitives (currently browser-default in a dark UI) | driver-applications, notifications | Medium |
| D9 | `micro` restricted to ≤ 4 words; add `text-xs` prose convention | S5 | Medium |
| D10 | Route all durations/money/dates through `lib/format`; remove inline `toLocaleString` and raw `{seconds}s` | audit, assignments, measurement-authority | Medium |
| D11 | Unify table header treatment (`micro text-muted`) — audit + planning-sources diverge | F44 | Low |
| D12 | Fix heading levels: approvals renders card titles as `h2` in one section and `h3` in another under the same `h2` | approvals:153 vs 225 | Low |

---

## 8 · Quick wins (each ≤ ~1 hour, no design decisions)

1. Add `overflow-x-auto` to the batches table — **restores an unreachable financial control** (F10).
2. Fix the pending label so it lands on the clicked button (F5).
3. `formatDuration` for `active_tracking_seconds` and `observed_seconds` (F23, F8).
4. Format the wizard's review step through `formatMoney` / `formatDateRange` (F24).
5. Add the afternoon branch to the advertiser greeting (F27).
6. Remove the `Workspace` span (F41).
7. Fix or remove the three dead `hover:text-fg` classes (F42).
8. Replace the eleven hand-rolled buttons with `<Button>` — closes the hi-vis contrast failure (D2).
9. Add `<label>`s to the two audit filter inputs — WCAG 4.1.2 (F14).
10. Add record names to the seven anonymous confirmations (S8).
11. Delete the `<pre>` JSON dump from the driver's offer card (F30).
12. Keep notification data during background refetch — stops the badge flicker (F42).
13. Align the "Planning sources" nav label with its page title (F13).
14. Apply `statusTone` on `/admin/billing` — the map is already written (F16).

---

## 9 · Structural improvements

| # | Change | Unblocks |
|---|---|---|
| ST1 | Detail pages for user / driver / vehicle / assignment; rows navigate; lifecycle actions move there | F18, F8, F19, S1 |
| ST2 | Split approvals into four paginated queues | F1 — currently unreachable work |
| ST3 | Driver-application review as a full-width page, not a table cell | F6, F7 |
| ST4 | Server-side search on the four entity lists | S4, F43 |
| ST5 | Rewrite the driver earnings screen around "how much, when" | F29 |
| ST6 | Driver offer card carries terms in human form; evidence relocated | F30 |
| ST7 | Turn `/admin` overview into a work queue | F15 |
| ST8 | Copy pass: state + next action first, disclosure second | S3, F22, F36 |
| ST9 | Payouts sub-navigation; admin sidebar grouping | F12, F39 |
| ST10 | Account control in the mobile topbar (sign out + change password) | F37, F38 |
| ST11 | Batch the driver installation-evidence fetch; degrade per-card | F32 |

---

## 10 · Requires usability validation (do **not** implement on my say-so)

- **Whether the row action should become an overflow menu.** I deliberately did not recommend this. With detail pages in place (ST1), inline transitions may be right to keep — approve/suspend on the drivers queue is plausibly high-frequency. Measure frequency before hiding it. What is *not* in question: the current at-rest colour-only, hover-only differentiation is wrong regardless (F19).
- **How many earnings figures a driver actually wants.** Ten is clearly wrong; whether the right answer is one, two, or four needs five driver interviews, not a designer's judgement.
- **Whether ops wants merged or per-type approval queues.** I recommend per-type on evidence-shape grounds; the operators who work the queue daily should confirm.
- **Whether the counter tiles should become filters** on driver assignments and admin overview. Reasonable, unvalidated.
- **The `micro` uppercase-mono label treatment** as a brand device. It is a legitimate aesthetic choice; my objection is scoped strictly to its use for full sentences (S5), which is a legibility fact, not a taste claim.
- **Which of the nine candidate themes ships.** Out of scope for this audit; noted only because the contrast finding (S6) is theme-dependent.

---

## 11 · Priority-ranked remediation backlog

| Rank | Item | Sev | Effort | Rationale |
|---|---|---|---|---|
| 1 | F10 batches overflow | High | XS | A financial control is unreachable on small screens. One line. |
| 2 | F1 approvals pagination | Critical | M | Pending work is currently unreachable — a correctness failure, not a UX one. |
| 3 | S1 / D6 human identity | Critical | L | Blocks the core ops task everywhere; also shrinks table widths. |
| 4 | F22 report fail-closed state | Critical | S | A paying customer hits a dead end showing an internal error code. |
| 5 | F30 driver offer card | Critical | M | JSON + hashes + unformatted rates on the highest-frequency surface. |
| 6 | F29 driver earnings | Critical | M | Ten tiles; the driver's core question is unanswerable. |
| 7 | F6 / F7 application review | Critical | L | Identity + bank decisions inside a 1500px cell with a pre-filled reject reason. |
| 8 | S8 / D5 confirmations | High | S | Audited destructive actions confirmed without naming the record. |
| 9 | F37 mobile sign-out | High | S | Functional gap; also a security expectation. |
| 10 | S6 / D2 button consolidation | High | S | Closes a measured AA contrast failure. |
| 11 | F8 assignments table | Critical | M | The archetypal "database screen"; JSON in a table cell. |
| 12 | S4 search | High | M | 14 tables with no way to find a record. |
| 13 | S3 / ST8 copy pass | High | M | The dominant "AI-generated" signal; touches every surface. |
| 14 | F12 / F39 navigation | High | S | Three modules reachable only from a footnote. |
| 15 | F32 driver N+1 | High | M | 50 sequential calls before first paint on mobile. |
| 16 | F18 / ST1 detail pages | High | L | Dissolves the action-column question rather than answering it. |
| 17 | F2 installation photos | High | M | An evidence screen that doesn't show evidence; popup-blocker risk. |
| 18 | F15 admin overview | High | M | Four numbers where a work queue belongs. |
| 19 | S2 / D1 status mapping | High | M | Raw enums in 9 of 10 domains. |
| 20 | F35 capability probe | High | XS | Internal diagnostic in a production driver session — pending §12. |
| 21 | F26 billing composition | High | M | Bank ref as headline; 100 requests per load. |
| 22 | F24 wizard review step | High | XS | Unformatted money on the final confirmation. |
| 23 | F19 action affordance | Med | S | Colour-only, hover-only destructive differentiation. |
| 24 | F42 notifications | Med | M | Flickering badge; bookkeeping-only actions. |
| 25 | F14 audit filters | Med | S | Unlabelled inputs (WCAG 4.1.2); no date range. |
| 26 | F13 planning sources | Med | S | Nav label ≠ title; four opaque columns. |
| 27 | S5 / D9 `micro` scope | Med | S | Legibility. |
| 28 | F21 campaign header | High | S | Navigation dressed as actions; emoji labels. |
| 29 | D4 DataTable | High | M | Prevents recurrence of F10 and F44. |
| 30 | Remainder (F3-F5, F16, F17, F23, F25, F27, F28, F34, F38, F40, F41, F43, D7-D12) | Low-Med | S each | Cleanup. |

---

## 12 · Owner decisions required

Three items are genuine product decisions, not defects I should resolve:

1. **Is the compliance/negation voice (S3) legally mandated?** If Nigerian regulatory or investor commitments require these exact disclosures, the remediation changes from *rewrite* to *relocate* — same words, moved out of headline position into a single per-screen disclosure. If it is not mandated, it should be rewritten. This decision gates ST8, the largest copy workstream.

2. **Is `/driver/capabilities` (F35) intentional pilot instrumentation?** If field engineers need drivers to run probes on real devices during the pilot, it stays — but should be gated and relabelled. If it is leftover build tooling, it should leave the production bundle. I can't infer intent from the code.

3. **Should evidence artefacts be advertiser-visible at all?** Snapshot hashes, run IDs and "reproducible" chips may be a deliberate trust-differentiating feature for an unfamiliar measurement product. My recommendation (relocate behind a "Verification" disclosure) preserves the claim while removing the noise — but if hash-visibility is a positioning commitment, that changes the treatment.

Everything else in this report is remediable without an owner decision.

**No files were edited, staged, or committed; no tests were run.**
