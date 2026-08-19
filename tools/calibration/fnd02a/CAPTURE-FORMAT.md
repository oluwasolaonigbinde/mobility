# FND-02A Option-A calibration — capture format (P1/P2 corpora)

Owner-authorized collection program (19 Aug 2026). Real physical traces only:
synthetic fixtures must NEVER enter these corpora (P4 evidence rule).

## One CSV file per session, UTF-8, header row required

```
session_id,corpus,environment,device_model,recorded_at,latitude,longitude,accuracy_m
P1-S01,parked,street_canyon,Pixel-7,2026-08-25T09:00:00+01:00,9.057812,7.489034,18.4
```

| Column | Rule |
| --- | --- |
| session_id | `P1-Snn` (parked) or `P2-Snn` (congestion); unique per session |
| corpus | `parked` or `congestion` |
| environment | parked: `open_sky` / `street_canyon` / `under_bridge`; congestion: named road segment slug |
| device_model | free text, consistent per device |
| recorded_at | RFC3339 with offset, device clock, strictly increasing per session |
| latitude/longitude | WGS84 decimal degrees, full precision |
| accuracy_m | reported horizontal accuracy; blank only if the platform gives none |

## Session rules (from the reviewed protocol)
- Cadence: production cadence 10–15 s; capture EVERY fix, including
  low-accuracy ones (the fix-poor/C5 measurement needs them).
- P1 parked: engine off, phone mounted, vehicle stationary; ≥ 30 min/session;
  ≥ 10 sessions total spanning ≥ 3 device models and all 3 environments.
- P2 congestion: real Abuja peak-congestion driving; ≥ 20 min/session;
  ≥ 10 sessions across ≥ 3 distinct road segments; note the segment slug.
- No personal data beyond the operator's device coordinates during the
  session; no passenger/third-party capture; files named
  `<session_id>_<device_model>.csv`.

## Delivery
Zip all CSVs + a manifest line per session (who captured, where, when,
device) and hand to the controller. The controller runs
`compute_calibration.py`, produces the P3 acceptance report, and packages
P4 evidence for the decision row.
