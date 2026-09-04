# Prompt 8 — external boundary review

## Scope and provenance

This preserves the completed ChatGPT task **Review External Dependencies**. Its
requested revision `7e5746661b0c6abe8dae40c6ba0668ce15155230` could not be
verified from the supplied material; the returned review examined the supplied
`38094d6` snapshot and explicitly withheld a readiness claim. This reconciliation
checks the returned observations against current Mobility HEAD `1b7cc32` and the
canonical repository registers.

The returned review classified 62 rows as follows: 19 `EXTERNAL-LIVE-GATE`, 9
`EXTERNAL-BUILD-INPUT`, 2 `PRODUCT-DEFECT`, 10 `PRODUCT-COMPLETE`, 6
`OWNER-DECISION`, and 16 `DUPLICATE`. This file records only the requested
current-base reconciliation of PB-12, PB-13, and the six new owner-question
groups. It does not authorize implementation or add work to R01–R60.

## Current-base reconciliation

### PB-12 — gated analytics collapses independent advertiser work

**Classification: `PRODUCT-DEFECT`, P1 — still current.**

The privacy/reporting boundary is correct: `EXT-LEGAL-PRIVACY` and
`EXT-REPORT-METHOD` may block live analytics and disclosure, but they must not
remove unrelated campaign management.

Current evidence remains concrete:

- `/advertiser` treats the dashboard summary as a page-critical request
  (`frontend/src/app/advertiser/page.tsx:10-17`). The shared BFF client throws
  every non-OK response as `ApiError` (`frontend/src/lib/api/client.ts:16-29`),
  so a governed `503` has no bounded overview state.
- `/advertiser/campaigns/{id}` fetches campaign, summary, creatives,
  commercial state, review history and change requests in one `Promise.all`
  (`frontend/src/app/advertiser/campaigns/[campaignId]/page.tsx:55-83`) and
  rethrows every failure other than `404` (`:84-87`). A summary denial therefore
  hides otherwise usable campaign controls.
- `/advertiser/planning-sources` combines privacy-gated source/link reads with
  campaign and zone reads and has no page-level unavailable treatment
  (`frontend/src/app/advertiser/planning-sources/page.tsx:15-52`). The source
  service intentionally checks the privacy gate before reading anything
  (`app/services/audience.py:353-364`; `app/services/disclosure.py:67-89`).

The report route already demonstrates the desired bounded pattern: it maps a
governed failure to `GovernedAnalysisState` while preserving non-enumerating
`404` behavior (`frontend/src/app/advertiser/campaigns/[campaignId]/report/page.tsx:53-70`).

Required future acceptance criteria:

1. Campaign details, creatives, commercial state, review history, change
   requests and cancellation remain visible when only summary/reporting returns
   `503`.
2. Overview and planning-source routes render a bounded unavailable panel rather
   than an unhandled page failure.
3. A denied read causes no mutation; `404` remains non-enumerating.
4. `503`, `409`, malformed responses and transport failures retain distinct,
   tested treatments.
5. The UI never substitutes zero-valued analytics or weakens the privacy,
   disclosure or export gate.

Ordinary-user copy should stay plain, for example: **“Campaign analysis is not
available yet. You can continue managing the campaign.”** Operators may receive
the affected capability, authority category, last check and a short sanitised
support reference; raw gate IDs, thresholds and private data remain hidden.

### PB-13 — internal identifiers and technical evidence leak into product UI

**Classification: `DUPLICATE` of `CPY-002`, with partial remediation only.**

This is not a new normalized candidate. The current source confirms that the
existing copy outcome still owns residual leakage:

- `GovernedAnalysisState` now provides human-readable titles and explanations,
  but still renders the backend `code` directly and says “live-use gates” in the
  ordinary report surface (`frontend/src/app/advertiser/campaigns/[campaignId]/report/measurement-authority.tsx:306-336`).
