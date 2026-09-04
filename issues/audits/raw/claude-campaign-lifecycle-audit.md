---
source_surface: Claude desktop
workspace: mobility
conversation_id: 6b86ae67-ce66-4354-99a9-d412c1644f42
displayed_title: Cardvert campaign lifecycle audit
displayed_model: Claude Opus 5
created_at: 2026-09-01T07:51:56.484Z
retrieved_at: 2026-09-01
collection_state: COLLECTED
completeness: complete published artifact
redactions: none
artifact_url: https://claude.ai/code/artifact/3d655145-26c6-4680-8864-810ec38f4f8e
source_format: Claude HTML artifact converted to GitHub-flavored Markdown
---

# Cardvert campaign lifecycle audit

> This is the complete published audit artifact preserved as source evidence.
> It is not yet an accepted finding or remediation decision.

Cardvert Campaign Lifecycle Audit

<style>
  :root {
    --ground:      #ECEFED;
    --surface:     #F9FBFA;
    --surface-2:   #E3E8E5;
    --ink:         #121A18;
    --ink-2:       #34433E;
    --muted:       #5D6C67;
    --rule:        #C7D2CE;
    --rule-soft:   #DAE2DF;
    --signal:      #0B6B5B;
    --signal-ink:  #F9FBFA;

    --sev-critical: #9E2B1C;
    --sev-high:     #A0680F;
    --sev-medium:   #3D6280;
    --sev-low:      #5D6C67;
    --sev-ok:       #0B6B5B;

    --wash-critical: rgba(158, 43, 28, 0.07);
    --wash-high:     rgba(160, 104, 15, 0.07);
    --wash-medium:   rgba(61, 98, 128, 0.07);
    --wash-ok:       rgba(11, 107, 91, 0.07);

    --f-display: "Spectral", "Iowan Old Style", Georgia, serif;
    --f-body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
    --f-mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;

    --measure: 68ch;
    --shell: 1140px;
  }

  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --ground:     #0C1211;
      --surface:    #121A18;
      --surface-2:  #1B2523;
      --ink:        #DDE6E2;
      --ink-2:      #B4C2BD;
      --muted:      #849690;
      --rule:       #26332F;
      --rule-soft:  #1D2926;
      --signal:     #4FBFA8;
      --signal-ink: #0C1211;

      --sev-critical: #E4826C;
      --sev-high:     #D7A445;
      --sev-medium:   #85AACB;
      --sev-low:      #849690;
      --sev-ok:       #4FBFA8;

      --wash-critical: rgba(228, 130, 108, 0.10);
      --wash-high:     rgba(215, 164, 69, 0.10);
      --wash-medium:   rgba(133, 170, 203, 0.10);
      --wash-ok:       rgba(79, 191, 168, 0.10);
    }
  }

  :root[data-theme="dark"] {
    --ground:     #0C1211;
    --surface:    #121A18;
    --surface-2:  #1B2523;
    --ink:        #DDE6E2;
    --ink-2:      #B4C2BD;
    --muted:      #849690;
    --rule:       #26332F;
    --rule-soft:  #1D2926;
    --signal:     #4FBFA8;
    --signal-ink: #0C1211;

    --sev-critical: #E4826C;
    --sev-high:     #D7A445;
    --sev-medium:   #85AACB;
    --sev-low:      #849690;
    --sev-ok:       #4FBFA8;

    --wash-critical: rgba(228, 130, 108, 0.10);
    --wash-high:     rgba(215, 164, 69, 0.10);
    --wash-medium:   rgba(133, 170, 203, 0.10);
    --wash-ok:       rgba(79, 191, 168, 0.10);
  }

  * { box-sizing: border-box; }

  body {
    background: var(--ground);
    color: var(--ink);
    font-family: var(--f-body);
    font-size: 16px;
    line-height: 1.62;
    -webkit-font-smoothing: antialiased;
    margin: 0;
    padding: 0 24px 96px;
  }

  .shell { max-width: var(--shell); margin: 0 auto; }
  .col { max-width: var(--measure); }

  /* ---------- masthead ---------- */

  .masthead {
    border-bottom: 2px solid var(--ink);
    padding: 56px 0 22px;
    margin-bottom: 40px;
  }
  .kicker {
    font-family: var(--f-mono);
    font-size: 11.5px;
    font-weight: 500;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--signal);
    margin: 0 0 18px;
  }
  h1 {
    font-family: var(--f-display);
    font-weight: 700;
    font-size: clamp(2.1rem, 5.2vw, 3.15rem);
    line-height: 1.06;
    letter-spacing: -0.018em;
    text-wrap: balance;
    margin: 0 0 18px;
    max-width: 20ch;
  }
  .standfirst {
    font-size: 1.06rem;
    color: var(--ink-2);
    max-width: 62ch;
    margin: 0 0 30px;
  }

  .provenance {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 1px;
    background: var(--rule);
    border: 1px solid var(--rule);
  }
  .provenance div { background: var(--ground); padding: 12px 14px; }
  .provenance dt {
    font-family: var(--f-mono);
    font-size: 10.5px;
    letter-spacing: 0.11em;
    text-transform: uppercase;
    color: var(--muted);
    margin: 0 0 5px;
  }
  .provenance dd {
    font-family: var(--f-mono);
    font-size: 12.5px;
    color: var(--ink);
    margin: 0;
    word-break: break-all;
  }

  /* ---------- structure ---------- */

  section { margin: 0 0 64px; }

  .sec-head {
    display: flex;
    align-items: baseline;
    gap: 14px;
    border-bottom: 1px solid var(--rule);
    padding-bottom: 9px;
    margin-bottom: 26px;
  }
  .sec-num {
    font-family: var(--f-mono);
    font-size: 12px;
    font-weight: 500;
    color: var(--signal);
    letter-spacing: 0.06em;
  }
  h2 {
    font-family: var(--f-display);
    font-weight: 600;
    font-size: 1.52rem;
    letter-spacing: -0.012em;
    margin: 0;
    text-wrap: balance;
  }

  h3 {
    font-family: var(--f-display);
    font-weight: 600;
    font-size: 1.12rem;
    margin: 34px 0 12px;
    letter-spacing: -0.006em;
  }

  p { margin: 0 0 16px; }
  a { color: var(--signal); text-underline-offset: 3px; }
  a:focus-visible, summary:focus-visible {
    outline: 2px solid var(--signal);
    outline-offset: 3px;
  }

  code, .m {
    font-family: var(--f-mono);
    font-size: 0.875em;
    background: var(--surface-2);
    padding: 1px 5px;
    color: var(--ink);
    white-space: nowrap;
  }
  .path { white-space: normal; word-break: break-word; }

  ul, ol { margin: 0 0 16px; padding-left: 1.15rem; }
  li { margin-bottom: 7px; }
  li::marker { color: var(--muted); }

  /* ---------- verdict ---------- */

  .verdict {
    border: 1px solid var(--rule);
    border-top: 3px solid var(--sev-critical);
    background: var(--surface);
    padding: 26px 28px;
  }
  .verdict .line {
    font-family: var(--f-display);
    font-size: 1.28rem;
    font-weight: 600;
    line-height: 1.4;
    margin: 0 0 14px;
    text-wrap: balance;
  }
  .verdict p:last-child { margin-bottom: 0; }

  .tally {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(112px, 1fr));
    gap: 1px;
    background: var(--rule);
    border: 1px solid var(--rule);
    margin: 26px 0 0;
  }
  .tally div { background: var(--surface); padding: 14px 15px; }
  .tally .n {
    font-family: var(--f-mono);
    font-size: 1.7rem;
    font-weight: 600;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    display: block;
    margin-bottom: 7px;
  }
  .tally .l {
    font-family: var(--f-mono);
    font-size: 10.5px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .n-critical { color: var(--sev-critical); }
  .n-high { color: var(--sev-high); }
  .n-medium { color: var(--sev-medium); }
  .n-low { color: var(--sev-low); }

  /* ---------- diagram ---------- */

  .figure { margin: 0 0 22px; }
  .figure-scroll { overflow-x: auto; border: 1px solid var(--rule); background: var(--surface); }
  .figure svg { display: block; min-width: 780px; width: 100%; height: auto; }
  figcaption {
    font-size: 13.5px;
    color: var(--muted);
    margin-top: 11px;
    max-width: 72ch;
  }

  .s-box { fill: var(--surface-2); stroke: var(--rule); stroke-width: 1; }
  .s-box-dead { fill: var(--wash-critical); stroke: var(--sev-critical); stroke-width: 1; stroke-dasharray: 3 3; }
  .s-label { font-family: var(--f-mono); font-size: 12.5px; fill: var(--ink); }
  .s-label-dead { font-family: var(--f-mono); font-size: 12.5px; fill: var(--sev-critical); }
  .s-note { font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.08em; fill: var(--muted); }
  .s-note-hot { font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.08em; fill: var(--sev-critical); }
  .s-edge { stroke: var(--ink-2); stroke-width: 1.4; fill: none; }
  .s-edge-dead { stroke: var(--sev-critical); stroke-width: 1.6; fill: none; stroke-dasharray: 5 4; }
  .s-band { fill: none; stroke: var(--rule); stroke-width: 1; stroke-dasharray: 2 3; }

  /* ---------- tables ---------- */

  .table-scroll { overflow-x: auto; border: 1px solid var(--rule); }
  table { border-collapse: collapse; width: 100%; min-width: 640px; background: var(--surface); }
  th, td {
    text-align: left;
    padding: 11px 14px;
    border-bottom: 1px solid var(--rule-soft);
    vertical-align: top;
    font-size: 14px;
  }
  thead th {
    font-family: var(--f-mono);
    font-size: 10.5px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    font-weight: 500;
    border-bottom: 1px solid var(--rule);
    background: var(--surface-2);
  }
  tbody tr:last-child td { border-bottom: none; }
  td .m { background: none; padding: 0; }

  /* ---------- findings ---------- */

  .finding {
    border: 1px solid var(--rule);
    border-top-width: 3px;
    background: var(--surface);
    padding: 24px 26px;
    margin-bottom: 26px;
  }
  .f-critical { border-top-color: var(--sev-critical); }
  .f-high { border-top-color: var(--sev-high); }
  .f-medium { border-top-color: var(--sev-medium); }
  .f-low { border-top-color: var(--sev-low); }

  .f-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 9px;
    margin-bottom: 13px;
  }
  .f-id {
    font-family: var(--f-mono);
    font-size: 13px;
    font-weight: 600;
    color: var(--ink);
    background: var(--surface-2);
    padding: 3px 8px;
  }
  .chip {
    font-family: var(--f-mono);
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 4px 8px;
    border: 1px solid currentColor;
  }
  .c-critical { color: var(--sev-critical); background: var(--wash-critical); }
  .c-high { color: var(--sev-high); background: var(--wash-high); }
  .c-medium { color: var(--sev-medium); background: var(--wash-medium); }
  .c-low { color: var(--sev-low); }
  .c-reach { color: var(--sev-critical); background: var(--wash-critical); }
  .c-latent { color: var(--muted); }

  .f-title {
    font-family: var(--f-display);
    font-weight: 600;
    font-size: 1.2rem;
    line-height: 1.32;
    margin: 0 0 14px;
    text-wrap: balance;
  }

  .f-block { margin-top: 20px; }
  .f-block > h4 {
    font-family: var(--f-mono);
    font-size: 10.5px;
    font-weight: 500;
    letter-spacing: 0.11em;
    text-transform: uppercase;
    color: var(--muted);
    margin: 0 0 9px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--rule-soft);
  }

  ol.repro { counter-reset: step; list-style: none; padding-left: 0; margin-bottom: 0; }
  ol.repro li {
    counter-increment: step;
    position: relative;
    padding-left: 32px;
    margin-bottom: 10px;
  }
  ol.repro li::before {
    content: counter(step);
    position: absolute;
    left: 0;
    top: 1px;
    font-family: var(--f-mono);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    color: var(--signal);
    border: 1px solid var(--rule);
    background: var(--ground);
    width: 21px;
    height: 21px;
    display: grid;
    place-items: center;
  }

  ul.evidence { list-style: none; padding-left: 0; margin-bottom: 0; }
  ul.evidence li {
    font-size: 13.5px;
    padding-left: 15px;
    position: relative;
    margin-bottom: 8px;
  }
  ul.evidence li::before {
    content: "";
    position: absolute;
    left: 0;
    top: 0.72em;
    width: 7px;
    height: 1px;
    background: var(--signal);
  }
  ul.evidence .path {
    font-family: var(--f-mono);
    font-size: 12.5px;
    color: var(--ink);
  }

  .fix {
    border-left: 2px solid var(--signal);
    background: var(--wash-ok);
    padding: 14px 18px;
    margin-top: 20px;
    font-size: 14.5px;
  }
  .fix strong {
    font-family: var(--f-mono);
    font-size: 10.5px;
    font-weight: 500;
    letter-spacing: 0.11em;
    text-transform: uppercase;
    color: var(--signal);
    display: block;
    margin-bottom: 7px;
  }
  .fix p:last-child { margin-bottom: 0; }

  /* ---------- invariants ---------- */

  .inv {
    display: grid;
    gap: 1px;
    background: var(--rule);
    border: 1px solid var(--rule);
  }
  .inv > div { background: var(--surface); padding: 15px 18px; }
  .inv h4 {
    font-family: var(--f-body);
    font-size: 14.5px;
    font-weight: 600;
    margin: 0 0 5px;
    display: flex;
    gap: 9px;
    align-items: baseline;
  }
  .inv h4 span {
    font-family: var(--f-mono);
    font-size: 11px;
    color: var(--sev-ok);
    flex: none;
  }
  .inv p { font-size: 13.5px; color: var(--ink-2); margin: 0; }

  .limits {
    border: 1px dashed var(--rule);
    padding: 20px 24px;
    background: var(--surface);
  }

  footer {
    border-top: 1px solid var(--rule);
    margin-top: 72px;
    padding-top: 20px;
    font-family: var(--f-mono);
    font-size: 11.5px;
    letter-spacing: 0.05em;
    color: var(--muted);
  }

  @media (max-width: 620px) {
    body { padding: 0 18px 72px; }
    .verdict, .finding { padding: 20px 18px; }
  }
