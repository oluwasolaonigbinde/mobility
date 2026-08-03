# Adopted Decisions — Q1–Q34 Resolution Map (Agent-Facing)

**Status: ADOPTED (D8, 27 Jul 2026) — produced via the standard SOP: drafted,
independently adversarially reviewed (5 must-fix findings reconciled), then
delta-verified PASS by a fresh pass. Build against this file.**

Somto did not answer `Mobility_Product_Direction_Questionnaire_v2.docx`. To
unblock the build, industry best-practice defaults were adopted on 27 Jul 2026
(decision **D8** in `decisions-log.md`). The client-facing version of this
adoption is `docs/Mobility_Working_Decisions_and_Open_Items.docx` (sent to
Somto in place of the questionnaire). **This file is the agent-facing truth for
every Q-number.** The architecture doc's §33 map still routes each Q to the
section it feeds; the *status* of each Q now lives here.

## Status taxonomy

| Status | Meaning | What you may do |
|--------|---------|-----------------|
| **CONFIRMED** | Client-confirmed (Somto), directly or via D1–D7. | Build to it. Supersede only via a new decisions-log row. |
| **ADOPTED** | Best-practice default adopted (D8). Client has been told "we build to this unless you flag it". | Build to it as if confirmed — do **not** block on the client. You MUST implement the row's **divergence guard** so a late client reversal is a config/data change, not a rework. |
| **CONFIRM-PENDING** | Explicitly put to the client as a named yes/no. | Build the stated base case; the named structural escape hatch must be preserved. |
| **OPEN** | Only the client can answer (facts, authority, or commercial terms). | Old `[OPEN]` rule applies: smallest thing that works under all still-open options; flag foreclosing designs (architecture P10). |

**Rules for agents**

1. Commit messages implementing one of these cite the Q-number (and D8), same
   as D-numbers today.
2. If Somto's eventual reply diverges from an ADOPTED row: append a superseding
   row to `decisions-log.md`, update this file, and amend `architecture.md` in
   the same commit (amendment rule, architecture §1).
3. An ADOPTED row never weakens an architecture invariant. Where this file and
   `architecture.md` conflict, the architecture doc wins — flag the conflict
   instead of building.

## A. Core product decisions (Q1–Q14)

| Q | Topic | Status | Adopted direction | Build implication & divergence guard |
|---|-------|--------|-------------------|--------------------------------------|
| Q1 | Pricing structure | **ADOPTED** | Hybrid: standard packages + custom quotations for larger/unusual campaigns (§15). | Packages are **admin-configurable data, never code** — package CRUD + a custom-quote path. Guard: a client switch to packages-only or custom-only is a data/visibility change. |
| Q2 | Payment timing | **ADOPTED** | Deposit before production; balance before activation. Corporate credit terms post-pilot (§15). | Use §15.2's fixed shape as-is: deposit and balance are **N `payments` rows against the campaign's invoice**; campaign funding status derives from `invoices.status` (§15.3) and gates activation (Q15). Guard: instalments/credit terms later = more payment rows / issued-invoice terms, not a new flow. |
| Q3 | Payment methods | **ADOPTED** | Both: bank transfer with admin confirmation + online gateway (Paystack/Flutterwave), one shared payment history (§15.3). | Manual-confirmation and gateway-webhook paths write the same payment records. Guard: gateway behind a provider adapter; **which** gateway is still a parameter. |
| Q4 | Hourly-rate uniformity | **ADOPTED** — *delivered S1, 30 Jul 2026 (D9)* | One platform-standard hourly rate + admin-only per-campaign override (§16.1). | **Built:** the rule row stores the resolved `hourly_rate_naira`; `PAYOUT_DEFAULT_HOURLY_RATE_NGN` (Settings, ships unset) is the platform-default fallback applied at rule creation when > 0 — the divergence guard is this config mechanism (single-rate-always = every rule keeps the default; per-campaign = admin types a rate). Platform default is config, not data, until the client needs runtime editing (D9d). |
| Q5 | Payable-hour definition | **ADOPTED** — *delivered S1, 30 Jul 2026 (D9)* | Verified session time that meets campaign rules (time window, approved area, valid GPS movement); ineligible time **excluded, not discounted**; capped per D4 (§16.1). | **Built:** interval classifier (`payout_eligibility.py`) with reason codes `gps_gap/low_accuracy/teleport/out_of_window/out_of_area/stationary(+grace)`; each condition is an independent per-interval predicate (params: `PAYOUT_ELIGIBILITY_*` Settings + per-rule `eligibility_params` overlay), so adding/removing conditions keeps the engine's shape. Approved area = target zones minus exclusions (D9c). |
| Q6 | Campaign creation & approval | **ADOPTED** | Advertiser creates a draft; admin approval required before launch (§18). | Use §18's state names: `pending_review → approved` inserted between `draft` and `scheduled`; rejection is an admin action with a recorded reason, not a campaign enum value. Guard: full self-service later = an auto-approve policy on the same lifecycle, not a second path. |
| Q7 | Matching model | **ADOPTED** | System recommends eligible drivers/vehicles; admin approves the final assignment (§21). | Eligibility/scoring produces recommendations; assignment stays an admin action. Guard: full-auto later = auto-accepting the top recommendation — keep recommendation and assignment as separate steps. |
| Q8 | Driver acceptance | **ADOPTED** | Offer (rate, dates, area, branding) → driver accepts before assignment is final (§21). | Offer entity + accept/decline + expiry; recorded acceptance is the dispute anchor. Guard: none needed — auto-assign later just skips the offer step. |
| Q9 | Mid-flight changes | **ADOPTED** | Expansions apply immediately; reductions/removals/date changes need admin approval + recorded reason (§18/§15.5). | Change-request model with an expansion/reduction classification. Guard: classification is data-driven so the safe/unsafe boundary can move without new flow. |
| Q10 | Session start/end | **CONFIRMED** (via D3) | Driver-controlled Start/End; tracking only within a session; schedule/area checks applied to session data (§8.6). | Already built. D3 (client-sourced) states the Start/End session model carries over unchanged to the native app. No change. |
| Q11 | Retargeting MVP shape | **ADOPTED** | Anonymised exposure-based segments + controlled export/activation. **No direct Meta/Google push in MVP.** Export ships **disabled until Q31 legal sign-off** (§22). | Build aggregation + segment model behind the §22 privacy boundary (k = distinct vehicles); export is a gated admin capability. Guard: direct integrations later = adapters downstream of the same aggregation model. |
| Q12 | Advertiser results | **ADOPTED** | Verified operational results + clearly-labelled estimated impressions + downloadable campaign report (§27). | Report surfaces must keep measured vs modelled visually and structurally distinct. Guard: none needed — subsets are trivial. |
| Q13 | Driver joining | **ADOPTED** | Public driver self-registration with document upload + admin approval before any work (§23). | **Narrows D1**: operator-led onboarding remains for advertisers/orgs; drivers get public self-registration. Application → review-queue → approval flow + driver-signup surface. Guard: invite-only/referral-code later = a gate flag on the same application flow. |
| Q14 | Quotes/invoices in-platform | **ADOPTED** | Platform generates numbered, VAT-consistent invoices; quotations stay manual during the pilot (§15.2). | Invoice engine + numbering + VAT line from Q28 config. **Dependency: real invoices cannot be issued until Q28's company facts arrive** (fine to build/test with placeholders). Note: this is a build-scope wager, not industry consensus — risk is wasted effort, not rework. |

