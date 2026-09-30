# Requests — everything asked for, and what happened to it

One row per ask from the client, the PM or the owner, from the moment it is
raised until it is done. Rows are never deleted. What the client currently
wants, topic by topic, is in [client-decisions.md](client-decisions.md).

## How to use this file

1. **Record before working.** When the owner relays feedback ("the client said
   X, Y and Z"), add one row per ask with status `TODO` (or `NEEDS ANSWER` if it
   is a question) before any other edit. Use the next free `REQ-NNN` number.
   Never reuse a number, and do not use `Q<n>`, `D<n>`, `R<nn>` or `EXT-` as
   request IDs; those name questionnaire items, decisions, remediation slices
   and external prerequisites.
2. **If it changes a client rule,** also update the topic in
   [client-decisions.md](client-decisions.md) as that file describes, and link
   the topic in the *Topic* column.
3. **While working,** set `IN PROGRESS` and name the branch in *Notes*.
4. **When merged,** set `DONE` and put the implementing commit (short SHA) and
   date in *Done in*. Merge without squashing so that SHA reaches `master`; if a
   branch is squashed, cite the squash commit instead. A row becomes `DONE` only
   once its work is on `master`, so record it in the next change that touches
   this file (a commit cannot contain its own SHA).
5. **Questions** stay `NEEDS ANSWER` until answered. Then record the answer in
   *Notes*, update the topic, and either set `DONE` (nothing to build) or add
   the build work as a new row.
6. **Declined or superseded** asks become `WON'T DO` with the reason. Never
   delete a row.

| Status | Meaning |
| --- | --- |
| `TODO` | Agreed work, not started |
| `IN PROGRESS` | Being built; *Notes* names the branch |
| `DONE` | Merged to `master` after full CI passed; *Done in* cites the commit |
| `NEEDS ANSWER` | Waiting for the client, PM or owner; the question is in *Request* |
| `WON'T DO` | Declined or superseded; *Notes* says why |

## Register

