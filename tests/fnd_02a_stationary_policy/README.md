# FND-02A/B stationary policy evidence

This directory records the owner-selected Option A fixture contract adapted
from candidate `40f73026eaf49bd04ce4f75a0cd620fb434f64c8`. Production proofs live in
`tests/test_payout_eligibility.py`, `tests/test_payouts_v3.py`, and
`tests/test_payout_corrections.py`; this file is evidence context, not runtime
configuration.

`stationary-rd-v1` uses contiguous `[start,end)` 120-second windows and a
120-second stride, anchored at trip start or the first accepted-quality ping
after a GPS-gap reset. Endpoint coordinates are linearly interpolated only
through valid contiguous evidence. Net displacement `<= 25m` is stationary.
Two adjacent stationary windows confirm and backdate; one moving window
releases and backdates. Contamination resets only an unconfirmed streak and
holds an active stationary state. Rolling and legacy 200m/300s stationary
ranges share one chronological 240-second trip grace.

The complete accepted snapshot also freezes 75m maximum accuracy, 180km/h
teleport threshold, and 120-second maximum ping gap. `payout_v2` remains on the
legacy classifier. Only a complete frozen `payout_v3` binding carrying this
marker activates the rolling detector; old or incomplete markers fail closed.
