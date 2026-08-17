# FND-02A owner and controller handoff

## Concise owner selection form

Complete exactly one option and all common values. A selection is not complete
until independent product and money reviewers sign the exact commit/fixture
hash.

### 1. Select one mutually exclusive policy

- [ ] **A — rolling displacement**
- [ ] **B — cumulative sub-window stationary budget**
- [ ] **C — explicit fraud deferral/hold** (acknowledge PKG-02 dependency below)

### 2. Common immutable revision values

- `SR_M` (metres): **[OWNER TO SELECT]**
- `SW_S` (seconds): **[OWNER TO SELECT]**
- `SG_S` (seconds, one whole scope): **[OWNER TO SELECT]**
- `ACC_M` (metres): **[OWNER TO SELECT]**
- `TP_KMH` (km/h): **[OWNER TO SELECT]**
- `GAP_S` (seconds): **[OWNER TO SELECT]**
- `ELIGIBILITY_REVISION`: **[OWNER TO SELECT]**
- `EFFECTIVE_AT` (RFC3339): **[OWNER TO SELECT]**
- Effective application: `new_acceptances_only` **[OWNER ACKNOWLEDGE]**

### 3A. Complete only for option A

- `RD_WINDOW_S`: **[OWNER TO SELECT]**
- `RD_MIN_DISPLACEMENT_M`: **[OWNER TO SELECT]**
- `RD_CONFIRM_WINDOWS`: **[OWNER TO SELECT]**
- `RD_RELEASE_WINDOWS`: **[OWNER TO SELECT]**
- `RD_RESET_SCOPE`: **[trip | lagos_day — OWNER TO SELECT]**
- Inclusive equality and GPS-gap reset semantics: **[OWNER ACKNOWLEDGE]**

### 3B. Complete only for option B

- `CSB_BUDGET_S`: **[OWNER TO SELECT]**
- `CSB_SCOPE`: **[trip | lagos_day — OWNER TO SELECT]**
- Inclusive budget equality and retained-spend gap semantics:
  **[OWNER ACKNOWLEDGE]**

### 3C. Complete only for option C

- `HOLD_SECONDS_TRIGGER_S`: **[OWNER TO SELECT]**
- `HOLD_EPISODE_TRIGGER`: **[OWNER TO SELECT]**
- `HOLD_TRIGGER_LOGIC`: **[any | all — OWNER TO SELECT]**
- `HOLD_SCOPE`: **[trip | lagos_day — OWNER TO SELECT]**
- `FRAUD_ASSESSMENT_VERSION`: **[OWNER TO SELECT]**
- Acknowledge that FND-02B cannot close RM2 until MNY-08A/B is integrated:
  **[OWNER ACKNOWLEDGE]**

### 4. Required independent sign-off

- Exact packet commit SHA: **[FABLE TO INSERT]**
- Product reviewer / date / verdict: **[INDEPENDENT REVIEW REQUIRED]**
- Money reviewer / date / verdict: **[INDEPENDENT REVIEW REQUIRED]**
- Any requested fixture correction: **[NONE | DETAILS]**

## Decision-log-ready row

Fable may insert the next immutable D-number only after the owner selection and
independent product/money review. Replace every bracketed field; do not retain
unused option parameters.

```markdown
| D[NN] | [DATE] | **Stationary sub-window policy selected for payout_v3 (FND-02A/RM2).** The owner selected **Option [A rolling displacement | B cumulative sub-window budget | C explicit fraud deferral/hold]**. Common immutable eligibility values: stationary radius `[SR_M] m`, confirmed-stay window `[SW_S] s`, one-scope grace `[SG_S] s`, maximum accuracy `[ACC_M] m`, teleport boundary `[TP_KMH] km/h`, and GPS-gap boundary `[GAP_S] s`. Selected option values: [INSERT ONLY THE SELECTED OPTION'S COMPLETE PARAMETERS, SCOPE, EQUALITY AND GAP SEMANTICS]. The immutable eligibility revision is `[ELIGIBILITY_REVISION]`, effective at `[EFFECTIVE_AT]` for **new acceptances only**; previously accepted work and payout_v1/v2 history retain their bound revision. Fixture authority: `tests/fnd_02a_stationary_policy/fixtures/` at commit `[PACKET_SHA]`, independently reviewed `[PRODUCT_REVIEW_REF]` and `[MONEY_REVIEW_REF]`. | Project owner, [DATE/SOURCE] | D14 requires this change in what counts as payable to ship only through `payout_v3` under MNY-06B. FND-02B must add the selected typed parameters, immutable revision binding, fingerprint fields, interval/explanation outputs and the exact fixture regressions. [IF C: No financially effective implementation or RM2 closure exists until MNY-08A/B's current assessment and authoritative hold predicate are integrated; unresolved/error/stale evidence remains held.] Historical calculations are never repriced except through an approved MNY-06C maker-checker correction order. |
```

