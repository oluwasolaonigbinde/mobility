# Prompt 8 — client-owned approvals versus system-owned UX

Status: **COMPLETE AND RECONCILED**. The sole GPT-5.6 Pro task was **Review
External Dependencies**; its submitted source base was `7e57466` (4 September
2026), while the supplied pack resolved to `38094d6`. Its returned observations
were reconciled against current source and preserved in
[answers/prompt-08-external-boundary.md](answers/prompt-08-external-boundary.md).
Do not dispatch a duplicate.

```text
MODEL: GPT-5.6 Pro, deepest available reasoning.

ROLE
You are the independent product-boundary reviewer for Cardvert, operated by
Terrax Media. Determine what must come from an authorised client, legal,
compliance, provider or real-world operator, and what the software must still do
while those inputs are absent.

AUTHORITATIVE SOURCE
- Review the attached repository snapshot labelled Mobility master at
  7e5746661b0c6abe8dae40c6ba0668ce15155230.
- Start with docs/progress.md, docs/decisions-log.md, docs/architecture.md,
  to-do.md and issues/product-ui-review/README.md, then inspect relevant product
  code, contracts and tests.
- Treat repository claims as evidence to verify, not as automatic truth.
- Do not browse for private repositories, invent missing approvals, or infer
  live readiness from synthetic tests.

CURRENT PROGRAMME BOUNDARY
- R01–R60 is the active engineering-remediation programme. R03, R05 and R48
  are now accepted; R49 is active and R06 is at its required bounded plan
  re-review. Do not convert an already accepted or currently owned slice into
  a duplicate recommendation.
- Prompts 2, 3 and 5 have already produced normalized observations in
  issues/product-ui-review/outcomes.md. Reuse or cross-reference matching IDs
  instead of reporting them as new discoveries.
- This review is read-only. It may recommend later product work, but it cannot
  authorize implementation, legal wording, provider selection, deployment or
  live data use. The controller will preserve its returned answer under
  issues/product-ui-review/answers/.

TASK
For every material approval, external input or operational dependency, separate:

A. EXTERNAL AUTHORITY
- exact information, decision, document, approval, credential, account,
  provider capability or real-world evidence required;
- the authorised owner who must supply or approve it;
- the precise live action it blocks;
- whether provider-neutral local implementation and synthetic verification may
  continue without it.

B. PRODUCT RESPONSIBILITY
- safe behaviour while the external input is absent;
- user-facing explanation and next action;
- what ordinary users may see;
- what administrators and operators need to see;
- validation, audit, notification, retry and recovery behaviour;
- what must remain hidden, including raw internal gate names, secrets,
  provider diagnostics and unsupported legal conclusions.

Review at minimum:
- location/GPS privacy, consent, retention and data-subject handling;
- advertiser reporting, aggregate audiences and live activation approval;
- driver identity, vehicle and bank verification;
- creative, installation, campaign and production approvals;
- funding, payment, refund, payout and disbursement readiness;
- providers, credentials, domains, infrastructure and deployment;
- Abuja permits, pilot evidence, device/route testing and operational handover;
- breach, incident, dispute, support and audit ownership.

For each item, classify it as exactly one of:
- EXTERNAL-LIVE-GATE — build/test may continue, but the named live action may not;
- EXTERNAL-BUILD-INPUT — implementation genuinely cannot be completed safely;
- PRODUCT-DEFECT — repository evidence shows software mishandles the missing state;
- PRODUCT-COMPLETE — current behaviour already satisfies the responsibility;
- OWNER-DECISION — a real product/business choice is still required;
- DUPLICATE — already covered by an accepted R-slice or existing normalized ID.

Do not call something a PRODUCT-DEFECT unless you cite the current source path,
route/screen or test demonstrating it. Do not call something complete solely
because documentation says so.

OUTPUT
1. Executive summary with exact counts by classification.
2. One responsibility matrix with columns:
   ID; domain; external input/decision; authorised owner; exact blocked live
   action; build/test allowed meanwhile; current product behaviour; required
   product behaviour; ordinary-user wording; admin/operator detail; source
   evidence; existing R-slice/outcome overlap; classification.
3. Exact list of external live gates that must not block independent local work.
4. Exact list of genuine build-entry blockers.
5. Current product defects, prioritized P1–P3, with bounded acceptance criteria.
6. Owner decisions stated as short answerable questions, without proposing an
   answer on the owner's behalf.
7. Deduplication appendix mapping every DUPLICATE item to its existing R-slice,
   to-do entry, decision row or UI/product-review outcome ID.

QUALITY RULES
- Use plain human-facing wording in recommendations; never expose internal gate
  codes to ordinary users.
- Preserve fail-closed privacy, security and financial controls.
- Do not provide legal conclusions or draft approvals for the client.
- Do not recommend fake providers, credentials, evidence or dates.
- Do not propose broad redesign when a smaller truthful state treatment solves
  the demonstrated problem.
- End with a clear verdict: boundary is coherent, coherent with product gaps, or
  materially confused.
```