</style>

<div class="shell">

<div class="header masthead">

Independent audit · Cardvert · read-only

# Campaign Lifecycle Audit

A trace of one campaign from draft creation through creative review,
upload finalization, installation evidence, driver acceptance, admin
activation, vehicle work and cancellation — against the exact revision
below.

Repository  
oluwasolaonigbinde/mobility

Branch  
feat/pkg-04-build-first

Commit  
637841d95493bcc24334356da42097fa53a5d16f

Tree  
3751f22346eae91a9916eeb41d8a8b51b63254ba

</div>

<div class="section">

<div class="sec-head">

<span class="sec-num">01</span>

## Verdict

</div>

<div class="verdict">

The campaign lifecycle is built to a high standard up to admin approval,
and then stops. No code path at this revision writes the `scheduled` or
`active` campaign states, so every gate downstream of approval —
assignment, acceptance, activation, trips, mid-flight changes — is
unreachable in a deployed environment.

The machinery behind those gates is genuinely strong: immutable
submission snapshots, database-enforced append-only evidence,
digest-bound activation snapshots, deterministic lock ordering, and
complete route-level audit coverage. It is the connecting edge that is
absent, not the controls. Four further defects sit inside that
unreachable half; they do not bite today, but each one activates the
moment the launch edge is added, so they should be fixed in the same
change.

