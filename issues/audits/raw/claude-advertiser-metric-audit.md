---
source_surface: Claude desktop
workspace: mobility
conversation_id: fca68132-a1b3-43fd-81d3-15f1d0c3a051
displayed_title: Cardvert advertiser metric audit
displayed_model: Claude Opus 5
created_at: 2026-09-01T08:21:09.495Z
retrieved_at: 2026-09-01
collection_state: COLLECTED
completeness: complete published artifact
redactions: none
artifact_url: https://claude.ai/code/artifact/51c63fa8-e199-428c-81b3-da2189a223cc
source_format: Claude HTML artifact converted to GitHub-flavored Markdown
---

# Cardvert advertiser metric audit

> This is the complete published audit artifact preserved as source evidence.
> It is not yet an accepted finding or remediation decision.

Cardvert Measurement Assay

<style>
  :root {
    --ground:      #F2F5F5;
    --surface:     #FFFFFF;
    --surface-sunk:#E9EEEE;
    --ink:         #16232B;
    --ink-muted:   #55666F;
    --ink-faint:   #7D8C93;
    --rule:        #D2DBDB;
    --rule-strong: #B4C1C1;
    --accent:      #0F6E64;
    --accent-soft: #DCEAE7;
    --sev-major:   #9E3B2C;
    --sev-mod:     #99691A;
    --sev-minor:   #4A6572;
    --sev-ok:      #24685A;

    --measure: 68ch;
    --step--1: 0.815rem;
    --step-0:  1rem;
    --step-1:  1.22rem;
    --step-2:  1.55rem;
    --step-3:  2.05rem;
    --step-4:  2.85rem;
  }

  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --ground:      #0D1417;
      --surface:     #131E22;
      --surface-sunk:#0A1114;
      --ink:         #E2EAEB;
      --ink-muted:   #9BAEB3;
      --ink-faint:   #71858B;
      --rule:        #24343A;
      --rule-strong: #35494F;
      --accent:      #55B9AA;
      --accent-soft: #14322F;
      --sev-major:   #D97F6E;
      --sev-mod:     #D6A64F;
      --sev-minor:   #8FA6AE;
      --sev-ok:      #5FBBA6;
    }
  }

  :root[data-theme="dark"] {
    --ground:      #0D1417;
    --surface:     #131E22;
    --surface-sunk:#0A1114;
    --ink:         #E2EAEB;
    --ink-muted:   #9BAEB3;
    --ink-faint:   #71858B;
    --rule:        #24343A;
    --rule-strong: #35494F;
    --accent:      #55B9AA;
    --accent-soft: #14322F;
    --sev-major:   #D97F6E;
    --sev-mod:     #D6A64F;
    --sev-minor:   #8FA6AE;
    --sev-ok:      #5FBBA6;
  }

  * { box-sizing: border-box; }

  body {
    margin: 0;
    background: var(--ground);
    color: var(--ink);
    font-family: "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
    font-size: var(--step-0);
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }

  .wrap {
    max-width: 62rem;
    margin: 0 auto;
    padding: 0 1.5rem 6rem;
  }

  .prose { max-width: var(--measure); }

  h1, h2, h3 {
    font-family: "Newsreader", Georgia, "Times New Roman", serif;
    font-weight: 500;
    text-wrap: balance;
    margin: 0;
    line-height: 1.18;
  }

  .label {
    font-family: "IBM Plex Mono", ui-monospace, "SFMono-Regular", monospace;
    font-size: 0.7rem;
    font-weight: 500;
    letter-spacing: 0.13em;
    text-transform: uppercase;
    color: var(--ink-faint);
  }

  code, .mono {
    font-family: "IBM Plex Mono", ui-monospace, "SFMono-Regular", monospace;
    font-size: 0.86em;
  }

  a { color: var(--accent); }

  /* ---------- masthead ---------- */

  .masthead {
    border-bottom: 2px solid var(--ink);
    padding: 3.5rem 0 1.5rem;
    margin-bottom: 2rem;
  }

  .masthead h1 {
    font-size: var(--step-4);
    margin: 0.6rem 0 0.9rem;
  }

  .standfirst {
    font-family: "Newsreader", Georgia, serif;
    font-size: var(--step-1);
    line-height: 1.5;
    color: var(--ink-muted);
    max-width: 54ch;
    margin: 0;
  }

  .provenance {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
    gap: 1rem 2rem;
    margin-top: 2rem;
    padding-top: 1.25rem;
    border-top: 1px solid var(--rule);
  }

  .provenance div { display: flex; flex-direction: column; gap: 0.3rem; }
  .provenance .v { font-family: "IBM Plex Mono", monospace; font-size: var(--step--1); word-break: break-all; }

  /* ---------- verdict ---------- */

  .verdict {
    background: var(--surface);
    border: 1px solid var(--rule);
    border-left: 4px solid var(--accent);
    padding: 1.75rem 1.9rem;
    margin: 2.5rem 0;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .verdict h2 { font-size: var(--step-2); }
  .verdict p { margin: 0; max-width: var(--measure); }

  .verdict-line {
    font-family: "Newsreader", Georgia, serif;
    font-size: var(--step-1);
    font-style: italic;
    color: var(--ink);
    border-top: 1px solid var(--rule);
    padding-top: 1rem;
    margin: 0;
  }

  /* ---------- sections ---------- */

  section { margin-top: 4rem; }

  .sec-head {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding-bottom: 0.9rem;
    border-bottom: 1px solid var(--rule-strong);
    margin-bottom: 1.75rem;
  }

  .sec-head h2 { font-size: var(--step-3); }

  section p { max-width: var(--measure); }

  /* ---------- table ---------- */

  .scroll { overflow-x: auto; border: 1px solid var(--rule); background: var(--surface); }

  table { border-collapse: collapse; width: 100%; min-width: 46rem; font-size: var(--step--1); }

  th, td {
    text-align: left;
    padding: 0.7rem 0.9rem;
    border-bottom: 1px solid var(--rule);
    vertical-align: top;
  }

  thead th {
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.68rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--ink-faint);
    background: var(--surface-sunk);
    white-space: nowrap;
  }

  tbody tr:last-child td { border-bottom: 0; }
  td.name { font-weight: 500; }
  td .mono { color: var(--ink-muted); display: block; margin-top: 0.2rem; }

  /* ---------- findings ---------- */

  .findings { display: flex; flex-direction: column; gap: 1.5rem; }

  .finding {
    background: var(--surface);
    border: 1px solid var(--rule);
    border-top: 3px solid var(--sev);
    padding: 1.5rem 1.6rem;
    display: flex;
    flex-direction: column;
    gap: 1.1rem;
  }

  .f-major { --sev: var(--sev-major); }
  .f-mod   { --sev: var(--sev-mod); }
  .f-minor { --sev: var(--sev-minor); }

  .f-head { display: flex; flex-direction: column; gap: 0.55rem; }

  .f-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem; }

  .num {
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    color: var(--ink-faint);
  }

  .chip {
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.66rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--sev);
    border: 1px solid var(--sev);
    padding: 0.15rem 0.5rem;
  }

  .finding h3 { font-size: var(--step-2); }
  .finding p { margin: 0; max-width: var(--measure); }

  /* the diptych: promise vs delivery */
  .diptych {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1px;
    background: var(--rule);
    border: 1px solid var(--rule);
  }

  @media (max-width: 40rem) { .diptych { grid-template-columns: 1fr; } }

  .dip {
    background: var(--surface);
    padding: 1rem 1.1rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .dip p { font-size: var(--step--1); line-height: 1.55; }
  .dip.says .label { color: var(--accent); }
  .dip.does .label { color: var(--sev); }

  .evidence {
    background: var(--surface-sunk);
    border-left: 2px solid var(--rule-strong);
    padding: 0.8rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    overflow-x: auto;
  }

  .evidence .e {
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.78rem;
    color: var(--ink-muted);
    white-space: nowrap;
  }

  .evidence .e b { color: var(--ink); font-weight: 500; }

  /* ---------- cleared / credited ---------- */

  .cleared { display: flex; flex-direction: column; gap: 0.9rem; }

  .cl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.9rem;
    align-items: baseline;
    padding-bottom: 0.9rem;
    border-bottom: 1px solid var(--rule);
  }

  .cl:last-child { border-bottom: 0; padding-bottom: 0; }

  .tick {
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    color: var(--sev-ok);
    white-space: nowrap;
  }

  .cl p { margin: 0; font-size: var(--step--1); }

  /* ---------- remediation ---------- */

  .fixes { display: flex; flex-direction: column; gap: 1rem; counter-reset: fix; }

  .fix {
    display: grid;
    grid-template-columns: 2.2rem 1fr;
    gap: 1rem;
    background: var(--surface);
    border: 1px solid var(--rule);
    padding: 1.1rem 1.25rem;
  }

  .fix::before {
    counter-increment: fix;
    content: counter(fix);
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--accent);
    border-right: 1px solid var(--rule);
    padding-right: 0.9rem;
  }

  .fix p { margin: 0; font-size: var(--step--1); }
  .fix p + p { margin-top: 0.4rem; color: var(--ink-muted); }

  /* ---------- gates ---------- */

  .gates { display: grid; grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr)); gap: 1rem; }

  .gate {
    background: var(--surface);
    border: 1px solid var(--rule);
    padding: 1.1rem 1.2rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .gate .g-id { font-family: "IBM Plex Mono", monospace; font-weight: 600; font-size: var(--step--1); }
  .gate .g-state {
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.66rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--sev-major);
  }
  .gate p { margin: 0; font-size: var(--step--1); color: var(--ink-muted); }

  /* ---------- closing ---------- */

  .closing {
    margin-top: 4rem;
    padding: 2rem 0 0;
    border-top: 2px solid var(--ink);
  }

  .closing h2 { font-size: var(--step-2); margin-bottom: 1rem; }
  .closing p { max-width: var(--measure); }

  ul.tight { max-width: var(--measure); padding-left: 1.1rem; margin: 0.6rem 0 0; }
  ul.tight li { margin-bottom: 0.45rem; }

  .foot {
    margin-top: 3.5rem;
    padding-top: 1.25rem;
    border-top: 1px solid var(--rule);
    font-size: var(--step--1);
    color: var(--ink-faint);
    max-width: var(--measure);
  }

  :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

  @media (prefers-reduced-motion: reduce) {
    * { animation: none !important; transition: none !important; }
  }
