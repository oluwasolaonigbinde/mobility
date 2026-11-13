# Cardvert audit findings

Reports supplied by the owner, preserved verbatim below in report order. Scope and outstanding-work statements belong to each original report. This compilation does not independently verify findings or implement fixes.

---

Here is the report as it stands. Only the money-in area is complete and verified by me. The money-out, backend access, and frontend/links/logs audits are still running and are not included; treat those areas as unaudited, not clean.

## Cardvert audit at 75c4cbaa, partial report

**Scope covered:** advertiser invoices, VAT, funding receipts and allocations, manual transfers, invoice corrections, cancellation and refund settlement, budget "Booked"/alerts/pause/resume, advertiser and admin billing screens. Online checkout was skipped as a known gap. **Not yet covered:** driver pay, corrections, overpayment recovery, payment runs, closeout, and all access-control work.

### Findings, ranked

**1. Medium. Cancellation treats reversed (bounced) receipts as refundable cash.**
- `app/services/campaign_cancellations.py:73` (`_cash_remaining_for_terms`) sums every `ReceiptAllocation` for the terms with no receipt-lifecycle filter, minus recorded refunds. `app/services/billing/settlements.py:179` (`_historical_fully_funded_at`) walks all allocations the same way.
- Everywhere else funding means confirmed and not reversed: `app/services/billing/queries.py:145` (`_active_receipt_predicate`), `app/services/billing/invoices.py:393`, authority checks.
- Steps: admin records and allocates a ₦100k manual transfer to an issued invoice. The transfer bounces, so admin reverses the receipt via `POST /admin/receipts/{id}/reverse`. Within 24 hours of the original allocation, staff cancel the campaign.
- What happens: the immutable cancellation freezes `disposition = cash_refund_due`, `refundable_amount = 100,000` (`campaign_cancellations.py:187-198`) although Cardvert holds nothing. `record_refund_settlement` then accepts a refund record up to ₦100k because its guards only require a reversed receipt and an existing allocation (`settlements.py:353-370`), and the three caps are all satisfied. Finance can record a refund of money never received.
- Should happen: refundable cash should be the active-receipt basis, so the cancellation shows `cash_refund_not_due` and no refund can be recorded.
- Smallest fix: in `_cash_remaining_for_terms` sum `_active_cash_allocations(...)` instead of the raw sum, and reuse it in `_historical_fully_funded_at`. The intended cancel, then reverse, then refund order still works because cancellation freezes the amount before the reversal.
- Disproof: `reverse_payment_receipt` (`receipts.py:487`) records no reversal kind and no settlement; `tests/test_campaign_cancellations.py:150-205` only cover cancel before reverse. Nothing blocks the sequence.

**2. Low. A credit note can push the obligation below cash already paid, and the overpayment is invisible.**
- `settlements.py:135-143` bounds credit notes only by `credits + gross > invoice.gross + debits`; funded cash is ignored.
- Steps: invoice ₦100k fully paid. Admin posts a ₦30k credit note via `POST /admin/invoices/{id}/corrections`.
- What happens: obligation becomes ₦70k with ₦100k funded. `invoice_payment_status` (`invoices.py:413-419`) returns "paid"; the advertiser's amount-left-to-pay clamps at zero (`frontend/src/lib/billing/history.ts:12`). The ₦30k owed back is shown nowhere and cannot be refunded, since refunds require a cancellation.
- Smallest fix: reject a credit note that would reduce the obligation below active confirmed funding, or expose `overpaid = funded − obligation` on the invoice read and screens.
- Disproof: `tests/test_billing_corrections.py:197-240` and `test_billing_concurrency.py:44` only test credit before allocation.