**Assessment:** not fit for a controlled pilot as it stands. The gap
between the delivery record and the code is the material concern —
<span class="m">PKG-04</span> is recorded <span class="m">DONE</span>
and its activation, mid-flight-change and cancellation items are all
marked <span class="m">DONE</span>, while the state transition those
items depend on was never built and no test exercises it.

</div>

<div class="tally">

<div>

<span class="n n-critical">1</span><span class="l">Critical</span>

</div>

<div>

<span class="n n-high">2</span><span class="l">High</span>

</div>

<div>

<span class="n n-medium">1</span><span class="l">Medium</span>

</div>

<div>

<span class="n n-low">1</span><span class="l">Low</span>

</div>

<div>

<span class="n"
style="color:var(--sev-ok)">9</span><span class="l">Invariants
held</span>

</div>

</div>

</div>

<div class="section">

<div class="sec-head">

<span class="sec-num">02</span>

## Access and scope

</div>

<div class="col">

Commit <span class="m">637841d</span> was verified through the GitHub
API as the head of <span class="m">feat/pkg-04-build-first</span>,
carrying tree <span class="m">3751f22</span> and the message
*“docs(progress): close provider-neutral build controller”*
(2026-08-28). Every file was read at that exact revision by object
address; nothing was checked out, and <span class="m">master</span> was
not inspected.

The audit is read-only. No storage provider, malware scanner, payment
gateway or other external service was invoked, and no test suite was
run. Findings below are derived from source, migrations and the delivery
record, and each is labelled with whether the behaviour is reachable
today.

**Limitation worth stating plainly:** because no suite was run, the
claim that “no test catches F1” rests on reading the test fixtures, not
on observing a failure. The fixture evidence is direct — tests construct
campaigns at <span class="m">SCHEDULED</span> and
<span class="m">ACTIVE</span> by writing the column, never through the
API — but it is inference from source, not execution.

</div>

</div>

<div class="section">

<div class="sec-head">

<span class="sec-num">03</span>

## Lifecycle and authority map

</div>

