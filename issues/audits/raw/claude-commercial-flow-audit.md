---
source_surface: Claude desktop
workspace: mobility
conversation_id: 2cd1e18e-1261-4a6c-b883-1dee89f795cd
displayed_title: Cardvert commercial flow audit
displayed_model: Claude Opus 5
created_at: 2026-09-01T07:50:08.177Z
retrieved_at: 2026-09-01
collection_state: COLLECTED
completeness: complete published artifact
redactions: none
artifact_url: https://claude.ai/code/artifact/5a59fd7b-aa30-49b7-8647-bc53d8afc067
source_format: Claude HTML artifact converted to GitHub-flavored Markdown
---

# Cardvert commercial flow audit

> This is the complete published audit artifact preserved as source evidence.
> It is not yet an accepted finding or remediation decision.

Cardvert Commercial Flow Audit

<style>
  :root {
    --ground: #FAFAFB;
    --surface: #FFFFFF;
    --surface-2: #F3F4F6;
    --ink: #151A21;
    --ink-2: #39424E;
    --muted: #5C6672;
    --hair: #E1E5EA;
    --hair-strong: #C9D0D8;
    --accent: #0F5C63;
    --accent-soft: #E4F0F0;
    --crit: #A3221B;
    --crit-soft: #FBEAE8;
    --high: #8F5300;
    --high-soft: #FBF0DF;
    --med: #6E6110;
    --med-soft: #F7F3DE;
    --ok: #1C6B47;
    --ok-soft: #E4F2EA;

    --sans: "IBM Plex Sans Condensed", "Helvetica Neue", Arial, sans-serif;
    --serif: "IBM Plex Serif", Georgia, "Times New Roman", serif;
    --mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;

    --measure: 68ch;
    --pad: clamp(1.15rem, 4vw, 2.75rem);
  }

  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --ground: #0E1114;
      --surface: #161A1F;
      --surface-2: #1D2228;
      --ink: #E9ECEF;
      --ink-2: #C3CAD2;
      --muted: #949EAA;
      --hair: #262C34;
      --hair-strong: #39424C;
      --accent: #57B7B1;
      --accent-soft: #14312F;
      --crit: #F08A80;
      --crit-soft: #331916;
      --high: #E5A85C;
      --high-soft: #302213;
      --med: #D3C36A;
      --med-soft: #2B2814;
      --ok: #6BC79A;
      --ok-soft: #142B20;
    }
  }

  :root[data-theme="dark"] {
    --ground: #0E1114;
    --surface: #161A1F;
    --surface-2: #1D2228;
    --ink: #E9ECEF;
    --ink-2: #C3CAD2;
    --muted: #949EAA;
    --hair: #262C34;
    --hair-strong: #39424C;
    --accent: #57B7B1;
    --accent-soft: #14312F;
    --crit: #F08A80;
    --crit-soft: #331916;
    --high: #E5A85C;
    --high-soft: #302213;
    --med: #D3C36A;
    --med-soft: #2B2814;
    --ok: #6BC79A;
    --ok-soft: #142B20;
  }

  * { box-sizing: border-box; }

  body {
    background: var(--ground);
    color: var(--ink);
    font-family: var(--serif);
    font-size: 17px;
    line-height: 1.62;
    -webkit-font-smoothing: antialiased;
  }

  .wrap {
    max-width: 78rem;
    margin: 0 auto;
    padding: var(--pad);
    display: flex;
    flex-direction: column;
    gap: clamp(2.5rem, 6vw, 4.25rem);
  }

  .col { max-width: var(--measure); }

  h1, h2, h3, h4 { font-family: var(--sans); text-wrap: balance; margin: 0; line-height: 1.16; }

  .eyebrow {
    font-family: var(--sans);
    font-size: .74rem;
    font-weight: 600;
    letter-spacing: .13em;
    text-transform: uppercase;
    color: var(--muted);
  }

  /* ---------- masthead ---------- */
  .masthead { display: flex; flex-direction: column; gap: 1.5rem; }
  .masthead h1 {
    font-size: clamp(2.1rem, 5.6vw, 3.5rem);
    font-weight: 700;
    letter-spacing: -.015em;
  }
  .standfirst {
    max-width: var(--measure);
    font-size: 1.12rem;
    color: var(--ink-2);
  }
  .rule { height: 1px; background: var(--hair); border: 0; margin: 0; }
  .rule-heavy { height: 2px; background: var(--ink); border: 0; margin: 0; opacity: .8; }

  .provenance {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
    gap: 1px;
    background: var(--hair);
    border: 1px solid var(--hair);
  }
  .provenance div { background: var(--surface); padding: .85rem 1rem; }
  .provenance dt {
    font-family: var(--sans); font-size: .68rem; font-weight: 600;
    letter-spacing: .12em; text-transform: uppercase; color: var(--muted);
  }
  .provenance dd {
    margin: .3rem 0 0; font-family: var(--mono); font-size: .78rem;
    color: var(--ink); word-break: break-all;
  }

  /* ---------- verdict ---------- */
  .verdict {
    border: 1px solid var(--hair-strong);
    border-left: 4px solid var(--crit);
    background: var(--surface);
    padding: clamp(1.25rem, 3vw, 2rem);
    display: flex; flex-direction: column; gap: 1rem;
  }
  .verdict h2 { font-size: 1.5rem; font-weight: 700; }
  .verdict p { margin: 0; max-width: var(--measure); }
  .verdict .stamp {
    display: inline-block;
    font-family: var(--sans); font-weight: 700; font-size: .8rem;
    letter-spacing: .12em; text-transform: uppercase;
    color: var(--crit); background: var(--crit-soft);
    border: 1px solid currentColor; padding: .3rem .7rem;
    align-self: flex-start;
  }

  /* ---------- section ---------- */
  section { display: flex; flex-direction: column; gap: 1.5rem; }
  section > h2 {
    font-size: clamp(1.4rem, 3.4vw, 1.95rem); font-weight: 700;
    padding-bottom: .55rem; border-bottom: 2px solid var(--ink);
  }
  section p { margin: 0; }
  .lede { max-width: var(--measure); color: var(--ink-2); }

  /* ---------- register table ---------- */
  .scroller { overflow-x: auto; border: 1px solid var(--hair); background: var(--surface); }
  table { border-collapse: collapse; width: 100%; min-width: 46rem; font-family: var(--sans); }
  thead th {
    text-align: left; font-size: .7rem; font-weight: 700; letter-spacing: .11em;
    text-transform: uppercase; color: var(--muted);
    padding: .8rem 1rem; border-bottom: 1px solid var(--hair-strong); white-space: nowrap;
  }
  tbody td { padding: .8rem 1rem; border-bottom: 1px solid var(--hair); vertical-align: top; font-size: .93rem; }
  tbody tr:last-child td { border-bottom: 0; }
  td.id { font-family: var(--mono); font-weight: 600; white-space: nowrap; }
  td.num { font-variant-numeric: tabular-nums; white-space: nowrap; }

  .sev {
    display: inline-block; font-family: var(--sans); font-size: .68rem; font-weight: 700;
    letter-spacing: .09em; text-transform: uppercase; padding: .18rem .5rem;
    white-space: nowrap; border: 1px solid currentColor;
  }
  .sev-crit { color: var(--crit); background: var(--crit-soft); }
  .sev-high { color: var(--high); background: var(--high-soft); }
  .sev-med  { color: var(--med);  background: var(--med-soft); }
  .sev-ok   { color: var(--ok);   background: var(--ok-soft); }

  /* ---------- pipeline ---------- */
  .pipeline {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(11.5rem, 1fr));
    gap: 1px; background: var(--hair); border: 1px solid var(--hair);
  }
  .stage { background: var(--surface); padding: 1rem; display: flex; flex-direction: column; gap: .6rem; }
  .stage h3 { font-size: .82rem; font-weight: 700; letter-spacing: .09em; text-transform: uppercase; color: var(--accent); }
  .stage ol { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: .35rem; }
  .stage li {
    font-family: var(--mono); font-size: .74rem; line-height: 1.45;
    color: var(--ink-2); padding-left: .85rem; position: relative;
  }
  .stage li::before {
    content: "→"; position: absolute; left: 0; color: var(--hair-strong);
  }
  .stage li.term::before { content: "■"; font-size: .55rem; top: .28rem; color: var(--muted); }
  .stage .note {
    font-family: var(--sans); font-size: .74rem; color: var(--muted);
    border-top: 1px dashed var(--hair-strong); padding-top: .5rem; margin-top: auto;
  }
  .stage .breach {
    font-family: var(--sans); font-size: .72rem; font-weight: 600;
    color: var(--crit); border-top: 1px dashed var(--crit); padding-top: .5rem; margin-top: auto;
  }

  /* ---------- findings ---------- */
  .findings { display: flex; flex-direction: column; gap: 1.75rem; }
  .finding {
    border: 1px solid var(--hair-strong); background: var(--surface);
    display: grid; grid-template-columns: 4px 1fr;
  }
  .finding > .stripe { background: var(--hair-strong); }
  .finding.crit > .stripe { background: var(--crit); }
  .finding.high > .stripe { background: var(--high); }
  .finding.med  > .stripe { background: var(--med); }
  .finding-body { padding: clamp(1.15rem, 2.6vw, 1.85rem); display: flex; flex-direction: column; gap: 1.1rem; }
  .finding-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: .7rem; }
  .finding-head .fid { font-family: var(--mono); font-weight: 600; font-size: .85rem; color: var(--muted); }
  .finding-head h3 { font-size: 1.28rem; font-weight: 700; flex: 1 1 20rem; }
  .finding p { max-width: var(--measure); }

  .facets { display: grid; grid-template-columns: repeat(auto-fit, minmax(17rem, 1fr)); gap: 1.1rem; }
  .facet { display: flex; flex-direction: column; gap: .35rem; }
  .facet h4 {
    font-size: .69rem; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; color: var(--muted);
  }
  .facet p { font-size: .93rem; margin: 0; }

  code {
    font-family: var(--mono); font-size: .855em;
    background: var(--surface-2); padding: .08em .32em; border-radius: 2px;
    word-break: break-word;
  }
  .evidence {
    background: var(--surface-2); border-left: 2px solid var(--accent);
    padding: .85rem 1rem; overflow-x: auto;
  }
  .evidence pre { margin: 0; font-family: var(--mono); font-size: .78rem; line-height: 1.62; color: var(--ink-2); }
  .evidence .cap {
    font-family: var(--sans); font-size: .67rem; font-weight: 700; letter-spacing: .11em;
    text-transform: uppercase; color: var(--muted); display: block; margin-bottom: .5rem;
  }
  .out { color: var(--crit); font-weight: 600; }

  .fix { border-top: 1px solid var(--hair); padding-top: 1rem; display: flex; flex-direction: column; gap: .5rem; }
  .fix h4 {
    font-family: var(--sans); font-size: .69rem; font-weight: 700; letter-spacing: .12em;
    text-transform: uppercase; color: var(--accent);
  }
  .fix p { font-size: .93rem; }

  /* ---------- diagram ---------- */
  figure { margin: 0; display: flex; flex-direction: column; gap: .75rem; }
  .figbox { overflow-x: auto; border: 1px solid var(--hair); background: var(--surface); padding: 1.25rem; }
  figcaption { font-size: .87rem; color: var(--muted); max-width: var(--measure); }
  svg { display: block; min-width: 44rem; }
  .svg-label { font-family: "IBM Plex Sans Condensed", sans-serif; font-size: 12px; font-weight: 600; }
  .svg-small { font-family: "IBM Plex Mono", monospace; font-size: 10.5px; }

  /* ---------- gates / decisions ---------- */
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr)); gap: 1rem; }
  .card {
    border: 1px solid var(--hair); background: var(--surface);
    padding: 1.15rem; display: flex; flex-direction: column; gap: .55rem;
  }
  .card.good { border-left: 3px solid var(--ok); }
  .card.ask  { border-left: 3px solid var(--accent); }
  .card h3 { font-size: 1rem; font-weight: 700; }
  .card p { font-size: .91rem; margin: 0; }
  .card .gate { font-family: var(--mono); font-size: .74rem; color: var(--muted); }

  ul.plain { margin: 0; padding-left: 1.15rem; display: flex; flex-direction: column; gap: .55rem; max-width: var(--measure); }
  ul.plain li { padding-left: .2rem; }

  footer {
    border-top: 2px solid var(--ink); padding-top: 1.25rem;
    font-size: .87rem; color: var(--muted); max-width: var(--measure);
    display: flex; flex-direction: column; gap: .6rem;
  }

  a { color: var(--accent); }
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  @media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
</style>

