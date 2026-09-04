# UI/product-review normalized outcomes

## Scope and provenance

This register normalizes only the three controller-dispatched follow-up audits
`CTL-CLD-01` through `CTL-CLD-03`. It does not ingest or reinterpret the
owner's other Claude sessions. The source reports audited `3832cff` (the
advertiser report also recorded a concurrent `25925e2` HEAD). Normalization was
reconciled against accepted HEAD `9305afe140ef12b700a137efc4db380ed465fec3`;
current-file observations are not substitutes for behavioral verification.

The first-pass register remains closed at 115 candidates. These 42 later-
snapshot candidates retain separate IDs and provenance: 28 executable
behavioral/copy corrections, 6 usability deferrals, and 8 owner decisions.
They are not inserted into the R01-R60 executable queue by this document.

Status meanings: `OBSERVED` means the cited current source still contains the
reported condition; `VERIFY` means implementation must reproduce the behavior
before changing it; `DEFER` and `OWNER DECISION` are deliberately
non-executable.

## Behavioral and accessibility candidates

| ID | Atomic claim | Follow-up provenance | Current-state evidence | Status |
| --- | --- | --- | --- | --- |
| FUX-001 | Campaign and creative approval queues fetch only the first 25 records without pagination, so later pending work is unreachable. | CTL-CLD-01 F1 | `admin/approvals/page.tsx` still fixes both queues at `limit: 25, offset: 0`. | OBSERVED |
| FUX-002 | Installation evidence opens only after an awaited signed-URL request and does not handle a popup-blocked `window.open`, so a reviewer can receive no evidence or error. | CTL-CLD-01 F2 | The awaited `window.open` path remains in `installation-review-actions.tsx`. | OBSERVED |
| FUX-003 | Driver-application approval and rejection controls are co-visible inside a horizontally scrolling table and a rejection reason is preselected, permitting an unintended attributed decision. | CTL-CLD-01 F6-F7 | Requires responsive/manual and action-state reproduction. | VERIFY |
| FUX-004 | The payout-batch maker/checker action column is clipped at narrow widths because its fixed-width table is wrapped in `overflow-hidden` without a horizontal scroller. | CTL-CLD-01 F10 | The `overflow-hidden` panel and `min-w-[760px]` table remain. | OBSERVED |
| FUX-005 | Operator screens use truncated/full UUIDs as the only actor, driver, vehicle, assignment, or organization identity, making the addressed record unrecognizable in-product. | CTL-CLD-01 S1, F8, F11, F13, F43; CTL-CLD-02 B4, D8 | Current admin surfaces still contain multiple `id.slice(0, 8)` renderers. | OBSERVED |
| FUX-006 | Audited destructive actions use anonymous native confirms and a native prompt for a permanent reason, without record identity or reviewable structured validation. | CTL-CLD-01 S8, F9, F20 | Current admin assignment, user, driver, and vehicle actions still use `window.confirm`/`window.prompt`. | OBSERVED |
| FUX-007 | Admin and advertiser logout and password-change controls are absent below the desktop breakpoint. | CTL-CLD-01 F37-F38 | Logout remains in the `md:flex` sidebar; the mobile header has no account control. | OBSERVED |
| FUX-008 | Driver assignments request installation history once per assignment and replace the whole page on partial-source failure. | CTL-CLD-01 F32 | Per-assignment installation-history requests remain in the page loader. | OBSERVED |
| FUX-009 | Notification background refetch hides cached count/list data, making the badge and open list flicker; notifications also lack destinations. | CTL-CLD-01 F42; CTL-CLD-03 D15; CTL-CLD-02 E2, E5 | `isFetching` still forces count to zero and list to undefined; destination behavior needs API/UI verification. | OBSERVED / VERIFY |
| FUX-010 | Audit filters rely on placeholders without programmatic labels and require raw event vocabulary. | CTL-CLD-01 F14; CTL-CLD-02 F4 | Requires current accessibility-tree and filter inspection. | VERIFY |
| FUX-011 | Hand-built accent buttons fail the reported high-visibility theme contrast ratio instead of using the shared button contract. | CTL-CLD-01 S6 | Theme CSS has concurrent owner changes; remeasure final accepted tokens before implementation. | VERIFY |
| FUX-012 | The driver-home “Trip entries” metric counts a ledger response capped at six and therefore reports six for any larger history. | CTL-CLD-01 F33 | The ledger call remains `limit: 6` and its array length feeds “Trip entries”. | OBSERVED |
| FUX-013 | Rejecting an approval can place the pending label on the Approve button, misreporting which action is underway. | CTL-CLD-01 F5 | Requires focused component reproduction. | VERIFY |
| FUX-014 | Server-paginated operator entity lists lack a server-side search route/control, making records beyond page-by-page traversal impractical. | CTL-CLD-01 S4, F43 | Verify current list APIs and realistic multi-page behavior before selecting exact surfaces. | VERIFY |