</style>

<div class="wrap">

<div class="header masthead">

Independent measurement-science audit · Read-only

# Are Cardvert's advertiser metrics honest?

The governance is genuinely strong. The gap is that the contract's own
honesty caveats do not survive the journey into the artifacts an
advertiser actually keeps.

<div class="provenance">

<div>

<span class="label">Repository</span>
<span class="v">oluwasolaonigbinde/mobility</span>

</div>

<div>

<span class="label">Branch</span>
<span class="v">feat/pkg-04-build-first</span>

</div>

<div>

<span class="label">Commit verified</span>
<span class="v">637841d95493bcc24334356da42097fa53a5d16f</span>

</div>

<div>

<span class="label">Head confirmed</span> <span class="v">GitHub API +
local object · 28 Aug 2026</span>

</div>

</div>

</div>

<div class="verdict">

Verdict

## Qualified pass on definition. Fail on disclosure completeness.

Every advertiser-visible metric is **defined** and, where it is served
at all, **reproducible** — the frozen-run architecture is the real
thing, not a veneer. Labelling is honest in what it *says* and defective
in what it *omits*: the methodology contract specifies uncertainty and
missing-data behaviour that the code does not carry into the frozen
result, the screen, or the exported CSV/PDF.

No prohibited claim is made anywhere in the advertiser surface. No
metric is renamed to imply reach, views, people, or attribution. The
failure mode here is not overstatement — it is **silent omission of the
qualifiers that make an understated metric safe**.