**3. Low. Correction VAT is typed by staff, not derived from the invoice's stored rate.**
- `app/schemas/billing.py:375-380` takes `net_amount` and `tax_amount` freely; `settlements.py:71-73` only computes `gross = net + tax`. The admin form has two free fields (`frontend/src/app/admin/billing/[campaignId]/content.tsx:465-466`). The DB check (`app/models/billing.py:870-874`) only enforces the sum.
- Steps: post a debit note net ₦100,000 with VAT ₦0 or ₦7,500.01. It is accepted.
- What happens: the corrected invoice's "VAT 7.5%" line no longer equals 7.5% of net, breaking the client's invoice rule (Q28, D71). The original invoice computes VAT once on net correctly (`quotes.py:144`).
- Smallest fix: derive `tax_amount` server-side as `net × invoice.tax_rate` quantized HALF_UP, or reject mismatches.

**Noted, out of scope (online payments gap):** a stale `INITIALIZED` checkout intent whose amount no longer matches the balance blocks all new online checkouts with `PAYMENT_CHECKOUT_ALREADY_ACTIVE` (`checkout.py:102-150`) and has no expiry or supersede path. Paying the old link then over-collects, with the excess recorded only as an audit row (`gateway.py:384-408`). Worth fixing before Paystack goes live.

### Clean areas checked (money in)

- VAT and rounding: Decimal throughout, tax computed once on net with HALF_UP (`quotes.py:144`), `gross = net + tax` enforced by `ck_invoices_total_conservation`; per-unit lines cross-checked (`billing/common.py:196-203`); frontend percentage conversion uses exact BigInt arithmetic.
- Money only against an issued invoice (D139): `allocate_payment_receipt` locks the invoice and requires issued status (`receipts.py:360-363`); manual path pre-checks (`receipts.py:565-569`); gateway path cannot create a checkout for a non-issued invoice (`checkout.py:61-66`). No code sets `VOID`.
- Double-apply protection: unique `(receipt_id, commercial_terms_id)` and unique `external_transaction_id` (`app/models/billing.py:382-383`, 304); receipt row lock plus campaign advisory lock; exact-replay returns the existing row; per-receipt and per-obligation caps (`receipts.py:410-443`). Concurrency covered by `tests/test_billing_concurrency.py`.
- Receipt lifecycle append-only with unique `(receipt_id, status)`; reversal requires confirmed and is idempotent (`receipts.py:511-519`).
- Refund settlement: requires immutable `cash_refund_due` cancellation, reversed receipt, allocation, and three caps (`settlements.py:353-416`); unique external reference.
- 24-hour window and expedited waiver v2: boundary consistent between production start and refund eligibility; waiver unique per campaign.
- Budget (D104): pause strictly above 100% (`budget.py:100`), 80/95 on `>=`, agreed-price guard first, fixed lines included via invoice obligation, alerts deduped per epoch, resume needs admin, reason, changed funding fingerprint and booked at or below budget.
- Screen agreement: advertiser billing, invoice document, admin money list, admin campaign billing and campaign Booked all read the same `effective_obligation_amount`/`funded_amount` and `campaign_budget_used`, so no net/gross or corrected/uncorrected divergence. Booked is never summed across campaigns.
- Invoice numbering: advisory lock plus sequence row lock; synthetic issuer allowed only in local/test/staging.

### Uncertain

- Paystack webhook versus verify payloads may differ in `payer_name`/`paid_at`, which would raise `PAYMENT_EVENT_IDENTITY_CONFLICT` on the second ingest. No double count; needs live payload evidence.
- A draft campaign's budget can be lowered below the agreed price after quote acceptance (`campaigns.py:270-320`); the screen then shows Booked above budget while the state stays within budget. Consistent with D104 wording, so not reported as a bug.

### Still outstanding

Money out (driver pay, corrections, recovery, payment runs, closeout) and both access audits (backend routes and downloads; frontend routes, reusable links, PII in logs/exports/errors) have no results yet. If credits allow a follow-up, those three reports can be verified and appended.

---

Backend access report arrived. One quick verification pass on its two most material items, then I'll append.