## B. MVP rules (Q15–Q24)

| Q | Topic | Status | Adopted direction | Build implication & divergence guard |
|---|-------|--------|-------------------|--------------------------------------|
| Q15 | Activation gates | **ADOPTED** | Active requires: funding status met (per §15.3, derived from `invoices.status`) + creative approved + vehicles assigned + installation evidence approved; admin performs final activation (§18). | Gate checklist evaluated as data; admin activation is the pilot's manual final step. Guard: gates configurable per campaign type later. |
| Q16 | One campaign per vehicle | **ADOPTED** | One active campaign per vehicle during the pilot (§21). | Assignment-overlap constraint. Guard: enforce as a rule, not a schema cardinality — multi-placement later relaxes the rule with compatibility conditions. |
| Q17 | Installation evidence | **ADOPTED** | Admin-approved installation photo before a vehicle's hours generate earnings (§19/§18). | Evidence upload on assignment + approval state feeding both the Q15 gate and the earnings engine. |
| Q18 | Creative upload & approval | **ADOPTED** (confirms D7) | In-platform creative upload; admin approves/rejects before production/launch (§19/§18). | D7's "pending approval" is resolved — build the file pipeline (§19 presigned POST) + review queue. |
| Q19 | Vehicle eligibility | **ADOPTED** | Roadworthy cars only for the pilot; other vehicle types are later expansion (§21). | Vehicle-type field exists but pilot validation accepts cars. Guard: type list is data. |
| Q20 | Minimum activity | **ADOPTED** | Configurable minimum verified hours/week; auto-flag assignment after 7 consecutive inactive days (§21). | Thresholds are Settings/campaign data; flagging is a worker sweep output. Exact weekly number stays a parameter (set before pilot). |
| Q21 | Fraud handling | **ADOPTED** (confirms D5) | Hold-and-review: flagged-session earnings held for admin review; reasons shown to driver + dispute channel; thresholds configurable (§17). | D5's "pending formal approval" is resolved. Fraud review workflow (acknowledge/resolve) is required build. |
| Q22 | Earnings release | **ADOPTED** | Earnings pending 7 days → weekly payout batch; only named ops admins adjust; every adjustment audited (old, new, reason, actor) (§16.2). | Release/disbursement pipeline of payout v2. Guard: review-window length and batch cadence are Settings. |
| Q23 | Owner-drivers only | **CONFIRM-PENDING** | Pilot = every vehicle registered to the driver who drives it; that driver is the payee. Fleet owners are phase two. **The one question put to Somto as a named yes/no** — Nigerian supply is often fleet-based, and fleets restructure payouts (driver/owner/split). | Build owner-driver-only. The §16.3 **payee abstraction is mandatory** (payouts pay a payee, which for now is always the driver) — that is the no-rework promise if the answer comes back "fleet-based". |
| Q24 | Cancellation & refunds | **ADOPTED** | On cancellation of a paid campaign: assignments + earnings stop immediately; drivers paid verified hours to that moment; refund settled per contract **outside** the platform; settlement recorded on the campaign (§15). | Cancel flow + terminal financial-settlement record. Guard: in-platform refund execution later = automating the recorded settlement, not a new model. |

