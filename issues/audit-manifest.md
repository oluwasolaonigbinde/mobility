# Cardvert first-pass audit manifest

Retrieved on 1 September 2026. The expected set is owner-confirmed at 14 source
responses: 8 ChatGPT, 2 Codex and 4 Claude.

Collection states: `COLLECTED`, `DUPLICATE`, `INCOMPLETE`, `MISSING`,
`INACCESSIBLE`, or `PENDING` while collection is active.

## Expected source responses

| ID | Surface | Conversation/task ID | Displayed title | Expected model | Audited ref | State | Raw artifact |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GPT-01 | ChatGPT TSS | `6a969279-48a8-83ea-8b2f-e2cceef24a75` | Audit Database Concurrency | GPT-5.6 Pro | `637841d95493bcc24334356da42097fa53a5d16f` | COLLECTED | `audits/raw/chatgpt-database-concurrency-audit.md` (`sha256:5536a8bde62ca9414f378b5df90e9b5f638b3bd14852fa7cc1ce4f7d17adf766`) |
| GPT-02 | ChatGPT TSS | `6a9692e5-f738-83e9-a454-e79d97a25369` | Audit test evidence | Claude Opus 5 via ChatGPT | `637841d95493bcc24334356da42097fa53a5d16f` | COLLECTED | `audits/raw/chatgpt-test-evidence-audit.md` (`sha256:1915c9c9e6469a807a8794ac1dc64f558b8dbd04224ec019dca895d3ab7a2edc`) |
| GPT-03 | ChatGPT TSS | `6a969018-fd90-83ea-b8ce-fa39b76c0dbc` | Retargeting Contract Audit | GPT-5.6 Pro | `637841d95493bcc24334356da42097fa53a5d16f` | COLLECTED | `audits/raw/chatgpt-retargeting-contract-audit.md` (`sha256:e7d8d84e060caa9be2c9df2eecb17c51cdddbe78435a494f7e574488ceb60549`) |
| GPT-04 | ChatGPT | `6a968442-15ec-83ea-92f8-d2089acdca32` | Audit offline protocol | GPT-5.6 Pro | `637841d95493bcc24334356da42097fa53a5d16f` | COLLECTED | `audits/raw/chatgpt-offline-protocol-audit.md` (`sha256:48997e22b10a9e24d4fddf6058174249c6a850e11956880f98ba83000e9d724a`) |
| GPT-05 | ChatGPT TSS | `6a967da0-6524-83e9-ad55-5c49240a857f` | Audit architecture implementation | GPT-5.6 Pro | `637841d95493bcc24334356da42097fa53a5d16f` | COLLECTED | `audits/raw/chatgpt-architecture-implementation-audit.md` (`sha256:1d4785318f84e1f7eecdf1eeb675b5a1335125d024170083b1c46b5cdebde4aa`) |
| GPT-06 | ChatGPT TSS | `6a967dcf-177c-83ea-8592-a923fd93b507` | Privacy Audit Verification | GPT-5.6 Pro | `637841d95493bcc24334356da42097fa53a5d16f` | COLLECTED | `audits/raw/chatgpt-privacy-audit.md` (`sha256:d7b364c25f6a0da0c5bef11f9a5494235832e2d9c74ef316a2bd0b9d2a6720c3`) |
| GPT-07 | ChatGPT TSS | `6a967dc0-eb14-83ea-a4b1-b4dde47dc0a7` | Audit Authentication Authorization | GPT-5.6 Pro | `637841d95493bcc24334356da42097fa53a5d16f` | COLLECTED | `audits/raw/chatgpt-authentication-authorization-audit.md` (`sha256:f5d84d60d5a279ef967c8edbcce3eb046c0ff9d16f80c5381eab8383811dfba3`) |
| GPT-08 | ChatGPT TSS | `6a967de6-be28-83ea-b93f-c790092584de` | Audit payout settlement safety | GPT-5.6 Pro | `637841d95493bcc24334356da42097fa53a5d16f` | COLLECTED | `audits/raw/chatgpt-payout-settlement-safety-audit.md` (`sha256:35e6e726fb137972c5f7034c59b1a69fb4ecc4a34365f7b17cbd9ebe700419b9`) |
| CDX-01 | Codex | `01a05c2c-7875-7d11-9bf1-f6459bdb3fba` | Audit Cardvert Production Readiness | GPT-5.6 Sol/xhigh | `637841d95493bcc24334356da42097fa53a5d16f` | COLLECTED | `audits/raw/codex-production-readiness-audit.md` (`sha256:d56fd881cd29d3bb093e217ac474495b39d6f0fbc4be12d2158660155e041b5e`) |
| CDX-02 | Codex | `01a05c2b-ad63-70f2-8dac-d64b3e4c9264` | Audit Frozen Report Authority | GPT-5.6 Sol/xhigh | `637841d95493bcc24334356da42097fa53a5d16f` | COLLECTED | `audits/raw/codex-frozen-report-authority-audit.md` (`sha256:7d75cdc8048c845deee9a129b0a9a862244f4e34b60c62dc0fe96c2397bc9298`) |
| CLD-01 | Claude desktop | `2cd1e18e-1261-4a6c-b883-1dee89f795cd` | Cardvert commercial flow audit | Claude Opus 5 | `637841d95493bcc24334356da42097fa53a5d16f` | COLLECTED | `audits/raw/claude-commercial-flow-audit.md` (`sha256:c4e89501785ea9fc9d66da1d2e69c530ad086c65211bc8e3770775f87d964594`) |
| CLD-02 | Claude desktop | `eaa468ec-bac4-4fc2-ab69-2fc8aa94415b` | Driver onboarding security audit | Claude Opus 5 | `637841d95493bcc24334356da42097fa53a5d16f` | COLLECTED | `audits/raw/claude-driver-onboarding-security-audit.md` (`sha256:594e542a5609b7b3c783fc352e1f6bb96a7e394d9a289359875c92dd5edf0d11`) |
| CLD-03 | Claude desktop | `6b86ae67-ce66-4354-99a9-d412c1644f42` | Cardvert campaign lifecycle audit | Claude Opus 5 | `637841d95493bcc24334356da42097fa53a5d16f` | COLLECTED | `audits/raw/claude-campaign-lifecycle-audit.md` (`sha256:975ff747b21a91e114bd38366fef53e78e8505e96257cf49e2577fc57b71ad77`) |
| CLD-04 | Claude desktop | `fca68132-a1b3-43fd-81d3-15f1d0c3a051` | Cardvert advertiser metric audit | Claude Opus 5 | `637841d95493bcc24334356da42097fa53a5d16f` | COLLECTED | `audits/raw/claude-advertiser-metric-audit.md` (`sha256:1c999c5aa73675aa74ee7ea09e85ed9cd55bfb13a929f7c0d99b8b88a0143b50`) |