<div class="wrap">

<div class="header masthead">

Independent commercial-flow audit · Terrax Media / Cardvert

# Where the money can leave the ledger

A read-only trace of the commercial lifecycle — custom quotation,
funding, production, cancellation, refund — against the binding product
decisions. Seven defects confirmed, six of them by execution at the
audited commit.

------------------------------------------------------------------------

Repository  
oluwasolaonigbinde/mobility

Branch  
feat/pkg-04-build-first

Commit  
637841d95493bcc24334356da42097fa53a5d16f

Verified via  
git ls-remote origin → branch tip matches

</div>

<div class="verdict">

<span class="stamp">Not fit to accept live advertiser cash</span>

## Verdict

The commercial spine is unusually well built. Conservation, immutability
and idempotency are enforced twice — once in database check constraints,
again in the service layer. Tenant scoping holds on every path I tested.
The three external gates (payment provider, statutory issuer facts,
budget policy) genuinely fail closed rather than defaulting to a
permissive stub. This is not a codebase that confuses external facts
with completed code.

But the two controls that decide whether money stays with Terrax or goes
back to the advertiser are both defeatable. **The 24-hour refund cutoff
mandated by decision D18(d) can be pushed forward after production has
already started**, letting a fully-produced campaign be refunded in
full. **The budget pause silently fails to re-apply after a resume**,
leaving an over-threshold campaign running while the API reports it as
paused. Both are reproducible; neither is covered by the existing suite,
which passes green.

