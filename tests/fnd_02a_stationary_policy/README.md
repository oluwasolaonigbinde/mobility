# FND-02A — stationary-time policy decision packet

## Status and authority boundary

This is a contributor-owned **decision-evidence packet**, not an adopted policy
and not production code. It intentionally leaves every owner-controlled value
unset. It does not edit `docs/progress.md`, `docs/architecture.md`,
`docs/decisions-log.md`, application code, migrations, generated contracts, CI,
or any existing test.

FND-02A remains `TODO`; FND-02B remains `BLOCKED — EXT-RM2-POLICY`. Only the
canonical controller may reconcile the selected decision into authority docs,
clear the external prerequisite, integrate a production implementation, or
change checklist status.

### Contributor-owned manifest

Everything in this packet is isolated under
`tests/fnd_02a_stationary_policy/`:

- `README.md` — authority boundary, first-hand facts and shared invariants;
- `OPTIONS.md` — complete A/B/C parameter and behavior contracts;
- `FIXTURES.md` — shared corpus matrix and execution commands;
- `HANDOFF.md` — owner form, decision-log row and FND-02B/MNY-06 notes;
- `fixtures/*.json` — one shared, split fixture corpus with parameterized
  expected outcomes for options A/B/C;
- `model.py` — packet data model, fixture loader and fail-closed parameter
  validation;
- `evaluator.py` — deterministic test-only evaluator;
- `witness.py` — algebraic test witnesses derived from fixture durations only;
- `run_evaluator.py` — standalone CLI for a completed owner parameter file;
- `option-a.parameters.template.json` — visibly unset option-A fields;
- `option-b.parameters.template.json` — visibly unset option-B fields;
- `option-c.parameters.template.json` — visibly unset option-C fields and the
  current unavailable hold dependency;
- `test_packet_contract.py` — corpus completeness and fail-closed CLI tests;
- `test_policy_outcomes.py` — parameterized outcome, precedence and invariant
  tests for all three options;
- `__init__.py` — test namespace marker.

No file in this namespace is imported by `app/` or packaged by Hatch (the
project wheel includes only `app`).

## First-hand repository facts frozen by this packet

The packet was reconstructed from repository authority and code, not from a
session scratchpad.

1. `app/services/payout_eligibility.py::_stay_point_regions` confirms a stay
   only when its duration is `>= stationary_window_seconds`. A stay strictly
   below that boundary contributes no stationary exclusion.
2. A displacement `>= stationary_radius_m` ends the current stay anchor. The
   required `4:59 → hop beyond radius → repeat` pattern can therefore avoid the
   current five-minute-style stay confirmation for an entire shift.
3. `stationary_grace_seconds` is already one chronological **whole-session
   budget**. Out-of-area slices do not reset it; a GPS gap breaks positional
   continuity.
4. Current precedence is: `gps_gap` → `low_accuracy` (including null accuracy)
   → `teleport` → `out_of_window` → `out_of_area` → `stationary` → payable.
5. `EligibilityParams.as_metadata()` currently fingerprints radius, stationary
   window, whole-session grace, accuracy, teleport and ping-gap values.
6. `app/services/payouts.py` accepts per-rule `eligibility_params` overlays,
   resolves them over `PAYOUT_ELIGIBILITY_*` settings, and includes the complete
   effective metadata in the write-once payout input fingerprint together with
   the ping set, zone state and campaign window.
7. Eligible time is cut at **Africa/Lagos midnight** and allocated by Lagos
   calendar day. Every classifier result must satisfy
   `eligible_seconds + excluded_seconds = session_duration`.
8. D14 makes a change to what counts as payable a genuine immutable formula
   change. D18/MNY-06B owns `payout_v3`; `payout_v2` history must not move.
9. D18/Q5 preserves base/premium rate tiers: valid time outside the premium
   zone uses `BASE_RATE_NGN_PER_HOUR`, valid time inside uses
   `PREMIUM_RATE_NGN_PER_HOUR`; excluded/invalid time earns neither.
10. Option C cannot be made financially authoritative today. MNY-08A/B in
    PKG-02 must first provide current assessments, serialized review states and
    one shared `hold_active` predicate used by every money consumer.

## Shared contract for all three choices

These rules are not optional differences between A/B/C:

