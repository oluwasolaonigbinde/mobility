# W2-C driver renewal correction â€” delivery contract

Owner-approved scope: Claude review of local commit 2e29b09, 7 October 2026; REQ-125â€“130. No push. Phone verification behavior is approved and preserved except requested demo configuration.

## Outcome and implementation

C1. A driver sees each document separately with a human label and its recorded outcome/reason; filenames never reach this renewal view. Record which documents a staff rejection/expiry concerns and optional actual document expiry dates on the exact immutable review. Approval accepts all documents only after the existing audited approval gates. Non-approved reviews record explicit per-document outcomes; omitted details retain an unreviewed/on-file outcome, never inferred acceptance. An accepted per-document outcome requires the exact document read audit. A bank/identity-only rejection does not falsely reject documents. Staff selects affected documents; a broad document rejection can explicitly affect all. Do not infer an insurance expiry date from a whole-car approval expiry. Automatic expiry preserves the previous document facts/dates. Before and after that worker runs, whole-car expiry allows zero-file resubmission of retained documents for a new review.

C2. Partial driver resubmission merges replacement files with the previous revisionâ€™s retained files, reuses the existing encrypted NIN and bank-account version unless their own rejection requires replacing them, creates one new review revision, and preserves ownership, clean scans, retention, exact-retry, expected-version, user-lock and work-authority gates. Identity mismatch requests NIN; bank mismatch requests bank details from a named bank list. Purged/missing retained material requires complete fresh replacement rather than silently recovering erased data; partial retries after source purge fail closed. Recorded document expiry dates constrain acceptance and work authority using the database date in Nigeria time. Existing accepted files need no upload.

C3. Renewal UI uses styled accessible upload controls, loading/error/pending/retry states and only the fields required by C2. No filenames, NIN or bank values are exposed by the status response. Clearly explain that new campaign trips are paused where the current person/car approval fails; distinguish a whole-car review expiry from an individual document expiry. Verify finish-trip and other approved-car behavior before wording.

C4. All seeded cities, campaign/zone/route/address/place names and geometry/GPS use real Abuja areas. Preserve brands except Lagos-specific names, synthetic financial history and seed idempotency. Update seed assertions/e2e fixtures and docs/demo-data.md together. Use coordinated Abuja corridors/polygons, not a name-only replacement.

C5. Demo driver phones use documented synthetic +234 numbers. Temporary Terrax destination is owner-approved +2347068369842 only for local/preview; production/staging remain blank and existing live-use gates remain. REQ-126 remains NEEDS ANSWER for the PMâ€™s real preview WhatsApp number. No messages or provider calls.

C6. Capture and visually inspect real browser screenshots at 375 px: rejected licence, expired vehicle insurance, seeded Abuja campaign/map. Verify partial replacement through authenticated API/browser flow.

C7. Rerun touched tests without local coverage instrumentation, relevant lint/types and generated OpenAPI/native contract checks when schemas change. Record criterion-by-criterion results once stable. Independent plan review, privacy/security supplement and SAME post-build reviewer PASS required, then one local commit with explicit staging. No CI/push/deploy and no launch-programme status changes.

## Entry points and scope

app/schemas/driver_onboarding.py, kyc.py; app/models/kyc.py and a review-detail migration if needed; driver_documents and kyc APIs; driver_onboarding/kyc/vehicle_onboarding services; driver renewal component and staff review controls/actions; generated contract baselines; app/seeds/** (source only), docs/demo-data.md and touched tests/e2e. Decision/index/architecture and request records updated for actual new rules. The approved phone challenge flow, payments, accepted campaign terms and unrelated W1/W2D work are outside scope. Never access docs/account-access.md or tmp/. Work only mobility-w2c.

## Risk and verification

Sensitive reuse must not return plaintext to a browser or logs, bypass fresh review, fabricate approval or reuse purged files. New review details must be included in retry fingerprints and remain bound to exact revisions. Exercise one-file renewal, bank-only replacement, rejected identity, stale/foreign/purged/unsafe IDs, retry conflicts, pending restrictions and preserved accepted-file references. Seed geographic bounding assertions include routes/trips as well as campaign polygons; rerun safety/idempotency tests. Native fixture checks verify updated shared contract baselines. Browser evidence uses isolated synthetic data and existing local services.

## Checkpoints

Requests recorded first â†’ independent plan review and valid corrections â†’ present reviewed contract (existing explicit owner scope authorizes implementation) â†’ implement â†’ touched checks and C1â€“C7 evidence â†’ privacy/security supplements â†’ same consolidated reviewer FIX/PASS loop â†’ explicit local commit, report screenshots and any pending external inputs.

## Independent plan review disposition

GPT-6.1 Sol plan reviewer returned two FIX findings: untouched-document acceptance must be explicit/audited, and whole-car expiry must preserve document facts and support zero-file resubmission. Both are incorporated into C1–C2 above. Also test changed-payload retries and retries after source payload purge. No findings rejected.