The cited lines match. Here is the addendum to the report above; the backend access audit is now complete, with no Critical or High findings. Still outstanding: money out (driver pay, corrections, recovery, payment runs, closeout) and the frontend/links/logs audit.

## Addendum: backend access control (284 routes enumerated)

**Verdict:** every `/admin`, `/advertiser` and `/driver` route carries the matching role dependency, and the service layer scopes each parameterised read by organization or driver profile. No cross-tenant read, no driver personal data on advertiser routes, and no mass-assignment path was found. Four Low findings.

**4. Low. Invited drivers can sign in and work.** `app/api/v1/dependencies.py:117-118` and `app/services/auth.py:280-282` block only suspended/disabled users, and require ACTIVE only for admins. `app/schemas/users.py:17` lets an admin create a driver with any status. Steps: admin creates a driver with status `invited` and a password; the driver logs in, changes the password, and reaches assignments, trips, earnings and complaints, since the driver-profile lookup (`app/services/drivers.py:23-28`) has no status check. Meanwhile file uploads and KYC require ACTIVE (`stored_files.py:106-122`, `kyc.py:98-104`), so the layers disagree. Public applicants are not affected. Fix: require `status == ACTIVE` for every role in `get_current_user` and `login_with_password`.

**5. Low. Public application-status page exposes masked NIN and bank-verification state via a URL-path secret.** `GET /auth/driver-application-status/{reference}` (`app/api/v1/auth.py:513-534`) returns `masked_nin` and `bank_account_verified` (`auth.py:170-172`). The reference never expires while pending (`driver_applications.py:513-524`) and travels in the path, so it lands in browser history, proxy logs and Referer headers; the route sets no `no-store` or `Referrer-Policy` header. The signed-in driver surface strips `masked_nin` (`driver_documents.py:71,117`), so the anonymous page reveals more than the authenticated one. Fix: drop those two fields from the public envelope and add `Cache-Control: no-store`.

**6. Low. Campaign-create idempotency lookup is unscoped, giving a platform-wide campaign-ID existence oracle.** `app/services/campaigns.py:125` selects `Campaign.id == client_request_id` with no organization filter. A foreign ID returns 409 `CAMPAIGN_CREATE_IDEMPOTENCY_CONFLICT`; an unused ID returns 201. No data is returned or mutated. Fix: add `Campaign.organization_id == organization.id` to the lookup.

**7. Low, informational. Presigned download URLs are bearer URLs for their lifetime.** After a correct owner check and audit row, `stored_files.py:912-923` returns a provider-signed GET; nothing re-checks suspension or logout on fetch. The 60-second TTL (`config.py:192`) and `no-store` on the BFF redirect are adequate mitigations. Only a concern if the TTL is raised.

**Also noted (accepted risk):** any pending public applicant can resolve third-party bank account names via `POST /auth/driver-onboarding/account-name`, limited to 3 per application and 10 per IP per hour (`auth.py:116-150`, `config.py:159-162`).

**Clean areas verified by the worker (guards cited in the code):** token claims and session-version revocation; refresh capped to the original lifetime; one-time, expiring, session-bound password reset, advertiser invite and driver account-setup tokens; applicant capability routes scoped to the applicant's own user; campaign, creative, zone, change and file reads bound to `(id, organization_id)` or `(id, campaign_id)`; live map emits only delayed, shuffled, in-area coordinates; reports and heatmaps apply the three-car rule and contain no driver names, plates or IDs; advertiser financial reads omit driver liability; every driver assignment, trip, ping, evidence, vehicle, dispute and earnings route filters on the caller's own profile; complaints never reveal the counter-party; notifications filter on recipient; Paystack webhooks require a valid HMAC and dedupe on event ID; all request schemas use `extra="forbid"`, and no client schema accepts `organization_id`, `driver_id` or amounts.

**Uncertain:** admin free-text `notes` on assignments and activation-event metadata are returned to the owning driver; admin-typed quotation line-item dicts reach advertisers and could carry driver-pay figures by content, not by code; the must-change-password allow-list compares the exact path, untested behind a non-root proxy prefix.

