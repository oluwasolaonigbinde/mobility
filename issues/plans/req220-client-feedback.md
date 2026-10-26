# REQ-220–229: approved look and 20 October feedback

Owner-authorized contract, Lane B, `design/req220-client-feedback` (base `1a7b5757`).
Review-required: advertiser/driver UI flows, stored redirect destinations and location disclosure.
The owner's task approves the concrete scope below; no push, deployment, provider call or account action.

## Outcome and boundaries

Implement the approved background-additions design using the supplied SVG/HTML assets:
warm cream/green, faint Terrax stripes, soft decorative Abuja skyline, white content,
fixed Terrax-van welcome hero, coloured wallet/megaphone/car icons, real artwork and actual maps.
Keep one main action, plain human copy, accessibility, readable phone layouts and current
loading/unavailable/retry distinctions. Billing retains its approved design. Admin changes
stay in shared styling/layout/components, preserving drawers and operations.

Lane A owns report logic, removals and all existing backend business logic. The
23 Oct taste-round-2 grant permits report presentation wrappers/classes and plain
help copy only, retaining accessible names and all report contracts. This lane
adds small QR/live-map modules and their router/model registration/migration. Coordinate
any necessary existing-backend guard correction with Lane A rather than edit its files.
No fake basemap, budget tracker, CTR, visits, ROI, new approval workflow or calendar.
No company-page alias or campaign-invoice duplicate survives S25/S26; invoice details
move under Billing with all callers updated. No progress.md or forbidden files touched.

## Acceptance and verification

| Criterion | Required outcome and evidence |
| --- | --- |
| C1 Brand | Advertiser Home matches v2: Terrax hero, skyline/stripes, icon tiles without money total, artwork beside actual campaign map; welcoming empty state with one start action. Desktop/phone screenshots plus existing Home/shell checks. |
| C2 Driver | After Lane A display-photo removal, Home/Jobs use warm job card, frozen real artwork on the same van and Where to drive/Avoid chips. New driver state remains truthful. Existing trip/pay behaviour untouched. Desktop/phone, empty/populated screenshots and touched driver/artwork tests. |
| C3 Assets | Campaign assets show thumbnail, created/upload date, exact approval status and rejection reason, Upload/Replace and van preview. Printed (production started) or running campaigns link to existing support for replacement; no artwork swap is offered or allowed through the wizard. Verify before-production upload/replacement and after-production request with current server authority; failures distinguish unavailable reasons. |
| C4 QR | Per-artwork validated public https URL, owned advertiser read/write, stable random short code, local downloadable QR encoding the Cardvert short URL. Redirect ignores request-supplied destinations, revalidates stored URL, uses no-store/no-referrer, counts an atomic daily bucket only on successful GET, and rate limits across workers without IP/UA keys. HEAD does not increment. Invalid/unknown links, cross-tenant access, invalid schemes/credentials/local hosts, limiter outage/limit and concurrent increments have deterministic tests and local API/browser evidence. No scan identifiers, IPs, user agents or request URLs persisted/logged. |
| C5 Performance | Home and campaign cards use existing governed estimated views, actual cars and last-seven-day distance/car chart with readable text fallback; missing is a dash/unavailable, true zero stays zero. QR scans appear when positive, campaign page exposes QR scans. Report presentation only may use shared cards, fields, headings and buttons under the 23 Oct round-2 scope grant; no report logic/API/validation/date changes. Verify real API data and empty/error states; touched tests. |
| C6 Live dots | New campaign-owned endpoint returns only anonymous coordinate pairs from currently active trips/assignments/campaigns. Select latest point per vehicle BEFORE area filtering, within the 15–30-minute-old window, both recorded and received at least 15 minutes ago, inside target area and outside exclusions, with positive movement. No older in-area point substituted after a later out-of-area point. No identity, stable dot ID, heading, exact timestamp or route; shuffled order, no-store and campaign filter only. Existing map component/activeMapStyle; empty text exactly No cars driving right now. Test time edges, latest-outside, exclusions, stale/ended/stationary, tenant and response allowlist; privacy review of actual endpoint and UI. Existing history coverage stays. |
| C7 Dates | Campaign list timeline shows running/scheduled/finished start/end dates using current extension dates. Advertiser detail/list and staff detail/list show Day X of Y derived from Nigeria calendar dates, clamped to the actual campaign interval; scheduled says Starts…, missing dates have no fabricated counter. Test same-day, scheduled, end/past-end, timezone and extension boundaries. No new lifecycle or billing authority. |
| C8 Admin/S25/S26 | Admin white minimal shared styling with no behaviour rewrite. Account contains previous company fields/actions and account controls; removed Company URL and callers. Billing is sole invoice list and detail location, campaign links preserve the selected campaign. Tests for navigation, account permissions and invoice links; staff drawer screenshot and existing shell checks. |
| C9 Records/integration | REQ-220–229, D120–129/current Q rows, architecture v1.149 with placement/data/security amendment, one final evidence receipt. REQ-196 remains NEEDS ANSWER with one parked note. Rebase onto Lane A final commit before final review, rechain migration, regenerate three API baselines together, run native R14-B fixtures and touched tests/type/lint/build on integrated tree. Final privacy, security and consolidated minimal-change PASS; complete desktop/phone empty/populated before/after screenshot set sent to orchestrator for taste judgment before final commit. |

