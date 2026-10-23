# REQ-220–229 client feedback evidence

Status: implementation, screenshot taste, final privacy/security and consolidated
minimal-change reviews PASS; own runtime cleanup complete. This is the one
receipt; it does not contain the SHA of its own commit.
Contract: [approved delivery contract](../plans/req220-client-feedback.md).

## Integrated source

- Approved design base: `1a7b5757`; Lane A S1 `be1fc9de` preceded driver edits.
- Lane A FINAL and correction: `9d6f663d3cc7acb923adfcb4bd6fd50f164df618`,
  following `589cbc9d`. Fresh verified binary patches and retained exact stashes
  precede each integration. The last integration was conflict-free. No Lane B
  edit to `app/api/v1/navigation.py` or `app/schemas/navigation.py`, no readiness
  bypass, and no behavioural conflict resolution in Lane A's staff screens.
- `0117_req220_artwork_links` follows `0116_campaign_reports`: one head, 12 linear
  revisions. A fresh isolated database applied the full chain. Both OpenAPI JSON
  baselines and TypeScript schema were regenerated after the final integration.
- The narrow existing-file exceptions are the one disclosure inventory entry
  and QR-only Caddy logging/headers. Report presentation was separately granted
  by the orchestrator on 23 October; report logic/API/validation/dates are intact.

## Criterion-by-criterion evidence

| Criterion | Evidence and technical verdict |
| --- | --- |
| C1 Brand | PASS: approved source assets, Home/shell tests and 60 desktop/phone PNGs, populated/empty. Thirteen affected report/Home/staff captures refreshed after round 2. Orchestrator taste PASS after round 3. Whole vans, wrapped names, compact artwork/map cards, wallet/megaphone icons; no Home money total. |
| C2 Driver | PASS: S1 integrated first, real frozen artwork and target/Avoid geometry. Both widths show actual Start trip after A's authoritative current-job correction. Existing trip/readiness logic retained. Phone top/bottom viewports prove content bottom 748px clears fixed nav top 785px, with 96px bottom padding. Driver/job and native fixture tests pass. |
| C3 Assets | PASS: current private image/PDF, date, approval/rejection reason, secondary thumbnails, van image/neutral PDF preview and one support entry captured. Actual local upload/replacement before production and post-production create rejection were verified: 409 CAMPAIGN_ARTWORK_LOCKED, exact A copy. Actual Ask Terrax form posts to the existing support path. No new approval workflow. |
| C4 QR | PASS locally: actual save form, downloadable SVG, stored-target-only GET302, attacker query ignored, GET+1/HEAD+0; aggregate atomic counters and cross-worker Redis limiter tests. Scan IP/UA sentinels absent from API/web/edge logs, SDK in-memory telemetry filtering and pinned Caddy success/outage probes pass. Final security PASS; deployed-edge proof remains a release gate. |
| C5 Performance | PASS: A D118 default seven Africa/Lagos dates, partial today, permitted zero retained and suppressed null retained. Actual permitted campaign shows estimated views 544,140 and populated daily chart; Wuse shows the honest withheld explanation. Suppressed chart has no empty axes/gap. No CTR/ROI/website visits. Report presentation and help copy match each portal; logic unchanged. |
| C6 Live dots | PASS locally: real area/delayed dot, refresh-to-empty removes prior dot, restore shows current snapshot. Ownership/current membership/governance, time edges, latest-outside, Avoid, ended/stale/stationary, response allowlist and salted audit tests pass. No identity/time/car filter/trail. Final privacy PASS. |
| C7 Dates | PASS: Nigeria-day Day X of Y and simple campaign timeline on advertiser/staff list/detail; scheduled/finished/extension boundaries tested. Running/Finished wording consistent. Existing per-campaign Booked figure, bar, percentage and over-budget colour are inherited unchanged; only the wallet icon is B's. |
| C8 Admin/S25/S26 | PASS: white shared staff shell, existing Cardvert mark, operations and drawers preserved. Full-height rail backgrounds and sticky inner rails verified at scroll (top0/bottom1000). Account contains company fields; obsolete Company/campaign-invoice routes and callers removed; Billing-only links and permissions tested. Billing look retained. |
| C9 Records/integration | PASS: REQ/D/topic/architecture1.149 records, A final integration, linear migration, three baselines/native fixtures and focused checks below. Final privacy/security and consolidated minimal-change PASS; own runtime cleanup complete. No progress.md edit. |

## Runtime source and screenshots