## Per-response provenance appendix

This one-to-one appendix completes the programme manifest contract. `UNKNOWN`
means the source surface did not expose the value during collection; it is not
reconstructed. Every row is response ordinal 1, complete, uniquely retained,
and has no content redaction unless stated otherwise.

| ID | Project/workspace and retrieval method | Source URL | Ordinal | Prompt/scope pointer | Source created | Retrieved | Completeness / redaction / duplicate |
| --- | --- | --- | ---: | --- | --- | --- | --- |
| GPT-01 | ChatGPT TSS project; project conversation index plus owner-supplied complete response | `https://chatgpt.com/c/6a969279-48a8-83ea-8b2f-e2cceef24a75` | 1 | raw artifact title/frontmatter | UNKNOWN | 2026-09-01 | complete / none / unique |
| GPT-02 | ChatGPT TSS project; project conversation index plus owner-supplied complete response | `https://chatgpt.com/c/6a9692e5-f738-83e9-a454-e79d97a25369` | 1 | raw artifact title/frontmatter | UNKNOWN | 2026-09-01 | complete / none / unique |
| GPT-03 | ChatGPT TSS project; project conversation index plus owner-supplied complete response | `https://chatgpt.com/c/6a969018-fd90-83ea-b8ce-fa39b76c0dbc` | 1 | raw artifact title/frontmatter | UNKNOWN | 2026-09-01 | complete / none / unique |
| GPT-04 | ChatGPT; task index plus owner-supplied complete response | `https://chatgpt.com/c/6a968442-15ec-83ea-92f8-d2089acdca32` | 1 | raw artifact title/frontmatter | UNKNOWN | 2026-09-01 | complete / none / unique |
| GPT-05 | ChatGPT TSS project; project conversation index plus owner-supplied complete response | `https://chatgpt.com/c/6a967da0-6524-83e9-ad55-5c49240a857f` | 1 | raw artifact title/frontmatter | UNKNOWN | 2026-09-01 | complete / none / unique |
| GPT-06 | ChatGPT TSS project; project conversation index plus owner-supplied complete response | `https://chatgpt.com/c/6a967dcf-177c-83ea-8592-a923fd93b507` | 1 | raw artifact title/frontmatter | UNKNOWN | 2026-09-01 | complete / none / unique |
| GPT-07 | ChatGPT TSS project; project conversation index plus owner-supplied complete response | `https://chatgpt.com/c/6a967dc0-eb14-83ea-a4b1-b4dde47dc0a7` | 1 | raw artifact title/frontmatter | UNKNOWN | 2026-09-01 | complete / none / unique |
| GPT-08 | ChatGPT TSS project; project conversation index plus owner-supplied complete response | `https://chatgpt.com/c/6a967de6-be28-83ea-b93f-c790092584de` | 1 | raw artifact title/frontmatter | UNKNOWN | 2026-09-01 | complete / none / unique |
| CDX-01 | Codex task index and task response | N/A | 1 | raw artifact title/frontmatter | UNKNOWN | 2026-09-01 | complete / none / unique |
| CDX-02 | Codex task index and task response | N/A | 1 | raw artifact title/frontmatter | UNKNOWN | 2026-09-01 | complete / none / unique |
| CLD-01 | Claude `mobility` workspace list plus local conversation JSONL | N/A | 1 | raw artifact title/frontmatter | UNKNOWN | 2026-09-01 | complete / none / unique |
| CLD-02 | Claude `mobility` workspace list plus local conversation JSONL | N/A | 1 | raw artifact title/frontmatter | UNKNOWN | 2026-09-01 | complete / none / unique |
| CLD-03 | Claude `mobility` workspace list plus local conversation JSONL | N/A | 1 | raw artifact title/frontmatter | UNKNOWN | 2026-09-01 | complete / none / unique |
| CLD-04 | Claude `mobility` workspace list plus local conversation JSONL | N/A | 1 | raw artifact title/frontmatter | UNKNOWN | 2026-09-01 | complete / none / unique |