---

Frontend/links/logs report arrived. Quick line check on its three Low items, then the addendum.

The cited lines match. Second addendum below; the frontend, reusable-link and logs audit is complete with no Critical or High findings. Only the money-out audit (driver pay, corrections, recovery, payment runs, closeout) is still outstanding.

## Addendum 2: frontend routes, reusable links, personal data in logs and exports

**Verdict:** the BFF forwards only the caller's own session token, every unsafe `/api/*` request passes an exact-origin mutation boundary, role layouts plus backend role checks stop cross-role rendering, and backend logs, Sentry, audit metadata, error envelopes and advertiser CSV/PDF exports are scrubbed or fixed-text. Three Low findings.

**8. Low. Password-reset and driver account-setup links carry the one-time token in the query string, unlike invites and application links which use the fragment.**
- `app/services/email_delivery.py:294-302` builds `?token=` for reset; `:381-384` for account setup. Invites (`:290-293`) and application links (`:341-342`) use `#token=`, which D130/D149 require.
- `frontend/src/app/reset-password/page.tsx:13-14` and `driver-account-setup/page.tsx:16-17` read the token from `searchParams`.
- What happens: the live token sits in browser history, sync, and any intermediary that records full URLs. Mitigations keep it Low: single-use, 30-minute or 24-hour expiry, session-version binding, `no-referrer` on both pages, Caddy logs only the path, and frontend Sentry scrubs `?token=`.
- Fix: emit `#token=` for both links and reuse the fragment-capture pattern in `frontend/src/lib/auth/invite-link.ts`.

**9. Low. BFF dynamic-segment routes relay unvalidated path ids to the backend.**
- Example `frontend/src/app/api/driver/files/[fileId]/route.ts:5-11`; same pattern in the advertiser files, notifications read, admin installation-review, onboarding upload/status, driver installation-evidence, vehicle documents, report re-run and report download handlers.
- An encoded slash in the segment is decoded by uvicorn before routing, so a browser can target any backend GET under the same prefix with its own bearer. The backend still authorises every route and rejects non-UUID params, so no cross-user access results; this is a defence-in-depth gap against architecture §8.2.
- Fix: a UUID shape check returning 404, as already done in the artwork, QR, job-artwork and Paystack-return routes.
- Uncertain: depends on Next 16.4 decoding `%2F` inside a segment; node_modules were not installed to confirm.

**10. Low. Two pages render arbitrary query-string text as an application error banner.**
- `frontend/src/app/advertiser/account/page.tsx:36-38` and `admin/billing/[campaignId]/content.tsx:109` print `notice.error` verbatim from the URL. A crafted link shows attacker-chosen text styled as a Cardvert alert. React escaping and CSP prevent script injection.
- Fix: pass an error code and map it to fixed text, as the campaign and billing pages do.

**Clean areas verified by the worker:** httpOnly, SameSite=Lax, secure session cookie; refresh on GET cannot revive a revoked or capped session; logout bumps the session version, invalidating bearers and outstanding reset/invite tokens; mutation boundary requires exact origin, consistent Fetch Metadata and JSON content-type, failing closed without a configured origin; no service or admin token exists in frontend code; open redirects blocked on login return, Paystack return and QR redirect; file streaming uses 60-second presigned URLs with `private, no-store` and type/size caps; all reusable links (reset, invite, account setup, application continuation) are HMAC tokens stored hashed, compared in constant time, time-limited, and bound to the user and session version; backend logging scrubs messages, exceptions and extras, Sentry sends no PII or bodies, validation errors never echo input, audit metadata is redacted on write and read, emails interpolate only campaign name and report kind, and advertiser exports contain no driver name, phone, plate, driver ID, trip ID or coordinates. No admin CSV export endpoint exists.

