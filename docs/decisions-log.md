# Decisions Log — Mobility AdTech Platform

Confirmed product decisions, in the order they were made. Each entry notes
the build implication so nothing gets re-litigated or silently forgotten.
Newer entries supersede older ones where they conflict.

| # | Date | Decision | Source | Build implication |
|---|------|----------|--------|-------------------|
| D1 | Jul 2026 | **Onboarding is operator-led** — no public self-serve advertiser signup; admin creates users/orgs. | Backend design + questionnaire v1 | Admin "create user + org" flow (built, F5). Driver self-registration is a separate open question (Q13 in questionnaire v2). |
| D2 | Jul 2026 | **Driver pay = fixed naira amount per hour**, not a revenue share and not per-km rate cards. | Somto, via refined questionnaire (Q4 preamble) | Payout engine reworked: hourly rate × verified payable time replaces the per-km + zone-bonus + impression components. Zones shift from pay-bonuses to campaign rules & analytics inputs. Rate flexibility (one rate vs per-campaign override) still open → Q4. |
| D3 | Jul 2026 | **MVP tracking = screen-on tracking** with the installable driver app (phone mounted, app visible — navigation-app posture). Native app with true background tracking comes after the pilot; identical backend contract. | Somto, via OJ | No native-app build blocks the pilot. Driver UX copy says "keep the app on screen while driving". Q10's Start/End session model carries over unchanged to the native app later. |
| D4 | Jul 2026 | **Payable hours are capped** — each campaign sets a max payable hours per driver per day (admin-configured, shown in the driver's offer before acceptance). | Somto, via OJ | Earnings calculation gains a per-campaign daily cap; driver app shows progress toward the cap; campaign cost becomes quotable (cap × rate × vehicles × days). |
| D5 | Jul 2026 | **Fraud posture = hold-and-review**, not automatic permanent pay discounts: seriously flagged sessions hold earnings until admin review; repeat/severe flags can pause new assignments; drivers get the reason and a dispute channel. Thresholds stay configurable, tuned with pilot data. | Refined questionnaire (Q21 rule, pending formal approval) | Fraud-review workflow (acknowledge/resolve endpoints) becomes a required backend addition. The old severity multipliers (0.9/0.7/0.25) become secondary/configurable rather than the primary mechanism. |
| D6 | Jul 2026 | **Offline-to-online retargeting enters the MVP** (shape still open → Q11: dashboard-only vs anonymised exportable segments vs direct platform integrations). | Refined questionnaire | New MVP workstream once Q11 lands: audience aggregation model + export/activation flow + privacy controls. Was "future layer" in the original brief. |
| D7 | Jul 2026 | **In-platform creative upload is an MVP rule** (pending approval, Q18 rule): advertisers upload files; admin approves/rejects before production. | Refined questionnaire | File upload + storage + review queue becomes a backend/frontend addition (was deferred in v1 questionnaire). |

## Open questions

Everything else lives in **Product Direction Questionnaire v2**
(`docs/Mobility_Product_Direction_Questionnaire_v2.docx`) — 34 questions:
Q1–14 core build direction, Q15–24 MVP rules to approve/adjust,
Q25–34 pilot/launch. As Somto answers, entries move from there into this log.

## How to use this log

- When an answer arrives, add a row with source "Somto, {date}".
- When a decision changes, add a new row that supersedes it — never edit
  history.
- Every build phase that implements a decision references its D-number in
  the commit message.
