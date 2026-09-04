---
source_surface: Codex
conversation_id: 01a05c2b-ad63-70f2-8dac-d64b3e4c9264
displayed_title: Audit Frozen Report Authority
actual_model: gpt-5.6-sol
reasoning_effort: xhigh
retrieved_at: 2026-09-01
collection_state: COLLECTED
completeness: complete final answer
redactions: none
audited_ref: 637841d95493bcc24334356da42097fa53a5d16f
---

# Audit Frozen Report Authority

> Preserved final answer. It is source evidence, not an accepted finding or
> remediation decision.

## Verdict

**B. We have part of it, but there is a problem.**

The pinned revision has a strong frozen-artifact pipeline, but on-screen, CSV and PDF results do **not** consistently represent the same authority. The principal failures are:

- Screen aggregates and export metrics can select different source cohorts.
- Required ROI assumptions are not disclosed beside the result.
- CSV and PDF omit different provenance and disclosure fields.
- Retry, reissue and artifact-retention edge cases are incomplete.

No live-data exposure is currently demonstrated because the production method, privacy, storage and basemap gates remain closed.

## Revision verified

GitHub reports `feat/pkg-04-build-first` at exactly `637841d95493bcc24334356da42097fa53a5d16f`: [branch reference](https://api.github.com/repos/oluwasolaonigbinde/mobility/git/ref/heads/feat/pkg-04-build-first), [commit](https://github.com/oluwasolaonigbinde/mobility/commit/637841d95493bcc24334356da42097fa53a5d16f). GitHub marks the commit unsigned.

I inspected only the commit-addressed archive—no clone and no `master` inspection. Task title: `Audit Frozen Report Authority`.

## Report-authority pipeline

```text
Admin-issued measurement run
  → immutable input/result/proof/report manifests
  → governed advertiser screen
  → owner/manager/admin issuance request
  → frozen issuance snapshot and authority fingerprint
  → lease-based worker renders CSV + PDF
  → both private objects verified, then atomically published
  → current authorization + full object hash check before download
```

- Measurement runs verify canonical input, proof, report and reproduced result hashes: [app/services/measurement.py:146](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/measurement.py#L146-L157). PostgreSQL prevents run mutation or deletion: [alembic/versions/0063_measurement_runs.py:167](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/alembic/versions/0063_measurement_runs.py#L167-L184).
- Issuance requires an active user, active organization, matching campaign and owner/manager membership, or an active admin: [app/services/report_issuances.py:199](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/report_issuances.py#L199-L246).
- Privacy and reporting-method authority is fingerprinted before rendering: [app/services/report_issuances.py:88](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/report_issuances.py#L88-L161).
- The worker rechecks scope, run hashes, snapshot hash and authority before writing both artifact records and marking the issuance ready in one transaction: [app/services/report_issuances.py:706](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/report_issuances.py#L706-L864).
- Download reauthorizes the issuance and matches artifact, stored-file and object metadata: [app/services/report_issuances.py:956](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/report_issuances.py#L956-L1024). The S3 adapter reads the complete object to recalculate SHA-256: [app/adapters/storage/s3.py:91](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/adapters/storage/s3.py#L91-L116).

## Cross-format consistency matrix

| Boundary | Screen | CSV | PDF | Result |
|---|---|---|---|---|
| Exact run identity | Shows run and truncated hashes | Embeds run/result/proof/report | Embeds run/input/result/proof/report | Partial |
| Core performance totals | Mixes result manifest with a separately frozen report snapshot | Result manifest | Result manifest | **Fail** |
| ROI omission | Correctly omits failed gate | Correctly omitted | Correctly omitted | Pass |
| Qualified ROI | Percent, currency, method only | Ratio/percent/method; no currency | Ratio/percent/currency/method | **Fail** |
| ROI assumptions | Not shown | Not shown | Not shown | **Fail** |
| Disclosure uncertainty | Shown in zone panel | Omitted | Included | **Fail** |
| Rounding | Whole contacts/km; money may omit decimals | Exact source strings | Exact source strings | Undocumented divergence |
| Timezone | Deployment-default `Intl` timezone | Exact ISO offset | Exact ISO offset | **Fail** |
| Unicode labels | Preserved | Preserved | Replaced with ASCII `?` | **Fail** |
| Partial publication | UI requires exactly CSV+PDF | Published in pair | Published in pair | Pass on normal writer path |
| Current authorization | Rechecked | Rechecked at download | Rechecked at download | Pass |

## Confirmed defects

1. **High — the screen and exports use different source-selection rules.**

   Measurement inputs select impressions and payouts by the trip’s half-open `started_at` period: [app/services/measurement.py:342](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/measurement.py#L342-L383). The frozen screen snapshot instead filters impressions by `estimated_at` and payouts by `calculated_at`: [app/services/reports.py:241](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/reports.py#L241-L271), [app/services/reports.py:355](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/reports.py#L355-L370). Its range is also inclusive at the end, unlike the measurement run: [app/services/reports.py:80](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/reports.py#L80-L84).

   The page displays those snapshot aggregates while also displaying the measurement result: [frontend/…/report/page.tsx:97](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/frontend/src/app/advertiser/campaigns/%5BcampaignId%5D/report/page.tsx#L97-L165). A delayed impression or replacement payout can therefore produce contradictory totals on one page and between the page and exports.

2. **High before live ROI — required method disclosure is absent.**

   The governed methodology requires limitations, exclusions, corrections, attribution window and provenance beside ROI: [docs/measurement-methodology.json:66](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/docs/measurement-methodology.json#L66-L73). The issuance snapshot retains only ratio, percent, currency and method revision: [app/services/report_issuances.py:390](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/report_issuances.py#L390-L398). The UI likewise shows only percent, currency and revision: [frontend/…/measurement-authority.tsx:168](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/frontend/src/app/advertiser/campaigns/%5BcampaignId%5D/report/measurement-authority.tsx#L168-L180).

3. **Medium — CSV and PDF do not carry equivalent authority.**

   Exact-revision, in-memory execution confirmed:

   - Measurement input SHA: PDF yes, CSV no.
   - Exposure uncertainty: PDF yes, CSV no.
   - ROI currency: PDF yes, CSV no.
   - Unicode zone label: CSV preserved, PDF replaced.

   The CSV provenance omits the input hash: [app/services/report_rendering.py:46](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/report_rendering.py#L46-L90), while PDF includes it: [app/services/report_rendering.py:276](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/report_rendering.py#L276-L285). PDF uses lossy ASCII replacement: [app/services/report_rendering.py:207](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/report_rendering.py#L207-L209).

4. **Medium — expired worker leases can retry indefinitely.**

   Caught failures become terminal after three attempts: [app/services/report_issuances.py:666](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/report_issuances.py#L666-L703). Expired `processing` rows, however, are claimed without checking `worker_attempts`, and each claim increments it: [app/services/report_issuances.py:895](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/report_issuances.py#L895-L944). A process crash or unexpected exception can therefore bypass the advertised retry bound.

5. **Medium — authority changes or requester turnover can strand reissuance.**

   Once any issuance exists, a new request must supply the exact latest ready/failed parent: [app/services/report_issuances.py:475](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/report_issuances.py#L475-L503). Changed authority fingerprints hide the old status as `404`: [app/services/report_issuances.py:619](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/report_issuances.py#L619-L628). The UI offers reissue only when it successfully receives a ready or failed issuance, leaving no recovery after that `404`: [frontend/…/report-issuance-panel.tsx:236](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/frontend/src/app/advertiser/campaigns/%5BcampaignId%5D/report/report-issuance-panel.tsx#L236-L258).

6. **Medium — failed jobs can leave private orphan objects.**

   CSV and PDF are written sequentially before the database transaction: [app/services/report_issuances.py:752](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/report_issuances.py#L752-L767). A terminal failure after one write leaves that object unregistered and without a report-specific cleanup path.

## Privacy and security implications

- No cross-tenant download or generic-file bypass was found. Generic advertiser and admin file routes explicitly exclude `report_export`: [app/services/stored_files.py:907](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/services/stored_files.py#L907-L973).
- Revocation blocks new status and download requests, but an already-issued presigned URL remains usable until expiry—60 seconds by default: [app/core/config.py:85](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/app/core/config.py#L85-L96).
- Published artifacts and linked stored-file records cannot be deleted under migration `0071`: [alembic/versions/0071_report_issuances.py:213](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/alembic/versions/0071_report_issuances.py#L213-L240). This preserves evidence but leaves retention/withdrawal unresolved.
- Measurement-output retention is explicitly unapproved: [docs/privacy-register.json:169](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/docs/privacy-register.json#L169-L173).
- No advertiser-facing copy claimed verified views, unique reach or causal attribution. The qualified ROI surface is nevertheless too terse to meet its own attribution-disclosure contract.

## External method, storage and basemap gates

| Gate | State | Consequence |
|---|---|---|
| `EXT-REPORT-METHOD` | Missing | Blocks first live report and any live ROI methodology |
| `EXT-LEGAL-PRIVACY` | Missing | Blocks live disclosure, retention and DSR authority |
| `EXT-STORAGE-PROVIDER` | Missing | No approved production account, region or provider behavior |
| `EXT-KMS-CUSTODY` | Missing | Production object/key custody not approved |
| `EXT-BASEMAP` | Missing | No production provider, licence, account or key |

These states are authoritative in [docs/progress.md:2492](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/docs/progress.md#L2492-L2513). Production configuration defaults both privacy and measurement issuance off: [docker-compose.production.yml:60](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/docker-compose.production.yml#L60-L68).

The development fallback is safely local and network-free, but merely setting a style URL labels it “configured”; the application does not validate provider approval or licensing: [frontend/src/lib/map/config.ts:12](https://github.com/oluwasolaonigbinde/mobility/blob/637841d95493bcc24334356da42097fa53a5d16f/frontend/src/lib/map/config.ts#L12-L40).

## Smallest remediation

1. Build one canonical frozen projection from one half-open, trip-time cohort. Use current authoritative impressions and one latest payout calculation per trip. Feed both the screen and exporters from that projection.
2. Add the frozen ROI attribution window, cost basis, exclusions, corrections, late-data rule and input provenance to the UI, CSV and PDF.
3. Make both renderers consume one parity projection; include measurement input SHA, currency and uncertainty in both, and embed a Unicode-capable PDF font.
4. Define an explicit timezone and rounding contract; show the same rounded value plus the exact underlying value where appropriate.
5. Enforce `worker_attempts < REPORT_MAX_ATTEMPTS` during lease reclaim and clean unregistered partial objects after terminal failure.
6. Add an authorized “current issuance for run” lookup so a new owner or changed authority can discover and reissue the latest parent.
7. Before live approval, adopt a report-artifact retention/tombstone policy and bound presigned-link TTL in production validation.

Focused regression cases should cover delayed calculation timestamps, end-boundary facts, stale impression formulae, superseded payouts, CSV/PDF field parity, Unicode labels, worker death after the third claim, authority revision, requester replacement and terminal partial-object cleanup.

## Execution limitations

No dependencies were installed and no full suite was run. The archived environment lacked `pytest`; I therefore ran only a standard-library, in-memory probe against the pinned renderer. No database, browser, report issuance endpoint, external storage or basemap provider was contacted. The database/PostGIS, MinIO and browser claims in Package 8 remain historical committed evidence rather than tests re-executed in this audit.