- The advertiser report still exposes the run ID and full input/result/proof/
  report hashes (`.../measurement-authority.tsx:292-300`), while campaign review
  history exposes a full submitted-snapshot hash
  (`frontend/src/app/advertiser/campaigns/[campaignId]/page.tsx:227-231`).
- Planning-source screens expose campaign/zone UUIDs and source/segment hashes
  (`frontend/src/app/advertiser/planning-sources/page.tsx:87-89,129-134,203-207`).
- `/driver/capabilities` visibly names `R14-A`, contract metadata, statuses and
  capability codes (`frontend/src/app/driver/(portal)/capabilities/capability-probe.tsx:235-279`).
  Whether that route is intentional field instrumentation remains the existing
  `FOD-003` owner decision; it is not silently reclassified here.

Required future acceptance criteria:

1. Ordinary advertiser, applicant and driver views do not render `EXT-*`, `R*`,
   backend error names, contract/capability codes, full hashes, UUIDs or raw JSON.
2. Every known public state maps to a plain title, explanation, what happened or
   did not happen, and one next action; unknown states use safe generic copy plus
   a short support reference.
3. Complete immutable evidence remains available only in an authorized
   operator/audit surface, without suppressing distinctions among unavailable,
   pending, rejected, integrity-failed and unknown states.

`CPY-002` remains the canonical normalized outcome. `FOD-002` retains the
separate owner choice about whether hashes and reproducibility facts are
customer-facing trust features, support details or export-only evidence.

## Six owner-question groups retained from the returned review

These are unanswered questions, not approvals or implementation instructions.
Each is classified `OWNER-DECISION`; no answer is supplied on the owner's
behalf. Provider-neutral construction and synthetic verification may continue
where the cited canonical entry permits it.

### PB-20 — upload policy

**Question:** For creative, KYC, vehicle and installation-evidence uploads,
which file types and maximum sizes are approved?

- **Authorised owner:** named Terrax Media product/compliance authority.
- **Blocks:** adoption of the live upload policy for those surfaces.
- **May continue:** current fail-closed type/size/checksum validation, private
  storage/scanning contracts and synthetic upload tests. Current checks reject
  metadata mismatches (`app/services/stored_files.py:443-461`).
- **Product responsibility while absent:** do not accept an upload outside the
  configured safe limits; explain that requirements are not configured and that
  no file was accepted; retain retry-conflict and scan-failure evidence.
- **Canonical boundary:** `EXT-UPLOAD-POLICY` in `docs/progress.md:2699`;
  related provider-neutral work is W2-02A/C/D and W2-03C.

### PB-24 — installation-evidence and proof policy

**Question:** Who may submit installation evidence, which views are mandatory,
how long is approval valid, and what challenge, renewal and spot-check
thresholds apply?

- **Authorised owner:** named Terrax Media operations/product authority, with
  required compliance approval where applicable.
- **Blocks:** live/pilot adoption of uploader roles, required views, validity,
  renewal, challenge and physical spot-check values.
- **May continue:** the assignment-bound, nonce-based W2-03C/G contracts and
  synthetic evidence flows. The API already reports whether the configured policy
  is complete (`app/api/v1/installation_evidence.py:153-181`).
- **Product responsibility while absent:** fail closed before activation or
  payable work, show the missing evidence requirement and next operator action,
  and preserve audited retry/expiry outcomes without claiming vehicle identity
  from GPS.
- **Canonical boundary:** `EXT-EVIDENCE-POLICY` in `docs/progress.md:2689`;
  owning plans are `docs/progress.md:2188-2240`.

### PB-29 — commercial values

**Question:** What quotation components, commissions, base and premium driver
rates, production charges and vendor values are approved, in which currencies and
effective periods?

- **Authorised owner:** named Terrax Media commercial/finance authority.
- **Blocks:** real quotation, accepted commercial terms, production/vendor
  costing and financially effective payout configuration.
- **May continue:** configurable quotation/rate schemas, immutable snapshots and
  synthetic money tests; no value may be invented.