The word doing the most work in this product is “Verified,” and it is
the one metric that ships with no caveat at all.

</div>

<div class="section">

<div class="sec-head">

Section 01

## Metric dictionary and evidence map

</div>

Five metrics are defined in the machine-checkable contract at
`docs/measurement-methodology.json`. Four reach an advertiser surface;
one does not exist outside tests.

<div class="scroll" style="margin-top:1.5rem">

| Metric & class | Definition source | Computation | Advertiser surface | Status |
|----|----|----|----|----|
| Verified vehicle movement<span class="mono">measured_operational_fact</span> | methodology.json · contract line for `verified_vehicle_movement` | <span class="mono">measurement.py:82</span> — trip count, distance, active tracking seconds over `status == computed` rows | Report panel; CSV/PDF rows | Defined, reproducible, **caveat dropped** |
| Modelled potential contacts<span class="mono">modelled_measure</span> | methodology.json; storage field `estimated_impressions` | <span class="mono">measurement.py:94</span> sums `impressions_v1` outputs; formula at <span class="mono">impressions.py:687</span> | Report headline stat, chart, daily table, CSV/PDF | Defined, reproducible, **vintage & completeness absent** |
| Driver campaign cost<span class="mono">measured_financial_fact</span> | methodology.json | <span class="mono">measurement.py:109</span> — per-currency sum of `calculated` payout rows, no currency mixing | Report stat, chart, CSV/PDF | Sound |
| Exposure score<span class="mono">operational_composite_index</span> | `exposure_v1` contract in <span class="mono">exposure_scores.py:26</span> | Weighted distance/dwell composite × quality, 0–100, fingerprinted formula + input | Report headline stat; zone insight footer | **Exemplary** — carries its own uncalibrated disclosure |
| Target-area coverage<span class="mono">modelled_derived_measure</span> | methodology.json candidate formula, `SYNTHETIC_VALIDATION_ONLY` | <span class="mono">target_area_coverage.py:336</span> — cleared-cell area ÷ approved zone area | **None.** No API route, no component | Correctly gated; client success criterion undelivered |
| Return on investment<span class="mono">conditional_financial_measure</span> | methodology.json `roi_gate`, seven prerequisites | <span class="mono">measurement.py:133</span> — `(revenue − cost) / cost`, cost basis constrained `gt=0` | Omitted by default; synthetic runs chipped “synthetic test-only result” | Fails closed correctly |