CF-1 and CF-2 are release blockers. CF-3 and CF-4 cause real
advertiser-facing loss and should land with them. The rest are ordinary
hardening.

</div>

<div class="section">

## Defect register

Severity is the reachable financial or statutory consequence, not the
size of the diff. “Reproduced” means I executed it against this exact
tree and observed the outcome.

<div class="scroller">

| ID | Severity | Defect | Consequence | Status |
|----|----|----|----|----|
| CF-1 | <span class="sev sev-crit">Critical</span> | Refund cutoff re-anchors after production starts | Full campaign gross refundable mid-production | Reproduced |
| CF-2 | <span class="sev sev-crit">Critical</span> | Budget pause never re-applies after a resume | Uncapped spend; status projection reports a pause that did not happen | Reproduced |
| CF-3 | <span class="sev sev-high">High</span> | Superseded quotation revision is still acceptable | Campaign binds at a withdrawn price, then freezes immutable | Reproduced |
| CF-4 | <span class="sev sev-high">High</span> | Valid cancellation refund becomes unrecordable | Advertiser owed cash the system refuses to settle | Reproduced |
| CF-5 | <span class="sev sev-med">Medium</span> | Expedited-waiver wording is caller-supplied and unverifiable | The audited waiver proves a hash, not a disclosure | Reproduced |
| CF-6 | <span class="sev sev-med">Medium</span> | Invoice corrections take no campaign lock | Over-funding past a concurrently-lowered obligation | Lock-order reading |
| CF-7 | <span class="sev sev-med">Low</span> | Invoice numbers use the UTC calendar year | New-year invoices mis-filed into the prior statutory sequence | Reproduced |