## Controller-dispatched follow-up audits

These three read-only Claude Opus 5 High sessions were dispatched by the
remediation controller after the 14-response first-pass collection. They are
preserved as additional provenance and do not change the first-pass expected
set, its counts, or product authority. Their claims remain audit observations
until separately verified, normalized, and admitted through repository control.

| ID | Conversation/task ID | Displayed title | Audited ref reported by source | State | Raw artifact |
| --- | --- | --- | --- | --- | --- |
| CTL-CLD-01 | `7b03371a-1471-4afe-b640-c236834dd328` | Cardvert UX audit | `master @ 3832cff` | COLLECTED | `product-ui-review/answers/prompt-02-ui-ergonomics.md` (`sha256:457133623a6ee6e7a9ed68c34bbea6288dd82b662e22411e1f676525873ffd7f`) |
| CTL-CLD-02 | `40bbab0c-bac9-4e96-88e0-f1ada01d926c` | Cardvert copy audit and voice guide | `master @ 3832cff` | COLLECTED | `product-ui-review/answers/prompt-03-copy-voice.html` (`sha256:50c123f3a59ba5935fca43495f2ab2549a4d2008387b9cd3bcb42feff64aa190`) |
| CTL-CLD-03 | `fd6240e1-f64f-4a72-b879-7656ee8bbf82` | Cardvert advertiser journey audit | working tree `3832cff` (`HEAD 25925e2` reported by source) | COLLECTED | `product-ui-review/answers/prompt-05-advertiser-journey.md` (`sha256:d33fe0249f22e9a2be8693d3fa3ae84dc8dc2d34b03a2cb40b43ba507efe37b5`) |

All three were recovered on 3 September 2026 from their exact local Claude
conversation JSONL. CTL-CLD-02's authored HTML artifact was also still present
in that session's scratchpad and is retained byte-for-byte. CTL-CLD-01 and
CTL-CLD-03 retain the complete terminal Markdown reports visible in their
assistant responses. No report text was reconstructed or normalized in place.
Their separate later-snapshot normalization is complete in
`product-ui-review/outcomes.md`; dependency and likely-lease design is in
`product-ui-review/packets.md`. This adds 42
follow-up candidates without changing the 14-response first-pass count or the
R01-R60 executable queue.

## Explicitly excluded source sessions

These Claude conversations were discovered locally but predate the owner's
four-audit Claude batch. They are not omissions and will not be ingested as
first-pass audits.

| Conversation ID | Displayed title | Created | Exclusion reason |
| --- | --- | --- | --- |
| `e93fa693-b65b-4552-a92f-4ba2b41d6f8d` | Cardvert future-delivery audit | 28 Aug 2026 | Older delivery-planning session, outside the owner-confirmed four Claude audits |
| `2c69eb94-fe2e-4759-a19a-12cd7dceb68b` | Cardvert external-dependency reconciliation | 27 Aug 2026 | Older dependency-reconciliation session, outside this first-pass audit batch |
| `847bff75-9952-4a38-bcd2-89eec30d77bc` | Cardvert future-delivery audit | 28 Aug 2026 | Older delivery-planning session, outside the owner-confirmed four Claude audits |

## Search evidence

- ChatGPT: task index and visible TSS project conversation list; the Codex app
  task interface supplied one complete response and seven 20,000-character
  response prefixes. A browser fallback used a different signed-in account and
  could not access the TSS conversations.
- Codex: application task index and task metadata.
- Claude: visible `mobility` workspace list plus local conversation JSONL
  metadata. Only visible assistant response text will be preserved.
- Older Laravel/TSS release-blocker conversations were inspected by title and
  prompt summary and excluded because they concern a different application.

## Completeness summary

All 14 expected responses are accounted for and complete, with 0 incomplete, 0
missing and 0 duplicates. The original ChatGPT captures were preserved only up
to the 20,000-character application retrieval limit, and a separate browser
attempt could not access those chats because the available browser profile was
signed into a different ChatGPT account. The project owner subsequently
supplied complete copies of all eight ChatGPT responses, replacing or
confirming those application captures. No omitted text was reconstructed.
Three older Claude
planning/reconciliation sessions were discovered and explicitly excluded above
rather than counted as first-pass audits.