## Smallest FND-02B production write surface after selection

This packet authorizes **none** of these writes. It records the minimum surface
Fable should plan once `EXT-RM2-POLICY` is genuinely cleared.

| Area | Option A | Option B | Option C |
|---|---|---|---|
| `app/services/payout_eligibility.py` | Add rolling-window displacement state, inclusive boundary, confirmation/release runs, selected reset scope and `stationary_rolling_displacement` reason. Preserve all existing precedence and partition invariants. | Add chronological short-candidate accumulation, selected scope and `stationary_subwindow_budget_exceeded` reason. Keep existing long-stay grace unchanged. | At most emit typed, versioned stationary-pattern **evidence**. Do not create a local release predicate or relabel held time as excluded. |
| `EligibilityParams` / `as_metadata()` | Add RD fields and reset/gap semantics. | Add cumulative budget/scope/gap semantics. | Add evidence-trigger metadata only if MNY-08A owns/consumes it; avoid a second parameter authority. |
| `app/core/config.py` | Add typed `PAYOUT_ELIGIBILITY_*` fallback settings for every selected RD field, with no defaults invented by implementation. | Add typed cumulative-budget/scope settings, with no invented values. | Any evidence settings belong to the single fraud-assessment configuration/revision chosen with MNY-08A; no shadow config. |
| `app/services/payouts.py` overlay and fingerprint | Extend allowlist, effective overlay resolution and `EligibilityParams.as_metadata()` fingerprint. | Same for budget/scope. | Payout fingerprint references the current assessment/evidence revision and shared hold predicate; it must not decide review state itself. |
| Per-interval / driver explanation | Store tier plus rolling stationary reason and parameter revision. | Store tier plus spent/remaining budget reason and revision. | Show sanitized hold reason/status from MNY-08C; internal thresholds/raw route evidence remain private. |
| Automated regressions | Port every shared fixture, cadence/equality/jitter case, Lagos-day split and partition invariant into production classifier/integration tests. | Same, including no reset on hop/area/window/gap and inclusive budget equality. | Same evidence fixtures plus MNY-08A/B transition, race, stale/error and release-consumer tests. |

## Interaction with MNY-06A/B/C

- **MNY-06A — immutable revisions:** the selected complete parameter set must be
  an immutable, effective-dated eligibility revision with value-complete audit.
  Existing mutable rule overlays are not sufficient authority for real use.
- **MNY-06B — assignment/trip binding and payout_v3:** accepted terms freeze
  base/premium rates, cap, zones **and this eligibility revision**. Each interval
  records tier/reason; the input fingerprint includes every selected parameter,
  scope/equality/gap semantic and revision ID. `EXT-RM2-POLICY` must remain
  fail-closed until the owner row exists.
- **MNY-06C — maker-checker corrections:** later policy changes create a new
  revision for new acceptances. Correcting historical work requires a projected
  correction order, separate approver, stale-projection re-review and
  append-only delta; no silent recomputation or payout_v2 mutation.
- **Integration serialization:** FND-02B and MNY-06 share
  `payout_eligibility.py`, payout-rule metadata/overlay/fingerprint and driver
  explanation surfaces. Fable should serialize the production implementation
  against MNY-06A/B/C unless an exact disjoint file/domain manifest is proven.

## Explicit non-decisions

- No option is selected.
- No threshold, duration, radius, budget, count, rate or effective timestamp is
  recommended or adopted.
- No existing deployment default is promoted to owner authority.
- No payout formula or historical row is changed.
- No physical-driver or pilot behavior is authorized.
- No claim is made that FND-02A or FND-02B is complete.