## Implementation checkpoints

Pre-final review preparation (orchestrator, 20 Oct): run privacy and security
reviews now on the complete current diff, then re-check the integrated delta
after Lane A FINAL. Three active agents are justified for this bounded round:
the implementer alone edits files; two read-only specialists assess disjoint
privacy and security questions and return separate reports. Neither edits source,
runs Docker, or starts another delivery workflow.

Final Areas-only copy check: preserve Lane A D116's removal of bonus zones and
its caller updates. No Extra area/bonus legend or pill remains. The page title
is Areas; the intro says: Draw the areas where you want your advert seen. Mark
any places cars should avoid. No zone-editor listener change.

### Prepared final integration sequence

Final integration (23 Oct): A FINAL plus its current-job correction is
9d6f663d3cc7acb923adfcb4bd6fd50f164df618, following 589cbc9d.
A fresh full binary patch hash-matches the retained stash before integration.
B migration 0117_req220_artwork_links follows 0116_campaign_reports (12 linear
revisions). A's final report APIs, immutable files, image/PDF types, date-derived
finished and removals prevail. Reports navigation is preserved. The performance
adapter requests the default seven Africa/Lagos dates with no period query;
zero empty days remain zero, suppressed days remain null, and today is partial.
Final baselines/checks/build/captures, taste and post-taste reviews PASS; evidence is recorded in the single receipt.

Earlier integrations preserved S1, B1b/B6 and B7/B2/B4/B5 with verified external
binary patches and retained uniquely identified stashes. No behaviour-changing
resolution was made in A's staff payout/correction/privacy/check screens.

Round 1 (23 Oct) found A's current-job count projection still uses write statuses
and omits the promised derived finished. A's 9d6f663d correction is integrated
without conflicts; B keeps readiness checks and shows genuine unknown status
quietly. One clean final build/capture refresh follows. Visual corrections cover continuous
rails with sticky contents, collapsed suppressed charts, uncropped artwork with
labels outside it, map captions outside real shapes and safe-area nav clearance.
No money, privacy or API behaviour changes are authorized by these corrections.

- Preserve the current tracked/untracked B tree in a fresh verified binary patch
  and uniquely named stash, then integrate A's correction commit. Keep both
  lanes' records and A's removals; do not bypass driver readiness.
- Preserve both lanes' REQ/D rows, A architecture v1.148 and B v1.149, plus the
  exact authorized disclosure inventory entry and QR-only Caddy exceptions.
  Integrate A's artwork guard/error, image/PDF types, lifecycle, bonus removal,
  roles and D118 Nigeria-day series; remove superseded B-side assumptions.