</div>

</div>

<div class="section">

<div class="sec-head">

Section 02 · Ranked most severe first

## Confirmed defects

</div>

Each defect is stated as the gap between what the repository's own
contract promises and what its code delivers. All were verified by
reading the code at the audited commit; none is inferred from
documentation alone.

<div class="findings" style="margin-top:1.75rem">

<div class="f-head">

<div class="f-meta">

<span class="num">DEFECT 01</span> <span class="chip">Major ·
labelling</span>

</div>

### The “verified movement” caveat exists in no shipped output

</div>

The contract's required qualifier for the measured metric — that
movement does not prove a person saw an advert — appears nowhere in
`app/` or `frontend/src/`. A full-text search of every source file at
this commit returns no match. The exported PDF and CSV therefore present
“Verified vehicle movement” with trip count, distance, and active
tracking time under a heading reading *Campaign Performance Analysis*,
with no statement of what the number does not mean.

<div class="diptych">

<div class="dip says">

<span class="label">Contract promises</span>

“Completeness and quality scores describe collection quality; movement
does not prove that a person saw an advert.”

</div>

<div class="dip does">

<span class="label">Code delivers</span>

`calculate_measurement_result` builds the metric with no `uncertainty`
key. The renderer then explicitly sets `uncertainty = None` for it, and
only emits an uncertainty row `if metric.get("uncertainty")`.

</div>

</div>

<div class="evidence">

<span class="e">**docs/measurement-methodology.json** — uncertainty
defined for `verified_vehicle_movement`</span>
<span class="e">**app/services/measurement.py:82** — metric dict omits
any uncertainty field</span>
<span class="e">**app/services/report_issuances.py:272** —
`uncertainty = None` for this metric</span>
<span class="e">**app/services/report_rendering.py** — row emitted only
`if metric.get("uncertainty")`</span>
<span class="e">**measurement-authority.tsx** — renders label, distance,
trip count; no caveat</span>

</div>

<div class="f-head">

<div class="f-meta">

<span class="num">DEFECT 02</span> <span class="chip">Major ·
missing-data behaviour</span>

</div>

### Incompleteness is computed, then discarded before the advertiser sees it

</div>

The backend counts trips that produced no estimate —
`insufficient_data_trip_count` and `excluded_trip_count` — and ships
them in the API payload. They are rendered by no component: the only
occurrences anywhere in the frontend are in the generated type
definitions. The frozen measurement result has no field for them at all,
so the totals in the CSV and PDF have no disclosed denominator. An
advertiser reading “Modelled potential contacts: 482,000” cannot tell
whether that covers every trip in the period or half of them.

<div class="diptych">

<div class="dip says">

<span class="label">Contract promises</span>

“Mark the period incomplete and omit affected totals; never zero-fill
missing route evidence.” The exposure score honours exactly this,
publishing `missing_route_count` beside its value.