- **No rate value is selected here.** Outcomes expose rate-seconds and the
  symbolic expression
  `(base_seconds/3600)*BASE_RATE_NGN_PER_HOUR +
  (premium_seconds/3600)*PREMIUM_RATE_NGN_PER_HOUR`.
- **One reason per second.** Signal/window/area precedence remains unchanged.
  A stationary policy cannot relabel a GPS gap, low/null accuracy, teleport,
  out-of-window or out-of-area interval.
- **Hold is an overlay, not a third duration partition.** Under option C,
  `payable + excluded = duration` still holds; `held <= payable`, and
  `releaseable = payable - held`.
- **Out-of-area and out-of-window do not restore allowance or erase evidence.**
  They retain their own exclusion reason while valid positional evidence can
  continue the stationary detector/budget/hold evidence.
- **GPS position is never inferred through a gap.** Option A resets its rolling
  detector. Option B retains already spent budget without bridging positions.
  Option C retains already accumulated suspicion evidence without treating the
  gap as movement.
- **Signal-invalid intervals do not contribute new sub-window evidence.** Low
  or null accuracy and teleport keep their existing exclusion reasons.
- **Accepted terms remain frozen.** The selected revision applies only to
  assignments/offers accepting that revision on or after `EFFECTIVE_AT`.
  Existing accepted work keeps its bound revision. Retroactive correction, if
  ever required, is a separate MNY-06C maker-checker order.
- **Historical formulas stay readable.** The selected values become part of an
  immutable eligibility revision and every payout/explanation fingerprint.

## Common parameters required for any selection

All values below are deliberately unset in every option template. “Inherited”
means the concept already exists; the owner must still either state the value
for the new immutable revision or explicitly bind the revision to an already
approved value source. A deployment default is not owner approval.

| Symbol / template field | Unit/type | Required scope and boundary semantics | Missing-data / gap behavior | Effective/version timing |
|---|---|---|---|---|
| `SR_M` / `stationary_radius_m` | metres, positive | Existing stay-radius fact. Equality (`distance >= SR_M`) exits a stay anchor. | Never inferred through `gps_gap`; low/null accuracy and teleport keep precedence. | Frozen in `ELIGIBILITY_REVISION`; no mutation of prior revisions. |
| `SW_S` / `stationary_window_seconds` | seconds, positive | Existing confirmed-stay boundary. `episode_duration >= SW_S` uses the existing long-stay path; `< SW_S` is the open sub-window class. | Gap breaks a positional episode. Area/window boundaries do not create a new allowance. | Frozen in the revision used by newly accepted work. |
| `SG_S` / `stationary_grace_seconds` | seconds, non-negative | One chronological allowance for the selected scope; never per episode. | An excluded area/window slice can consume chronological grace but cannot renew it. | Frozen and fingerprinted. |
| `ACC_M` / `max_accuracy_m` | metres, positive | Existing inclusive quality ceiling: null or worse-than-ceiling accuracy is invalid. | `low_accuracy` wins before stationary policy. | Frozen and fingerprinted. |
| `TP_KMH` / `teleport_kmh` | km/h, positive | Existing impossible-speed boundary. | `teleport` wins before stationary policy. | Frozen and fingerprinted. |
| `GAP_S` / `max_ping_gap_seconds` | seconds, positive | Existing gap boundary. A larger interval is position-unknown. | `gps_gap` wins; option-specific state behavior is fixed below. | Frozen and fingerprinted. |
| `EFFECTIVE_AT` / `effective_at` | RFC3339 timestamp | Exact instant at which new accepted terms may bind the revision. | Not applicable. | Owner-supplied; never backdates existing accepted work. |
| `ELIGIBILITY_REVISION` / `eligibility_revision` | immutable stable ID | Identifies the complete common + selected-option parameter set. | Missing ID fails closed. | Bound by MNY-06B to accepted assignment/trip terms and payout fingerprint. |
| `effective_application` | enum | Fixed as `new_acceptances_only` to preserve immutable accepted terms. | Not applicable. | Any different application mode requires an explicit architecture/money decision. |

## Packet navigation

- [Option contracts](OPTIONS.md)
- [Fixture corpus and execution](FIXTURES.md)
- [Owner/controller handoff](HANDOFF.md)

