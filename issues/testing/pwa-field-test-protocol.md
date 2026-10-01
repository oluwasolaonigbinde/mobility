# PWA field-test protocol: real phones on real Abuja routes

For the owner to run. It tests whether the current screen-on web app (the driver
PWA) records a normal day's driving well enough to pay by distance (D39: 70 miles a
day). It is the evidence for decision D-a (keep the PWA, or build a native or
background-tracking app). Nothing in this protocol changes the product.

## 1. What you need

**Phones** (record make, model, OS version, browser version and battery health for
each):
- 2–3 Android phones: at least one mid-range (for example Tecno, Infinix or Samsung
  A-series) and, if possible, one older or low-memory phone.
- 1 iPhone on a current iOS.

**Accounts and setup**
- One synthetic test driver per phone on a test or staging deployment, never a real
  driver's account. Each needs an approved car and an active campaign assignment so
  that Start is allowed.
- Install the app to the home screen on every phone (Android: Chrome menu → *Install
  app* / *Add to Home screen*; iPhone: Safari → Share → *Add to Home Screen*). Open it
  from the home-screen icon, not a browser tab.
- Allow location "While using the app" (Android) / "While Using" (iPhone) and precise
  location. Leave battery saver **off** unless a run says otherwise.
- A power bank and cable for each phone, a car phone mount, and a second phone or
  watch for timing.

**People**: one driver per car and, ideally, one passenger to take notes and
screenshots so the driver never touches the phone while moving.

## 2. Before each run

1. Charge to 100% and unplug (unless the run is a charging run).
2. Close all other apps. Note the time, the start battery % and whether the phone
   feels warm.
3. Open the driver app → **Phone check** (currently *Capabilities*, the
   "Production PWA capability probe"). Run each check (storage and queue, Web Locks,
   screen wake lock, session, foreground location). Tap **Copy** and paste the
   redacted report into the run log. It contains no coordinates, trip IDs or tokens.
4. Open **Track**. Confirm the campaign shows and **Start** is available.

## 3. Runs

Drive each run on a real Abuja route with a mix of main roads and traffic (for
example Wuse → Garki → Central Area → Maitama, or Kubwa expressway). Aim for 45–60
minutes per run. Do the runs in this order on every phone.

| Run | What to do | What it shows |
| --- | --- | --- |
| A. Screen on (baseline) | Start a trip. Keep the app on screen the whole drive; the phone stays awake by itself (wake lock). End the trip at the destination. | Best-case recording. |
| B. Long drive | Same as A for at least 2 hours (or a whole shift), plugged into car power. | Wake lock holding, heat, memory. |
| C. Phone locks | Start a trip, then press the power button to lock the phone for 10 minutes, unlock, return to the app; repeat twice. | Whether recording stops while locked and recovers after. |
| D. Switch apps | Start a trip, then open Google Maps (navigation running) for 10 minutes, then Bolt/Uber driver app for 5 minutes, then return. | Whether switching to navigation or ride-hail apps loses distance. |
| E. Poor network | Start a trip, then switch to airplane mode for 5 minutes while still moving (or drive through a known weak-signal area), then back on. | Offline queue and upload after reconnect. |
| F. Battery saver | As A, with battery saver / Low Power Mode on. | OS throttling. |

Keep the second phone's timer for every event (lock, unlock, app switch, airplane
on/off) and write the times down to the minute.

## 4. What to capture per run

Copy this block into the run log for every run:

```
Run: A/B/C/D/E/F       Phone: <make model, OS, browser>
Driver account: <synthetic email>     Route: <from → to, roads>
Trip ID (from Track or the trip summary): <id>
Start time / end time (Nigeria time, WAT): <hh:mm> / <hh:mm>
Odometer or map distance driven (km): <n>
Battery % start / end:  <n> / <n>        Charging: yes/no
Heat (1 = cool, 2 = warm, 3 = hot to hold) at 15/30/60 min: <n/n/n>
Event times (lock/unlock, app switches, airplane on/off): <hh:mm ...>
What the app showed (errors, "recording paused", sync messages): <text>
Phone check report (before run): <pasted>
Screenshots: <Track at start, at each event, at end>
```

Measure the real distance independently (car trip meter, or a separate navigation app
recording on another phone) so the recorded distance can be compared with it.

## 5. Reading the result in the admin screens

1. Driver side, on the test phone: **Earnings** → the trip. Check that the trip
   shows, its times match the log, its review status, and the excluded time it
   lists (for example "GPS signal gaps").
2. Admin side, signed in as a Terrax Media admin on the same deployment:
   - **Fraud** (trip reviews): whether the trip raised a review (for example *Ping
     gap*, *Insufficient pings*, *Poor accuracy*) and its evidence. Gaps during a lock
     or app switch usually show here.
   - **Late trip evidence**: after an airplane-mode run, whether batches arrived late
     or were quarantined, and whether they were applied.
   - **Payouts**: the trip's row and its calculated amount.
3. Recorded distance, valid pings, the longest gap between pings, stationary time and
   GPS accuracy have no admin page yet. Give the developer the trip IDs from the log;
   they read each one from `GET /api/v1/admin/trips/{trip_id}/analytics` and send you
   the figures.

For each run, write down:
- **Distance captured** = recorded km ÷ real km (target ≥ 95% for runs A and B).
- **Largest gap** in minutes and when it happened (does it match a lock or app
  switch?).
- **Reviews raised** and why.
- **Battery used per hour** and the highest heat score.

## 6. How to decide

- If runs A and B capture ≥ 95% and C–E recover without losing more than the time
  the app was away, the screen-on PWA is workable for the pilot with the driver
  instruction "keep Cardvert open on screen".
- If C or D lose most of their distance (drivers will lock phones and use Maps or
  Bolt), or phones overheat or drain too fast on B, that is the evidence for a
  native or background-tracking app (D-a revisit).
- Record the result, the phone list and the run logs in
  `issues/testing/pwa-field-test-results-<date>.md`, and give the owner a one-line
  recommendation.

## 7. Safety and privacy

- The driver never handles the phone while the car is moving; the passenger does.
- Use synthetic test accounts only. Don't share screenshots that show real people,
  number plates other than the test cars, or home addresses.
- Stop a run if a phone becomes too hot to hold.
