# FND-02A/B stationary policy evidence

This directory records the owner-selected Option A fixture contract adapted
from candidate `40f73026eaf49bd04ce4f75a0cd620fb434f64c8`. Production proofs live in
`tests/test_payout_eligibility.py`, `tests/test_payouts_v4.py`, and
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
teleport threshold, and 120-second maximum ping gap. D80 retires payout v1-v3. Current `payout_v4` daily-rate eligibility uses the
complete frozen stationary policy; missing or incomplete accepted authority
fails closed. Historical hourly-engine comparisons above are fixture context.