<figure class="figure">
<div class="figure-scroll">
<img
src="data:image/svg+xml;base64,PHN2ZyB2aWV3Ym94PSIwIDAgOTAwIDMzMCIgcm9sZT0iaW1nIiBhcmlhLWxhYmVsPSJDYW1wYWlnbiBzdGF0ZSBtYWNoaW5lIHNob3dpbmcgZHJhZnQsIHBlbmRpbmcgcmV2aWV3LCBhcHByb3ZlZCwgcmVqZWN0ZWQgYW5kIGNhbmNlbGxlZCBhcyByZWFjaGFibGUgc3RhdGVzLCBhbmQgc2NoZWR1bGVkLCBhY3RpdmUsIHBhdXNlZCBhbmQgY29tcGxldGVkIGFzIHN0YXRlcyB3aXRoIG5vIHdyaXRlciwgc2VwYXJhdGVkIGJ5IGEgc2V2ZXJlZCB0cmFuc2l0aW9uLiI+CiAgICAgICAgICA8IS0tIGJhbmQgbGFiZWxzIC0tPgogICAgICAgICAgPHRleHQgY2xhc3M9InMtbm90ZSIgeD0iMjgiIHk9IjI4Ij5SRUFDSEFCTEUgVEhST1VHSCBUSEUgQVBJPC90ZXh0PgogICAgICAgICAgPHRleHQgY2xhc3M9InMtbm90ZS1ob3QiIHg9IjU2MCIgeT0iMjgiPk5PIFdSSVRFUiBFWElTVFMgwrcgVU5SRUFDSEFCTEU8L3RleHQ+CiAgICAgICAgICA8bGluZSBjbGFzcz0icy1iYW5kIiB4MT0iNTQwIiB5MT0iNDAiIHgyPSI1NDAiIHkyPSIzMDAiPjwvbGluZT4KCiAgICAgICAgICA8IS0tIHJlYWNoYWJsZSBzdGF0ZXMgLS0+CiAgICAgICAgICA8cmVjdCBjbGFzcz0icy1ib3giIHg9IjI4IiB5PSI3NiIgd2lkdGg9IjEwNCIgaGVpZ2h0PSI0MCIgLz4KICAgICAgICAgIDx0ZXh0IGNsYXNzPSJzLWxhYmVsIiB4PSI4MCIgeT0iMTAxIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj5kcmFmdDwvdGV4dD4KCiAgICAgICAgICA8cmVjdCBjbGFzcz0icy1ib3giIHg9IjE3NiIgeT0iNzYiIHdpZHRoPSIxNTIiIGhlaWdodD0iNDAiIC8+CiAgICAgICAgICA8dGV4dCBjbGFzcz0icy1sYWJlbCIgeD0iMjUyIiB5PSIxMDEiIHRleHQtYW5jaG9yPSJtaWRkbGUiPnBlbmRpbmdfcmV2aWV3PC90ZXh0PgoKICAgICAgICAgIDxyZWN0IGNsYXNzPSJzLWJveCIgeD0iMzcyIiB5PSI3NiIgd2lkdGg9IjExOCIgaGVpZ2h0PSI0MCIgLz4KICAgICAgICAgIDx0ZXh0IGNsYXNzPSJzLWxhYmVsIiB4PSI0MzEiIHk9IjEwMSIgdGV4dC1hbmNob3I9Im1pZGRsZSI+YXBwcm92ZWQ8L3RleHQ+CgogICAgICAgICAgPHJlY3QgY2xhc3M9InMtYm94IiB4PSIzNzIiIHk9IjE2MCIgd2lkdGg9IjExOCIgaGVpZ2h0PSI0MCIgLz4KICAgICAgICAgIDx0ZXh0IGNsYXNzPSJzLWxhYmVsIiB4PSI0MzEiIHk9IjE4NSIgdGV4dC1hbmNob3I9Im1pZGRsZSI+cmVqZWN0ZWQ8L3RleHQ+CgogICAgICAgICAgPHJlY3QgY2xhc3M9InMtYm94IiB4PSIxNzYiIHk9IjI1MiIgd2lkdGg9IjE1MiIgaGVpZ2h0PSI0MCIgLz4KICAgICAgICAgIDx0ZXh0IGNsYXNzPSJzLWxhYmVsIiB4PSIyNTIiIHk9IjI3NyIgdGV4dC1hbmNob3I9Im1pZGRsZSI+Y2FuY2VsbGVkPC90ZXh0PgoKICAgICAgICAgIDwhLS0gZWRnZXMgYW1vbmcgcmVhY2hhYmxlIC0tPgogICAgICAgICAgPHBhdGggY2xhc3M9InMtZWRnZSIgZD0iTTEzMiA5NiBIMTcwIiBtYXJrZXItZW5kPSJ1cmwoI2FyKSIgLz4KICAgICAgICAgIDxwYXRoIGNsYXNzPSJzLWVkZ2UiIGQ9Ik0zMjggOTYgSDM2NiIgbWFya2VyLWVuZD0idXJsKCNhcikiIC8+CiAgICAgICAgICA8cGF0aCBjbGFzcz0icy1lZGdlIiBkPSJNMzI4IDEwNiBxMjIgNzQgNDAgNzQiIG1hcmtlci1lbmQ9InVybCgjYXIpIiAvPgogICAgICAgICAgPHBhdGggY2xhc3M9InMtZWRnZSIgZD0iTTM3MiAxODAgSDM0NCBxLTE4IDAgLTE4IC0xOCBWMTE2IiBtYXJrZXItZW5kPSJ1cmwoI2FyKSIgLz4KICAgICAgICAgIDxwYXRoIGNsYXNzPSJzLWVkZ2UiIGQ9Ik00MzEgMjAwIFYyMzYgcTAgMTYgLTE2IDE2IEgzMzQiIG1hcmtlci1lbmQ9InVybCgjYXIpIiAvPgoKICAgICAgICAgIDx0ZXh0IGNsYXNzPSJzLW5vdGUiIHg9IjM1MiIgeT0iMTUwIj5yZWplY3Q8L3RleHQ+CiAgICAgICAgICA8dGV4dCBjbGFzcz0icy1ub3RlIiB4PSIxOTYiIHk9IjE1MCI+cmVzdWJtaXQ8L3RleHQ+CiAgICAgICAgICA8dGV4dCBjbGFzcz0icy1ub3RlIiB4PSIzNTYiIHk9IjIzMCI+Y2FuY2VsPC90ZXh0PgoKICAgICAgICAgIDwhLS0gc2V2ZXJlZCBlZGdlIC0tPgogICAgICAgICAgPHBhdGggY2xhc3M9InMtZWRnZS1kZWFkIiBkPSJNNDkwIDk2IEg1MjQiIC8+CiAgICAgICAgICA8cGF0aCBjbGFzcz0icy1lZGdlLWRlYWQiIGQ9Ik01NTYgOTYgSDU5MCIgbWFya2VyLWVuZD0idXJsKCNhci1kZWFkKSIgLz4KICAgICAgICAgIDxsaW5lIGNsYXNzPSJzLWVkZ2UtZGVhZCIgeDE9IjUzMCIgeTE9Ijc2IiB4Mj0iNTE2IiB5Mj0iMTE4IiBzdHJva2UtZGFzaGFycmF5PSIwIj48L2xpbmU+CiAgICAgICAgICA8bGluZSBjbGFzcz0icy1lZGdlLWRlYWQiIHgxPSI1NTAiIHkxPSI3NiIgeDI9IjUzNiIgeTI9IjExOCIgc3Ryb2tlLWRhc2hhcnJheT0iMCI+PC9saW5lPgogICAgICAgICAgPHRleHQgY2xhc3M9InMtbm90ZS1ob3QiIHg9IjQ3MCIgeT0iNTYiPkYxIMK3IE5PIFRSQU5TSVRJT048L3RleHQ+CgogICAgICAgICAgPCEtLSB1bnJlYWNoYWJsZSBzdGF0ZXMgLS0+CiAgICAgICAgICA8cmVjdCBjbGFzcz0icy1ib3gtZGVhZCIgeD0iNTk2IiB5PSI3NiIgd2lkdGg9IjExOCIgaGVpZ2h0PSI0MCIgLz4KICAgICAgICAgIDx0ZXh0IGNsYXNzPSJzLWxhYmVsLWRlYWQiIHg9IjY1NSIgeT0iMTAxIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj5zY2hlZHVsZWQ8L3RleHQ+CgogICAgICAgICAgPHJlY3QgY2xhc3M9InMtYm94LWRlYWQiIHg9Ijc1NiIgeT0iNzYiIHdpZHRoPSIxMTgiIGhlaWdodD0iNDAiIC8+CiAgICAgICAgICA8dGV4dCBjbGFzcz0icy1sYWJlbC1kZWFkIiB4PSI4MTUiIHk9IjEwMSIgdGV4dC1hbmNob3I9Im1pZGRsZSI+YWN0aXZlPC90ZXh0PgoKICAgICAgICAgIDxyZWN0IGNsYXNzPSJzLWJveC1kZWFkIiB4PSI2NzYiIHk9IjE2MCIgd2lkdGg9IjExOCIgaGVpZ2h0PSI0MCIgLz4KICAgICAgICAgIDx0ZXh0IGNsYXNzPSJzLWxhYmVsLWRlYWQiIHg9IjczNSIgeT0iMTg1IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj5wYXVzZWQ8L3RleHQ+CgogICAgICAgICAgPHJlY3QgY2xhc3M9InMtYm94LWRlYWQiIHg9IjY3NiIgeT0iMjUyIiB3aWR0aD0iMTE4IiBoZWlnaHQ9IjQwIiAvPgogICAgICAgICAgPHRleHQgY2xhc3M9InMtbGFiZWwtZGVhZCIgeD0iNzM1IiB5PSIyNzciIHRleHQtYW5jaG9yPSJtaWRkbGUiPmNvbXBsZXRlZDwvdGV4dD4KCiAgICAgICAgICA8cGF0aCBjbGFzcz0icy1lZGdlLWRlYWQiIGQ9Ik03MTQgOTYgSDc1MCIgbWFya2VyLWVuZD0idXJsKCNhci1kZWFkKSIgLz4KICAgICAgICAgIDxwYXRoIGNsYXNzPSJzLWVkZ2UtZGVhZCIgZD0iTTY5MCAxMTYgcTEwIDQ0IDI0IDQ0IiAvPgogICAgICAgICAgPHBhdGggY2xhc3M9InMtZWRnZS1kZWFkIiBkPSJNNzkwIDExNiBxLTEwIDQ0IC0yNCA0NCIgLz4KICAgICAgICAgIDx0ZXh0IGNsYXNzPSJzLW5vdGUtaG90IiB4PSI2MDAiIHk9IjIyMiI+YnVkZ2V0IHBhdXNlIC8gcmVzdW1lPC90ZXh0PgogICAgICAgICAgPHRleHQgY2xhc3M9InMtbm90ZS1ob3QiIHg9IjYwMCIgeT0iMzE2Ij5ubyB3cml0ZXIgYXQgYWxsPC90ZXh0PgoKICAgICAgICAgIDxkZWZzPgogICAgICAgICAgICA8bWFya2VyIGlkPSJhciIgdmlld2JveD0iMCAwIDggOCIgcmVmeD0iNyIgcmVmeT0iNCIgbWFya2Vyd2lkdGg9IjciIG1hcmtlcmhlaWdodD0iNyIgb3JpZW50PSJhdXRvLXN0YXJ0LXJldmVyc2UiPgogICAgICAgICAgICAgIDxwYXRoIGQ9Ik0wIDAgTDggNCBMMCA4IHoiIGZpbGw9InZhcigtLWluay0yKSIgLz4KICAgICAgICAgICAgPC9tYXJrZXI+CiAgICAgICAgICAgIDxtYXJrZXIgaWQ9ImFyLWRlYWQiIHZpZXdib3g9IjAgMCA4IDgiIHJlZng9IjciIHJlZnk9IjQiIG1hcmtlcndpZHRoPSI3IiBtYXJrZXJoZWlnaHQ9IjciIG9yaWVudD0iYXV0by1zdGFydC1yZXZlcnNlIj4KICAgICAgICAgICAgICA8cGF0aCBkPSJNMCAwIEw4IDQgTDAgOCB6IiBmaWxsPSJ2YXIoLS1zZXYtY3JpdGljYWwpIiAvPgogICAgICAgICAgICA8L21hcmtlcj4KICAgICAgICAgIDwvZGVmcz4KICAgICAgICA8L3N2Zz4=" />
</div>
<figcaption>Every write to <span class="m">Campaign.status</span> across
the application, mapped. The right-hand band is not merely unused — the
two budget transitions there can only move a campaign that is already
<span class="m">scheduled</span> or <span class="m">active</span>, so
nothing can enter the band at all.</figcaption>
</figure>

