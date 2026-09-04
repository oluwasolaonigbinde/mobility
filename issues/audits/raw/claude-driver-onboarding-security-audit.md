---
source_surface: Claude desktop
workspace: mobility
conversation_id: eaa468ec-bac4-4fc2-ab69-2fc8aa94415b
displayed_title: Driver onboarding security audit
displayed_model: Claude Opus 5
created_at: 2026-09-01T07:52:23.451Z
retrieved_at: 2026-09-01
collection_state: COLLECTED
completeness: complete published artifact
redactions: none
artifact_url: https://claude.ai/code/artifact/2e3c2c98-240b-47ba-89ed-92920881d425
source_format: Claude HTML artifact converted to GitHub-flavored Markdown
---

# Driver onboarding security audit

> This is the complete published audit artifact preserved as source evidence.
> It is not yet an accepted finding or remediation decision.

Driver Eligibility Audit

<style>
:root{
  --ground:#F6F8FB;
  --surface:#FFFFFF;
  --surface-2:#EFF2F7;
  --ink:#141922;
  --ink-2:#3D4653;
  --muted:#5A6472;
  --faint:#8B94A2;
  --hair:#DCE1E9;
  --hair-strong:#C3CBD7;
  --accent:#2A4B8D;
  --accent-soft:#E8EDF7;
  --pass:#0F7A6B;
  --pass-soft:#E2F1EE;
  --warn:#9A5B04;
  --warn-soft:#FBEFDC;
  --low:#57627A;
  --low-soft:#EAEDF3;
  --shadow:0 1px 2px rgba(20,25,34,.05);

  --f-display:"Newsreader",ui-serif,Georgia,"Times New Roman",serif;
  --f-body:"IBM Plex Sans",ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  --f-mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#0E1219;
    --surface:#151A23;
    --surface-2:#1B212C;
    --ink:#E3E8F0;
    --ink-2:#C0C8D4;
    --muted:#98A1B0;
    --faint:#6F798A;
    --hair:#262D38;
    --hair-strong:#333C4A;
    --accent:#89A7E4;
    --accent-soft:#1B2537;
    --pass:#45C3AD;
    --pass-soft:#122A2A;
    --warn:#E2A855;
    --warn-soft:#2E2415;
    --low:#98A1B0;
    --low-soft:#1D232E;
    --shadow:0 1px 2px rgba(0,0,0,.35);
  }
}
:root[data-theme="dark"]{
  --ground:#0E1219;
  --surface:#151A23;
  --surface-2:#1B212C;
  --ink:#E3E8F0;
  --ink-2:#C0C8D4;
  --muted:#98A1B0;
  --faint:#6F798A;
  --hair:#262D38;
  --hair-strong:#333C4A;
  --accent:#89A7E4;
  --accent-soft:#1B2537;
  --pass:#45C3AD;
  --pass-soft:#122A2A;
  --warn:#E2A855;
  --warn-soft:#2E2415;
  --low:#98A1B0;
  --low-soft:#1D232E;
  --shadow:0 1px 2px rgba(0,0,0,.35);
}

*{box-sizing:border-box}
body{
  background:var(--ground);
  color:var(--ink);
  font-family:var(--f-body);
  font-size:16px;
  line-height:1.6;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1040px;margin:0 auto;padding:0 24px 96px}
.prose{max-width:72ch}

/* ---------- masthead ---------- */
.masthead{padding:56px 0 0}
.eyebrow{
  font-family:var(--f-mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--muted);display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;
}
.eyebrow .dot{width:4px;height:4px;border-radius:50%;background:var(--hair-strong);display:inline-block}
h1{
  font-family:var(--f-display);font-weight:500;font-size:clamp(38px,6vw,60px);
  line-height:1.04;letter-spacing:-.02em;margin:20px 0 0;text-wrap:balance;
}
h1 .sub{display:block;font-style:italic;font-size:.52em;color:var(--muted);font-weight:400;margin-top:10px;letter-spacing:-.005em}

/* ---------- commit banner ---------- */
.commit{
  margin-top:32px;border:1px solid var(--hair);background:var(--surface);
  border-radius:4px;box-shadow:var(--shadow);overflow:hidden;
}
.commit-head{
  display:flex;align-items:center;gap:10px;padding:11px 16px;
  border-bottom:1px solid var(--hair);background:var(--pass-soft);
}
.commit-head .label{
  font-family:var(--f-mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--pass);font-weight:500;
}
.commit-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:1px;background:var(--hair)}
.commit-cell{background:var(--surface);padding:13px 16px}
.commit-cell dt{
  font-family:var(--f-mono);font-size:10.5px;letter-spacing:.11em;text-transform:uppercase;
  color:var(--faint);margin:0 0 5px;
}
.commit-cell dd{margin:0;font-family:var(--f-mono);font-size:12.5px;color:var(--ink-2);word-break:break-all;line-height:1.45}

/* ---------- verdict ---------- */
.verdict{
  margin-top:40px;border:1px solid var(--hair-strong);border-radius:4px;
  background:var(--surface);box-shadow:var(--shadow);
}
.verdict-top{padding:26px 28px 22px;border-bottom:1px solid var(--hair)}
.verdict-tag{
  display:inline-flex;align-items:center;gap:8px;font-family:var(--f-mono);font-size:11px;
  letter-spacing:.13em;text-transform:uppercase;color:var(--pass);font-weight:500;margin-bottom:14px;
}
.verdict-tag::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--pass)}
.verdict-top p{
  font-family:var(--f-display);font-size:clamp(20px,2.6vw,26px);line-height:1.42;
  margin:0;color:var(--ink);letter-spacing:-.008em;max-width:60ch;text-wrap:balance;
}
.verdict-body{padding:20px 28px 24px;display:grid;gap:13px}
.verdict-body p{margin:0;color:var(--ink-2);max-width:74ch}

/* ---------- sections ---------- */
section{margin-top:64px}
h2{
  font-family:var(--f-display);font-weight:500;font-size:29px;letter-spacing:-.014em;
  margin:0 0 6px;padding-bottom:12px;border-bottom:1px solid var(--hair-strong);
  display:flex;align-items:baseline;gap:13px;text-wrap:balance;
}
h2 .num{
  font-family:var(--f-mono);font-size:12px;letter-spacing:.1em;color:var(--accent);
  font-weight:500;flex:none;position:relative;top:-2px;
}
.lede{color:var(--muted);margin:14px 0 0;max-width:74ch}
h3{
  font-family:var(--f-body);font-weight:600;font-size:15px;letter-spacing:.005em;
  margin:34px 0 10px;color:var(--ink);
}
p{margin:14px 0}
a{color:var(--accent);text-decoration:underline;text-underline-offset:2px;text-decoration-thickness:1px}
a:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:2px}
code{font-family:var(--f-mono);font-size:.865em;background:var(--surface-2);padding:1px 5px;border-radius:3px;color:var(--ink-2)}
strong{font-weight:600;color:var(--ink)}

