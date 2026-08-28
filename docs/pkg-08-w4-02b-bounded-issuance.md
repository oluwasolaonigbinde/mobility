# PKG-08 W4-02B — bounded CSV/PDF issuance evidence

Date: 2026-08-28
Base: `b64d07a0d7dcf97eb2654345ce55642165a570cf`
Branch: `feat/pkg-08-w4-02b-bounded-issuance`

## Delivery contract

W4-02B adds asynchronous CSV/PDF issuance from one exact reproducible
`MeasurementRun` and its W4-02A Campaign Performance Analysis projection. An
owner/manager advertiser or active administrator can request an initial
issuance or an explicit append-only reissue. The request freezes a positive
allowlist of measurement metrics, conditional-financial decision, exposure
score, safe high-zone labels, suppression/disclosure state and provenance. A
database-derived worker claim produces both bounded artifacts; neither is
published until both private objects and hashes are verified.

Important break cases are tenant/role or membership loss, changed/revoked
privacy or report-method authority, non-reproducible source hashes, stale score
or disclosure projection, partial/private-object failure, lease expiry,
concurrent/replayed request identity, tampered object metadata, renderer bounds
and unsafe spreadsheet/PDF text. These cases fail closed without exposing
artifact content or existence.

Unchanged behavior: W4-02A report/map presentation, Package 5 measurement and
disclosure calculations, W4-01 PWA behavior, raw-route isolation and all
person-level/segment export gates. Segment export remains disabled. No live
provider, method, privacy approval or basemap fact is supplied.

## Plan review and reconciliation

The independent clean-context plan review returned `REVISE`: the existing
measurement-run, uploaded-file and audience-delivery models could not
truthfully represent a durable generated-artifact lifecycle. The authorized
scope amendment was reconciled once as follows:

- migration `0071` adds the smallest issuance/job row plus immutable artifact
  children and extends `StoredFile` only for generated `report_export` objects;
- the database row, not a broker response, is the due-work/lease/recovery
  authority;
- the request persists the exact W4-02A composed allowlist rather than reading
  mutable latest state in the worker;
- run-lineage and actor/request advisory locks plus database uniqueness govern
  replay, initial issuance and explicit version allocation;
- request, worker publication and download independently reauthorize current
  tenant/role and live/synthetic gates;
- deterministic object keys and no-overwrite storage semantics converge after
  a lost response or partial write, while pair publication is atomic in the
  database;
- renderer bounds, formula-prefix protection, PDF text escaping/wrapping and
  fixed metadata close value-level safety cases.

## Adversarial-boundary matrix

| Boundary | Invariant and break case | Evidence |
|---|---|---|
| Identity / concurrency | Same actor + request identity replays one fingerprint; changed reuse conflicts; initial and reissue versions serialize on the frozen run. | PostgreSQL concurrent `asyncio.gather` test plus replay/conflict/reissue tests. |
| Ordering / recovery | DB commit is sufficient for pickup; expired processing leases recover; retry never publishes a partial pair; terminal recovery appends a version. | Worker partial-write, due-time, lease-expiry and terminal-reissue tests. |
| Measurement / money | Performance-only bytes contain no ROI wording; financial result is emitted only for a frozen consistent `INCLUDE` decision. | Performance-only and synthetic qualified-ROI golden CSV/PDF assertions. |
| Privacy / authorization | Tenant, active membership, owner/manager/admin role and current privacy/method authority are checked at request, publication, status and download. Safe snapshot has no routes, people, private links or geometry. | Cross-tenant, viewer, revoked membership, changed-gate, non-synthetic approved-configuration, generic-file-bypass and raw-trip-ID assertions. |
| Storage / tamper | Issued evidence uses shared private `StoredFile`; exact size/type/hash/object key must agree, linked file rows are immutable and deterministic writes cannot overwrite different bytes. | Tamper, missing/partial object, storage retry, ORM/SQL immutability, real MinIO conditional-write race and migration constraints/tests. |
| Rendering / bounds | CSV cells neutralize formula prefixes and controls; fixed input/field/row/output/page limits bound memory and PDF work; PDF has no active content or external fetch. | Renderer unit bounds plus Poppler `pdfinfo`, text extraction and rendered PNG visual inspection. |
| Migration / contract | Populated evidence cannot downgrade; frozen issuance/artifact authority cannot mutate/delete; all §9 baselines move together. | Real PostgreSQL up/down/re-upgrade, trigger, populated-downgrade, autogenerate-empty, OpenAPI tests and byte-stable regeneration. |

## Implementation authority

- `report_issuances` persists organization/campaign/run/requester identity,
  request and snapshot fingerprints, source hashes, schema/renderer/method/ROI
  decision, append-only version lineage and bounded worker state.
- `report_artifacts` is immutable and binds exactly one CSV and one PDF to
  generated private stored-file rows.
- Each artifact embeds issuance/version/schema/renderer/creation-authority,
  run/input/result/proof/report hashes, method/formula provenance and the
  disclosure projection identity. The API returns deterministic content hashes.
- Report exports are excluded from generic stored-file reads/downloads; only
  the report-aware endpoint can reauthorize and presign them.
- The advertiser report page persists the client request identity before POST,
  replays a lost response, polls through TanStack Query, withholds incomplete
  pairs and offers explicit append-only reissue.

## Verification evidence

Red evidence:

- backend renderer test initially failed with `ModuleNotFoundError` before the
  implementation existed;
- frontend report-panel and route suites initially failed to resolve the
  missing component/routes;
- the first PDF PNG inspection showed clipped provenance lines, after which
  wrapping and the readable document projection were added and re-rendered.

Green evidence:

- focused backend/PostgreSQL aggregate: `86 passed, 1 skipped` (report
  rendering/issuance, migration/autogenerate, stored files, worker registry,
  OpenAPI and MVP hardening);
- focused report UI/BFF: `14 passed`; typecheck, scoped ESLint and Prettier pass;
- preserved R14-B capability/queue/tracker fixtures: `99 passed` (existing
  React `act` diagnostics only);
- production Next build passes and lists all three same-origin issuance routes;
- all three §9 baselines regenerate byte-stably after synchronization;
- real MinIO `S3StorageProvider` integration passes first write, identical
  replay, changed-byte conflict and concurrent different-byte same-key race
  (`1 passed`, exactly one immutable winner);
- PDF QA: PDF 1.4, A4, one page, no JavaScript/forms, successful Poppler render
  and extraction, visually inspected with no clipping, overlap or broken page
  transition;
- the synthetic issuance regression journey covers request → replay → worker →
  status/download for performance CSV/PDF, qualified synthetic financial
  output, suppression rendering, partial/failed object recovery, tamper,
  cross-tenant/viewer/revoked denial and generic-file-route denial.
- a separate non-synthetic approved-configuration simulation covers request →
  worker → status → download and proves that revoking the configured report
  method authority hides both status and download. It is test evidence only,
  not a claim that the live external approvals exist.

Post-build review:

- the clean-context privacy/measurement/security review found exact-request
  retry, status-time authority recheck and linked stored-file immutability gaps;
  each was reproduced and corrected with focused regression evidence;
- its remaining provider-boundary evidence gap was closed with the pinned real
  MinIO integration above; the reviewer then returned `PASS` with no remaining
  P0–P2 finding.

## External and unchanged gates

`EXT-REPORT-METHOD` and `EXT-LEGAL-PRIVACY` still gate every first live
request, worker publication and download. Synthetic issuance requires the
explicit test environment and disclosure-test switch. Q31 person/segment
export remains disabled. `EXT-BASEMAP` has no relationship to artifact
generation. No live issuance is claimed.