</div>

<div class="dip does">

<span class="label">Code delivers</span>

The result sums only `status == "estimated"` rows and records nothing
about the rest. `ModelledContactsMetricRead` declares no completeness
field, so the omission is structural rather than a display oversight.

</div>

</div>

<div class="evidence">

<span class="e">**app/services/reports.py:293-294** — counters computed
and returned</span> <span class="e">**frontend/src/lib/api/schema.d.ts**
— sole frontend occurrence; no component reads them</span>
<span class="e">**app/schemas/measurement.py:99** —
`ModelledContactsMetricRead` has no completeness field</span>
<span class="e">**app/services/exposure_scores.py** — contrast: exposure
score does publish `missing_route_count`</span>

</div>

<div class="f-head">

<div class="f-meta">

<span class="num">DEFECT 03</span> <span class="chip">Major · provenance
& vintage</span>

</div>

### Traffic-profile vintage is unimplementable, and profile drift is undetected

</div>

The contract defines the vintage of modelled contacts as including the
“traffic-profile effective interval.” The `TrafficDensityProfile` model
has no such interval — no effective-from, no effective-to, no version,
no calibration or approval reference. Profiles are edited in place by
direct attribute assignment, with no version bump.

The consequence is worse than a missing field. The staleness check
compares formula version, analytics identity, analytics fingerprint and
fraud counts — but never the profile's parameter values. The output
fingerprint carries only the profile *id*. So an administrator can
double `traffic_density_per_km` and every existing estimate stays
“current” and authoritative. A single frozen report can then blend
estimates computed under materially different model parameters, with
nothing in the output disclosing the mix.

<div class="diptych">

<div class="dip says">

<span class="label">Contract promises</span>

Vintage = “traffic-profile effective interval, source fingerprint,
formula version, and calculation time.”

</div>

<div class="dip does">

<span class="label">Code delivers</span>

Formula version and calculation time only. No effective interval exists
to record; the profile fingerprint is an id that survives arbitrary
parameter change.

</div>

</div>

<div class="evidence">

<span class="e">**app/models/impression.py:114** — profile fields; no
effective interval, no version</span>
<span class="e">**app/services/impressions.py:450** — `setattr` in-place
mutation, no version bump</span>
<span class="e">**app/services/impressions.py:147** — staleness check
ignores profile parameter values</span>
<span class="e">**app/services/impressions.py:177** — fingerprint
carries `traffic_density_profile_id` only</span>

</div>

<div class="f-head">

<div class="f-meta">

<span class="num">DEFECT 04</span> <span class="chip">Moderate ·
uncertainty</span>

</div>

### The model's calibration status is disclosed for the minor metric, not the major one

</div>

Modelled potential contacts is driven by an unsourced constant:
`impression_default_traffic_density_per_km` defaults to `120.0`, and the
demo seed uses `240.0`. Nothing in the repository ties either figure to
Abuja traffic measurement, a survey, or any external reference; the
estimate metadata is candid internally, recording the road method as
`profile_default_weight_no_road_classification_v1` — an explicit
admission that no road classification is applied.

None of that reaches the advertiser. The frozen metric carries a value,
a formula version list, and one sentence about confidence not being a
statistical interval. Meanwhile the exposure score — a far less
consequential number — correctly ships “Synthetic uncalibrated
operational index.” The disclosure discipline is inverted relative to
the stakes.

<div class="evidence">

<span class="e">**app/core/config.py:174** —
`impression_default_traffic_density_per_km: float = 120.0`</span>
<span class="e">**app/seeds/demo.py:1172** — seed profile uses
`240.0`</span> <span class="e">**app/services/impressions.py:687** —
density multiplies distance directly into the headline value</span>
<span class="e">**app/services/report_issuances.py:275** — artifact
carries one uncertainty line, no model parameters</span>

</div>

<div class="f-head">

<div class="f-meta">

<span class="num">DEFECT 05</span> <span class="chip">Moderate · latent
gate</span>

</div>

### The exported artifact is protected by a weaker gate than the screen

</div>

`report_issuances.py` defines its own local `_approved_reference` that
omits the `ext-` prefix rejection present in the disclosure service's
version, and the issuance and download paths never call
`ensure_disclosure_live_gate`. An operator who sets the privacy
reference to the literal name of the unmet gate — `EXT-LEGAL-PRIVACY`,
the most natural placeholder to type — is refused by the on-screen
report but accepted by artifact issuance and download.