## Advertiser-journey candidates

| ID | Atomic claim | Follow-up provenance | Current-state evidence | Status |
| --- | --- | --- | --- | --- |
| ADV-001 | No advertiser campaign-edit route consumes the existing campaign PATCH contract, despite copy directing users to edit. | CTL-CLD-03 D2-D3 | No `[campaignId]/edit` page exists at the reconciled HEAD. | OBSERVED |
| ADV-002 | A campaign created without artwork cannot add it later, and a rejected creative cannot replace its asset although the UI promises those recovery paths. | CTL-CLD-03 D1, D4 | Creative create/update calls remain confined to creation/review flows; exact state matrix needs verification. | OBSERVED / VERIFY |
| ADV-003 | Advertisers cannot see the creative rejection reason even though advertiser review-history authority exists. | CTL-CLD-03 D5 | Verify current campaign creative rendering and authorization before adding a consumer. | VERIFY |
| ADV-004 | Campaign/creative rejection and quotation-ready events do not consistently notify the advertiser with campaign identity and a destination. | CTL-CLD-03 D6, D15; CTL-CLD-02 E1-E4, E6 | The current campaign-approved notification still contains a generic message; complete event coverage needs verification. | OBSERVED / VERIFY |
| ADV-005 | Quote-request, quote-acceptance, and waiver redirects set success parameters that the campaign page does not read, so successful actions have no confirmation. | CTL-CLD-03 D7 | Redirects still set three success parameters while the page types only `commercial_error`. | OBSERVED |
| ADV-006 | Quotation acceptance renders totals but omits returned line items, payment terms, production cost, and production scope. | CTL-CLD-03 D8 | Verify the current OpenAPI response and commercial panel together before changing presentation. | VERIFY |
| ADV-007 | “Preview and request change” immediately submits the request while the returned impact preview is not shown. | CTL-CLD-03 D9 | Server action still posts immediately and reports “Campaign change recorded”; admin consumes the preview. | OBSERVED |
| ADV-008 | The advertiser “coverage map” claims vehicle movement but renders target-zone polygons rather than movement/heatmap data. | CTL-CLD-03 D11 | Verify current map data source and copy against the accepted reporting contract. | VERIFY |
| ADV-009 | Advertisers cannot see a consolidated launch-readiness state for creative, funding, assignment, production, and installation gates. | CTL-CLD-03 journey stages 10-12 and flow §5.8 | Cross-service projection and product wording require current contract verification. | VERIFY |
| ADV-010 | The principal advertiser report surfaces remain unavailable until a staff-issued frozen run, leaving no truthful in-flight progress view. | CTL-CLD-03 D14 | Report and map still render `SAFE_MEASUREMENT_RUN_REQUIRED` when no report exists; existing summary authority must be evaluated separately. | OBSERVED |
| ADV-011 | Completed campaigns have no closing surface joining final report, invoice/payment reconciliation, and completion status. | CTL-CLD-03 journey stage 16 and flow §5.13 | Requires current completed-campaign journey reproduction. | VERIFY |

## Cross-surface copy candidates

| ID | Atomic claim | Follow-up provenance | Current-state evidence | Status |
| --- | --- | --- | --- | --- |
| CPY-001 | Product, role, and destination names are inconsistent enough to misdirect users, including advertiser entry copy that refers to the driver app. | CTL-CLD-02 A1-A3 | Reconcile the canonical product/role naming decision before a mechanical replacement. | VERIFY |
| CPY-002 | User-facing surfaces expose internal state-machine, governance, cryptographic, deployment, and backend-job vocabulary instead of a state and next action. | CTL-CLD-01 S2, F22-F23, F34; CTL-CLD-02 B1, B3, B5-B8, C1-C3, C6-C11, C13-C15, D3, D5-D7, D9, D11-D12, E4-E5, F2-F3; CTL-CLD-03 fail-closed and planning-source findings | Current source still exposes raw report codes, SHA labels, “canonical receipts”, `Payout v3`, and deployment-oriented messages. Existing MET/REP boundaries are excluded below. | OBSERVED |
| CPY-003 | Validation errors expose database/API field names instead of the user-visible field labels. | CTL-CLD-02 F1 | Reproduce each reported validation path and map only confirmed public messages. | VERIFY |

## Deliberately deferred usability choices

