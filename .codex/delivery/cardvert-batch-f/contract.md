# Cardvert Batch F — delivery contract and evidence (REQ-009, REQ-010, REQ-012)

Branch `batch-f` from `master` `fedd41b`. Owner-approved on 29 Sep 2026 after one independent plan
review (vfd-plan-reviewer, Opus 5.5: 4 material, 8 should-fix, 3 notes, all adopted).

## 1. Owner decisions (29 Sep 2026)
- REQ-011 (client guide rewrite) is out of this batch; the owner will do it later.
- Invoice bank slots stay blank until Terrax's real OPay details arrive (REQ-041); a real invoice
  needs them. Accountant confirmation is REQ-042.
- Prices stay entered before VAT; the invoice leads with the VAT-inclusive total.
- From the client's invoice-field list: quantity is the number of advert campaigns (default 1);
  client name, company, email, date and services rendered are shown; "type of campaign budget"
  is shown as the payment arrangement. Recorded as D42.

## 2. Scope
- **F1 invoice layout (REQ-009, D42).** Advertiser and staff invoice pages; quotation lines with
  quantity and unit price; campaign dates frozen in the accepted quotation; migration `0095` adds
  RC number, phone, email and bank details to append-only issuer profiles (downgrade refuses once
  recorded); verified profiles and issuance require every fact and the accountant sign-off
  reference. VAT computation, numbering, immutability, corrections and payments unchanged.
- **F2 deployment templates (REQ-010).** `deploy/render/render.yaml`, `deploy/aws/`,
  `docs/deployment-templates.md` (13 go-live gaps), `tests/test_deploy_templates.py`. Nothing
  applied; no account, deploy or provider call.
- **F4 docs (REQ-012).** Architecture §15.2, §16 introduction, §16.2, §25, two §30 rows, §34
  v1.102; PRD M-06, M-08, M-09, M-11–M-15 scoping, new §7.9 M-30–M-32.
- **Records.** D42 and the Q28 note; client-decisions "Invoices and VAT" and "Hosting" histories;
  requests REQ-011 back to TODO, new REQ-041 and REQ-042.

Non-goals: VAT-inclusive price entry, numbering change, PDF, print styling, issuer/issue UI,
seeded issuer, any real RC/TIN/bank value, CSP/edge/KMS-custody/release-script changes, payout or
complaint logic.

## 3. Criterion evidence (final source state)
| AC | Verdict | Evidence |
| --- | --- | --- |
| AC1 quantity lines | PASS | `test_quotation_lines_accept_quantity_and_unit_price_and_campaign_dates`: 3 × 100,000.00 = 300,000.00; amount given must equal the product; 0, bool, string, missing half refused; a line without quantity keeps the exact earlier key set; totals 370,001.00 / 27,750.08 / 397,751.08 |
| AC2 campaign dates | PASS | same test: missing end, `01/10/2026`, `20261001`, end before start → `INVALID_PRODUCTION_SCOPE`; admin page test: 23:00 UTC 30 Sep pre-fills 2026-10-01 (WAT); live form pre-filled the same |
| AC3 verified issuer facts | PASS | `test_verified_issuer_needs_rc_contact_and_bank_facts_and_the_accountant_gate`: each missing fact → `INCOMPLETE_ISSUER_FACTS`; blank sign-off reference → `VERIFIED_ISSUER_GATE_REQUIRED`; blanks normalise so replays converge; changed facts conflict; `test_issuer_profile_request_bounds_the_new_facts` (lengths, email) |
| AC4 issuance | PASS | `test_issued_snapshot_carries_contact_and_bank_and_incomplete_verified_is_refused` (pre-0095 verified row refused; snapshot carries six facts); `test_pkg03_pro_corrections` issues a real verified invoice with complete facts |
| AC5 migration | PASS | `test_issuer_contact_and_bank_columns_match_models_and_block_lossy_downgrade`: metadata matches, round trip, downgrade refused with recorded bank details; single head `0095` |
| AC6 invoice pages | PASS | `invoice-document.test.tsx` (every field, WAT issue date across midnight, exact kobo, credit/debit wording, draft/test/void labels, "Not yet recorded", no internal references); both page tests (404 for another campaign's invoice or a 404 campaign); live check below |
| AC7 admin form | PASS | `page.test.tsx` and `actions.test.ts`: quantity 1 default, unit price required, VAT 0.075, required dates, exact request body |
| AC8 contract baselines | PASS | `openapi.json`, `docs/api/openapi.snapshot.json` (`update_openapi_snapshot --check` OK), `schema.d.ts` regenerated from the committed `openapi.json`; full Vitest: 1,134 passed, 3 font-scan tests timed out under full-suite load and pass alone (85/85) |
| AC9 templates | PASS | `test_deploy_templates.py` (4): backend keys are Settings fields, committed values validate through Settings, no secret values, secret-shaped key guard, switches off, DB/Redis hand-entered, exact IAM actions, KMS via S3 only; gap list reviewed |
| AC11 docs and records | PASS | architecture inventory `--check` OK; D42, Q28, PRD §7, client-decisions, requests updated |
| AC12 D32 | PASS | changed lines vs `fedd41b`: backend 60/60 lines, 18/18 branches; frontend 63/63 lines, 98/109 branches (89.9 %), confirmed on CI run 36599216949's own LCOV. That run's critical-backend ratio sat 0.064 points under the adopted floor because 19 previously incidental `billing.py` refusal lines went uncovered after the shard layout changed; `test_commercial_validation_paths_fail_closed` now covers them deterministically before the D33 refresh |

AC10 (client guide) was removed by the owner.

Live check (throwaway local stack, `ENVIRONMENT=test`, demo seed, synthetic data): staff recorded a
quotation through the new form (2 × ₦150,000.00, dates pre-filled 1–31 Oct), the advertiser
accepted it, the admin API created a draft; the advertiser draft page showed "Draft invoice",
₦322,500.00 VAT inclusive and blank bank slots; a verified profile without the sign-off was
refused (409); a synthetic issuer issued `TEST-TMX-2026-000001`; the issued page showed the RC,
TIN, contact, duration "1 October 2026 – 31 October 2026 (31 days)", signature lines and no
internal reference, on both the advertiser and staff pages; an unknown invoice returned 404.

## 4. Reviews
- Plan review: vfd-plan-reviewer, Opus 5.5 — findings adopted before implementation.
- Money/legal specialist (Opus 5.5): FIX (1 must-fix: an existing verified-issuance test lacked
  the new facts; 3 should-fix: strict dates, signed corrections, field bounds) → fixed → PASS.
- Deployment/security specialist (Opus 5.5): FIX (2 must-fix: `fromService` inside the env group,
  region attribution; 7 should-fix) → fixed → PASS.
- Post-build: vfd-change-reviewer (Opus 5.5): FIX (D42 row cut off from the decisions table by a
  blank line) → fixed → PASS.
