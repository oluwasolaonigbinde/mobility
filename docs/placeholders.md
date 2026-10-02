# Demo inputs and replacement checklist

Owner authority: D46, narrowed by D47; REQ-059 and REQ-060. Demo displays use
records from existing seed/synthetic fixtures, with their real database status
and working actions. The UI does not manufacture names, money or completed
checks. Replace these inputs before launch; retain the existing live-use gates.
No additional runtime placeholder blocker is part of L2-1.

| Input | Existing source and where it appears | Real replacement | Waiting request / gate |
|---|---|---|---|
| Driver identities, contact details and cars | `app/seeds/demo.py`, `app/seeds/rich.py`; Drivers search/list/hub, campaign jobs, Trip checks and Work queue | Approved Abuja pilot drivers, their own accounts/contact consent and actual vehicle/document evidence | REQ-059; EXT-PILOT-FACTS, EXT-PHONE-OPERATOR, EXT-EVIDENCE-POLICY |
| Advertiser identities and campaign details | Same seed graph; Advertisers directory/company page, campaign lists/hubs and search | The five pilot advertisers, company profiles, individual campaign terms and approved artwork | REQ-059; EXT-PILOT-FACTS, EXT-COMMERCIAL-VALUES |
| Recorded trips and reach assumptions | Existing deterministic seed GPS, analytics and traffic-density records; Trip checks, Results, Settings Reach estimates | Real authorized collected trips, approved reach assumptions and method evidence | REQ-059; EXT-LEGAL-PRIVACY, EXT-REPORT-METHOD |
| Legal/privacy previews | Existing test-only synthetic journey fixtures (`docs/pkg-08-w4-03b-synthetic-journey.md`); no synthetic legal acceptance added to the admin portal | Approved legal/privacy wording, consent versions, retention and responsible adviser | REQ-059; Q26/Q31, EXT-LEGAL-PRIVACY |
| Permit references | No real permit record or invented approval is added to the portal | Approved pilot permit documents and references | REQ-059; EXT-PILOT-PERMITS |
| Terrax bank details on demonstration invoices | Existing synthetic invoice fixtures only; no replacement bank account is added to a verified invoice or payment instruction | Approved settlement bank and verified Terrax account details | REQ-041; EXT-SETTLEMENT-BANK |
| Report method text | Existing synthetic report journey fixtures only; no new live issuance authority | Approved performance/ROI method and disclosure references | REQ-059; EXT-REPORT-METHOD |

The local demo seed is explicitly refused in staging/production by its existing
`ensure_seed_allowed` guard. Synthetic privacy modes require `environment=test`.
L2-1 does not widen either rule. Consequently this register does not claim that
staging has been configured or that absent permit/legal/bank inputs have been
filled. Their previews stay confined to the existing synthetic fixtures, and
their replacement obligations remain open.

Before launch, replace the registered demo identities and external inputs,
verify document/phone/contact consent for the real users, and satisfy the
existing provider, legal, permit, bank and reporting gates. Real pay and payout
figures always come from existing calculations/ledger records; they are never
placeholder values.