| ID | Decision requiring evidence | Provenance | Disposition |
| --- | --- | --- | --- |
| FUD-001 | The driver earnings hierarchy and the number of headline figures require driver comprehension testing; only the present ten-state overload is established. | CTL-CLD-01 F29; CTL-CLD-02 C4 | DEFER — usability validation |
| FUD-002 | Per-type tabs versus a merged approvals queue is an operator-workflow choice; FUX-001 alone owns reachability. | CTL-CLD-01 F1 and §10 | DEFER — operator validation |
| FUD-003 | Payout subnavigation, sidebar grouping, breadcrumbs, and nested-route composition require an information-architecture decision. | CTL-CLD-01 F12, F39-F40 | DEFER — usability/IA validation |
| FUD-004 | Replacing the admin overview with a work queue needs queue-priority and operator-task evidence. | CTL-CLD-01 F15 | DEFER — operator validation |
| FUD-005 | Driver assignment filter/group defaults and duplicated home calls-to-action need observed driver-task evidence; FUX-012 independently owns the false count. | CTL-CLD-01 F31, F33 | DEFER — usability validation |
| FUD-006 | Broad `micro` typography restrictions, row-click behavior, campaign-header composition, and decorative cleanup are design-system preferences unless a specific accessibility failure is demonstrated. | CTL-CLD-01 S5, F19, F21, F28, F41 | DEFER — design/accessibility validation |

## Owner decisions

| ID | Required decision | Provenance | Disposition |
| --- | --- | --- | --- |
| FOD-001 | Identify legally required applicant, driver, privacy, and fraud disclosures before rewriting or relocating compliance/negation copy. | CTL-CLD-01 S3/F36/§12; CTL-CLD-02 B2, C13, E1 and legal queue | OWNER DECISION |
| FOD-002 | Decide whether hashes, run IDs, raw evidence, and reproducibility facts are customer/driver trust features, support-only details, or export-only evidence. | CTL-CLD-01 S7, F30/§12; CTL-CLD-02 C5, D1 | OWNER DECISION |
| FOD-003 | Decide whether `/driver/capabilities` is intentional field instrumentation and, if so, which role/build gate may expose it. | CTL-CLD-01 F35/§12; CTL-CLD-02 C12 | OWNER DECISION |
| FOD-004 | Define the advertiser front door and whether account creation is self-service, enquiry-led, or operator-led. | CTL-CLD-03 journey stages 1-3 and flow §5.1 | OWNER DECISION |
| FOD-005 | Supply approved payment instructions, invoice ownership, and advertiser support/dispute route; no implementation may invent bank/support authority. | CTL-CLD-03 journey stages 8/15, D12 and flow §5.7/§5.10; CTL-CLD-02 D6/F2 | OWNER DECISION / EXTERNAL INPUT |
| FOD-006 | Decide whether to deliver advertiser target-area coverage or remove/relabel the marketed “Measured” promise. | CTL-CLD-03 D13 | OWNER DECISION |
| FOD-007 | Decide whether Terrax delivery cost, driver payouts, and fraud signals belong on advertiser surfaces and under what explanation. | CTL-CLD-03 trust risks 1/7 and flow §5.12; CTL-CLD-02 D10 | OWNER DECISION |
| FOD-008 | Confirm canonical product identity, legal entity presentation, pilot-city scope, locale, and spelling before normalizing contradictory brand/location copy. | CTL-CLD-02 A2-A6 | OWNER DECISION |

## Existing candidates reused; no duplicate IDs

The following follow-up evidence strengthens an existing candidate and creates
no new finding: reporting movement caveats (`MET-001`), incomplete totals
(`MET-002`), density/calibration provenance (`MET-004`), advertiser methodology
vocabulary guard (`MET-006`), ROI method disclosure (`REP-002`), cross-format
units/rounding/provenance (`REP-003`), planning-source lifecycle promises
(`AUD-006`), and durable logout semantics (`AUT-004`). FUX-007 is retained
because control reachability at a mobile breakpoint is not the same behavior as
the existing logout revocation/race contract.

## Source-label coverage

Every labeled finding is disposed above. CTL-CLD-01 S1-S8 and F1-F43 map to
FUX-001-FUX-014, ADV-008/ADV-010, CPY-002, FUD-001-FUD-006,
FOD-001-FOD-003/FOD-007, or the reused MET/REP candidates. Its D1-D12,
quick-win, and ST1-ST11 sections are proposed remedies for those same claims,
not additional findings. CTL-CLD-02 A1-A6, B1-B8, C1-C15, D1-D13, E1-E6,
and F1-F4 map to CPY-001-CPY-003, FUX-005/FUX-009/FUX-010,
ADV-004/ADV-010, FUD-001/FUD-006, FOD-001-FOD-003/FOD-007-FOD-008,
or the reused MET/REP candidates. Its voice guide is a proposed remedy and its
legal queue maps to FOD-001/FOD-005/FOD-008. CTL-CLD-03 D1-D15 map one-to-one
or in explicitly joined root causes to ADV-001-ADV-010, FUX-009, FOD-005,
FOD-006, and AUD-006; its journey gaps and trust risks repeat or contextualize
those normalized claims.