### Who holds which authority

<div class="table-scroll">

| Step | Actor | Authority and where it is enforced |
|----|----|----|
| Create draft | Advertiser (owner/manager) | Must be created as <span class="m">draft</span>; any other status is rejected. <span class="m">campaigns.py:96</span> |
| Edit | Advertiser | Only in <span class="m">draft</span> or <span class="m">rejected</span>, under a row lock; currency freezes once commercial terms are accepted. <span class="m">campaigns.py:190</span> |
| Submit for review | Advertiser | Writes an immutable canonical snapshot plus SHA-256 into append-only <span class="m">campaign_review_events</span>. <span class="m">campaigns.py:358</span> |
| Approve / reject | Admin | Binds the exact submission event; rejection requires a non-blank reason; approval refuses one. <span class="m">campaigns.py:418</span> |
| **Schedule / launch** | — | **No implementation.** See F1. |
| Creative upload | Advertiser | Presigned POST bound to exact type/size/checksum; server re-stats and promotes. <span class="m">stored_files.py:314</span> |
| Malware scan | Worker only | No API can set <span class="m">scan_status</span>; magic-byte sniff must match the declared type or the file is <span class="m">rejected</span>. <span class="m">stored_files.py:752</span> |
| Creative review | Admin | Serialized campaign → creative → file locks; re-checks the clean managed file on approval. <span class="m">campaigns.py:1069</span> |
| Offer assignment | Admin | Requires <span class="m">scheduled/active/paused</span>, an approved creative, frozen zones, and payout-v3 terms. <span class="m">campaign_assignments.py:434</span> |
| Accept / decline | Driver | Driver-owned decision; creates the frozen rule binding. Admin cannot accept on a driver's behalf. <span class="m">campaign_assignments.py:1528</span> |
| Activate | Admin | Twelve prerequisites re-checked under lock, then one digest-bound activation snapshot. <span class="m">campaign_assignments.py:1748</span> |
| Installation evidence | Configured uploader, admin reviews | Exact configured view set, clean subject-owned images, append-only revisions. <span class="m">installation_evidence.py:118</span> |
| Trip work | Driver | Requires active assignment, active campaign, activation snapshot, funding, and a current display proof. <span class="m">trips.py:194</span> |
| Mid-flight change | Advertiser requests; admin approves reductions and date changes | Pure expansions self-apply against funded headroom. <span class="m">campaign_changes.py:293</span> |
| Cancel campaign | Advertiser | One immutable cutoff: releases reservations, cancels assignments, computes settlement disposition. <span class="m">campaign_cancellations.py:97</span> |

</div>

</div>

<div class="section">

<div class="sec-head">

<span class="sec-num">04</span>

## Confirmed findings

</div>

<div class="f-head">

<span class="f-id">F1</span>
<span class="chip c-critical">Critical</span>
<span class="chip c-reach">Reachable now</span>

</div>

### The lifecycle dead-ends at <span class="m">approved</span>: nothing in the application writes <span class="m">scheduled</span> or <span class="m">active</span>

A campaign created through the product can reach <span class="m">draft →
pending_review → approved</span> and can be cancelled from there. It can
never become <span class="m">scheduled</span> or
<span class="m">active</span>, because no code writes those values.
Every downstream gate demands one of them, so assignment offers, driver
acceptance, admin activation, trip tracking and mid-flight changes are
all unreachable for any real campaign.