- Read A's single Alembic head. Rename/re-number B's current
  0117_req220_artwork_links.py after A's final sequence, set revision and
  down_revision to a single linear chain, and update the head/count fixture.
  Recreate only disposable cardvert_req220b before upgrading the new chain;
  do not apply revised ancestry to the previous synthetic database stamp.
- Regenerate openapi.json and docs/api/openapi.snapshot.json together with
  python scripts/update_openapi_snapshot.py, then generate
  frontend/src/lib/api/schema.d.ts through npm run api:types. Refresh architecture
  inventory using scripts/update_architecture_inventory.py and preserve A's
  current audit-route registry removals alongside B's website mutation entry.
- Verify one head, clean local upgrade, the three baselines, current-state and
  audit-route checks; rerun the four touched R14-B fixture files, relevant
  backend/frontend checks and a clean production build. After taste PASS, run specialist delta
  rechecks alongside remaining final tests, then the one consolidated minimal-change
  review until PASS. Complete every C1–C9 row in the single receipt.
- Final isolated-browser pass covers all roles, phone/desktop, empty/populated,
  artwork image/PDF/no-art, pre/post-production entry points, QR and live refresh.
  Obtain orchestrator taste judgment on that complete post-rebase set before
  the authorized explicit-path commit. Remove only B's database/container/profile.

20 Oct orchestrator taste amendment (D129, already authorized): remove Home's
campaign selector; compact each card into artwork/map, status/name, dates/area/cars,
Day X of Y and one figures strip/80px chart. Put Refresh within populated maps.
Whole hero vans, wrapped names; campaign map/performance before assets, then
unchanged Booked, Details/Manage. One change-request entry, thumbnail/PDF tile for
every asset, no repeated scan footer, Dates and Running/Finished consistently.
Driver image fills panel; existing frozen geometry may add a real area/Avoid map,
without an endpoint. Admin uses existing mark. Verify scrolled sidebar before
altering it. Diagnose Wuse withholding/failure honestly and integrate D118 before
populated figures pass; no advertiser UTC copy. One shared installed-package
same-origin worker bootstrap via supported setWorkerUrl, bundler-emitted asset
preferred; no listener change. Production proof covers live map and zone editor,
actual polygons/dots, CSP/worker requests and resolution check. Apply offline after
the current slot; no extra capture before the final post-rebase pass.

Worker packaging conditions (orchestrator, 20 Oct): measure the actual Next 16
production asset first. Only if its worker/sibling resolution fails, use the
documented automatic copy of both installed-package worker/shared modules.
Derive the output directory version from installed package.json, fail the build
if either source is absent, ignore generated output, and cover every build entry
(CI, frontend Dockerfile and deployment templates). Runtime public/ must contain
both files. No CDN or manual vendor copy; existing worker-src self/blob policy
must suffice. Prove a clean production build draws real zone-editor/live-map areas
and live dots with no worker/shared 404, and record the measured choice.