**Uncertain or accepted:** application continuation links are deliberately reusable for 24 hours until renewed or the application leaves pending, so a forwarded email lets someone else submit documents for that application; the frontend Sentry scrubber redacts URLs, tokens and GPS but not free-text emails or names, though no code path was found that puts them in an error; the advertiser artwork route fetches the backend-supplied storage URL without the scheme check the driver route applies.

## Consolidated ranking so far

| # | Severity | Finding |
|---|---|---|
| 1 | Medium | Cancellation counts reversed receipts as refundable cash |
| 2 | Low | Credit note can drop obligation below funded cash; overpayment invisible |
| 3 | Low | Correction VAT typed freely, not derived from invoice rate |
| 4 | Low | Invited drivers can sign in and work |
| 5 | Low | Public application-status page exposes masked NIN via URL-path secret |
| 6 | Low | Unscoped campaign-create idempotency lookup is an ID existence oracle |
| 7 | Low | Presigned download URLs reusable until 60-second expiry |
| 8 | Low | Reset and account-setup tokens in query string |
| 9 | Low | BFF relays unvalidated path ids |
| 10 | Low | Query-string text rendered as error banner |

Money out remains unaudited; if that report arrives it will be verified and appended the same way.

---

No reviewer results have arrived yet, so this is an interim report from my own direct reading only. Everything below is proven from the code at commit 75c4cbaa. Nothing was edited, committed, pushed or sent outside.

**Interim audit report, Cardvert at 75c4cbaa (read-only)**

**Findings so far: none confirmed.** I have not yet proven a defect in the paths I read. The three delegated reviews (failure paths, driver app, data layer) were still running when you asked for this, so their results are not included and must not be assumed.

**Clean areas verified directly**

- **Double-tap Start cannot create two trips.** Beyond the Python check at app/services/trips.py:245 and 257, the database enforces it with partial unique indexes on active trips per driver and per vehicle at app/models/trip.py:124 and 130. The start path also takes campaign, assignment, profile and vehicle row locks in one fixed order at app/services/trips.py:329 to 351, so two concurrent starts serialise instead of both succeeding.
- **Retried End is safe.** End locks the trip row with FOR UPDATE at app/services/trips.py:543 and returns a typed 409 TRIP_ALREADY_ENDED at line 551 if the status is no longer active. A second End after a timeout cannot re-end or re-seal.
- **Resent ping batches are deduplicated.** The unique constraint on trip plus idempotency key at app/models/trip.py:244, and the receipt replay comment at app/api/v1/trips.py:142, mean a batch resent after a lost response returns the same signed receipt with a duplicate flag rather than double-counting pings. A sequence-manifest uniqueness index follows at line 250.
- **Money chain is only opened after commit.** In app/api/v1/trips.py:164, 229 and 273 the trip-processing job is enqueued only after the session commits, and the router comment states the sweep is the guaranteed path, so a lost enqueue cannot strand a sealed trip and a failed commit cannot start processing.
- **Migration chain is linear and complete.** All 16 revisions from 0106_development_baseline to 0121_payout_recovery_offsets chain by exact down_revision with no branches or gaps.
- **Demo seed guards and dedups.** The seed refuses to run outside local or test without ALLOW_DEMO_SEED at app/seeds/demo.py:145, and ping batches are versioned by idempotency key at line 1206 and checked before insert at 1215, so reruns do not duplicate them.
- **Trip status is constrained at the database.** A check constraint restricts status to active, ended or sealed at app/models/trip.py:47, with further check constraints on the session and batch tables through line 240.

**Not yet covered**
Payout batches, corrections and disbursement concurrency, staff double-approval races, upload and scan state machines, session expiry mid-form, the frontend tracker's offline queue and restart recovery, GPS edge cases, pay computation across midnight and after auto-end, remaining database constraints, migration behaviour on an empty database beyond chain linearity, and seed data consistency with the client rules. Email, map key, online payments and hosting were skipped as instructed.