## C. Pilot & launch (Q25–Q34)

| Q | Topic | Status | Adopted direction | Build implication & divergence guard |
|---|-------|--------|-------------------|--------------------------------------|
| Q25 | Production/permits ownership | **ADOPTED** | Platform-managed printing, installation, removal, permits via approved vendors; costs itemised in the quotation. | Ops decision — no code beyond itemisable quotation/invoice line items (Q14/Q28). |
| Q26 | Driver onboarding requirements | **ADOPTED** (checklist) / **OPEN** (legal wording) | Compulsory docs: driver's licence, vehicle registration, insurance, NIN, standard vehicle photos — this is the Q13 flow's document set (§19.3/§23). Onboarding also captures the driver's **verified bank account** (Q27 payouts pay verified accounts; §30's bank-account/BVN row unblocks with Q26+Q27 adopted). Agreement/consent wording + renewal rules await the Q31 adviser. | Build the document-set upload/review + bank-account capture; wording is content, renewal periods are config. **Blocks onboarding go-live, not the build.** |
| Q27 | Payout channel | **ADOPTED** | Manual weekly bank transfers to verified accounts + downloadable payout report; automated transfers when volume justifies (§16.3). | Disbursement = mark-paid + exportable report for the pilot; bank-account capture/verification happens at onboarding (Q26). Guard: disbursement behind a port so a provider adapter slots in without touching release logic. |
| Q28 | VAT & invoice presentation | **ADOPTED** (mechanism) / **OPEN** (facts) | Tax treatment configurable; default = VAT-exclusive prices with VAT itemised (standard Nigerian B2B) (§15.2). Company facts (registered name, TIN, billing address, accountant's confirmation) are client-only. | Build the configurable tax field + invoice template now with placeholder company config. **Blocks issuing real invoices (Q14), not building the engine.** |
| Q29 | Product name & brand | **OPEN** | Working name "Vantage" continues internally. Must be confirmed before anything is distributed externally. | No hard-coded brand strings outside the existing token/manifest layer; §33's rename-sweep note stands. **Blocks app listing/domain/external distribution.** |
| Q30 | Pilot shape | **OPEN** | Strawman offered to client: 1 city (Lagos), 15–25 vehicles, 2–3 anchor advertisers, 8–12 weeks. Not a decision until edited/confirmed. Note: smaller than §2.3's earlier 25–50-vehicle sizing sketch — the client-offered strawman governs if confirmed. | Sizing inputs only (§2.3/§25; §24.2's partition-math trigger assumed ~50 vehicles). Do not encode pilot numbers anywhere. |
| Q31 | Privacy/consent/retention sign-off | **OPEN** | Client must name the legal/compliance approver. Retention stays configurable (§24); consent wording is content. | **Gates**: live data collection at go-live and Q11 segment-export activation. Build proceeds; the export capability ships disabled. *Build delivered (S4, 3 Aug 2026):* retention is enforced — monthly `location_pings` partitions, ⚙ `PING_RETENTION_MONTHS` (default 12) worker purge with append-only `data_purge_audit` evidence, backup-rotation note in the runbook. A late client-chosen window is a config change only. |
| Q32 | Infra ownership | **ADOPTED** (decision) / **OPEN** (client account action) | Client-owned cloud account + domain; developer granted access; monthly budget confirmed by client (§25). | Deploy targets client-owned accounts. **Blocks production deployment**, not preproduction work (staging topology already provider-neutral). |
| Q33 | Day-to-day operations owner | **OPEN** | Commercial arrangement between OJ Solutions and Somto (suggested: the developer supports the pilot while training Somto's team). | Ops decision — no code. Blocks go-live staffing plan. |
| Q34 | Notification channels | **ADOPTED** | In-app + automated email for advertisers; operations-run WhatsApp for drivers; automated SMS/WhatsApp post-pilot (§20). | §20's proposed default is now adopted: in-app + email channels in the outbox model; WhatsApp/SMS are later channel adapters, not MVP integrations. |

## Cross-cutting dependency notes

- **Q14 → Q28**: invoice engine builds now; issuing real invoices waits on
  company facts.
- **Q11 → Q31**: segment aggregation builds now; export/activation stays
  disabled until legal sign-off.
- **Q23**: payee abstraction (§16.3) is the insurance policy on the only
  structurally risky adoption. Do not shortcut it.
- **Q13 vs D1**: D1 (operator-led onboarding) now applies to advertisers/orgs
  only; drivers self-register per Q13. Cite both when touching onboarding.