</div>

</div>

<div class="section">

## The commercial state machine

Five append-only chains, serialized per campaign by a Postgres advisory
lock (`acquire_campaign_terms_lock`). Every chain is write-once at the
row level; correction happens by appending, never by update. The two red
notes mark where the machine loses its guard.

<div class="pipeline">

<div class="stage">

### 1 · Quotation

1.  quote_request <span style="opacity:.7">(1/campaign)</span>
2.  revision 1..N
3.  commercial_terms

CF-3 — any revision is acceptable, not only the latest.

</div>

<div class="stage">

### 2 · Invoice

1.  draft
2.  issued + number
3.  credit / debit notes

CF-6 — corrections move the obligation outside the campaign lock.

</div>

<div class="stage">

### 3 · Cash

1.  observed
2.  reconciled
3.  confirmed
4.  allocated → terms
5.  reversed

Bank transfer and gateway converge here on one receipt ladder.

</div>

<div class="stage">

### 4 · Authority

1.  financial authorization
2.  liability reservation
3.  production_start

Basis: window elapsed · waiver · approved credit. Subsidy never
authorizes production.

</div>

<div class="stage">

### 5 · Exit

1.  cancellation cutoff
2.  refund settlement
3.  credit settlement

CF-1, CF-4 — the refund window is recomputed, not frozen.

</div>

</div>

Money conservation is genuinely well guarded inside each chain: an
allocation cannot exceed its receipt (`RECEIPT_OVERALLOCATION`) or the
effective obligation (`OBLIGATION_OVERFUNDING`); a refund cannot exceed
its allocation or its receipt; credit notes cannot drive the obligation
below zero. The failures are all at the *boundaries between* chains,
where a fact from one chain is meant to gate the next.

</div>

<div class="section">

## Confirmed defects

<div class="findings">

<div class="stripe">

</div>

<div class="finding-body">

<div class="finding-head">

<span class="fid">CF-1</span>

### The refund cutoff re-anchors after production has started

<span class="sev sev-crit">Critical</span>

</div>

`_refund_window` closes the window early for exactly one production
basis — `advertiser_expedited_waiver`. For a `standard_window_elapsed`
start the window is always `funded_at + 24h`, and `funded_at` is not
stored: it is recomputed on every call by walking allocations until they
cover the *current* `effective_invoice_obligation`. A debit note raises
that obligation, so the anchor jumps to whichever later allocation now
tips the balance — and a cutoff that had already expired springs back
open.

