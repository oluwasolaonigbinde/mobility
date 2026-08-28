# PKG-08 W4-02A governed maps and report evidence

- Date: 2026-08-28
- Base: `1e194cfb789cb8d1418d56d12424da2584ca0bd5`
- Branch: `feat/pkg-08-w4-02a-governed-maps-report`

## Delivered contract

- Advertiser Campaign Performance Analysis requires a reproducible immutable
  measurement run and validates the run/result title, schema, period, formula,
  method, proof hash, required metric set, score provenance and conditional-ROI
  decision before rendering any report value.
- Performance-only runs contain no ROI section, label, value or explanatory ROI
  copy. A conditional financial result appears only when the frozen result says
  `INCLUDE`, the run is `roi_enabled`, and the result method revision equals the
  run's non-empty ROI method revision. Synthetic results remain visibly marked.
- The advertiser map re-authorizes through the frozen report after campaign and
  zone reads. Only target-zone geometry whose identifier and safe name occur in
  the ready disclosure-cleared ranking reaches the client component. Suppressed,
  stale, empty, unavailable, inconsistent and unauthorized results render no map.
- MapLibre defaults to an inline local schematic with no network source. Startup,
  style, geometry/layer, post-load and readiness-timeout failures hide the map and
  show an explicit unavailable state. A configured production provider is never
  claimed by the local default.
- Admin planning monitoring renders the same server-issued high-zone projection
  and now exposes its measurement run, exposure formula/input and source-segment
  version/snapshot provenance. Advertiser projections keep zone UUIDs and source
  segment metadata hidden.
- The old advertiser heatmap action and client heatmap request path are removed.
  Admin raw-route access, its purpose-scoped server authorization and audit
  authority are unchanged.

Unchanged: Package 5 measurement calculation, disclosure thresholds/history,
segment/recommendation/score issuance, report and zone-insight APIs, public
contracts, database schema and migrations; Package 7 PWA behavior; export,
deployment and pilot work owned by W4-02B/W4-03A/W4-03B.

## Adversarial boundary matrix

| Boundary         | Break case                                                                      | Fail-closed evidence                                                               |
| ---------------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Frozen authority | Missing/mismatched run, result, period, method, proof, metric set or score hash | Whole analysis withheld with a distinct integrity/unavailable state                |
| Conditional ROI  | Performance run, absent value, contradictory decision or method revision        | No ROI text for omission; inconsistent inclusion withholds the report              |
| Disclosure       | Suppressed/stale/empty insight or ranked-zone name/geometry mismatch            | No geometry is serialized or mounted; state copy remains distinct                  |
| Tenant/role      | Different advertiser organization or non-advertiser role                        | Non-enumerating `404` or role redirect; no campaign title/value/geometry           |
| Map runtime      | Constructor, style, layer/geometry, post-load error or 3-second timeout         | Canvas hidden and explicit map-unavailable alert shown                             |
| Provider gate    | No production basemap account/licence                                           | Local inline style works without a provider; UI makes no production claim          |
| Raw routes       | Advertiser visibility or map navigation                                         | No raw-route endpoint is called; existing admin-only server authority is unchanged |

## Observed red/green and focused evidence

The initial focused frontend run failed as expected because the frozen authority
module and governed map projection did not exist, the map still called the legacy
heatmap/latest-state paths, the default style referenced public CARTO resources,
and performance/suppression copy still contained ROI wording. The added tests then
passed after implementation.

- Frontend focused authority/map/admin component set: 21 tests across 8 files
  passed, including 8 map projection/lifecycle cases across 2 files.
- Frontend typecheck, scoped lint and scoped formatting pass.
- Frontend production build passes and emits both advertiser report and map routes.
- Backend PostGIS focus covering measurement runs, zone insights, reports,
  heatmaps, disclosure, exposure scores and segments: 54 passed.
- Backend Ruff focus passes. A preliminary SQLite-only run exposed one existing
  second-precision stale-zone timestamp limitation; the same intended PostGIS
  set passes and no Package 5 authority was changed for that test-only artifact.
- Isolated browser journey: performance-only report shows all three frozen metric
  classes and no ROI text; a newly issued fully qualified synthetic ROI run shows
  `100.00%` and `synthetic-roi-v1`; an empty zone projection mounts no map; a
  cross-tenant advertiser receives a non-enumerating 404; an admin cannot enter
  the advertiser report route. The temporary database and servers were removed.

The clean-context post-build privacy/measurement/map review is `PASS`. Its
initial score-to-zone lineage, issued-rank ordering, admin reissue-provenance and
final-build evidence findings were corrected once, verified, and re-reviewed
with no remaining findings or verification gaps.

## Contract and live gates

No API schema, generated contract baseline, database model or migration changed.
`EXT-BASEMAP` still blocks a production-provider claim. `EXT-REPORT-METHOD` and
`EXT-LEGAL-PRIVACY` still block live issuance/use. This checkpoint proves only
provider-neutral local and synthetic performance/conditional-ROI behavior; it
does not issue CSV/PDF, deploy, execute a pilot or claim real campaign results.