/* ---------- diagram ---------- */
.figure{margin:30px 0 0;border:1px solid var(--hair);border-radius:4px;background:var(--surface);box-shadow:var(--shadow)}
.figure-scroll{overflow-x:auto;padding:26px 24px 18px}
.figure svg{display:block;min-width:880px;width:100%;height:auto}
figcaption{
  border-top:1px solid var(--hair);padding:11px 20px;font-size:13px;color:var(--muted);
  font-family:var(--f-mono);letter-spacing:.01em;
}
.d-label{font-family:"IBM Plex Mono",monospace;font-size:10px;letter-spacing:.09em;text-transform:uppercase;fill:var(--faint)}
.d-node{font-family:"IBM Plex Sans",sans-serif;font-size:12.5px;font-weight:500;fill:var(--ink)}
.d-sub{font-family:"IBM Plex Mono",monospace;font-size:10px;fill:var(--muted)}
.d-gate{font-family:"IBM Plex Mono",monospace;font-size:10.5px;font-weight:500;fill:var(--warn)}
.d-pass{font-family:"IBM Plex Mono",monospace;font-size:11px;font-weight:500;fill:var(--pass)}

/* ---------- findings ---------- */
.findings{display:grid;gap:18px;margin-top:28px}
.finding{
  border:1px solid var(--hair);border-radius:4px;background:var(--surface);
  box-shadow:var(--shadow);overflow:hidden;
}
.f-head{
  display:flex;flex-wrap:wrap;align-items:center;gap:12px;
  padding:14px 18px;border-bottom:1px solid var(--hair);background:var(--surface-2);
}
.f-id{
  font-family:var(--f-mono);font-size:12px;font-weight:500;letter-spacing:.09em;
  color:var(--accent);flex:none;
}
.f-title{font-weight:600;font-size:15px;flex:1 1 260px;line-height:1.35;color:var(--ink)}
.chip{
  font-family:var(--f-mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;
  padding:3px 9px;border-radius:3px;font-weight:500;flex:none;white-space:nowrap;
  border:1px solid transparent;
}
.chip.med{background:var(--warn-soft);color:var(--warn);border-color:var(--warn)}
.chip.lowmed{background:var(--warn-soft);color:var(--warn);border-color:transparent}
.chip.low{background:var(--low-soft);color:var(--low);border-color:transparent}
.f-body{padding:18px}
.f-body p{margin:0 0 13px;color:var(--ink-2);max-width:78ch}
.f-body p:last-child{margin-bottom:0}
.f-fix{
  margin-top:15px;padding:12px 15px;background:var(--accent-soft);border-radius:3px;
  font-size:14px;color:var(--ink-2);
}
.f-fix b{
  font-family:var(--f-mono);font-size:10px;letter-spacing:.11em;text-transform:uppercase;
  color:var(--accent);display:block;margin-bottom:5px;font-weight:500;
}

/* evidence lines */
.ev{list-style:none;padding:0;margin:0 0 14px;display:grid;gap:5px}
.ev li{
  font-family:var(--f-mono);font-size:12.5px;line-height:1.55;color:var(--muted);
  padding-left:16px;position:relative;word-break:break-word;
}
.ev li::before{content:"›";position:absolute;left:0;color:var(--hair-strong);font-weight:500}
.ev b{color:var(--ink-2);font-weight:500}

/* ---------- tables ---------- */
.tablewrap{overflow-x:auto;margin-top:26px;border:1px solid var(--hair);border-radius:4px;background:var(--surface);box-shadow:var(--shadow)}
table{border-collapse:collapse;width:100%;min-width:600px;font-variant-numeric:tabular-nums}
th{
  text-align:left;font-family:var(--f-mono);font-size:10.5px;letter-spacing:.11em;
  text-transform:uppercase;color:var(--faint);font-weight:500;
  padding:12px 16px;border-bottom:1px solid var(--hair-strong);background:var(--surface-2);
  white-space:nowrap;
}
td{padding:13px 16px;border-bottom:1px solid var(--hair);vertical-align:top;font-size:14px;color:var(--ink-2)}
tr:last-child td{border-bottom:none}
td.mono{font-family:var(--f-mono);font-size:12px;color:var(--muted);word-break:break-word}
td .ok{color:var(--pass);font-weight:500;font-family:var(--f-mono);font-size:11px;letter-spacing:.07em;text-transform:uppercase;white-space:nowrap}

/* ---------- lists ---------- */
ol.steps{counter-reset:s;list-style:none;padding:0;margin:26px 0 0;display:grid;gap:0}
ol.steps li{
  counter-increment:s;position:relative;padding:16px 0 16px 46px;border-top:1px solid var(--hair);
  color:var(--ink-2);max-width:80ch;
}
ol.steps li:last-child{border-bottom:1px solid var(--hair)}
ol.steps li::before{
  content:counter(s,decimal-leading-zero);position:absolute;left:0;top:16px;
  font-family:var(--f-mono);font-size:11px;color:var(--accent);font-weight:500;letter-spacing:.06em;
}
ol.steps li b{display:block;color:var(--ink);font-weight:600;margin-bottom:3px;font-size:15px}

ul.plain{list-style:none;padding:0;margin:20px 0 0;display:grid;gap:14px}
ul.plain li{padding-left:19px;position:relative;color:var(--ink-2);max-width:78ch}
ul.plain li::before{
  content:"";position:absolute;left:0;top:10px;width:7px;height:1px;background:var(--hair-strong);
}
ul.plain li b{color:var(--ink);font-weight:600}

.gates{display:grid;gap:1px;background:var(--hair);border:1px solid var(--hair);border-radius:4px;margin-top:26px;overflow:hidden}
.gate{background:var(--surface);padding:16px 18px}
.gate .g-top{display:flex;align-items:center;gap:10px;margin-bottom:6px;flex-wrap:wrap}
.gate .g-name{font-weight:600;font-size:14.5px;color:var(--ink)}
.gate .g-tag{
  font-family:var(--f-mono);font-size:10px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--warn);background:var(--warn-soft);padding:2px 7px;border-radius:3px;
}
.gate p{margin:0;font-size:14px;color:var(--muted);max-width:76ch}

.note{
  margin-top:28px;border-left:2px solid var(--hair-strong);padding:2px 0 2px 18px;
  color:var(--muted);font-size:14.5px;max-width:74ch;
}
.note b{color:var(--ink-2);font-weight:600}

footer{
  margin-top:72px;padding-top:22px;border-top:1px solid var(--hair);
  font-family:var(--f-mono);font-size:11.5px;color:var(--faint);
  display:flex;flex-wrap:wrap;gap:8px 20px;letter-spacing:.02em;
}

