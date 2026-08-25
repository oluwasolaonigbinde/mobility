# Measurement Methodology Contract

Status: **draft build-only**. External gate: `EXT-REPORT-METHOD` is
**MISSING**. This contract does not authorize a live report, an ROI claim, or
the collection of real data.

The standard deliverable is **Campaign Performance Analysis**. It separates
verified operational facts from modelled measures and financial facts. The
machine-checkable source is `docs/measurement-methodology.json`.

## Claims hierarchy

- **Verified vehicle movement** means accepted system evidence about a vehicle's
  movement. It never proves a person saw an advert.
- The internal `estimated_impressions` field is displayed as **Modelled
  potential contacts**. It is a formula output, not verified views, unique
  reach, an audience, attribution, or people exposed.
- **Target-area coverage** is a geographic measure. Its build-time candidate is
  the share of immutable approved target-zone area intersected by
  disclosure-cleared fixed cells containing qualifying movement evidence. The
  live qualifying-evidence rule and label remain unapproved and MISSING.
- **Driver campaign cost** is an operational financial fact. It is not revenue,
  incremental value, or ROI.

Every presented metric carries its class, unit, source provenance, source
vintage, missing-data behavior, and uncertainty treatment from the JSON
contract. Modelled values show their model and formula revision. Confidence is
a model diagnostic, not a statistical confidence interval. Missing evidence is
omitted or marked incomplete; it is never silently zero-filled.

## ROI is conditional and fail closed

Financial ROI is absent by default. It may appear only when an advertiser has
provided defined conversion and revenue inputs and an approved reproducible
method covers attribution, cost basis, time window, exclusions, corrections,
late data, currencies, provenance, and reissue behavior. Every prerequisite is
required. Missing or invalid input omits the entire ROI section and claim.

The repository's ROI-enabled golden case is explicitly synthetic and
`test_only`; it demonstrates the gate and arithmetic contract without becoming
a production method or client fact. `EXT-REPORT-METHOD` remains MISSING.

## Corrections and reissues

Issued results are immutable. A changed input, source vintage, formula,
approval, or correction creates a new run linked to the prior issue and never
rewrites history. W3-00E owns the run and proof-manifest implementation and is
currently blocked by its Package 4 evidence dependencies. This slice defines
the contract only and issues no report.

## Copy and issuance controls

Advertiser-visible product copy uses **Campaign Performance Analysis** and
**Modelled potential contacts**. It does not use “attribution report”,
“verified exposure”, “verified views”, “unique reach”, “people exposed”, or an
ungated ROI claim. Live issuance remains disabled until the registered legal,
disclosure, and report-method gates are satisfied.