<div class="facets">

<div class="facet">

#### What the decision requires

D18(d) / Q24: a refund is permitted “only within 24 hours of the first
confirmed cash allocation that authorizes production; after that cutoff
there is no advertiser refund.” The cutoff is meant to be a one-way
door.

</div>

<div class="facet">

#### Why nothing catches it

`record_invoice_correction` has no production-start or cancellation
guard, so debit notes are accepted at any time on an issued invoice. The
existing re-anchoring test only exercises a *credit* note, which moves
the anchor harmlessly backwards.

</div>

</div>

<div class="evidence">

<span class="cap">app/services/billing.py:2789–2795 — only the waiver
basis closes the window</span>

    if (
        production is not None
        and production.authority_basis == ProductionAuthorityBasis.ADVERTISER_EXPEDITED_WAIVER
        and _stored_aware_utc(production.started_at) < standard_end
    ):
        return funded_at, _stored_aware_utc(production.started_at), production
    return funded_at, standard_end, production   ← standard basis ignores production entirely

</div>

<div class="evidence">

<span class="cap">Reproduced — prepaid campaign, ₦100.00 funded,
standard-basis start</span>

    production basis                     : standard_window_elapsed
    production started                   : 2026-09-02 08:55:56Z
    re-anchored funded_at (after debit)  : 2026-09-02 23:55:56Z
    window ends_at                       : 2026-09-03 23:55:56Z
    window ends AFTER production start   : True
    >>> REFUND ACCEPTED amount: 100.00
    >>> production_start_id on settlement: 496b791d-…   ← it knows, and allows it anyway

</div>

The settlement row even records the `production_start_id`. The evidence
that production began is present at the moment the refund is authorized;
it is simply not consulted for this basis.

<div class="fix">

#### Smallest remediation

In `_refund_window`, let *any* production start close the window, not
only a waived one — replace the basis test with
`end = min(standard_end, started_at)` whenever a `ProductionStart`
exists. One condition removed, no schema change, and the waiver
behaviour D20(b) requires falls out of the same expression.

Worth doing next, separately: persist the anchor once (on
`commercial_terms` or `production_starts`) so the cutoff stops being a
function of a mutable obligation at all. That also fixes CF-4 and
removes CF-6’s money consequence.

</div>

</div>

<div class="stripe">

</div>

<div class="finding-body">

<div class="finding-head">

<span class="fid">CF-2</span>

### The budget pause never re-applies after a resume

<span class="sev sev-crit">Critical</span>

</div>

`evaluate_campaign_budget_policy` returns an existing evaluation
whenever the `evaluation_key` matches — and it returns *before* it
computes `pause_will_apply`. The key hashes campaign, budgets, policy
identity, spend, thresholds and state. It carries no notion of which
pause/resume epoch it belongs to. So the second time a campaign reaches
a spend figure it has reached before, the decision is treated as a
replayed retry and the pause is never applied.

<div class="facets">

<div class="facet">

#### How the spend value recurs

Routinely. A receipt is reversed for a wrong reference and re-recorded
for the same amount — spend returns to precisely its previous value. And
once production starts, spend *is* the effective obligation: a constant,
so every later evaluation produces the same key by construction.

</div>

<div class="facet">

#### Second-order effect

Budget notices are only created for newly inserted evaluations, so the
replayed pause is also silent — no alert, no notification. And the stale
row is returned to the caller with `pause_applied=True` while the
campaign is `active`.

</div>

</div>

<div class="evidence">

<span class="cap">app/services/billing.py:3254–3266 — the early return
precedes the pause</span>

    existing = await session.scalar(
        select(BudgetPolicyEvaluation).where(
            BudgetPolicyEvaluation.campaign_id == campaign.id,
            BudgetPolicyEvaluation.evaluation_key == evaluation_key,
        )
    )
    if existing is not None:
        return existing            ← returns here…

    pause_will_apply = decision.should_pause and campaign.status in {   …so this never runs
        CampaignStatus.SCHEDULED.value, CampaignStatus.ACTIVE.value,
    }

</div>

<div class="evidence">

<span class="cap">Reproduced — budget ₦1,000, pause ratio 1.00, resume
ratio 0.70</span>

    E1  spend 1000  state pause_threshold   pause_applied True   campaign → paused
        reverse the ₦400 receipt
    E2  spend  600  state within_budget      resume_allowed True  admin resume → active
        re-record the same ₦400 under the corrected reference
    E3  spend 1000  E3 id == E1 id (replayed row): True
        state pause_threshold   pause_applied True
    >>> campaign status: active   ← at the pause threshold, still running