This requires both live-authorization flags to be enabled, and both
default to false, so it is latent rather than active. It is worth fixing
precisely because the `ext-` rule exists to catch that exact operator
mistake, and the path it fails to guard produces the durable, shareable
file rather than the ephemeral view.

<div class="evidence">

<span class="e">**app/services/disclosure.py:48** — strict: rejects
placeholders *and* `ext-` prefixes</span>
<span class="e">**app/services/report_issuances.py:84** — local copy
omits the `ext-` rejection</span>
<span class="e">**app/services/report_issuances.py** — no call to
`ensure_disclosure_live_gate` on any route</span>

</div>

<div class="f-head">

<div class="f-meta">

<span class="num">DEFECT 06</span> <span class="chip">Moderate · control
coverage</span>

</div>

### The copy guard tests yesterday's wording, not the contract's vocabulary

</div>

A test scans advertiser copy for prohibited language — a genuinely good
control, and rare. Its coverage does not match its purpose on two axes.
It scans only `frontend/src/app/advertiser/`, so it misses
`components/analytics/high-exposure-zone-insights.tsx`, which renders
advertiser-visible metric text on both the report and map pages. And it
asserts against eleven specific historical strings that were removed in
earlier passes, not against the nine `prohibited_claims` in the
contract. Case-sensitive substring checks for “Attribution report” and
“GPS-verified exposure” would not catch a new surface reading “verified
views,” “unique reach,” or “people exposed.”

<div class="evidence">

<span class="e">**tests/test_measurement_methodology.py:10** —
`ADVERTISER_DIR` excludes `components/`</span>
<span class="e">**tests/test_measurement_methodology.py:95** — asserts
legacy strings, not `prohibited_claims`</span>
<span class="e">**docs/measurement-methodology.json** — nine prohibited
claims, none asserted verbatim</span>

</div>

<div class="f-head">

<div class="f-meta">

<span class="num">DEFECT 07</span> <span class="chip">Minor ·
lineage</span>

</div>

### Exposure-score reissue lineage is scoped more loosely than run lineage

</div>

Measurement-run lineage selects its parent by campaign *and* period.
Exposure-score lineage selects by campaign only, so a score issued for
August can be recorded as a reissue of July's score rather than as an
independent head. The field is internal — it is excluded from the
advertiser projection — so this misstates admin lineage rather than any
advertiser-facing figure.

<div class="evidence">

<span class="e">**app/services/exposure_scores.py:287** — parent
selected on `campaign_id` alone</span>
<span class="e">**app/services/measurement.py** — run lineage
additionally matches period start and end</span>

</div>

</div>

</div>

<div class="section">

<div class="sec-head">

Section 03

## Reproducibility assessment

</div>

**Strong, and genuinely verified rather than asserted.** A measurement
run freezes its input manifest, result manifest, proof manifest and
report snapshot, each SHA-256 fingerprinted over a canonical JSON
encoding. `measurement_run_reproducible` re-executes the result
computation from the frozen inputs and requires both the recomputed hash
and the recomputed object to match. Issued history is append-only;
changed inputs create a new lineage head rather than rewriting a prior
issue. Actor-and-request replay converges, and reuse with different
inputs conflicts rather than silently overwriting.

The frontend independently re-validates provenance before rendering —
comparing run and result identity, formula and method revisions, proof
hashes, period instants, metric completeness, ROI gate consistency, and
exposure-score binding — and renders a fail-closed state rather than
partial output when any check fails. Client-side verification of a
server-issued artifact is a deliberate, uncommon control and it works
here.

**The one real reproducibility hole is Defect 03.** Determinism holds
given a fixed input manifest, because the profile parameters used at
estimate time are snapshotted into `estimate_metadata`. What is not
guaranteed is that the estimates *within* one manifest share a single
model vintage, because nothing detects or records profile parameter
drift. Reissuing a report is deterministic; interpreting two reports as
commensurable is not currently safe.

</div>

<div class="section">

<div class="sec-head">

Section 04

## Checked and cleared

</div>

Several plausible defects were investigated and did not survive
verification. Recording them prevents a later reviewer re-raising them,
and two are controls worth crediting outright.

