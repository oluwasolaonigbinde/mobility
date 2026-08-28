# W4-03B-P3 synthetic target-area coverage evidence

Status: **implemented and verified for synthetic validation only** on base
`09382eacf10c826d8bf4ab1a9b78e56a1f10a07a`. This checkpoint does not authorize
live measurement, issue a report, satisfy `EXT-REPORT-METHOD`, or mark W4-03B
done.

## Delivered boundary

The private build-time calculator consumes a sealed synthetic provenance
envelope. It binds one organization, campaign, half-open complete measurement
period, calculation time, frozen target-zone id/revision/geometry, the existing
`heatmap_v1` / `postgis_grid_ping_weighted` fixed-cell scheme and resolution,
the synthetic disclosure reference, every fixed-cell geometry, the exact
disclosure-cleared cell ids, and exact qualifying synthetic cell ids. Canonical
ordering makes the SHA-256 independent of input order while duplicate evidence
references are rejected. Every cell id is parsed as a `heatmap_v1` grid origin,
and every cell geometry—including non-qualifying cells—must match the envelope
derived from that origin and the frozen resolution within a one-millimetre
serialization tolerance. Unknown, malformed, mismatched, or tampered evidence
is rejected before the coverage query.

The calculation is:

`100 × area(union(polygon(intersection(cleared qualifying fixed cell, frozen target zone)))) / area(frozen target zone)`

PostGIS validates finite WGS84 Polygon/MultiPolygon inputs. It clips each cell
to the target zone, extracts polygonal components, unions them, and then uses
geography area. It does not sum overlapping cells and does not numerically
clamp the result. A valid cleared qualifying cell wholly outside the zone yields
`0.000000`; absence of qualifying evidence is not converted to zero.

The frozen Abuja golden provenance hash is
`12247dcbd865ec990d8f5f0e66532579fd5d402c8183c13220e3012fc89839e5`.
It produces numerator `1211174.312837 m²`, denominator `1937878.914551 m²`,
and coverage `62.500000%`, so the confirmed synthetic `>=60%` target evaluates
true. The label and qualifying-evidence rule remain unapproved; the result says
`SYNTHETIC_VALIDATION_ONLY`, `test_only=true`, and both live method and live
qualifying-rule approval are `MISSING`. It explicitly excludes people, views,
reach, attribution, causal effect, and live approval.

## Omission rules

The percentage is omitted for non-test input; missing/tampered provenance;
missing, invalid, or non-positive target-zone geometry; absent qualification;
absent disclosure clearance; unknown or duplicate cell identity; missing or
mismatched fixed-cell authority; organization/campaign/period mismatch;
incomplete or non-half-open period; invalid cell geometry; or unavailable/
failed PostGIS calculation. No SQL is attempted for non-test input.

## Review and verification

The one independent pre-edit Sol/high review returned `REVISE`. Its required
corrections were adopted: the provenance envelope is private and explicitly
synthetic rather than claiming fields the runtime heatmap does not produce;
period semantics are explicitly half-open; calculation time and semantic
canonicalization are frozen; malformed producer evidence fails closed;
polygonal clipping/union ordering is exact; zero coverage is distinguished from
missing evidence; and P3 has no API or synchronized-contract impact.

The sole clean-context post-build `$minimal-change-review` returned `FIX` with
two P1 findings: fixed-cell identity was not yet spatially verified, and
duplicate evidence references were normalized instead of rejected. One bounded
correction now validates every fixed cell against its parsed grid origin and
resolution, rejects duplicates in both disclosure and qualification lists, and
adds moved/oversized/id/resolution, malformed non-qualifying, and duplicate-list
regressions. The affected P3 suite and static checks were rerun green. Per the
checkpoint instruction, no reviewer chain or repeated review was started.

Red/green overlap evidence used one temporary mutation replacing union area
with additive area. The overlap regression failed at `75.000152%` versus the
expected `62.500000%`; restoring `ST_Union` made the same test pass.

Focused checks at the restored implementation:

- `tests/test_target_area_coverage.py`: **22 passed** on PostgreSQL/PostGIS.
  The matrix covers exact Abuja output/hash and replay, input-order invariance,
  overlap, partial clipping, exact `60.000000%`, below target, organization/
  campaign/half-open-period mismatch, suppression, missing qualification,
  incomplete period, missing and zero-area zones, outside-zone zero, duplicate/
  unknown ids, duplicate evidence lists, fixed-cell identity/geometry/resolution
  mismatch, malformed non-qualifying cells, non-polygon/out-of-range geometry,
  hash tampering, non-test no-SQL behavior, and unavailable PostGIS.
- Existing methodology plus fixed-cell/disclosure preservation selection:
  **7 passed**. One combined run initially recorded six passes and a connection
  timeout before the disclosure-floor assertion; the single timed-out case was
  rerun once and passed.
- Scoped Ruff and Python compilation: **passed**.
- `git diff --check`: **passed** before the evidence document was added and is
  rerun at handoff.

No measurement run, API/schema, database/migration, report, ROI, disclosure
history, heatmap producer, gate evaluator, P2 journey, architecture, decision,
or §9 synchronized contract baseline changed. Consequently R14-B regeneration
is not applicable. P4 integration and every external/live pilot gate remain
outside this checkpoint.