</div>

`docs/progress.md:421` records the intent as “Exact retries reuse
evaluations, transitions and outbox keys.” That is the right rule; the
key simply cannot tell an exact retry apart from a genuinely new
threshold breach that happens to carry the same numbers.

<div class="fix">

#### Smallest remediation

Add an epoch discriminator to `_budget_evaluation_key` — the id (or
count) of the campaign’s latest `BudgetCampaignTransition`. A true retry
within the same epoch still collapses onto one row; a breach after a
resume gets a fresh key, a fresh evaluation, a real pause and a real
notification. One extra field in the hash source.

</div>

</div>

<div class="stripe">

</div>

<div class="finding-body">

<div class="finding-head">

<span class="fid">CF-3</span>

### A superseded quotation revision can still be accepted

<span class="sev sev-high">High</span>

</div>

`accept_quotation_revision` validates the organization, the acceptance
provenance and the currency — but never checks that the revision is the
latest for its quote request. Supersession exists only in the browser:
the advertiser panel binds its Accept button to
`commercial.revisions.at(-1)`. Any client holding an older revision id
can accept a price operations has already withdrawn.

<div class="evidence">

<span class="cap">Reproduced — ops corrects a pricing error, advertiser
accepts the old figure</span>

    revision 1  gross 1,075,000.00     (published, then superseded)
    revision 2  gross 1,612,500.00     (the corrected price)

    >>> ACCEPTED revision_number: 1
    >>> binding gross: 1,075,000.00
    >>> shortfall: 537,500.00

</div>

The damage compounds because those terms are then
correct-by-construction immutable — one `commercial_terms` row per
campaign, enforced by `uq_commercial_terms_campaign`. The only recovery
is a debit note, which is exactly the instrument that triggers CF-1.

<div class="fix">

#### Smallest remediation

After taking the campaign terms lock in `accept_quotation_revision`,
reject when a higher `revision_number` exists for the same
`quote_request_id`. Four lines, and it makes the server agree with what
the UI already implies.

</div>

</div>

<div class="stripe">

</div>

<div class="finding-body">

<div class="finding-head">

<span class="fid">CF-4</span>

### A cancellation made inside the window becomes unrefundable

<span class="sev sev-high">High</span>

</div>

Cancellation does the right thing: it freezes an immutable settlement
snapshot at the cutoff — disposition `cash_refund_due`, the refundable
amount, and the eligibility end. But `record_refund_settlement` ignores
all of it and re-derives the window at the moment ops records the bank
settlement. If the actual transfer is booked after the window closes,
the system refuses to record a refund it has already committed to in
writing.

<div class="evidence">

<span class="cap">Reproduced — advertiser cancels 2h in, ops books the
transfer at 26h</span>

    cancellation disposition : cash_refund_due
    promised refundable      : 100.00
    refund_eligibility_ends  : 2026-09-02 07:59:31Z    (cutoff was 2026-09-01 09:59Z)

    >>> settlement REFUSED with: REFUND_WINDOW_CLOSED
    >>> advertiser is owed 100.00 but the system cannot record it

</div>

The result is a self-contradicting audit trail — an immutable
cancellation record asserting a debt, and no permitted path to discharge
it. Ops will settle out-of-band, which is exactly what this ledger
exists to prevent.

<div class="fix">

#### Smallest remediation

In `record_refund_settlement`, when a `CampaignCancellation` exists for
the campaign, evaluate eligibility against `cancellation.cutoff_at`
rather than the current clock. The cancellation already stores
everything needed.

</div>

</div>

<div class="stripe">

</div>

<div class="finding-body">

<div class="finding-head">

<span class="fid">CF-5</span>

### The expedited waiver records a hash, not a disclosure

<span class="sev sev-med">Medium</span>

</div>

`record_expedited_production_waiver` hashes whatever `accepted_wording`
the caller sends, and `wording_version` is unconstrained free text. The
canonical sentence lives only in a hidden input in the advertiser panel,
which the server action forwards verbatim. There is no server-side
registry to validate the hash against.

D20(b) makes this waiver the sole basis on which production may begin
early and refund eligibility may end. The record is genuinely immutable
and genuinely bound to the campaign’s own advertiser — but in a dispute
it proves only that *some* string was submitted, not that the advertiser
was shown the approved disclosure.

<div class="fix">

#### Smallest remediation

Keep a server-side map of `wording_version → canonical text`, and reject
a submission whose hash does not match the registered wording for that
version. The waiver then proves what it is supposed to prove, and the
version string becomes meaningful.