<div class="cleared" style="margin-top:1.5rem">

<div class="cl">

<span class="tick">CLEARED</span>

**Chart zero-filling.** The report chart maps
`Number(d.estimated_impressions ?? 0)`, which reads as a zero-fill. The
field is non-nullable in `DailyMetricItem` and the serializer never
emits null for it, so the fallback is unreachable. Not a defect.

</div>

<div class="cl">

<span class="tick">CLEARED</span>

**Dashboard tiles showing unfrozen numbers.** The advertiser dashboard
and campaign-detail pages render “Modelled potential contacts” from
dynamic, non-frozen endpoints. Those four routes pass
`requires_measurement_run=True`, and that branch raises
`SAFE_MEASUREMENT_RUN_REQUIRED` unconditionally outside test mode — so
they cannot serve a number in production at all. Crude, but closed.

</div>

<div class="cl">

<span class="tick">CLEARED</span>

**ROI division by zero.** `(revenue − cost) / cost` is guarded upstream
by `approved_cost_basis: Decimal = Field(gt=0)`.

</div>

<div class="cl">

<span class="tick">CLEARED</span>

**Empty method reference passing as approved.** The empty string is a
member of the placeholder set, so the default configuration fails the
gate closed rather than open.

</div>

<div class="cl">

<span class="tick">CLEARED</span>

**Synthetic test mode reachable in production.** A settings validator
raises unless the environment is `test`. The one bypass — `model_copy`
during snapshot construction — writes to storage behind a serve-time
gate that is still enforced, so it discloses nothing new.

</div>

<div class="cl">

<span class="tick">CREDIT</span>

**Exposure score versus impressions.** Cleanly separated. Distinct
formula version, unit, fingerprints and metric class; per-route detail
stripped from the advertiser projection; the UI states it is “not an
impression estimate, audience count, statistical confidence interval or
attribution result.” This is the disclosure standard the other metrics
should be held to.

</div>

<div class="cl">

<span class="tick">CREDIT</span>

**Target-area coverage.** Refuses to compute unless the provenance is
explicitly `test_only`, the period is marked complete, and the zone
geometry is valid; returns a structured omission reason otherwise,
carrying `live_method_approval: MISSING`. It is a synthetic candidate
and says so.

</div>

</div>

</div>

<div class="section">

<div class="sec-head">

Section 05

## Unsupported claims

</div>

**None found in advertiser-visible copy.** This is the audit's clearest
positive result. A full sweep of every `.ts` and `.tsx` file for reach,
view, people, audience and guarantee language returned exactly one hit —
a disclaimer stating that rankings do “not represent observed people or
guaranteed outcomes.” The deliverable is titled *Campaign Performance
Analysis* throughout; the internal `estimated_impressions` field is
never surfaced under that name; model confidence is consistently
labelled a diagnostic; the ROI section is absent by default and chipped
“synthetic test-only result” when a synthetic run enables it.

Two claims are unsupported by omission rather than by wording, both
already recorded above: “Verified vehicle movement” presented without
its qualifier (Defect 01), and any total presented without its
completeness denominator (Defect 02). One further gap is not a claim but
a shortfall — the 60% target-area coverage figure named in the D18
client success criteria has no advertiser surface at this commit. It
exists only as a synthetic service, a load script, and tests. Nothing
overstates it; it is simply not delivered.

</div>

<div class="section">

<div class="sec-head">

Section 06

## External methodology gates

</div>

All remain unmet at this commit, and the code fails closed against each.
No finding above is a request to open one.

<div class="gates" style="margin-top:1.5rem">

<div class="gate">

<span class="g-id">EXT-REPORT-METHOD</span>
<span class="g-state">Missing</span>

No approved reporting or ROI method. Live issuance defaults false; the
ROI gate omits by default and requires seven prerequisites.

</div>

<div class="gate">

<span class="g-id">EXT-LEGAL-PRIVACY</span>
<span class="g-state">Missing</span>

Disclosure thresholds are synthetic build parameters, not approved pilot
values. Defect 05 concerns this gate's enforcement asymmetry.

</div>

<div class="gate">

<span class="g-id">EXT-AD-PLATFORM</span>
<span class="g-state">Missing</span>

Segment and person-level export remain disabled. Out of scope for this
audit beyond confirming no advertiser metric depends on it.

</div>

</div>