The two budget transitions cannot bootstrap the state either: the pause
only fires when the campaign is already <span class="m">scheduled</span>
or <span class="m">active</span>, and the resume restores the status the
pause recorded. Recording a production start does not touch
<span class="m">Campaign.status</span> either.

<div class="f-block">

#### Evidence — the complete set of status writers

- <span class="path">app/services/campaigns.py:372</span> — writes
  <span class="m">pending_review</span>
- <span class="path">app/services/campaigns.py:453</span> — writes
  <span class="m">approved</span> or <span class="m">rejected</span>
- <span class="path">app/services/billing.py:3310</span> — writes
  <span class="m">paused</span>, guarded by <span class="m">status IN
  (scheduled, active)</span>
- <span class="path">app/services/billing.py:3440</span> — restores
  <span class="m">pause.prior_status</span>, requiring the campaign to
  already be <span class="m">paused</span>
- <span class="path">app/services/campaign_cancellations.py:265</span> —
  writes <span class="m">cancelled</span>

</div>

<div class="f-block">

#### Evidence — consumers that can therefore never pass

- <span class="path">app/services/campaign_assignments.py:226</span> —
  <span class="m">ensure_campaign_assignable</span> requires
  scheduled/active/paused
- <span class="path">app/services/campaign_assignments.py:354</span> —
  <span class="m">ensure_campaign_activatable</span> requires active
- <span class="path">app/services/trips.py:109</span> —
  <span class="m">ensure_campaign_active_for_trip</span> requires active
- <span class="path">app/services/campaign_changes.py:151</span> —
  mid-flight changes require scheduled/active/paused

</div>

<div class="f-block">

#### Why it was not caught

- <span class="path">tests/conftest.py:395</span> —
  <span class="m">create_test_campaign</span> writes the status column
  directly, so every downstream test starts from a state the API cannot
  produce
- <span class="path">app/seeds/demo.py:115</span> — the seed that
  creates <span class="m">ACTIVE</span> campaigns refuses to run in
  production-like environments, so a deployed pilot has no such campaign
  at all
- <span class="path">docs/architecture.md:1468</span> — records the
  <span class="m">approved → scheduled</span> edge as
  <span class="m">\[TARGET\]</span> “behind W2-03C/D's complete launch
  gate”, while <span class="path">docs/progress.md:1537–1538</span>
  marks both W2-03C and W2-03D <span class="m">DONE</span> and
  <span class="path">docs/progress.md:76</span> closes PKG-04

The frontend is honest about it: the advertiser campaign page renders
“Approved. Scheduling and activation are not available in this step.”
(<span class="path">frontend/src/app/advertiser/campaigns/\[campaignId\]/status-actions.tsx</span>).
This is a delivery-record error rather than a frontend/backend mismatch.

</div>

<div class="fix">

**Smallest fix**

Add one admin transition — <span class="m">approved → scheduled</span> —
in <span class="path">app/services/campaigns.py</span>, taking the same
campaign row lock and writing a
<span class="m">campaign_review_events</span> row bound to the approval,
plus its route and audit action.

Do *not* take the apparently smaller route of adding
<span class="m">approved</span> to
<span class="m">ensure_campaign_assignable</span>. The
<span class="m">budget_campaign_transitions</span> check constraint
(<span class="path">app/models/billing.py:1023</span>) restricts both
<span class="m">prior_status</span> and
<span class="m">new_status</span> to <span class="m">scheduled \| active
\| paused</span>, so a campaign working while still
<span class="m">approved</span> could never be budget-paused — trading a
visible gap for a silent one.

</div>

<div class="f-head">

<span class="f-id">F2</span> <span class="chip c-high">High</span>
<span class="chip c-latent">Blocked by F1</span>

</div>

### Nothing enforces one active assignment per driver, but the driver's own read path treats a second one as a 500

Assignment exclusivity is enforced per *vehicle* only. Trips, by
contrast, have both a per-vehicle and a per-driver partial unique index.
A driver who owns two vehicles can therefore hold two simultaneously
active assignments — a state the read path declares impossible.

The consequence is a silent, permanent lockout rather than a visible
error: the driver portal treats the 500 as “unavailable”, so activation
authority and the tracker disappear from the PWA with no explanation and
no path to recovery.

<div class="f-block">

#### Reproduction

1.  Admin creates a driver profile with no public application, so the
    applicant eligibility gate returns early
    (<span class="path">vehicle_onboarding.py:250–254</span>).
2.  Admin creates two vehicles for that driver, both
    <span class="m">status=active</span>; nothing bounds vehicles per
    driver (<span class="path">app/services/vehicles.py:71</span>).
3.  Admin offers one campaign to (driver, vehicle A) and the same
    campaign to (driver, vehicle B). The duplicate guard is keyed on
    <span class="m">(campaign_id, vehicle_id)</span>, so both are
    accepted.
4.  The driver accepts both.
    <span class="m">accept_driver_assignment</span> checks profile,
    vehicle, ownership and eligibility — never other assignments held by
    the same driver.
5.  Admin activates both.
    <span class="m">ensure_no_other_active_assignment_for_vehicle</span>
    and the backing index are vehicle-scoped, so neither blocks.
6.  <span class="m">GET
    /api/v1/driver/campaign-assignments/active</span> now raises
    <span class="m">MULTIPLE_ACTIVE_ASSIGNMENTS</span> with status 500,
    permanently.

</div>

<div class="f-block">

#### Evidence

- <span class="path">app/models/campaign_assignment.py:89–95</span> —
  <span class="m">uq_campaign_assignments_vehicle_active</span> indexes
  <span class="m">vehicle_id</span> alone; confirmed in
  <span class="path">alembic/versions/0006_campaign_assignments.py:100–106</span>
- <span class="path">app/services/campaign_assignments.py:188</span> —
  the activation pre-check is vehicle-scoped
- <span class="path">app/services/campaign_assignments.py:2167–2186</span>
  — the read path raises a 500 on more than one row
- <span class="path">frontend/src/lib/driver/load-campaign-journey.ts:28–40</span>
  — any non-401/403 error collapses to <span class="m">{state:
  "unavailable"}</span>, so the failure is silent
- <span class="path">app/db/integrity.py:16–19</span> — the registered
  exclusivity set confirms the asymmetry: trips have
  <span class="m">uq_trip_sessions_driver_profile_active</span>,
  assignments have no driver-level equivalent

</div>

<div class="fix">

**Smallest fix**

Mirror the pattern the trip table already uses. Add a partial unique
index on <span class="m">campaign_assignments(driver_profile_id) WHERE
status = 'active'</span>, register its name in both maps in
<span class="path">app/db/integrity.py</span>, add the matching
pre-check beside the vehicle one in
<span class="m">activate_admin_assignment</span>, and add its envelope
to <span class="m">ASSIGNMENT_CONFLICT_ENVELOPES</span> so a lost race
returns the same stable 409 the pre-check returns.