Evidence root: `C:\Users\Dell\.t3\worktrees\mobility\req220-screens\`.
Original `before/` screenshots are retained; accepted map diagnostics and
before/candidate/final Caddy proofs remain in `diagnostics/` and `edge/`.
The complete final set is `final/`: 60 PNGs, QR SVG and capture evidence.
Round 1 is preserved separately in `taste-round1/`.

Round 2 full pass: 23 Oct 17:34:28–17:39:13Z, frontend fingerprint
`9ab172b315226d0a4fcecde0b99fb3a3d3f68ae236dcae438a647cb9be1f5d9e`,
build `_YaTmGIY6hOCTOfh5kAm4`. No page errors, broken images, horizontal
page overflow or external requests. All worker/shared module responses are 200.
Round-2 runtime details are `req220-tools/round2-capture-evidence.json`.

Round 3 refresh changes only the 13 affected Home/report/staff PNGs, per the
orchestrator's instruction. Frontend fingerprint
`e1720cdd11176742b031dc4075a2b64a39340f987997e89d8afa56f99449e83b`;
build ID, source-file comparison and runtime-only config are recorded in
`req220-tools/round3-build-id.txt` and `round3-frontend-source.json`.
All 764 frontend source files match the build copy except the documented local
single-worker/standalone/disabled-indicator Next config. Captures have no errors,
overflow, broken images or external requests. `round3-capture-evidence.json`
records the real report controls and opaque staff tabs (header/tab edges differ
by 1px, overlapping, with no exposed gap on desktop or phone).
The orchestrator granted taste PASS and authorized a final report date/kind
presentation tidy verified by tests only, with no further capture required.

## Map root cause and measured repair

The original 1a7b5757 production zone editor was blank in the same isolated
Edge/Swiftshader harness despite a 729×520 canvas: its worker resolved to the
page URL. The baseline diagnostic proves a pre-existing production defect.
No style.load or zone-editor listener change was made.

Next16 webpack emitted the worker but omitted its relative shared-module sibling.
The measured bundler attempt is retained. The approved prebuild/predev fallback
copies both modules from the installed MapLibre package into an ignored,
package-version-derived public directory. Missing source fails loudly before
partial output. CI/Docker/Playwright use npm run build; runtime images copy
public. Same-origin worker CSP is retained, with no CDN or provider fetch.
All three maps draw real areas: live map/dot, driver target/hatched Avoid and
zone editor. The local basemap style is unset; MapTiler remains external REQ-050.
The small Avoid shape is its real geometry.

Final layout resize/refit uses the existing load event and observes the actual
map container. The touched test verifies refitting on size changes and cleanup.
Pixel proof in `req220-tools/round3-map-padding-proof.json` shows both Home maps
at both widths have 23–24px top/bottom outline margins and larger side margins.
Captions/legends sit outside map shapes. No fake roads, landmarks or positions.

## QR security proof and trade-off

Pinned Caddy2.8.4 initially overwrote no-referrer via its deferred global header
and logged QR outage markers. The first handle_errors candidate also suppressed
non-QR ERROR diagnostics and was rejected. The approved named QR error logger,
QR access-log exclusion and scoped winning headers preserve GET/HEAD302
no-referrer/no-store and zero QR success/outage markers. Non-QR /health200 ACCESS,
502 ACCESS and original ERROR diagnostic remain. QR frontend outage is the
approved 502 with empty body. No other path's headers/logging are changed.
`/api/v1/qr/*` is internal, not externally edge-routed.

Final repo-config probe and raw log: `req220-tools/round2-caddy-runtime-proof.json`
and `round2-caddy-runtime-probe.log`. Actual app log/Sentry SDK proofs:
`round2-actual-qr-log-proof.json`, `round2-sentry-sdk-proof.json`; SDK transport is
in-memory and made no network call. Stored destinations are never server-fetched.
Hosting/deployed-edge log proof remains an explicit release gate.

## Checks and review gates

- Final integration: 403 frontend cases in 48 focused files; R14-B129 in four
  native fixtures; TypeScript, scoped lint/format, architecture/audit6 and 62 real
  PostgreSQL/PostGIS/Redis cases PASS. Logs: `req220-tools/round2-*.log`.
- Round-3 presentation/resize delta: 67 cases in nine affected files, including
  A's report tests; typecheck, scoped lint/format and clean production build PASS.
  Logs: `req220-tools/round3-*.log`. No API contract or native changes in this delta.
- Seven new Python modules have zero basedpyright errors/warnings with an isolated
  empty baseline; the repository baseline is unchanged. Scoped Python style
  passed before taste; no Python source changed during presentation corrections.
  Full Python baseline is not claimed green (A reports inherited errors).
- Final date/kind-only tidy: 36 tests in three affected files PASS. Existing date and vocabulary helpers are reused; stored dates, timezone/API handling and report logic are unchanged. The owner explicitly required tests only, with no new capture/taste round.
- Independent plan: gpt-6.1-sol/high; five valid findings addressed before build.
- Pre-integration full privacy/security reviews: PASS, gpt-6.1-sol/high, on the
  be1fc9de-based B diff. Final integrated privacy and security rechecks: both PASS on 9d6f663d plus the complete B diff, gpt-6.1-sol/high. No corrections required; specialists started no infrastructure and made no provider calls.
- Consolidated minimal-change review: PASS, gpt-6.1-sol/high, on the complete
  integrated diff, C1–C9 evidence and specialist verdicts; no actionable findings.
  Its staging reminder was checked: all reviewed working-tree versions are
  staged together before the explicit-path commit.

## Resource use, cleanup and gaps

The own container is capped at 2.5GiB; checks use one process/worker at a time.
Windows Available, not FreePhysicalMemory, gates starts and is sampled between
steps. No heavy API/browser runs during production builds. Round-2 hold
17:20:33–17:39:55Z (19m22s), Available1574MB at release. Round-3 hold
17:43:37–17:50:00Z (6m23s), Available1570MB at release. Every release stops only
cv-req220b before deleting its exact-token lock. Only the isolated task Edge
profile was opened, closed and deleted. No personal profile or sign-in.
Final display-tidy hold ended 17:55:26Z, Available1320MB. The own database cardvert_req220b and container cv-req220b are removed; exact-token lock released. Cleanup proof is req220-tools/final-cleanup.json.

No push, deploy, provider calls, other database/container, main checkout or
forbidden-file access. Remaining external gates: MapTiler/real street basemap,
production-edge/hosting logging, real-use privacy/legal approval, physical/native
release evidence and full CI/merge. REQ-196 stays NEEDS ANSWER; budget discussion
is parked. These local checks do not close those release gates.