Three inputs must come from outside the repository before any of this is
a live measurement product: a calibration basis for
`traffic_density_per_km` — the number that most determines the headline
figure and is currently unsourced; an approved qualifying-evidence rule
and label for target-area coverage; and an approved ROI method covering
attribution, cost basis, window, exclusions, corrections and late data.
Nothing in the code can substitute for these, and the code correctly
does not try.

</div>

<div class="section">

<div class="sec-head">

Section 07

## Smallest remediation

</div>

Defects 01, 02 and 04 are one coherent change at a single chokepoint.
All three are omissions from the same function and the same schema, and
fixing them opens no external gate.

<div class="fixes" style="margin-top:1.5rem">

<div class="fix">

**Carry the contract's uncertainty text into every metric.** Add the
`uncertainty` key to the `verified_vehicle_movement` dict in
`calculate_measurement_result`, sourced verbatim from
`measurement-methodology.json`, and let it through in `_metric_snapshot`
instead of hardcoding `None`. Render it in the authority panel alongside
the existing modelled-contacts caveat.

Closes Defect 01. Roughly a dozen lines across three files.

</div>

<div class="fix">

**Add completeness to the modelled-contacts metric.** Record excluded
and insufficient counts on the metric in the same function, add the
fields to `ModelledContactsMetricRead`, and display them the way the
exposure score already displays `missing_route_count`. This is a new run
schema, so it needs a formula-version increment rather than an in-place
edit of issued results.

Closes Defect 02.

</div>

<div class="fix">

**Put the model's parameters and calibration status beside its number.**
Include the profile identity, the density constant and a
calibration-status statement in the metric's provenance, mirroring the
exposure score's wording. Until a calibration basis exists, the honest
statement is that the density constant is an uncalibrated build
parameter.

Closes Defect 04 and makes the shortfall visible rather than invisible.

</div>

<div class="fix">

**Fingerprint profile parameters, not just the profile id.** Fold the
snapshotted `traffic_density_profile` values into the staleness
comparison and the output fingerprint so an in-place profile edit marks
dependent estimates stale. Add an effective interval to the profile, or
make profiles append-only, so the contract's vintage becomes recordable.

Closes Defect 03. The largest of the four, and the only one touching a
migration.

</div>

<div class="fix">

**Delete the local `_approved_reference` in `report_issuances.py` and
import the disclosure one.** A two-line change that removes the
asymmetry entirely.

Closes Defect 05.

</div>

<div class="fix">

**Point the copy test at the contract.** Read `prohibited_claims` from
the JSON, lowercase both sides, and widen the scan to every
advertiser-reachable component directory. The test then tracks the
contract automatically instead of drifting from it.

Closes Defect 06.

</div>

</div>

</div>

<div class="closing">

## Could a reasonable advertiser be misled?

**Yes — narrowly, and by omission rather than by any false statement.**

Not about reach. The naming discipline here is better than most of this
industry: nothing in the advertiser surface claims views, people, unique
reach, audience or attribution, and a reader who studies the report will
understand that contacts are modelled.

The exposure is elsewhere, in three specific readings a careful
advertiser could reasonably make and be wrong about:

- That “**Verified** vehicle movement” carries some evidentiary weight
  about advertising exposure. The contract explicitly anticipates this
  misreading and specifies the sentence that prevents it. That sentence
  is in no shipped output.
- That a modelled-contacts total **covers the whole period**. Excluded
  and insufficient trips are counted, then dropped before display, so a
  partial total is indistinguishable from a complete one.
- That two campaigns' figures are **commensurable**. With no profile
  vintage and no drift detection, numbers produced under different model
  parameters are presented identically.

Set against that: no live issuance is authorized, the external method
gate is missing, production issuance defaults false, and the dynamic
metric routes are hard-blocked. **At this commit the risk is
prospective, not realized** — no advertiser can currently be misled,
because no advertiser can currently be served. The defects matter
because they sit precisely where the gate will open, and each one is
small enough to close before it does.

Read-only audit. No repository file was modified and no test suite was
executed. Findings rest on source inspection at commit `637841d`,
verified against the GitHub API and the local git object store. Where a
concern could not be substantiated it is recorded as cleared rather than
omitted. Runtime behaviour under a live database, and any behaviour
depending on operator configuration not present in the repository, are
outside the evidence available to this review.

</div>

</div>