</div>

</div>

<div class="stripe">

</div>

<div class="finding-body">

<div class="finding-head">

<span class="fid">CF-6</span>

### Invoice corrections run outside the campaign lock

<span class="sev sev-med">Medium · lock-order reading</span>

</div>

Every other path that touches the obligation takes
`acquire_campaign_terms_lock(campaign_id)`, then the campaign row, then
the terms row — allocation, reversal, refund, authorization, production
start, budget evaluation and cancellation all agree on that order, and
reversal even sorts its campaign ids to stay deadlock-free.
`record_invoice_correction` takes only the invoice row lock.

So a credit note can commit concurrently with an allocation that is
checking `OBLIGATION_OVERFUNDING` against the pre-correction figure.
Under READ COMMITTED the allocation can be admitted at an amount the
corrected obligation would have refused. The same gap is the mechanism
behind CF-1: corrections move the obligation with no coordination
against the funding and production timeline.

<div class="fix">

#### Smallest remediation

Take the campaign terms lock in `record_invoice_correction` before
reading the invoice, matching the order every sibling path already uses.
One added call.

</div>

</div>

<div class="stripe">

</div>

<div class="finding-body">

<div class="finding-head">

<span class="fid">CF-7</span>

### Invoice numbers use the UTC calendar year

<span class="sev sev-med">Low · statutory</span>

</div>

`issue_invoice` derives the sequence year from the UTC database clock,
while the codebase uses `LAGOS_TZ` for every other business boundary —
budget days, payable day counts, campaign windows. For one hour after
each New Year in Lagos, invoices are filed into the previous year’s
statutory sequence.

<div class="evidence">

<span class="cap">Reproduced — issued 1 Jan 2027, 00:30 Lagos</span>

    issued_at (UTC)   : 2026-12-31 23:30:00+00:00
    issued_at (Lagos) : 2027-01-01 00:30:00+01:00
    >>> invoice_number: TEST-CV-2026-000001
    >>> Lagos calendar year at issuance: 2027

</div>

<div class="fix">

#### Smallest remediation

Derive the year as `now.astimezone(LAGOS_TZ).year`. Changing invoice
numbering is normally expensive — here it is free, because real issuance
is still blocked behind `EXT-Q28-COMPANY` and no statutory number has
been minted yet. Fix it before that gate opens, not after.

</div>

</div>

</div>

</div>

<div class="section">

## Reachable financial impact

Every path below is reachable through the shipped HTTP API by an
ordinary active administrator or, where noted, the advertiser. None
requires database access or a privileged escape.

<div class="scroller">

| Path | Actor | Exposure per campaign | Detectability |
|----|----|----|----|
| CF-1 — refund a produced campaign in full | Admin | Full gross paid | Audit trail looks correct; the settlement records a valid open window |
| CF-1 + reserved liability — drivers still payable | Admin | Reserved driver liability, uncovered | Reservations survive; only funding is withdrawn |
| CF-2 — spend past the pause threshold | None (passive) | Unbounded above the configured cap | Actively misreported: the API returns `pause_applied=True` |
| CF-3 — bind a withdrawn price | Advertiser | Difference between revisions | Visible only by comparing the accepted revision number to the latest |
| CF-4 — cancellation debt cannot be settled | Ops delay | The promised refundable amount | Loud — the call fails; the risk is off-ledger settlement |

</div>

</div>

<div class="section">

## Gates that are correctly external-only

I looked specifically for external facts being passed off as working
code. I did not find that pattern. These three seams fail closed, and
`docs/progress.md` describes their status accurately rather than
optimistically.

<div class="cards">

<div class="card good">

EXT-PAYMENT-PROVIDER

### Payment gateway

`get_payment_gateway_adapter()` returns `DisabledPaymentGatewayAdapter`
unconditionally — there is no settings-driven path to a live provider.
Every method raises, and the webhook route surfaces
`503 PAYMENT_PROVIDER_NOT_CONFIGURED`. No real payment can be processed.
Correct.

</div>

<div class="card good">

EXT-Q28-COMPANY

### Statutory invoice issuance

Issuance requires either a synthetic issuer in a test environment —
whose numbers are prefixed `TEST-` — or a verified issuer whose external
reference matches the configured value. Otherwise
`VERIFIED_ISSUER_FACTS_REQUIRED`. No real invoice can be minted on
invented facts. Correct.

</div>

<div class="card good">

EXT-BUDGET-POLICY

### Budget thresholds