**What happens next**
The three reviewers are still running in this session. When their reports arrive I will verify each claimed finding against the code before adding it. If the session ends first, rerunning the same three-area brief is the fastest way to pick up where this stopped.

---

I'll survey the repo structure, the governing docs, git history, and test/CI health, then give you an assessment.

Ruff found one lint error on the current head. I'm now checking what it is, the type-check baseline, test collection, the frontend checks, and master's CI status on GitHub.

Backend checks are green locally. Frontend dependencies finished installing, so I'm running the frontend lint, type check and unit tests now, then I'll write up the assessment.

Here is my read of the codebase as of master `75c4cba` (your branch is identical to master, nothing uncommitted).

## Health: green and verifiable

Everything I could run locally passes, and the last master CI run is green.

| Check | Result |
| --- | --- |
| Backend lint (ruff, CI's version) | clean |
| Backend types (basedpyright vs baseline) | 0 errors, baseline stale by 17 resolved entries |
| Backend tests | 3696 collected, 92 DB-free ones run and pass; the rest need Postgres/Redis/MinIO |
| Frontend typecheck | clean |
| Frontend lint | 0 errors, 3 hook warnings |
| Frontend unit tests | 2196 passed in 259 files |
| Coverage receipt (global) | 93% line, 82% branch |
| Last 8 master CI runs | 5 green, 3 red; the newest needed a second attempt |

Shape of the thing:

| Area | Size |
| --- | --- |
| Backend Python | ~86k lines, 283 endpoints, 89 services, 39 model modules |
| Backend tests | ~118k lines, more than the app itself |
| Frontend TS/TSX | ~96k lines in 668 files |
| Docs plus issues | ~78k lines of Markdown, 294 requests, 158 decision rows |

## What stands out

- **Engineering is effectively done. The client is the bottleneck.** The controller is paused on the payment provider, and every remaining launch gate is external: Paystack activation, domain, OPay details, invoice format, legal pack, physical devices. There are 18 requests marked NEEDS ANSWER, nearly all client-side. Three weeks of commits are preview polish, wording and receipt refreshes. That is a holding pattern, not a build.

- **The governance apparatus now outweighs the product.** Required reading before any edit is roughly 7k lines across five docs, and architecture alone is 4.3k lines. Each change pays a tax in request rows, D-rows, topic history and receipts. That discipline earned the clean money and privacy paths, but at this stage it is the main cost of every small fix.

- **The request ledger has probably drifted.** Twenty-four requests sit IN PROGRESS, and most of them date from 18 to 20 October (the REQ-181 to REQ-197 audit batch). The architecture marks that batch's decisions as built, yet none of those topics carry a "Built in" line. Either they are unfinished or they were closed without the bookkeeping. Worth a one-pass reconciliation.

- **CI is heavy and a little fragile.** Six backend shards each spin up real MinIO, ClamAV, Caddy and Playwright, with skips treated as failures. That gives strong evidence but also explains the red runs and reruns on master. The receipt-reuse rules in D33 and D135 exist to avoid rerunning it, which is itself a signal.

- **Money logic is concentrated in a few very large files.** Disbursements is 2.7k lines, campaign assignments 2.3k, automatic payouts 1.6k. Ruff's complexity gate is on, but 53 functions carry a complexity waiver. Correct today, expensive to review tomorrow.

- **Toolchain pin gap.** Ruff floats at any 0.x in both CI and dev. My system ruff was one minor version behind CI's and flagged an import-order error that CI's version does not. A future ruff release can break CI with no code change. Pin it like basedpyright is pinned.

- **Repo hygiene is loose at the root.** The root holds a 1MB OpenAPI snapshot, a 53KB architecture review, a money-path review, two issue files and a `.codex` delivery folder. Twelve megabytes of seed photos live inside the shipped app package. Six migrations were squashed to a development baseline, which fits the no-users policy.

## Recommendation

Spend the waiting time on three cheap wins rather than more preview polish: pin ruff, prune the basedpyright baseline, and reconcile the stale IN PROGRESS rows. Then stop. The next real work is unblocked only by client answers, and the repository already says so clearly.
I'll ground this in a few more numbers first: where CI time goes, and what the slowest tests are.

Here is what I would change, in the order I'd do it. Nothing below needs a client answer.

## Quick wins, under a day each

- **Pin ruff.** Both CI and the dev extra accept any 0.x release, so a ruff update can turn CI red with no code change. Pin it the way basedpyright already is, and bump deliberately.
- **Prune the basedpyright baseline.** It carries 17 entries for errors that no longer exist. One run without discard mode fixes it.
- **Reconcile the request ledger.** Twenty-four rows sit IN PROGRESS, mostly the October audit batch from REQ-181 to REQ-197, with no "Built in" lines on their topics even though architecture marks that batch built. Close what shipped, re-open what didn't. Right now the register you tell every agent to trust first is the least trustworthy file.
- **Move the seed photos out of the shipped package.** Five PNGs totalling about 12MB live under the app package, so every wheel and image carries them. Point the seed at a non-packaged folder or downscale them. The demo does not need 2.5MB per side view.
- **Tidy the root.** The money-path review, the architecture review, the two issue files and the `.codex` delivery folder are all historical evidence. Move them under the archive folder so the root reads as a codebase, not a case file.

## CI: cut the wall clock and the reruns

The backend suite costs roughly 8,300 seconds of test time split over six shards, so each shard runs about 23 minutes before setup. One file, the demo seed test, takes nearly 700 seconds on its own. Three of the last eight master runs went red and the newest needed a second attempt.

- **Split or speed up the demo seed test.** At 696 seconds it is three times slower than the next file and it pins the critical path of whichever shard holds it. Seeding once per module instead of per test, or splitting its scenarios, would likely halve the longest shard.
- **Raise the shard count or rebalance by duration.** The durations file already exists, so moving to eight shards is a one-line change that brings each to around 17 minutes.
- **Start MinIO, ClamAV and Caddy only on the shards that need them.** ClamAV is already conditional. MinIO is started unconditionally for all six shards. Make it conditional too.
- **Treat the reruns as a defect.** Find what failed on attempt one of the latest master run and fix the flake rather than re-running. Under the integration authority rule a flaky skip is a failure, so flakes cost a full 30-minute cycle every time.

## Process: lower the per-change tax

- **Shrink the required reading.** The pre-edit reading list is about 7k lines. Architecture alone has 36 sections, 94 of them tagged built and 23 still target. I would split it into a current design document and an archived decision history, and have the root rules point small changes at only the touched section.
- **Stop writing receipt commits by hand.** Coverage refreshes and D33 receipts are a recurring commit type with their own rules in D33 and D135. A CI job that uploads the receipt as an artifact, which a human then approves, would remove a whole class of bookkeeping commits and the SHA-circularity rules that come with them.
- **Collapse the parked lists.** The to-do file, the issues file and the NEEDS ANSWER rows describe the same external blockers three ways. One list, owned by the request register, is enough.

## Code: reduce review surface in the money path

- **Split the three largest money services.** Disbursements at 2.7k lines, campaign assignments at 2.3k and automatic payouts at 1.6k each hold several concerns. Pulling out the state-machine transitions, provider adapters and reporting reads into separate modules would make the 53 complexity waivers mostly disappear rather than need justification.
- **Reserve the waiver for real cases.** Fifty-three functions carry a complexity override. After the split, I would require each remaining one to name the reason in the comment, and fail the lint otherwise.
- **Fix the three React hook warnings.** They are stale-ref cleanup warnings, which are exactly the kind that become real bugs under concurrent rendering.

## What I would not touch

The integration-authority test model, the provider-neutral adapters, the frozen OpenAPI contract check and the delivery gates on money and privacy are all working and are why the codebase is clean. The goal above is to keep those guarantees while making a small change cost minutes instead of an afternoon.