| ID | Raised | From | Request | Status | Done in | Topic | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | 2026-09-25 | Owner | Batch A: D38 fixes (Terrax Media / Cardvert naming, WAT labels, driver Phone check, no hashes on advertiser/driver screens, review needs dates, budget and target area, "Waiting for you" admin home); budget alerts at 80/95/100 %; installation photo policy; per-purpose upload limits | DONE | `7a9ceb0` (2026-09-26) | [Budgets](client-decisions.md#budgets-and-alerts), [Installation photos](client-decisions.md#installation-photos), [Uploads](client-decisions.md#file-uploads) | |
| REQ-002 | 2026-09-25 | Client (D39) | Batch B: daily-rate driver pay engine (`payout_v4`), 5-minute stop rule, pay terms on offers | DONE | `e14149d` (2026-09-28) | [Driver pay](client-decisions.md#driver-pay) | Publishing stays off until REQ-014–REQ-016 are answered. Fix `4f318e3`. |
| REQ-003 | 2026-09-25 | Client (D39) | Batch C: automatic payout approval with safeguards, Finance pause switch, alerts, reconciliation view | DONE | `3b6b396` (2026-09-28) | [Payouts](client-decisions.md#payout-approval-and-timing) | Off until REQ-017, REQ-029 and REQ-030 are answered. |
| REQ-004 | 2026-09-25 | Owner | Batch D: Paystack payment and transfer adapters from the public docs, disabled without keys | DONE | `dbd41e1` (2026-09-28) | [Payments](client-decisions.md#advertiser-payments) | Live use waits for REQ-027 and REQ-035. |
| REQ-005 | 2026-09-25 | Client (D39) | Batch E: in-app complaints and a Customer Service inbox | DONE | `7e39c66` (2026-09-28) | [Complaints](client-decisions.md#complaints-and-support) | Defaults in use until REQ-020–REQ-024 are answered. |
| REQ-006 | 2026-09-28 | Owner | Repair GitHub CI (withdrawn MinIO images), fix what the first full run found, and stop the coverage check failing on run-to-run noise (D41) | DONE | `83444dc` (2026-09-29) | | First fully green CI run: 36516619520, on `83444dc`. |
| REQ-007 | 2026-09-29 | Owner | Shorten `docs/progress.md`; move history and package detail out | DONE | `9a0ef34` (2026-09-29) | | Done by another agent on branch `docs/client-decision-flow` with REQ-008; merged in `fedd41b`. |
| REQ-008 | 2026-09-29 | Owner | Track client decisions by topic with history, and track every request from ask to done | DONE | `b83de10` (2026-09-29) | | Branch `docs/client-decision-flow`; merged in `fedd41b`. |
| REQ-009 | 2026-09-25 | Owner | Batch F1: invoice layout — 7.5 % VAT included, Terrax details, serial number, campaign length, quantity, signature lines | DONE | `0b53eab` (2026-09-29) | [Invoices](client-decisions.md#invoices-and-vat) | D42; merged in `26cb6cb` after CI run 36608128554. Real invoices wait for REQ-019 (RC or TIN), REQ-041 (bank details) and REQ-042 (accountant). |
| REQ-010 | 2026-09-25 | Owner | Batch F2: deployment environment templates for Render, S3 with KMS, ClamAV, Postmark and Mapbox (templates only; no accounts or deploys) | DONE | `0b53eab` (2026-09-29) | [Hosting](client-decisions.md#hosting-accounts-and-providers) | Merged in `26cb6cb`. Not deploy-ready: see the go-live gaps in `docs/deployment-templates.md`. |
| REQ-011 | 2026-09-25 | Owner | Batch F3: rewrite the client guide *How Cardvert Works* for daily pay, automatic payouts and in-app complaints | TODO | | | Taken out of Batch F on 2026-09-29: the owner will rewrite the guide later. The current guide is a 17 Sep PDF held outside the repository. |
| REQ-012 | 2026-09-25 | Owner | Batch F4: amend architecture §16 and PRD §7 for D39, as D39 requires | DONE | `0b53eab` (2026-09-29) | [Driver pay](client-decisions.md#driver-pay) | Merged in `26cb6cb`. |
| REQ-013 | 2026-09-29 | Owner | Delete the merged `batch-c` and `batch-e` branches (local and GitHub) and the `mobility-batch-e` worktree | DONE | no commit — branches and worktree deleted 2026-09-29 | | After REQ-008 merges. |
| REQ-014 | 2026-09-25 | Owner → client | Short days: a driver covers 50 of 70 miles — pay in proportion (₦7,143), ₦10,000 minus ₦140 per missing mile (₦7,200), or another rule? Is there a minimum distance below which the day pays nothing? | NEEDS ANSWER | | [Driver pay](client-decisions.md#driver-pay) | Asked 2026-09-25. |
| REQ-015 | 2026-09-25 | Owner → client | Which miles count towards the 70: only inside the campaign area, or outside miles fully, partly (the ₦50 figure) or not at all? | NEEDS ANSWER | | [Driver pay](client-decisions.md#driver-pay) | Asked 2026-09-25. |
| REQ-016 | 2026-09-25 | Owner → client | Is the full day ₦10,000 or ₦9,800 (70 × ₦140)? Above 70 miles, is it still ₦10,000? | NEEDS ANSWER | | [Driver pay](client-decisions.md#driver-pay) | Asked 2026-09-25. |
| REQ-017 | 2026-09-25 | Owner → client | Should earnings be sent every day, or collected and sent weekly? | NEEDS ANSWER | | [Payouts](client-decisions.md#payout-approval-and-timing) | Asked 2026-09-25. |
| REQ-018 | 2026-09-25 | Owner → client | Advertiser reports show campaign results and general vehicle details but not driver names or profiles — is that OK? | NEEDS ANSWER | | [Reporting](client-decisions.md#advertiser-reporting-and-privacy) | Their answer mentioned "admin officer & driver profile and the car". |
| REQ-019 | 2026-09-25 | Owner → client | Is 2521515778093 Terrax's RC (CAC) number or its TIN? Invoices need both. | NEEDS ANSWER | | [Invoices](client-decisions.md#invoices-and-vat) | |
| REQ-020 | 2026-09-28 | Owner → client | Which complaint categories should drivers and advertisers choose from? | NEEDS ANSWER | | [Complaints](client-decisions.md#complaints-and-support) | Neutral default in use. |
| REQ-021 | 2026-09-28 | Owner → client | Is there a target time for Customer Service to reply to a complaint? | NEEDS ANSWER | | [Complaints](client-decisions.md#complaints-and-support) | None shown or enforced. |
| REQ-022 | 2026-09-28 | Owner → client | Should drivers get email or WhatsApp when a complaint is answered, or is in-app enough? | NEEDS ANSWER | | [Complaints](client-decisions.md#complaints-and-support) | In-app only today. |
| REQ-023 | 2026-09-28 | Owner → client | Should an advertiser company's complaints be visible to everyone in that company, or only to the person who raised them? | NEEDS ANSWER | | [Complaints](client-decisions.md#complaints-and-support) | Company-wide today. |
| REQ-024 | 2026-09-28 | Owner → client | When someone asks for their data to be erased, what happens to their complaint text? | NEEDS ANSWER | | [Complaints](client-decisions.md#complaints-and-support) | Kept and counted today; erasure is a manual staff decision. |
| REQ-025 | 2026-09-25 | Owner → PM | Paystack: change the exposed password and turn on two-factor login; invite the developer and Finance; confirm the business is verified and Transfers are on; turn transfer OTP off; confirm OPay settlement and how the balance is topped up | NEEDS ANSWER | | [Payments](client-decisions.md#advertiser-payments) | Test keys first, live keys only after testing. |
| REQ-026 | 2026-09-28 | Owner → PM | Who pays the Paystack transfer fee — Terrax, or deducted from the driver's amount? | NEEDS ANSWER | | [Payouts](client-decisions.md#payout-approval-and-timing) | |
| REQ-027 | 2026-09-25 | Owner → PM | Paystack test keys for the developer | IN PROGRESS | | [Payments](client-decisions.md#advertiser-payments) | Branch `codex/paystack-key-day`. Owner authenticated to the Terrax Paystack account on 2026-09-29; the existing test key is stored only in ignored local configuration. Test balance and missing-reference probes succeeded; real ₦100 and ₦101 checkouts initialized from Cardvert, and the ₦101 checkout completed through Paystack Test Mode and was verified and applied once by Cardvert. The request stays open until the implementation is merged and the remaining public-webhook evidence is recorded under REQ-035. |
| REQ-028 | 2026-09-25 | Owner → PM | Terrax-owned accounts with the developer invited: AWS (storage and encryption), Render (hosting), Postmark (email), Mapbox (maps) | NEEDS ANSWER | | [Hosting](client-decisions.md#hosting-accounts-and-providers) | |
| REQ-029 | 2026-09-28 | Owner → PM | The most Cardvert may pay out automatically in one run (`PAYOUT_AUTOMATIC_BATCH_LIMIT_NGN`) | NEEDS ANSWER | | [Payouts](client-decisions.md#payout-approval-and-timing) | |
| REQ-030 | 2026-09-28 | Owner → PM | Who receives alerts when a payout fails, is duplicated or hits a limit (name and email)? | NEEDS ANSWER | | [Payouts](client-decisions.md#payout-approval-and-timing) | |
| REQ-031 | 2026-09-25 | Owner → PM | Names (not just departments) for the Finance Officer, Compliance reviewer, Customer Service operator and the lawyer handling the legal pack | NEEDS ANSWER | | [Legal](client-decisions.md#legal-privacy-and-retention) | |
| REQ-032 | 2026-09-24 | Client (pending) | Legal/privacy pack; AMAC/APCON permit reference numbers; pilot drivers, vehicles and advertisers | NEEDS ANSWER | | [Pilot](client-decisions.md#pilot-shape-permits-and-launch) | Client said these will follow. |
| REQ-033 | 2026-09-24 | Owner → client | Confirm the product lives on terraxmedia.com (for example app.terraxmedia.com) | NEEDS ANSWER | | [Hosting](client-decisions.md#hosting-accounts-and-providers) | Client answer 10 named the domain. |
| REQ-034 | 2026-09-25 | Owner | Confirm motorcycles are allowed in the pilot, then record a decision row and update Q19 | NEEDS ANSWER | | [Drivers and vehicles](client-decisions.md#drivers-and-vehicles) | Told to the client as an assumption on 2026-09-25; Q19 still says cars. |
| REQ-035 | 2026-09-28 | Owner | Paystack key day: sandbox checks of field names, timestamps and references; wire the audited destination resolver and Paystack adapters into payout submit, poll and the worker; checkout flow with Cardvert references; queued transfer-webhook path; decide whether `sk_test_` is refused outside staging; configure the webhook URL | IN PROGRESS | | [Payments](client-decisions.md#advertiser-payments) | Branch `codex/paystack-key-day`. Exact checkout binding (reference, advertiser, accepted terms, amount, currency and key domain), company billing-email preference, audited frozen bank destination resolution, worker wiring and the single queued Paystack webhook are built. Live keys are refused outside production; production refuses test keys; the browser return is fixed to the public Cardvert origin and provider checkout redirects are restricted to Paystack. Confirmed cash is preserved when another payment changes the balance; unresolved or not-yet-applied checkouts cannot spawn a second reference; an applied checkout permits a later exact-balance repayment after reversal/debit; invalid local billing facts fail before provider contact; provider acceptance followed by local failure preserves one uncertain reference; newer provider reversals restore affected earnings to available; durable sweeps recover enqueue failure; driver data inventories include provider events and failed attempts; and permanently invalid transfer events stop retrying. Local API/worker/migration tests pass. On 2026-09-29 a real Paystack Test Mode ₦101 checkout completed: Cardvert verified the exact reference, processed one confirmed provider event, created one ₦101 receipt, made one allocation and marked the invoice paid. A public staging URL is still required for webhook delivery/replay proof; no transfer was submitted, and settlement-bank/OTP/production approval remain live-use gates. |
| REQ-036 | 2026-09-28 | Owner | Optional hardening from the Batch C security review: lock the open-dispute check (L2), audit alert creation (L3), actor-only run audit subjects (L4), fairer scan cap (L5) | TODO | | [Payouts](client-decisions.md#payout-approval-and-timing) | Optional; owner to prioritise. |
| REQ-037 | 2026-09-24 | Client | Count fixed costs (printing, installation, permits, design) towards the campaign budget | TODO | | [Budgets](client-decisions.md#budgets-and-alerts) | Client answers item 3; deferred from Batch A to a money batch. |
| REQ-038 | 2026-09-26 | Owner → client | Confirm the per-purpose upload limits (identity 10 MB, vehicle 20 MB, installation 20 MB, artwork 25 MB) | NEEDS ANSWER | | [Uploads](client-decisions.md#file-uploads) | Built as the developer's recommendation (REQ-001); told to the client for information. |
| REQ-039 | 2026-09-26 | Owner → client | Values for the inspector's installation spot checks and the display-proof windows | NEEDS ANSWER | | [Installation photos](client-decisions.md#installation-photos) | Still open after Batch A. |
| REQ-040 | 2026-09-28 | Owner | Optional Batch C follow-ups: a daily-limit check that counts cross-midnight trips per day rather than in full; tests that another day's submitted line stays out of "awaiting provider" and that manual failure audits cannot crowd the blocked-submission scan; a `submission_blocked` alert while the system account is invalid; excluded entries no longer taking candidate places | TODO | | [Payouts](client-decisions.md#payout-approval-and-timing) | Optional. The system-account edit guard is already done (`3b6b396`). |
| REQ-041 | 2026-09-29 | Owner → PM | Terrax Media's OPay account details for invoices and advertiser payment instructions: bank name, account name and account number | NEEDS ANSWER | | [Invoices](client-decisions.md#invoices-and-vat) | Invoice bank slots stay blank until supplied (D42). |
| REQ-042 | 2026-09-29 | Owner → PM | Terrax's accountant to confirm the invoice layout, VAT wording and invoice-number prefix before real invoices are issued | NEEDS ANSWER | | [Invoices](client-decisions.md#invoices-and-vat) | Recorded as `INVOICE_ISSUER_EXTERNAL_INPUT_REFERENCE` once given (D42). |