@media (max-width:640px){
  .wrap{padding:0 18px 72px}
  .masthead{padding-top:38px}
  .verdict-top,.verdict-body{padding-left:19px;padding-right:19px}
  h2{font-size:24px}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>

<div class="wrap">

<div class="header masthead">

<div class="eyebrow">

Independent security audit<span class="dot"></span> Cardvert driver
onboarding<span class="dot"></span> Read-only

</div>

# Can an applicant reach work-eligible off-path?<span class="sub">Auditing the driver onboarding eligibility pipeline at a pinned revision</span>

</div>

<div class="commit">

<div class="commit-head">

<span class="label">Revision verified against GitHub</span>

</div>

Commit  
637841d95493bcc24334356da42097fa53a5d16f

Branch head  
feat/pkg-04-build-first

Subject  
docs(progress): close provider-neutral build controller

Authored  
2026-08-28T18:16:08Z

</div>

<div class="section" style="margin-top:40px">

<div class="verdict">

<div class="verdict-top">

<div class="verdict-tag">

Verdict — no confirmed bypass

</div>

At this revision, an untrusted applicant **cannot** reach work-eligible
state except through the intended reviewed sequence. Every work gate
recomputes eligibility live from evidence rather than trusting a cached
status.

</div>

<div class="verdict-body">

The design holds because eligibility is *derived*, not stored as
authority. Approval requires an admin decision row, an admin-only payout
verification bound to the exact bank-account version, and audited reads
of the exact documents; the applicant's own submissions are explicitly
non-authoritative. Evidence rows are append-only and immutable at the
database level, and every producer serializes on a Postgres advisory
lock keyed to the driver profile.

Eight findings follow. None is an eligibility bypass. Three are worth
fixing soon: an email-enumeration timing oracle that defeats an
otherwise careful constant-response design, an application status that
is a compile-time constant (so the review queue never clears and
applicant write capability never terminates), and the absence of any
duplicate-person, duplicate-phone, or duplicate-bank-account detection.

</div>

</div>

</div>

<div class="section">

## <span class="num">§1</span> Scope and evidence base

Read-only inspection of the tree at the pinned commit. No provider
calls, no test suite execution, no writes.

The commit was confirmed through the GitHub API as the exact head of
`feat/pkg-04-build-first`, and the local object matched byte-for-byte.
All reads were performed against that revision via `git show` /
`git grep` pinned to the SHA — never against `master` or the working
tree.

### Surfaces read

- **Application and access** — `app/services/driver_applications.py`,
  `app/models/driver_application.py`, `app/api/v1/auth.py`,
  `app/core/rate_limit.py`, `app/services/account_recovery.py`
- **KYC, payee, vehicle** — `driver_onboarding.py`,
  `vehicle_onboarding.py`, `kyc.py`, `payees.py`, `vehicles.py`,
  `drivers.py`, plus their models and schemas
- **Evidence custody** — `stored_files.py`, `file_kyc_lifecycle.py`,
  `app/adapters/crypto/envelope.py`
- **Work gates** — `campaign_assignments.py`, `trips.py`,
  `app/jobs/vehicle_approvals.py`
- **Review surface and PWA** — `app/api/v1/admin.py`,
  `app/api/v1/kyc.py`, the `frontend/src/app/apply/*` and
  `frontend/src/app/driver/(portal)/*` trees
- **Schema authority** — migrations `0050`, `0055`, `0068`, `0069`,
  `0070`

### Evidence gaps

- **No runtime confirmation.** Findings are established by code and
  schema reading only. The timing oracle in [F1](#f1) is argued from the
  code path and Argon2 parameters, not from measured latency against a
  running instance.
- **Concurrency guarantees are Postgres-only.**
  `acquire_work_eligibility_lock` returns immediately on non-Postgres
  dialects (`vehicle_onboarding.py:74-75`), so any SQLite-backed test
  run does not exercise the serialization this audit credits.
- **Deployment values unverified.** Key custody, scanner behavior, and
  rate-limit backing store are configuration-dependent; see
  [§5](#external).

</div>

<div class="section">

## <span class="num">§2</span> Eligibility state machine

Two independent tracks — person/payee and vehicle — each ending in an
admin decision. Eligibility is the conjunction, recomputed at every work
gate.

<figure class="figure">
<div class="figure-scroll">
<img
src="data:image/svg+xml;base64,PHN2ZyB2aWV3Ym94PSIwIDAgOTgwIDQzMCIgcm9sZT0iaW1nIiBhcmlhLWxhYmVsPSJEcml2ZXIgb25ib2FyZGluZyBlbGlnaWJpbGl0eSBwaXBlbGluZTogcmVnaXN0cmF0aW9uIHByb2R1Y2VzIGEgcGVuZGluZyBhcHBsaWNhdGlvbiBhbmQgYW4gZW1haWxlZCBhY2Nlc3MgdG9rZW47IHRoZSBwZXJzb24gYW5kIHBheWVlIHRyYWNrIHJlcXVpcmVzIGFuIGFkbWluIGRlY2lzaW9uIHBsdXMgYW4gYWRtaW4tb25seSBwYXlvdXQgdmVyaWZpY2F0aW9uOyB0aGUgdmVoaWNsZSB0cmFjayByZXF1aXJlcyBhbiBhZG1pbiBkZWNpc2lvbiB3aXRoIGEgZnV0dXJlIHZhbGlkaXR5OyBib3RoIG11c3QgaG9sZCBmb3IgdGhlIGRlcml2ZWQgZWxpZ2liaWxpdHkgY29uanVuY3Rpb24sIHdoaWNoIGlzIHJlLWV2YWx1YXRlZCBhdCBmb3VyIGxpdmUgd29yayBnYXRlcy4iPgogICAgICAgIDxkZWZzPgogICAgICAgICAgPG1hcmtlciBpZD0iYXIiIG1hcmtlcndpZHRoPSI3IiBtYXJrZXJoZWlnaHQ9IjciIHJlZng9IjYiIHJlZnk9IjMuNSIgb3JpZW50PSJhdXRvIj4KICAgICAgICAgICAgPHBhdGggZD0iTTAsMCBMNywzLjUgTDAsNyBaIiBmaWxsPSJ2YXIoLS1oYWlyLXN0cm9uZykiIC8+CiAgICAgICAgICA8L21hcmtlcj4KICAgICAgICA8L2RlZnM+CgogICAgICAgIDwhLS0gZW50cnkgLS0+CiAgICAgICAgPHRleHQgY2xhc3M9ImQtbGFiZWwiIHg9IjAiIHk9IjE0Ij5VbnRydXN0ZWQgZW50cnk8L3RleHQ+CiAgICAgICAgPHJlY3QgeD0iMCIgeT0iMjYiIHdpZHRoPSIxNjgiIGhlaWdodD0iNjYiIHJ4PSIzIiBmaWxsPSJ2YXIoLS1zdXJmYWNlLTIpIiBzdHJva2U9InZhcigtLWhhaXItc3Ryb25nKSIgLz4KICAgICAgICA8dGV4dCBjbGFzcz0iZC1ub2RlIiB4PSIxNCIgeT0iNDkiPlBPU1QgL3JlZ2lzdGVyLWRyaXZlcjwvdGV4dD4KICAgICAgICA8dGV4dCBjbGFzcz0iZC1zdWIiIHg9IjE0IiB5PSI2NyI+dXNlcjogaW52aXRlZDwvdGV4dD4KICAgICAgICA8dGV4dCBjbGFzcz0iZC1zdWIiIHg9IjE0IiB5PSI4MSI+YXBwbGljYXRpb246IHBlbmRpbmc8L3RleHQ+CgogICAgICAgIDxsaW5lIHgxPSIxNjgiIHkxPSI1OSIgeDI9IjIxMiIgeTI9IjU5IiBzdHJva2U9InZhcigtLWhhaXItc3Ryb25nKSIgbWFya2VyLWVuZD0idXJsKCNhcikiPjwvbGluZT4KICAgICAgICA8cmVjdCB4PSIyMTIiIHk9IjI2IiB3aWR0aD0iMTU2IiBoZWlnaHQ9IjY2IiByeD0iMyIgZmlsbD0idmFyKC0tc3VyZmFjZSkiIHN0cm9rZT0idmFyKC0taGFpci1zdHJvbmcpIiAvPgogICAgICAgIDx0ZXh0IGNsYXNzPSJkLW5vZGUiIHg9IjIyNiIgeT0iNDkiPkFjY2VzcyB0b2tlbjwvdGV4dD4KICAgICAgICA8dGV4dCBjbGFzcz0iZC1zdWIiIHg9IjIyNiIgeT0iNjciPmVtYWlsZWQgb25seSDCtyAzMCBtaW48L3RleHQ+CiAgICAgICAgPHRleHQgY2xhc3M9ImQtc3ViIiB4PSIyMjYiIHk9IjgxIj5ITUFDLCBkaWdlc3Qtc3RvcmVkPC90ZXh0PgoKICAgICAgICA8IS0tIHNwbGl0IC0tPgogICAgICAgIDxwYXRoIGQ9Ik0zNjgsNTkgTDM5Miw1OSBMMzkyLDE1MCBMNDIwLDE1MCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJ2YXIoLS1oYWlyLXN0cm9uZykiIG1hcmtlci1lbmQ9InVybCgjYXIpIiAvPgogICAgICAgIDxwYXRoIGQ9Ik0zOTIsNTkgTDM5MiwzMDAgTDQyMCwzMDAiIGZpbGw9Im5vbmUiIHN0cm9rZT0idmFyKC0taGFpci1zdHJvbmcpIiBtYXJrZXItZW5kPSJ1cmwoI2FyKSIgLz4KCiAgICAgICAgPCEtLSBwZXJzb24vcGF5ZWUgdHJhY2sgLS0+CiAgICAgICAgPHRleHQgY2xhc3M9ImQtbGFiZWwiIHg9IjQyMCIgeT0iMTA2Ij5UcmFjayBBIOKAlCBwZXJzb24gJmFtcDsgcGF5ZWU8L3RleHQ+CiAgICAgICAgPHJlY3QgeD0iNDIwIiB5PSIxMTgiIHdpZHRoPSIxNzYiIGhlaWdodD0iNjQiIHJ4PSIzIiBmaWxsPSJ2YXIoLS1zdXJmYWNlKSIgc3Ryb2tlPSJ2YXIoLS1oYWlyLXN0cm9uZykiIC8+CiAgICAgICAgPHRleHQgY2xhc3M9ImQtbm9kZSIgeD0iNDM0IiB5PSIxNDEiPkFwcGxpY2FudCBzdWJtaXRzPC90ZXh0PgogICAgICAgIDx0ZXh0IGNsYXNzPSJkLXN1YiIgeD0iNDM0IiB5PSIxNTkiPk5JTiwgYmFuaywgMyBkb2N1bWVudHM8L3RleHQ+CiAgICAgICAgPHRleHQgY2xhc3M9ImQtc3ViIiB4PSI0MzQiIHk9IjE3MyI+cGF5b3V0IGF1dGhvcml0eTogbm9uZTwvdGV4dD4KCiAgICAgICAgPGxpbmUgeDE9IjU5NiIgeTE9IjE1MCIgeDI9IjYzMiIgeTI9IjE1MCIgc3Ryb2tlPSJ2YXIoLS1oYWlyLXN0cm9uZykiIG1hcmtlci1lbmQ9InVybCgjYXIpIj48L2xpbmU+CiAgICAgICAgPHJlY3QgeD0iNjMyIiB5PSIxMTIiIHdpZHRoPSIyMDAiIGhlaWdodD0iNzYiIHJ4PSIzIiBmaWxsPSJ2YXIoLS13YXJuLXNvZnQpIiBzdHJva2U9InZhcigtLXdhcm4pIiAvPgogICAgICAgIDx0ZXh0IGNsYXNzPSJkLWdhdGUiIHg9IjY0NiIgeT0iMTMyIj5BRE1JTiBHQVRFPC90ZXh0PgogICAgICAgIDx0ZXh0IGNsYXNzPSJkLXN1YiIgeD0iNjQ2IiB5PSIxNTAiPnBheW91dCB2ZXJpZmljYXRpb24gKGFkbWluLW9ubHkpPC90ZXh0PgogICAgICAgIDx0ZXh0IGNsYXNzPSJkLXN1YiIgeD0iNjQ2IiB5PSIxNjQiPmF1ZGl0ZWQgTklOICsgYWNjb3VudCArIGRvYyByZWFkczwvdGV4dD4KICAgICAgICA8dGV4dCBjbGFzcz0iZC1zdWIiIHg9IjY0NiIgeT0iMTc4Ij4zIGNvbmZpcm1hdGlvbnMgKyByZWFzb24gY29kZTwvdGV4dD4KCiAgICAgICAgPCEtLSB2ZWhpY2xlIHRyYWNrIC0tPgogICAgICAgIDx0ZXh0IGNsYXNzPSJkLWxhYmVsIiB4PSI0MjAiIHk9IjI1NiI+VHJhY2sgQiDigJQgdmVoaWNsZTwvdGV4dD4KICAgICAgICA8cmVjdCB4PSI0MjAiIHk9IjI2OCIgd2lkdGg9IjE3NiIgaGVpZ2h0PSI2NCIgcng9IjMiIGZpbGw9InZhcigtLXN1cmZhY2UpIiBzdHJva2U9InZhcigtLWhhaXItc3Ryb25nKSIgLz4KICAgICAgICA8dGV4dCBjbGFzcz0iZC1ub2RlIiB4PSI0MzQiIHk9IjI5MSI+QXBwbGljYW50IHN1Ym1pdHM8L3RleHQ+CiAgICAgICAgPHRleHQgY2xhc3M9ImQtc3ViIiB4PSI0MzQiIHk9IjMwOSI+cGxhdGUsIHR5cGUsIDMgZG9jdW1lbnRzPC90ZXh0PgogICAgICAgIDx0ZXh0IGNsYXNzPSJkLXN1YiIgeD0iNDM0IiB5PSIzMjMiPmdhdGVkIG9uIFRyYWNrIEEgYXBwcm92YWw8L3RleHQ+CgogICAgICAgIDxsaW5lIHgxPSI1OTYiIHkxPSIzMDAiIHgyPSI2MzIiIHkyPSIzMDAiIHN0cm9rZT0idmFyKC0taGFpci1zdHJvbmcpIiBtYXJrZXItZW5kPSJ1cmwoI2FyKSI+PC9saW5lPgogICAgICAgIDxyZWN0IHg9IjYzMiIgeT0iMjYyIiB3aWR0aD0iMjAwIiBoZWlnaHQ9Ijc2IiByeD0iMyIgZmlsbD0idmFyKC0td2Fybi1zb2Z0KSIgc3Ryb2tlPSJ2YXIoLS13YXJuKSIgLz4KICAgICAgICA8dGV4dCBjbGFzcz0iZC1nYXRlIiB4PSI2NDYiIHk9IjI4MiI+QURNSU4gR0FURTwvdGV4dD4KICAgICAgICA8dGV4dCBjbGFzcz0iZC1zdWIiIHg9IjY0NiIgeT0iMzAwIj5jdXJyZW50IHJldmlzaW9uICsgc25hcHNob3QgbWF0Y2g8L3RleHQ+CiAgICAgICAgPHRleHQgY2xhc3M9ImQtc3ViIiB4PSI2NDYiIHk9IjMxNCI+YXVkaXRlZCByZWFkcyBvZiBldmVyeSBkb2N1bWVudDwvdGV4dD4KICAgICAgICA8dGV4dCBjbGFzcz0iZC1zdWIiIHg9IjY0NiIgeT0iMzI4Ij41IGNvbmZpcm1hdGlvbnMgKyB2YWxpZF91bnRpbDwvdGV4dD4KCiAgICAgICAgPCEtLSBqb2luIC0tPgogICAgICAgIDxwYXRoIGQ9Ik04MzIsMTUwIEw4NzYsMTUwIEw4NzYsMzUyIEw3OTYsMzUyIEw3OTYsMzYyIiBmaWxsPSJub25lIiBzdHJva2U9InZhcigtLWhhaXItc3Ryb25nKSIgbWFya2VyLWVuZD0idXJsKCNhcikiIC8+CiAgICAgICAgPHBhdGggZD0iTTgzMiwzMDAgTDg3NiwzMDAiIGZpbGw9Im5vbmUiIHN0cm9rZT0idmFyKC0taGFpci1zdHJvbmcpIiAvPgoKICAgICAgICA8cmVjdCB4PSI2MTIiIHk9IjM2OCIgd2lkdGg9IjM2OCIgaGVpZ2h0PSI1MiIgcng9IjMiIGZpbGw9InZhcigtLXBhc3Mtc29mdCkiIHN0cm9rZT0idmFyKC0tcGFzcykiIC8+CiAgICAgICAgPHRleHQgY2xhc3M9ImQtcGFzcyIgeD0iNjI2IiB5PSIzOTAiPkRFUklWRUQg4oCUIHJlY29tcHV0ZWQsIG5ldmVyIHRydXN0ZWQgZnJvbSBjYWNoZTwvdGV4dD4KICAgICAgICA8dGV4dCBjbGFzcz0iZC1zdWIiIHg9IjYyNiIgeT0iNDA4Ij5lbGlnaWJsZSA9IHBlcnNvbl9hcHByb3ZlZCBBTkQgdmVoaWNsZV9hcHByb3ZlZCBBTkQgdmFsaWRfdW50aWwgJmd0OyBub3c8L3RleHQ+CgogICAgICAgIDwhLS0gbGl2ZSBnYXRlcyAtLT4KICAgICAgICA8dGV4dCBjbGFzcz0iZC1sYWJlbCIgeD0iMCIgeT0iMTQwIj5MaXZlIHJlLWV2YWx1YXRpb248L3RleHQ+CiAgICAgICAgPHJlY3QgeD0iMCIgeT0iMTUyIiB3aWR0aD0iMzM2IiBoZWlnaHQ9IjE4MCIgcng9IjMiIGZpbGw9InZhcigtLXN1cmZhY2UpIiBzdHJva2U9InZhcigtLWhhaXItc3Ryb25nKSIgLz4KICAgICAgICA8dGV4dCBjbGFzcz0iZC1zdWIiIHg9IjE2IiB5PSIxNzYiPmVuc3VyZV9jdXJyZW50X2RyaXZlcl92ZWhpY2xlX2VsaWdpYmlsaXR5KCk8L3RleHQ+CiAgICAgICAgPGxpbmUgeDE9IjE2IiB5MT0iMTg4IiB4Mj0iMzIwIiB5Mj0iMTg4IiBzdHJva2U9InZhcigtLWhhaXIpIj48L2xpbmU+CiAgICAgICAgPHRleHQgY2xhc3M9ImQtbm9kZSIgeD0iMTYiIHk9IjIxMSI+T2ZmZXI8L3RleHQ+PHRleHQgY2xhc3M9ImQtc3ViIiB4PSIxNTAiIHk9IjIxMSI+Y2FtcGFpZ25fYXNzaWdubWVudHMucHk6NTAyPC90ZXh0PgogICAgICAgIDx0ZXh0IGNsYXNzPSJkLW5vZGUiIHg9IjE2IiB5PSIyNDAiPkFjY2VwdDwvdGV4dD48dGV4dCBjbGFzcz0iZC1zdWIiIHg9IjE1MCIgeT0iMjQwIj5jYW1wYWlnbl9hc3NpZ25tZW50cy5weToxNjE1PC90ZXh0PgogICAgICAgIDx0ZXh0IGNsYXNzPSJkLW5vZGUiIHg9IjE2IiB5PSIyNjkiPkFjdGl2YXRlPC90ZXh0Pjx0ZXh0IGNsYXNzPSJkLXN1YiIgeD0iMTUwIiB5PSIyNjkiPmNhbXBhaWduX2Fzc2lnbm1lbnRzLnB5OjE4MjM8L3RleHQ+CiAgICAgICAgPHRleHQgY2xhc3M9ImQtbm9kZSIgeD0iMTYiIHk9IjI5OCI+VHJpcCBzdGFydDwvdGV4dD48dGV4dCBjbGFzcz0iZC1zdWIiIHg9IjE1MCIgeT0iMjk4Ij50cmlwcy5weToyODQ8L3RleHQ+CiAgICAgICAgPHRleHQgY2xhc3M9ImQtc3ViIiB4PSIxNiIgeT0iMzIyIj5lYWNoIHVuZGVyIGFkdmlzb3J5IGxvY2sgKyByb3cgbG9ja3M8L3RleHQ+CiAgICAgICAgPHBhdGggZD0iTTYxMiwzOTQgTDMzNiwzOTQgTDMzNiwzMzIiIGZpbGw9Im5vbmUiIHN0cm9rZT0idmFyKC0taGFpci1zdHJvbmcpIiBtYXJrZXItZW5kPSJ1cmwoI2FyKSIgLz4KICAgICAgPC9zdmc+" />
</div>
<figcaption>Applicant-controlled steps are neutral; admin gates are
amber; the derived conjunction is teal.</figcaption>
</figure>

### States

<div class="tablewrap">

| Object | States | Who writes it |
|----|----|----|
| User.status | invited → active | Registration sets `invited`. **No code path activates a driver** — only an admin `PATCH /admin/users/{id}`. |
| DriverApplication.status | pending *(only)* | Pinned by CHECK constraint. See [F2](#f2). |
| DriverKycSubmission.status | pending_review · approved · rejected · expired | Applicant creates versions; only `review_application_person_payee` decides. |
| VehicleEvidenceSubmission.status | pending_review · approved · rejected · expired | Applicant creates versions; admin decides; sweep expires. |
| Vehicle.status | pending · active · inactive · suspended | Projected by reconcile; suspended/inactive are never overwritten. |
| DriverProfile.onboarding_status | pending · active · suspended · rejected | Projected by reconcile; suspended/rejected are never overwritten. |

</div>

### The conjunction

`reconcile_driver_work_eligibility` (`vehicle_onboarding.py:188-237`)
computes `eligible = person_approved AND has_active_vehicle`, where:

- **person_approved** — latest KYC submission is `approved` *and* an
  approved `DriverKycReviewDecision` exists *and* a
  `PayeeBankAccountPayoutVerification` exists for that submission's
  exact `bank_account_version_id` (`vehicle_onboarding.py:141-167`).
- **vehicle_approved** — the latest submission for the vehicle, whose
  frozen snapshot still matches the live vehicle row, is `approved`,
  with a latest decision that is `approved`, a `valid_until` in the
  future, and `vehicle_type == car` (`vehicle_onboarding.py:170-185`).

This is written into `DriverProfile.onboarding_status` and
`Vehicle.status` as a cache — but the four work gates call
`ensure_current_driver_vehicle_eligibility`, which recomputes both
predicates from evidence under lock. A stale cache therefore cannot
grant work; it can only mislead a listing (see [F7](#f7)).

</div>

<div class="section">

## <span class="num">§3</span> Findings

No confirmed eligibility bypass. Eight issues: misleading state, missing
controls, and admin-trust ceilings.

<div class="findings">

<a id="cld-02-f1"></a>

<div class="f-head">

<span class="f-id">F1</span><span class="f-title">Registration leaks
registered emails through an Argon2 timing
oracle</span><span class="chip med">Medium</span>

</div>

<div class="f-body">

`submit_driver_application` goes to considerable lengths to make every
outcome look identical: it mints a fresh random reference even when it
will not be persisted, returns the same message for new and existing
emails, and treats a lost insert race exactly like a pre-existing user.
The response body genuinely does not distinguish them.

The *duration* does. The existing-user branch returns at line 202 after
two indexed selects. The new-user branch then calls
`_unreachable_password_hash()` at line 211, which runs Argon2id at
`time_cost=2, memory_cost=19456 KiB` — tens of milliseconds, against a
couple of milliseconds for the early return. There is no compensating
dummy hash and no response-timing normalization anywhere in the request
path.

- **app/services/driver_applications.py:201-207** — existing-user early
  return, no KDF
- **app/services/driver_applications.py:211** —
  `password_hash=_unreachable_password_hash()` on the new-user path only
- **app/services/driver_applications.py:43-44** — the hash helper
- **app/core/security.py:11** —
  `PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)`

Rate limiting bounds but does not remove this: 10 per IP/hour and 100
globally per hour (`config.py:63-68`) still allow steady probing, and a
third timing class exists — an existing *invited* applicant triggers
token issuance and a commit, which is slower than a non-applicant but
faster than a new registration.

<div class="f-fix">

**Smallest fix**Compute `_unreachable_password_hash()` before the
`existing_user` branch and discard it on the early-return path, so both
outcomes pay the same KDF cost.

</div>

</div>

<a id="cld-02-f2"></a>

<div class="f-head">

<span class="f-id">F2</span><span class="f-title">Application status is
a constant, so the review queue never clears and applicant write
capability never ends</span><span class="chip med">Medium</span>

</div>

<div class="f-body">

`DriverApplicationStatus` has exactly one member, and a CHECK constraint
pins the column to `'pending'`. Review outcomes are recorded on the KYC
and vehicle submissions instead, so the application row never reaches a
terminal state. Three things read that constant as if it carried
meaning:

- **app/models/driver_application.py:20-21, 34-37** — single-member
  enum, `status = 'pending'` CHECK
- **alembic/versions/0050_driver_applications.py:43** — same constraint
  at the schema level
- **app/services/driver_applications.py:294** — admin queue filters on
  `status == pending`, which is always true
- **app/services/driver_applications.py:143, 155-169** — token liveness
  and re-issue eligibility also test that constant
- **frontend/src/app/admin/driver-applications/page.tsx:35, 86** —
  renders “N pending applications” and a permanent amber `pending` chip

Consequences: the admin queue returns every application ever submitted
and grows without bound, with a header count that is always wrong —
reviewers are not blind, since each row also carries the real
person/payee and vehicle stage chips, but the application-level state is
noise. More materially, an already-approved or already-rejected
applicant keeps an indefinitely renewable 30-minute mutation capability
for as long as their user row stays `invited`, and no code path ever
moves a driver off `invited`. Someone holding that mailbox can re-submit
vehicle evidence and knock an approved driver back to pending at will.

<div class="f-fix">

**Smallest fix**Give `DriverApplication` a real terminal status driven
by the review decisions, then filter both the admin queue and the
access-token liveness check on it rather than on a constant.

</div>

</div>

<a id="cld-02-f3"></a>

<div class="f-head">

<span class="f-id">F3</span><span class="f-title">No duplicate-person,
duplicate-phone, or duplicate-bank-account
detection</span><span class="chip med">Medium</span>

</div>

<div class="f-body">

Of the four identity axes an onboarding system would normally
deduplicate, only one is enforced. The vehicle plate is properly
protected by a database unique constraint. The other three are not
deduplicated at all:

- **app/models/kyc.py:107** — NIN persists only as a randomized envelope
  ciphertext plus `nin_last_four`; no deterministic fingerprint exists
  anywhere, so no index or constraint is possible
- **app/models/user.py:45** — `phone` has no unique constraint;
  `DriverApplication.phone` has none either
- **app/models/payee.py:93** — `uq_payee_bank_accounts_payee_id` is one
  account *per payee*; nothing prevents the same account number across
  unlimited payees, and the details are encrypted with no blind index
- **app/models/vehicle.py:50-54** —
  `uq_vehicles_plate_country_normalized`, the one axis that is enforced

So one person can hold many approved driver identities under different
emails and phones, each with its own vehicle, all paying into a single
bank account — and the platform produces no signal. Detection rests
entirely on a reviewer recognizing a face or a name across separate
queue entries. Given that the same reviewer can also self-service the
payout verification ([F5](#f5)), this is the most plausible route to
fraudulent scale on this codebase.

Related: `ensure_unique_plate` (`vehicles.py:33-52`) is a
select-then-insert with no `IntegrityError` handling at the applicant
call site, so a genuine plate race surfaces as a 500 rather than the
intended 409. Data integrity is preserved by the constraint; only the
error contract is wrong.

<div class="f-fix">

**Smallest fix**Store a keyed HMAC fingerprint (server-side pepper,
distinct per field) of the NIN and the account number alongside each
ciphertext, and index it — unique where policy allows, otherwise indexed
and surfaced to the reviewer as a collision warning.

</div>

</div>

<a id="cld-02-f4"></a>

<div class="f-head">

<span class="f-id">F4</span><span class="f-title">Vehicle approval
validity has no upper
bound</span><span class="chip lowmed">Low–Medium</span>

</div>

<div class="f-body">

Vehicle approvals are deliberately time-boxed — `_vehicle_approved`
requires `valid_until > now` at every read, and a sweep job materializes
expiry. But nothing caps how far out `valid_until` may be set. The
validator only requires it to be in the future, and the schema declares
a bare `datetime`.

- **app/services/vehicle_onboarding.py:531-532** —
  `payload.valid_until is None or payload.valid_until <= now` is the
  entire check
- **app/schemas/driver_onboarding.py:155** —
  `valid_until: datetime | None = None`, no bound

A single admin action — mistyped year or otherwise — grants a
century-long approval that the expiry sweep will never reach, silently
converting a recurring re-verification control into a permanent one.

<div class="f-fix">

**Smallest fix**Reject `valid_until` beyond a configured maximum horizon
in `_validate_decision`.

</div>

</div>

<a id="cld-02-f5"></a>

<div class="f-head">

<span class="f-id">F5</span><span class="f-title">One admin account is
sufficient to manufacture a work-eligible
driver</span><span class="chip lowmed">Low–Medium</span>

</div>

<div class="f-body">

The three approval facts are strong individually — an admin-only payout
verification, an admin person/payee decision, an admin vehicle decision
— but there is a single `ADMIN` role and no separation of duties between
them. The actor is recorded on each artifact and never compared.

- **app/services/payees.py:361-370** —
  `verify_bank_account_version_for_payout`, gated only by
  `_require_active_admin`
- **app/services/driver_onboarding.py:479** — `decided_by_user_id`
  recorded, never compared to the verifier
- **app/services/payees.py:354** — `verified_by_user_id` recorded on the
  verification

This is inside the admin trust boundary and does not weaken the
applicant-facing verdict. It matters because it sets the blast radius of
one compromised or dishonest admin account to a fully eligible, payable
driver identity — and, combined with [F3](#f3), an unbounded number of
them.

<div class="f-fix">

**Smallest fix**Require `verified_by_user_id != decided_by_user_id` at
person/payee approval; a four-eyes rule on the money-bearing fact is the
cheapest meaningful constraint.

</div>

</div>

<a id="cld-02-f6"></a>

<div class="f-head">

<span class="f-id">F6</span><span class="f-title">Approval evidence
checks load an admin's entire audit history into
memory</span><span class="chip low">Low</span>

</div>

<div class="f-body">

Both approval paths verify that the reviewer actually opened the exact
evidence, which is a genuinely good control — the reads are scoped to
the submission id and, for the bank account, to the exact version. The
implementation loads every matching audit event for that actor across
all time, with no time bound and no limit, then filters the metadata in
Python.

- **app/services/driver_onboarding.py:321-336** — unbounded `AuditEvent`
  select for three actions, filtered at lines 337-358
- **app/services/vehicle_onboarding.py:554-563** — same pattern for
  `stored_file.read`

Correct today; it degrades linearly with each admin's lifetime review
volume, and it is on the critical path of every approval.

<div class="f-fix">

**Smallest fix**Push the metadata predicates into the SQL and bound the
window by the submission's `created_at`.

</div>

</div>

<a id="cld-02-f7"></a>

<div class="f-head">

<span class="f-id">F7</span><span class="f-title">Offer candidate lists
can surface drivers whose approval has already
lapsed</span><span class="chip low">Low</span>

</div>

<div class="f-body">

Candidate selection filters on the cached projections, which can lag an
elapsed `valid_until` until the sweep job runs.

- **app/services/campaign_assignments.py:668-671** — filters on
  `DriverProfile.onboarding_status` and `Vehicle.status` only
- **app/services/campaign_assignments.py:502** — the actual offer write
  is hard-gated by the live check

Not a bypass: an operator who acts on a stale row gets a clean 409
rather than an invalid offer. It is a misleading list, and the failure
lands on the operator rather than the data.

<div class="f-fix">

**Smallest fix**Add the `valid_until > now` predicate to the candidate
query so the list matches what the gate will allow.

</div>

</div>

<a id="cld-02-f8"></a>

<div class="f-head">

<span class="f-id">F8</span><span class="f-title">The global
registration cap is a shared bucket that fails
closed</span><span class="chip low">Low</span>

</div>

<div class="f-body">

Registration is limited per IP, per email, and globally. The global
bucket is 100 attempts per hour across all clients, and exhaustion
produces a hard rejection.

- **app/core/config.py:67-68** —
  `driver_registration_rate_limit_global_max_attempts = 100` per 3600s
- **app/api/v1/auth.py:159-166** — rate-limit storage unavailability
  also fails closed with 503

Failing closed is the right default for this endpoint, but it means a
distributed attacker can consume the global allowance cheaply and block
all legitimate driver signup for the rest of the window. Availability
only; no integrity impact.

<div class="f-fix">

**Smallest fix**Keep the global cap as a circuit breaker but alert on
it, so exhaustion is visible as an incident rather than a silent funnel
outage.

</div>

</div>

</div>

</div>

<div class="section">

## <span class="num">§4</span> Verified fail-closed checkpoints

Each of these was traced to code at the pinned revision and holds
against an untrusted applicant.

<div class="tablewrap">

| Checkpoint | Behavior | Evidence |  |
|----|----|----|----|
| Access token confidentiality | HMAC-derived, digest-stored, 30-min TTL, compared with `compare_digest`; never returned in an HTTP response — delivery is by notification only | driver_applications.py:124-152 · auth.py:360-371 | <span class="ok">Pass</span> |
| Applicant bank capture is non-authoritative | Applicant path passes `payout_authoritative=False`; the payout verification that approval depends on is admin-only | payees.py:194-230 (229) · payees.py:370 | <span class="ok">Pass</span> |
| Person/payee approval preconditions | All three confirmations plus a terminal reason; documents re-validated as owned, correct-purpose and CLEAN; bank binding rechecked; audited exact reads of NIN, account version and every document | driver_onboarding.py:277-295, 298-368 · kyc.py:344-371 | <span class="ok">Pass</span> |
| Vehicle approval preconditions | Car type and snapshot must match the live row; only the current revision is reviewable; audited reads of every document; future validity required | vehicle_onboarding.py:660-666, 696-716, 527-538 | <span class="ok">Pass</span> |
| Live gates at every work boundary | Offer, accept, activate and trip start each recompute both predicates under advisory lock and row locks — a stale cache cannot grant work | campaign_assignments.py:502, 1615, 1823 · trips.py:284 | <span class="ok">Pass</span> |
| Admin cannot hand-activate an applicant | Setting `onboarding_status = active` is rejected whenever a public application exists for the profile | drivers.py:172-181 | <span class="ok">Pass</span> |
| Evidence immutability at the database | Review decisions append-only; vehicle snapshots and evidence documents immutable; payout verifications append-only — all enforced by triggers, not application code | 0068:79-83 · 0069:67-76 · 0070:132-171 | <span class="ok">Pass</span> |
| Cross-tenant isolation | Files scoped by `subject_user_id`, purpose and CLEAN status; payees by `tenant_id`; vehicles by `driver_profile_id`; bank versions resolved through payee to profile | kyc.py:124-135, 158-167 · payees.py:212, 466 · vehicle_onboarding.py:399-406 | <span class="ok">Pass</span> |
| Idempotent retries are exact-match | KYC retry compares NIN, bank version and documents; vehicle retry compares the full snapshot and documents; decision retries compare a request fingerprint — a replayed request id cannot smuggle new evidence | kyc.py:263-272 · vehicle_onboarding.py:288-303, 352-360 · driver_onboarding.py:418 | <span class="ok">Pass</span> |
| Evidence change invalidates approval | Re-submission demotes an active vehicle to pending; a changed vehicle row breaks snapshot match; NIN key rotation resets an approved submission to pending review | vehicle_onboarding.py:432-433, 127-138 · kyc.py:605-612 | <span class="ok">Pass</span> |
| Document custody | Confirm promotes the object to a managed key outside the applicant's presigned scope, verifies declared metadata, then scans; CLEAN is terminal and re-scan is refused | stored_files.py:616-676, 752-770 | <span class="ok">Pass</span> |
| Applicants cannot reach the driver portal | Invited users cannot log in, and password reset explicitly excludes the driver role; the PWA apply routes are thin proxies with no client-side authority | account_recovery.py:129-133, 217 · frontend/src/app/api/apply/onboarding/\*/route.ts | <span class="ok">Pass</span> |
| Retention respects live approvals | Evidence purge touches only `rejected` and `expired` submissions | file_kyc_lifecycle.py:27-28, 74, 90 | <span class="ok">Pass</span> |
| Concurrent reviews and edits serialize | Every eligibility producer takes a Postgres advisory lock keyed to profile and vehicle before row locks; one decision per KYC submission, one verification per bank version, unique sequence per vehicle decision | vehicle_onboarding.py:65-83 · 0068:67 · 0069:42-45 · 0070:120-124 | <span class="ok">Pass</span> |
| Registration is off by default | `driver_registration_enabled` defaults to false; all eight applicant endpoints 404 when disabled | config.py:62 · auth.py:142-148 | <span class="ok">Pass</span> |

</div>

</div>

<div id="external" class="section">

## <span class="num">§5</span> External-only gates

Facts the code structurally cannot decide. Each is correctly modelled as
an assertion — the assurance lives outside this repository.

<div class="gates">

<div class="gate">

<div class="g-top">

<span class="g-name">Bank account
ownership</span><span class="g-tag">Human / provider</span>

</div>

`verify_bank_account_version_for_payout` records a hash of an
admin-supplied verification reference. There is no provider name-match
call in this codebase; the truth of "this account belongs to this
person" is entirely external.

</div>

<div class="gate">

<div class="g-top">

<span class="g-name">Legal
agreement</span><span class="g-tag">Human</span>

</div>

`signed_agreement` is one of three uploaded KYC files
(`models/kyc.py:43`). There is no agreement version, no document hash
binding, and no acceptance record — the gate is the reviewer's
`documents_readable_confirmed` checkbox. Which agreement was signed is
not recoverable from the data model.

</div>

<div class="gate">

<div class="g-top">

<span class="g-name">Owner–driver
relationship</span><span class="g-tag">Human</span>

</div>

`owner_match_confirmed` is an admin assertion. The only structural link
is `Vehicle.driver_profile_id`; nothing binds the registration
document's named owner to the applicant.

</div>

<div class="gate">

<div class="g-top">

<span class="g-name">Identity
authenticity</span><span class="g-tag">Registry</span>

</div>

The NIN is validated as exactly 11 ASCII digits (`kyc.py:216`) and
nothing more. No registry lookup exists.

</div>

<div class="gate">

<div class="g-top">

<span class="g-name">Key
custody</span><span class="g-tag">Deployment</span>

</div>

Envelope encryption is real — versioned keys, AAD bound to tenant,
record and field, and a rewrap path that resets approval. But the KEK is
an in-process keyring loaded from `PAYOUT_CRYPTO_KEYRING_B64`
(`auth.py:87-91`, `envelope.py:288-297`), not an HSM or KMS. Secret
handling is a deployment property.

</div>

<div class="gate">

<div class="g-top">

<span class="g-name">Malware
scanning</span><span class="g-tag">Deployment</span>

</div>

The CLEAN verdict that `_require_files` depends on is only as
trustworthy as the deployed `MalwareScanner`. The code correctly refuses
to proceed on `pending`, `error`, `infected` or `rejected`.

</div>

<div class="gate">

<div class="g-top">

<span class="g-name">Phone verification</span><span class="g-tag">Not
wired</span>

</div>

A full challenge flow exists in `contacts.py` with TTL and attempt caps,
but it is a post-activation driver-portal feature and forms no part of
`reconcile_driver_work_eligibility`. There is no phone gate on
eligibility today.

</div>

<div class="gate">

<div class="g-top">

<a id="cld-02-account-activation"></a>

<span class="g-name">Account
activation</span><span class="g-tag">Manual</span>

</div>

No code path moves a driver from `invited` to `active`. Even a fully
approved applicant cannot log in until an admin changes the user record
by hand. This errs toward less access, but it means the delivered flow
does not yet close — worth confirming it is intended rather than
missing.

</div>

</div>

</div>

<div class="section">

## <span class="num">§6</span> Smallest remediation

Ordered by ratio of risk removed to code touched. Nothing here changes
the eligibility model, which is sound.

1.  **Equalize the registration KDF cost
    <span style="color:var(--muted);font-weight:400">— F1</span>**Move
    `_unreachable_password_hash()` above the `existing_user` branch in
    `submit_driver_application` and discard the result on the
    early-return path. One moved line closes the enumeration channel and
    preserves the existing constant-response design.
2.  **Give the application a terminal status
    <span style="color:var(--muted);font-weight:400">— F2</span>**Widen
    `DriverApplicationStatus` and the CHECK constraint, set it from the
    review decisions, then filter the admin queue and
    `_eligible_access_application` on the real state. This
    simultaneously clears the queue, fixes the header count, and
    terminates applicant write capability at approval or rejection.
3.  **Fingerprint the identity axes
    <span style="color:var(--muted);font-weight:400">— F3</span>**Add a
    peppered HMAC column beside the NIN and bank-account ciphertexts,
    populate on write, index it, and surface collisions to the reviewer.
    This is the only change here that adds a control rather than
    tightening one, and it is what stands between the platform and
    cheaply replicated synthetic drivers.
4.  **Bound the approval horizon and split the duties
    <span style="color:var(--muted);font-weight:400">— F4,
    F5</span>**Clamp `valid_until` to a configured maximum in
    `_validate_decision`, and require the payout verifier and the
    person/payee approver to be different admins. Two predicates, both
    in existing validation functions.
5.  **Tighten the supporting edges
    <span style="color:var(--muted);font-weight:400">— F6, F7,
    F8</span>**Push the audit-evidence predicates into SQL with a time
    bound; add `valid_until > now` to the candidate query; alert on
    global registration-cap exhaustion. Also translate the
    plate-uniqueness `IntegrityError` into the intended 409 at the
    applicant call site.

<div class="note">

**Not recommended:** changes to the derived-eligibility model, the
advisory-lock ordering, or the append-only evidence schema. These are
the parts carrying the verdict, and they are working.

</div>

</div>

Read-only audit · no writes, no provider calls, no suite execution All
citations pinned to 637841d No real identity data was used or generated

</div>