</div>

<div class="f-head">

<span class="f-id">F3</span> <span class="chip c-high">High</span>
<span class="chip c-latent">Blocked by F1</span>

</div>

### A driver can self-deactivate to void an outstanding display-proof challenge and release the earnings it was meant to hold

The high-earner renewal challenge is the control that turns an
unanswered proof request into a fraud hold. Both the sweep that issues
challenges and the function that expires them consider only
<span class="m">ACTIVE</span> assignments — and deactivation is a
driver-initiated action with no check for outstanding verifications.

A driver who receives a challenge can therefore deactivate before it
falls due. The pending row is never evaluated again, never becomes
<span class="m">MISSED</span>, and never produces the
<span class="m">MISSED_DISPLAY_CHALLENGE</span> flag. Release is gated
solely on active fraud flags, so the earnings the challenge existed to
verify release on schedule.

<div class="f-block">

#### Reproduction

1.  The sweep issues a <span class="m">HIGH_EARNER_RENEWAL</span>
    verification with <span class="m">due_at = now +
    response_hours</span>
    (<span class="path">evidence_verification.py:202</span>).
2.  Before <span class="m">due_at</span>, the driver calls
    <span class="m">POST
    /driver/campaign-assignments/{id}/deactivate</span>. The only
    condition is that the assignment is active
    (<span class="path">campaign_assignments.py:2056–2061</span>).
3.  The assignment becomes <span class="m">deactivated</span>.
4.  The sweep's candidate query selects only active assignments
    (<span class="path">jobs/evidence_verification.py:57</span>), and
    <span class="m">evaluate_assignment_verification</span> returns an
    empty result for any other status
    (<span class="path">services/evidence_verification.py:434</span>).
5.  <span class="m">\_expire_due_challenges</span> never runs for that
    row; no fraud flag is created.
6.  Release sees no active hold
    (<span class="path">earnings_release.py:88–99</span>) and pays out.

</div>

<div class="f-block">

#### Evidence

- <span class="path">app/services/campaign_assignments.py:2013</span> —
  <span class="m">deactivate_driver_assignment</span> checks only the
  assignment status
- <span class="path">app/services/evidence_verification.py:153–199</span>
  — <span class="m">\_expire_due_challenges</span> is the sole producer
  of the missed-challenge flag
- <span class="path">app/services/earnings_release.py:88–99</span> —
  release is predicated on
  <span class="m">fraud_hold_active_clause()</span> alone

</div>

<div class="fix">

**Smallest fix**

Let due challenges expire regardless of assignment status. Widen the
sweep's candidate query to include <span class="m">deactivated</span>,
and in <span class="m">evaluate_assignment_verification</span> run
<span class="m">\_expire_due_challenges</span> before the status early
return, keeping issuance of new challenges active-only. That closes the
escape without adding a new state or blocking a driver's right to
deactivate.

</div>

<div class="f-head">

<span class="f-id">F4</span> <span class="chip c-medium">Medium</span>
<span class="chip c-latent">Blocked by F1</span>

</div>

### After a mid-flight extension, drivers on pre-extension assignments can legally start trips that are worth nothing

Trip start is gated on the campaign's *live* window, while payout is
clipped to the *frozen* window captured in the assignment's rule binding
at acceptance. Extending a campaign's <span class="m">end_at</span>
mid-flight moves the first boundary and not the second.

A driver whose assignment was accepted before the extension is therefore
permitted to start, run and complete trips throughout the extension
period, and every second of that work falls outside the frozen window
and earns nothing. Nothing warns the driver, and nothing refuses the
trip.

<div class="f-block">

#### Evidence

- <span class="path">app/services/trips.py:109–124</span> —
  <span class="m">ensure_campaign_active_for_trip</span> compares
  against <span class="m">campaign.end_at</span>
- <span class="path">app/services/payouts.py:1329–1341</span> —
  <span class="m">frozen_campaign_window</span> returns the binding's
  window
- <span class="path">app/services/payouts.py:171–187</span> —
  <span class="m">payout_time_bounds</span> sets
  <span class="m">effective_window_end</span> from that frozen value
- <span class="path">app/services/payout_eligibility.py:503–504</span> —
  <span class="m">window_to</span> becomes a hard slice boundary, so
  time beyond it is not eligible
- <span class="path">app/services/campaign_changes.py:293</span> — a
  date extension is an admin-approved change that never revisits
  existing bindings

</div>

Related but *not* a defect:
<span class="m">\_additional_window_liability</span> reserves extra
liability against those same frozen bindings, which is over-conservative
rather than under. Money is not lost to the platform — it is the
driver's unpaid work that is the exposure.

<div class="fix">

**Smallest fix**

Make trip start honour the same boundary that pays it. In
<span class="m">start_driver_trip</span>, after the binding is resolved,
refuse a start past
<span class="m">binding.campaign_window_end_at</span> with a dedicated
code, so the driver is told the assignment's terms have run out rather
than working for nothing. The durable alternative — a re-offer that
issues a fresh binding on extension — is a larger change and belongs to
the same decision.

</div>

<div class="f-head">

<span class="f-id">F5</span> <span class="chip c-low">Low ·
hardening</span> <span class="chip c-latent">Not reachable</span>

</div>

### Campaign review selects the latest submission; creative review selects the *undecided* one

<span class="m">\_current_creative_submission</span> excludes
submissions that already have a decision bound to them — a correction
the delivery record notes was made after a same-second event-ordering
bug. Its campaign twin,
<span class="m">\_current_submission_event</span>, has no such filter
and relies entirely on the caller's status check.

I could not construct a reachable double-bind: the campaign row is
locked and must read <span class="m">pending_review</span>, and
re-submission is only possible from <span class="m">draft</span> or
<span class="m">rejected</span>. Reporting it as a defect would
overstate it. It is worth closing anyway, because the campaign path
resolves ties using a Python clock and a random UUID rather than the
database clock, so its safety rests on an invariant held one call frame
away.

<div class="f-block">

#### Evidence

- <span class="path">app/services/campaigns.py:402–414</span> — no
  undecided filter; ordered by <span class="m">created_at desc, id
  desc</span>
- <span class="path">app/services/campaigns.py:1050–1063</span> — the
  creative equivalent, with the <span class="m">NOT EXISTS</span> guard

</div>

<div class="fix">

**Smallest fix**

Copy the <span class="m">NOT EXISTS</span> sub-select from
<span class="m">\_current_creative_submission</span> into
<span class="m">\_current_submission_event</span>. Behaviour is
unchanged today; the guard stops depending on the caller.

</div>

