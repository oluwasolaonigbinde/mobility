# FND-02A fixture corpus and execution

## Shared executable fixture corpus

`fixtures/*.json` stores one timeline per case and, for **every fixture and every
option**, explicit parameterized text for payable, excluded, held, review and
explanation outcomes. The evaluator normalizes each timeline into elapsed-time
segments; it never relies on ping count as money evidence.

| Fixture | Option A | Option B | Option C |
|---|---|---|---|
| `slow_creeping_lagos_traffic` | Pays when rolling displacement is above the selected threshold. | Pays through budget; can expose honest-traffic underpayment after budget. | Gross-payable; may be held if selected evidence trigger fires. |
| `stop_4m59_hop_repeat_two_hours` | Confirmed low-displacement stop windows become stationary after one shared grace. | Hops do not replenish budget; candidate time above budget is excluded. | Entire payable scope is held after trigger; cannot ship before MNY-08A/B. |
| `single_long_parked_stay` | Existing one-grace long-stay behavior. | Existing one-grace long-stay behavior; no sub-window budget. | Existing long-stay behavior; no duplicate short-pattern hold. |
| `genuine_brief_stops` | Pays where the rolling window still shows movement. | Pays while combined brief stops remain within budget. | Holds only if owner thresholds intentionally reach this honest case. |
| `out_of_area_parked_does_not_reset` | Area reason wins but detector/grace does not reset. | Area reason wins; no fresh budget/grace on re-entry. | Area reason wins and cannot erase evidence. |
| `gps_gap_position_unknown` | Gap excluded and rolling detector resets. | Gap excluded; spent budget retained. | Gap excluded; prior evidence retained without position inference. |
| `signal_precedence_low_null_teleport` | Existing low-accuracy/teleport reasons win. | Invalid signal does not consume new budget evidence. | Invalid signal does not create hold evidence. |
| `campaign_window_boundary_no_reset` | Window reason wins; detector/grace continues. | Window reason wins; spent budget continues. | Out-of-window time cannot earn but can retain valid evidence. |
| `africa_lagos_midnight_boundary` | State carries only with trip scope; day scope resets exactly at Lagos midnight. | Budget carries only with trip scope. | Evidence/hold carries only with trip scope. |
| `ping_cadence_dense` / `ping_cadence_sparse` | Same normalized elapsed/displacement outcome. | Same elapsed-time budget outcome. | Same elapsed-time/episode evidence outcome. |
| `boundary_equality` | Equal displacement is stationary. | Exactly-at-budget remains payable. | Exactly-at-trigger holds. |
| `jitter_around_rolling_boundary` | Exact confirmation/release counts determine the outcome. | Jitter labels do not alter elapsed budget. | Pattern is review evidence only. |
| `mixed_partition_and_money_expression` | Verifies one-reason partition and symbolic base/premium money. | Same invariant with budget reason. | Hold remains a payable overlay, never a third partition. |

## Running the evidence

From the repository root:

```bash
pytest -q tests/fnd_02a_stationary_policy
python tests/fnd_02a_stationary_policy/run_evaluator.py --list-fixtures
```

After an owner selection, copy the corresponding template outside the
repository, fill every placeholder, and run for one or all fixtures:

```bash
python tests/fnd_02a_stationary_policy/run_evaluator.py \
  --option A \
  --params /path/to/owner-approved-option-a.json

python tests/fnd_02a_stationary_policy/run_evaluator.py \
  --option B \
  --params /path/to/owner-approved-option-b.json \
  --fixture stop_4m59_hop_repeat_two_hours
```

The templates are intentionally non-runnable. Missing/null/placeholder values
raise `UnsetPolicyError`. Option C additionally raises
`DependencyUnavailableError` while `hold_infrastructure_ready` is false.

The unit suite creates algebraic witness values from fixture durations solely
to exercise evaluator branches. Those values are **not** candidate thresholds,
defaults or recommendations and must never be copied into authority docs.