The default adapter returns `blocked_external_policy`; a non-blocked
decision while the gate is missing is rejected with 503, and synthetic
policy values require explicit test authority. Thresholds are never
invented. Correct — the flaw in CF-2 is in the persistence key, not the
gate.

</div>

<div class="card good">

RM12 · Q2

### Subsidy is not production authority

Both `record_production_start` and
`assert_campaign_production_authorized` refuse subsidy authority
explicitly. Prepaid authority re-derives usable liability from
confirmed, unreversed allocations on every check, so a reversal
genuinely withdraws it. Correct.

</div>

</div>

</div>

<div class="section">

## Genuine owner decisions

Three questions I cannot settle from the code or the decisions log. Each
is a deliberate design position that may be right — but none is
currently written down, and all three carry money.

<div class="cards">

<div class="card ask">

Question 1

### Should corporate credit be capped and dual-controlled?

Nothing ties an approved credit limit to the accepted obligation, and
the recording admin may also be the approving admin. I verified
authorizing ₦10,000,000 of driver liability against ₦100,000 of accepted
terms — a 100× exposure — with a single administrator on both sides.
Prepaid authority has no equivalent gap because its amount is derived
from confirmed cash.

</div>

<div class="card ask">

Question 2

### Which figure does ops key into a quotation line item?

Q28 states customer-facing prices are VAT-inclusive. The engine computes
`tax = net × rate` and `gross = net + tax` — so line items are *net* and
VAT is added on top. Net, VAT and gross are all preserved immutably and
conserved by a database constraint, so this is a data-entry convention
rather than a money bug. But if operations keys the headline
VAT-inclusive price into line items, every campaign is over-billed by
the VAT rate, silently. Confirm the convention, and consider having the
form accept gross and derive net.

</div>

<div class="card ask">

Question 3

### Where exactly does the 24 hours start?

D18(d) says “the first confirmed cash allocation that authorizes
production.” The code anchors at the allocation that tips cumulative
funding over the obligation — the same thing for a single payment, the
*last* instalment for a staged one. That reading is defensible and
probably intended, but it is the anchor for the whole refund cutoff and
deserves to be ratified explicitly rather than inferred.

</div>

</div>

</div>

<div class="section">

## Method and evidence limits

- **Commit verified through GitHub.**
  `git ls-remote origin refs/heads/feat/pkg-04-build-first` returns
  `637841d…`, and `origin` is `github.com/oluwasolaonigbinde/mobility`.
  Master was never substituted.
- **All source read at the exact revision** via `git show <rev>:<path>`,
  never from the working tree, which is on master with unrelated
  modifications. Reproductions ran against a `git archive` export of
  that tree in a scratch directory. The repository was not modified —
  the working tree is byte-identical to how I found it.
- **No payment provider was invoked.** The only adapter reachable from
  the API is the disabled one; the reproductions used the repository’s
  own deterministic fixtures.
- **Baseline is green.** The nine commercial suites pass at this commit
  — 39 passed, 9 skipped. All seven findings are gaps in coverage, not
  known failures.
- **Races are verified by reading, not execution.** The repository’s
  four PostgreSQL concurrency tests skip without a configured test
  database (`test_billing_concurrency.py:27`,
  `test_billing_corrections.py:497`,
  `test_budget_enforcement_w2_01e.py:255`,
  `test_payment_gateway.py:256`). A PostGIS container is running
  locally, but pointing the suite at it would write a schema into your
  live development database, so I did not. CF-6 and the lock-order
  analysis behind item 10 are therefore code reading, and should be
  confirmed by running those four tests in CI.
- **Duplicate handling was checked and holds.** Webhook ingestion
  dedupes on `(provider, provider_event_id)` with an exact-match
  comparison, processing short-circuits on a completed attempt, receipts
  dedupe on the composed external transaction id, and allocations are
  unique per `(receipt, terms)` and per provider event. The gateway
  suite passes.
- **Cross-tenant leakage: none found.** Allocation and refund both
  reject a receipt whose organization differs from the terms; billing
  history is organization-scoped for advertisers and requires an
  explicit organization for admins; the advertiser commercial endpoint
  checks campaign ownership before projecting. A colliding external
  transaction id across tenants fails closed with a conflict rather than
  returning another tenant’s receipt.

</div>

Independent commercial-flow audit of Cardvert at commit
`637841d95493bcc24334356da42097fa53a5d16f` on `feat/pkg-04-build-first`.
Read-only; no provider calls; no repository changes.

Recommended order: CF-1 and CF-2 block release. CF-3 and CF-4 should
ship with them. CF-7 is free to fix today and expensive after
`EXT-Q28-COMPANY` opens.

</div>