</div>

<div class="section">

<div class="sec-head">

<span class="sec-num">05</span>

## Verified invariants

</div>

<div class="col">

These held under examination and are worth recording, both because they
are the strongest part of the build and because a fix for F1 must not
disturb them.

</div>

<div class="inv">

<div>

#### OK Advertisers cannot self-approve or self-launch

Creation refuses any status but <span class="m">draft</span>; generic
update refuses a status change; review states are writable only by the
dedicated admin actions.

</div>

<div>

#### OK Review evidence is append-only in the database, not just in code

Postgres triggers reject <span class="m">UPDATE</span> and
<span class="m">DELETE</span> on campaign review, creative review,
activation, installation-evidence, photo, challenge and proof tables
(migrations 0043, 0048, 0056, 0057).

</div>

<div>

#### OK Scan authority is server-side only

No route can set <span class="m">scan_status</span>. A file is
<span class="m">clean</span> only if a worker streamed it, the observed
size matched, and the magic bytes matched the declared type; the allowed
content types and the sniffer's repertoire are exactly aligned.

</div>

<div>

#### OK Creative and evidence ownership are tenant- and subject-bound

Creative files must belong to the campaign's organization; evidence
photos must be clean images owned by the assignment's driver. Both are
re-checked at approval, not only at binding.

</div>

<div>

#### OK Activation snapshots are immutable and self-verifying

Trip start recomputes the snapshot digest, re-derives every field from
live rows, and fails closed on any drift — including a changed
offer-terms hash.

</div>

<div>

#### OK Acceptance and activation are genuinely separate authorities

The driver holds the accept/decline decision; the admin holds activation
and cannot accept on the driver's behalf. A complete offer cannot be
cancelled out from under an undecided driver.

</div>

<div>

#### OK Exclusivity races return stable 409s, not 500s

Both assignment indexes and both trip indexes are registered in the
integrity classifier and mapped to the same code their guarding
pre-check returns; unrelated integrity errors deliberately stay
unexpected.

</div>

<div>

#### OK Cancellation is one idempotent, immutable cutoff

A single settlement revision records disposition, refundable amount,
released liability and every cancelled assignment id; the cutoff then
blocks new work and clips post-cutoff pings.

</div>

<div>

#### OK Audit coverage is enforced by the route table

A test derives every mutating route from the OpenAPI document and fails
on any route lacking an audit action or a named exemption.
<span class="m">KNOWN_UNAUDITED</span> is empty, and stale entries fail
too.

</div>

</div>

</div>

<div class="section">

<div class="sec-head">

<span class="sec-num">06</span>

## External provider and evidence gates

</div>

<div class="col">

These are recorded as <span class="m">MISSING</span> in the delivery
register and each one fails closed in code rather than degrading. They
bound what the lifecycle can do even after F1 is fixed.

</div>

<div class="table-scroll">

| Gate | Blocks | Behaviour when absent |
|----|----|----|
| <span class="m">EXT-EVIDENCE-POLICY</span> | Installation evidence and display proof | 503 <span class="m">INSTALLATION_EVIDENCE_POLICY_UNAVAILABLE</span> / <span class="m">DISPLAY_PROOF_POLICY_UNAVAILABLE</span>. Since evidence is an activation prerequisite, this alone blocks activation. |
| <span class="m">EXT-STORAGE-PROVIDER</span> | All creative and evidence uploads | 503 <span class="m">FILE_STORAGE_UNAVAILABLE</span> before any intent persists. |
| <span class="m">EXT-MALWARE-SCANNER</span> | Every file reaching <span class="m">clean</span> | Scan records <span class="m">error</span> with capped exponential backoff; the file stays unusable and undownloadable. |
| <span class="m">EXT-KMS-CUSTODY</span> | Production key custody for KYC and bank data | Pilot runs on the typed-settings envelope; production custody unresolved. |
| <span class="m">EXT-PAYMENT-PROVIDER</span> | Gateway checkout and signed events | W2-01C remains <span class="m">BLOCKED</span>; manual bank confirmation is the only funding route. |
| <span class="m">EXT-BUDGET-POLICY</span> | Threshold, pause and resume decisions | 503 <span class="m">BUDGET_POLICY_NOT_AUTHORIZED</span>; no automatic pause occurs. |
| <span class="m">EXT-COMMERCIAL-VALUES</span> | Real quotation and payout rates | Schema is configurable; no real values are asserted. |
| <span class="m">EXT-PILOT-PERMITS</span> | Abuja pilot authorization | W4-03B and launch remain blocked. |

</div>

</div>

<div class="section">

<div class="sec-head">

<span class="sec-num">07</span>

## Smallest fixes, in order

</div>

<div class="col">

F2 through F4 all live in the half of the lifecycle that F1 makes
unreachable. That is an argument for fixing them *with* F1, not after
it: the launch edge is precisely what turns three latent defects into
live ones, and each fix here is small enough to land in the same change.

1.  **F1 — add the missing transition.** One admin
    <span class="m">approved → scheduled</span> action, row-locked,
    bound to the approval event, audited. Not a widened
    <span class="m">ensure_campaign_assignable</span>, for the
    budget-constraint reason given above.
2.  **F2 — add the driver-level partial unique index** plus its
    pre-check, classifier registration and 409 envelope, exactly
    mirroring the trip table's existing pattern.
3.  **F3 — expire due challenges regardless of assignment status,**
    while keeping new-challenge issuance active-only.
4.  **F4 — refuse trip start past the frozen binding window,** so a
    driver is never permitted to do unpayable work.
5.  **F5 — copy the undecided-submission filter** into the campaign
    review path.

Two changes to the delivery record should accompany them: reopen the
<span class="m">PKG-04</span> items whose acceptance depends on states
the code cannot reach, and add one end-to-end test that drives a
campaign from <span class="m">POST /advertiser/campaigns</span> all the
way to a sealed trip through the API alone. A single such test would
have caught F1 before the package closed, and would catch its
recurrence.

</div>

</div>

<div class="section">

<div class="sec-head">

<span class="sec-num">08</span>

## What this audit did not establish

</div>

<div class="col limits">

- No test or suite was executed; F1's test-blindness is read from
  fixtures, not observed as a failure.
- No storage, scanner, payment or messaging provider was contacted, so
  their adapters were reviewed as source only.
- Money computation was traced only where it bears on the lifecycle —
  the window clipping in F4 and the release predicate in F3. Payout
  arithmetic, batch reconciliation and debt carry-forward were not
  audited.
- Privacy, measurement, retargeting and reporting were out of scope.
- F2 through F4 are confirmed in code and traced end to end, but not
  executed. Their reachability is stated relative to F1 and should be
  re-confirmed once the launch edge exists.

</div>

</div>

Read-only audit · commit 637841d · no external service invoked · no
suite run

</div>

