# Prompt 6 — driver journey audit

## Provenance

- Reviewer: Claude Opus 5, High effort
- Audited source: `5f84194df6e9527fcdcbc25b3cb66c9c58697d07`
- Mode: isolated-worktree, read-only source audit
- Controller capture: 9 September 2026

## Executive result

The evidence and offline queue engine are strong, and the trip-level earnings
breakdown is comparatively clear. The unaided driver journey is nevertheless not
pilot-complete: required device setup, account recovery, onboarding recovery,
support and several money explanations are absent or unreachable.

## Confirmed journey breaks

1. Standalone PWA mode is a hard requirement for Start, but the product contains no
   install prompt or Add-to-Home-Screen guidance. A driver opening the link in a
   normal browser cannot discover how to satisfy the gate.
2. Password-reset APIs exist but there is no forgot/reset page or login link. This
   is the same root cause as Prompt 1's credential finding.
3. Identity and vehicle submissions require an expiring emailed onboarding code,
   but there is no product path to request a replacement. Expiry or loss therefore
   becomes a staff-dependent dead end.
4. Vehicle revision asks the driver to retain and later type a vehicle UUID. There
   is no signed-in vehicle list or recovery lookup.
5. The public application status surface reports only pending review and does not
   provide rejection reasons or a resubmission route.
6. The driver product exposes no approved support destination. A support surface
   is required, but its real phone, WhatsApp or email value remains owner input and
   must not be invented.
7. Installation scheduling/removal logistics are absent from the repository. The
   product should not invent a real-world installer process; the client/operations
   model is required before building this journey.

## Safety, offline and money findings

1. The accepted screen-on tracking model stops the watcher when the app becomes
   hidden. The UI does not explain phone mounting or the consequence of switching
   to a navigation app, and the stop can be silent. This is a material safety and
   earnings-trust defect; the remedy must not encourage phone interaction while
   driving or silently broaden tracking into the background.
2. Capture deliberately continues offline during an active trip, but End requires
   connectivity and valid session authority. The disabled End action lacks a
   nearby explanation, leaving an open trip with no clear safe next step.
3. The offline navigation fallback does not explain that already stored trip
   evidence remains on the device. Jobs and earnings fail closed when freshness
   cannot be proved; that authority boundary should remain, while the product may
   still explain what is preserved and what cannot be shown.
4. `FreshDriverAuthority` records a stale condition when offline and does not
   visibly clear it on the online event. The claimed permanent latch needs a real
   App Router reproduction before implementation.
5. The same ledger states are presented under conflicting raw and friendly names
   across earnings list and trip detail. Held and carried-debt amounts often lack a
   directly reachable reason or dispute path.
6. Driver disputes cover fraud holds but not every way time or earnings can be
   excluded. Expansion is a product/operations decision; the confirmed defect is
   that existing adverse money states need a reason and an approved escalation
   path.
7. Payout cadence, hold timing and destination account are not shown. The product
   must present approved policy truth, but the actual provider, threshold and
   support destination remain external/owner inputs.
8. Bank account entry has no confirmation/read-back and the driver cannot view a
   masked submitted destination. Admin review reduces but does not remove the
   entry-error and trust risk.
9. Location/NIN/bank-data explanations are insufficient for a real pilot. Exact
   disclosure language and lawful basis remain legal/client inputs under Prompt 8.

## Reconciled presentation findings

Raw authority, governance, hash, watermark, quarantine, capability and enum terms
reinforce `CPY-002`; native confirms reinforce `FUX-006`; earnings overload remains
`FUD-001`; the capability diagnostic remains subject to `FOD-003`. Suggested copy
from the audit is design input, not approved legal or product wording.