1. Record decisions and inspect existing component/API authority; independent plan review
   (gpt-6.1-sol, high, owner override of the skill's default medium).
2. Advertiser/admin shared look, Account/Billing consolidation and date helper; capture before states.
3. Add isolated QR link/daily-count table + migration, endpoints, download/redirect frontend route;
   add isolated delayed-positions endpoint; reuse governed results for performance cards.
4. Integrate Lane A first commit before driver design; integrate final commit before final tests/reviews.
   S1 `be1fc9de8050e180888089cfd6f5f08bbd2761e3` rebased before the first driver edit;
   restored Lane B work with both lanes' decision/request rows preserved. Weekly
   photo authority is ready/installation_required/unavailable; no daily proof UI.
5. Verify every criterion. Privacy/security reviewers run alongside final tests, sequential reviewer
   slots if needed to respect two active workers. Consolidated minimal-change reviewer assesses
   integrated source and criterion evidence; correct/review until PASS. Write one final receipt,
   obtain orchestrator's screenshot judgment, commit explicit paths as configured identity.

## Risks and operational limits

Orchestrator clarification (20 October, not an owner decision): PNG/JPEG/WebP
receive actual thumbnail/van placement; PDF has a file tile with name/date/badge
and Open artwork, neutral design space plus Preview shows image files. No PDF
renderer. Upload controls quietly suggest Add a PNG or JPG to see it on the car.
Lane A S22 removes unreachable video/html/text/other; coordinate the existing PDF
`other` representation with A, and retain an honest pre-integration fallback only.

### Plan review resolution (gpt-6.1-sol/high)

All five FIX findings accepted before implementation:

1. C3's server invariant is a **Lane A dependency**, confirmed by orchestrator.
   Lane A REQ-215/D116, built in 7c5b1952, guards creative create/update under campaign/production lock with direct
   API/race tests. Its409 CAMPAIGN_ARTWORK_LOCKED message is This campaign's artwork is locked. Ask Terrax to change it.; the screen uses the same copy. B's REQ-222/D121
   covers the screen only: `commercial.production_start.started_at` or active status
   displays Ask Terrax to change it, linked into existing support. B also handles
   the server's exact rejection in wizard error copy, without changing A's service.
2. C5 exact mapping: each campaign's existing `/report` via
   readCampaignPerformance supplies governed `totals.estimated_views` (null is
   unavailable). Home shows one performance card per shown campaign, never
   combining mismatched periods. It does not aggregate estimate or money totals.
   `/daily-metrics` `items[].distance_m`, by its returned date, gives the **distance
   driven per day for last seven days** chart, never daily car counts or trips.
   Cars on the road = number of anonymous positions eligible for C6's current
   driving projection, labelled with its ≥15-minute delay. Existing assignment
   counts are never substituted. Scans use new per-campaign daily aggregate totals.
   D118 now supplies exactly seven Africa/Lagos dates through partial today,
   oldest first, without period/pagination overrides. Empty days stay zero;
   suppressed days stay null. When any daily values are withheld the chart
   collapses to its honest message, with no empty axis or fake zero. No advertiser
   UTC note is shown. True permitted zero retains its chart and daily figures.
3. C6 registers `advertiser.campaign.live_positions` with existing governed
   disclosure inventory, then calls `require_governed_advertiser_output` and
   current campaign ownership. Existing legal/development authority remains;
   the owner-approved individual dots have their own delay/area/no-identity policy,
   no invented three-car floor. Existing `record_disclosure` stores only query/
   result hashes, tenant/campaign/policy/window (no coordinates/driver IDs), using
   explicit allowed policy, then commit before returning. Orchestrator grants B
   a narrow exception: add exactly `advertiser.campaign.live_positions` to
   DISCLOSURE_ROUTE_INVENTORY in app/services/disclosure.py and change nothing
   else there; keep this entry through rebase. Negative inactive-member/org and tenant
   tests required. Endpoint has no time, car, or history query; UI offers explicit
   refresh only, replaces dots, and never retains previous sets or draws trails.
4. Rank among points whose **recorded AND received** times are ≤now−15m,
   newest recorded_at, then received_at, then ping ID (internal only), one per
   vehicle. Apply ≥now−30m freshness, positive speed, target and exclusion tests
   **after ranking**, so a newer stopped/excluded point removes that vehicle.
   Recent ineligible backfill is ignored; continuous current reports do not hide
   valid delayed points. Test ties, stopped/excluded/new-outside, received cutoff.
5. Logging: inspect Sentry, Next route/proxy, Uvicorn formatter and edge templates.
   Route-specific API middleware/telemetry filtering belongs to new module with
   minimal registration, not a global observability rewrite. Verify synthetic
   scan IP/UA/URL absent from captured app logs and Sentry hooks; successful
   redirect follows committed daily increment, DB failure returns unavailable.
   Orchestrator-authorized narrow exception: B owns only a `/q/*` access-log
   exclusion in root Caddyfile, with no other path's logging or edge behavior changed.
   Orchestrator pre-authorization, 20 Oct: if a pinned-Caddy GET/HEAD probe
   confirms its deferred global header overwrites QR `no-referrer`, add the
   smallest `/q/*`-only winning header or global-header matcher exclusion.
   Otherwise change no header. Recheck GET/HEAD plus successful/outage scan log
   sentinels, and record the measured result in REQ-223/security review.
   Pinned 2.8.4 probe confirmed the overwrite: the `/q/*` winning header restores
   no-referrer on GET/HEAD. It also confirmed default proxy-error logs retain the
   synthetic scan marker during frontend outage. The initially approved
   `handle_errors` candidate kept non-QR access logs but suppressed their separate
   default ERROR diagnostic. Security re-review rejected that scope claim.
   Orchestrator approved replacing it with the tested named logger: only `/q/*`
   uses `qr_private`, whose error output is discarded. Keep access-log exclusion
   and immediate/deferred no-referrer/no-store headers. No global error handler.
   A frontend-down QR request retains Caddy's plain 502/empty body; this approved
   trade-off preserves other paths' ACCESS and original ERROR diagnostics.
   Rerun the strengthened repo-config probe, preserve before/candidate/final
   proofs and include this extension in the security reassessment.
   `/api/v1/qr/*` is internal: the edge's public API matcher only forwards health
   and webhook paths, and there is no frontend QR API relay at that path. Validate
   using the pinned Caddy image in a container. Security review must inspect this
   exception. Actual production edge logging proof remains an **unresolved release
   gate**, with no claim local checks prove deployed access-log behavior.

Map integration uses existing zone editor's MapLibre construction/configuration
and geometry validation in a read-only reusable campaign map. Unconfigured style
is the actual polygon schematic, labelled Campaign areas, no streets/landmarks;
provider/WebGL failure gives a truthful unavailable state and area names. Keep
AreaGraphic as a geometry-only accessible fallback where needed.

Orchestrator clarification, 20 Oct: D103/D104's existing per-campaign Booked
figure, progress bar, percent and over-budget colour remain exactly unchanged.
Only its wallet icon is a visual addition. Day X of Y is separate; the decision
forbids adding a new usage/delivery warning. Home has no Booked tile. No budget
tracker, relabel or other change is authorized while that topic is parked.

The delayed-dot feature reduces disclosure but is not a claim of anonymisation for real users;
existing real-use privacy gates remain. Only synthetic data in local checks. Actual driver positions
must never enter logs/screenshots. Public redirect scan requests require disabled access logging
at the new local frontend/API route and a documented path-specific edge-log exclusion; existing
request telemetry must be inspected by the security reviewer. Stored URLs are never server-fetched.
QR uses an established local encoder rather than an external QR service; no provider call.
The final QR public origin uses existing app-origin configuration and fails closed if invalid;
no local test hostname is hard-coded into shipped QR downloads.

Docker cv-req220b is capped at 2.5 GiB for the final slots, database cardvert_req220b only. Acquire the shared file
lock atomically when absent; release within about 45 minutes after stopping this container.
No Python/Node on host: dependency docs/checks use container runtime. If another lane holds
Docker, continue static implementation. Clean up only this lane's container/database.
External CI/merge and MapTiler remain controller/external gates; no false DONE claim.
Measured Next 16.4 webpack output retains the worker's relative shared-module
import but omits that sibling. The approved fallback therefore copies both files
from the installed MapLibre package in prebuild/predev, into a git-ignored public
directory named from that package's version. Missing source files fail the build.
CI, Docker and Playwright builds use npm run build; runtime images copy public.
No deployment template builds Next directly. Verify clean production assets and
all three map surfaces with the existing same-origin worker CSP.
The generated architecture inventory classifies the new public `/api/v1/qr/*`
namespace; refresh that inventory after the final migration re-chain. Current
role/product route docs and the existing Billing e2e callers follow the Account move.

Orchestrator-confirmed browser exception, 20 Oct: use the documented isolated
Edge/CDP workflow from req208-tools / brand-look-mockup-tools for localhost only,
with synthetic accounts/data, no personal profile or sign-ins. Close that browser
and remove only its verified throwaway profile directory after testing. T3's
unidentified Default profile and unavailable CUA inventory are not used.