- **Product responsibility while absent:** keep values visibly unavailable or
  pending, prevent real issuance or activation, and preserve effective-dated
  terms rather than silently defaulting to a commercial amount.
- **Canonical boundary:** `EXT-COMMERCIAL-VALUES` in
  `docs/progress.md:2688`; placement is architecture §15/§16 and W2-00A plus
  the accepted payout-rule foundation.

### PB-30 — campaign-budget scope and controls

**Question:** Do printing and other fixed costs consume the governed campaign
budget, and what alert, pause, resume, override and funded-headroom rules apply?

- **Authorised owner:** named Terrax Media commercial/finance authority.
- **Blocks:** production budget-policy adoption and live spend enforcement.
- **May continue:** provider-neutral, configurable budget evaluation and
  synthetic alert/pause/resume tests. The configuration remains disabled until a
  complete approved revision is present (`app/core/config.py:222-229,405-420`).
- **Product responsibility while absent:** never use driver payout cost as a
  proxy for advertiser spend, never invent thresholds, and explain that budget
  enforcement is not configured before a live pause or override.
- **Canonical boundary:** `EXT-BUDGET-POLICY` and `EXT-CAMPAIGN-BUDGET-SCOPE`
  in `docs/progress.md:2680,2697`; W2-01E remains the owning build path.

### PB-41 — production messaging and support wording

**Question:** What sender identities and production email, WhatsApp and voice
wording are approved, and which support channels and coverage may be promised?

- **Authorised owner:** named Terrax Media communications/operations authority;
  legal/compliance approval remains required for regulated wording.
- **Blocks:** external message sending and any delivery or support promise.
- **May continue:** in-app notifications, provider-neutral templates, deduped
  outbox/retry behavior and auditable manual-contact tasks. W2-04 explicitly
  separates these from live provider delivery (`docs/progress.md:2242-2287`).
- **Product responsibility while absent:** queue or withhold safely, never claim
  external delivery, expose a useful in-product next step, and keep phone/KYC,
  bank and route data out of messages and logs.
- **Canonical boundary:** `EXT-MESSAGE-COPY`, `EXT-EMAIL-PROVIDER` and
  `EXT-PHONE-OPERATOR` in `docs/progress.md:2679,2681,2700`.

### PB-52 — support, resilience and evidence targets

**Question:** What support window, acknowledgement, triage, update and
escalation targets, availability objective, RPO, RTO and evidence-retention
target are approved?

- **Authorised owner:** named Terrax Media operations/release authority.
- **Blocks:** live support/handover commitments and accepted resilience targets.
- **May continue:** provider-neutral runbooks, incident/backup rehearsal design
  and evidence-linked handover preparation; no target or owner is invented.
- **Product responsibility while absent:** state that support and recovery
  commitments are not yet published, preserve incident and restore evidence,
  and do not imply a staffed channel, availability objective or recovery promise.
- **Canonical boundary:** `REL-008` in `to-do.md:32`, `EXT-OPERATIONS-OWNER` in
  `docs/progress.md:2702`, and W4-04B's named-owner/rehearsal gate
  (`docs/progress.md:2622-2630`).

## Scoped deduplication and verdict

- PB-12 remains a distinct current product-boundary defect and is not yet an
  implementation admission.
- PB-13 maps to `CPY-002`; its residual source evidence does not create a new
  outcome. `FOD-002` and `FOD-003` remain the relevant owner boundaries.
- PB-20, PB-24, PB-29, PB-30, PB-41 and PB-52 remain six owner questions from
  the returned 62-row review. They are preserved here rather than added as new
  `FOD` IDs or silently converted into engineering work.

**Verdict: coherent with product gaps.** External approvals, provider facts,
legal artifacts and real-world evidence correctly gate the named live actions;
the current product still needs bounded analytics-unavailable states and a
cleaner ordinary-user boundary for internal evidence and status vocabulary.
