**MOBILITY ADTECH PLATFORM**

**Product Direction Questionnaire**

Decisions we need from you before launch build-out

**Prepared for:** Somto

**Prepared by:** OJ Solutions

**Date:** July 2026

The platform is now functionally complete against the original product
brief: the advertiser portal (campaigns, geographic targeting,
attribution reporting, exposure heatmaps), the driver app (installable
on a phone, live GPS trip tracking, jobs and earnings), and the
operations console (onboarding, fleet, fraud monitoring, payout
processing) are all built, tested end to end, and running against the
full backend.

Before we push toward launch, there is a set of decisions that only you
can make. These are not technical questions --- the system can be built
in any of the directions below. They are business and product policy
choices, and several of them are wired into how money moves, so changing
them after launch is far more expensive than deciding them now. Where a
question has a sensible industry-standard answer, we have marked a
proposed default --- if you are happy with it, simply tick it and move
on.

How to respond: reply inline under each question, or mark "default OK".
We will then fold every answer into the build plan and confirm anything
that changes scope before we build it.

A. Commercial model --- how the platform earns

*Today the system measures campaign delivery precisely (verified
kilometres, estimated impressions, exposure quality) and tracks cost
precisely (driver payouts). What it deliberately does not yet fix is the
commercial layer between the two --- that is your pricing strategy.*

1\. What does an advertiser actually pay for?

> **Why it matters:** This defines invoicing, reporting and how sales
> pitches the product.

- Flat rate per vehicle per month (classic transit media --- simple to
  sell and invoice; impression reports become proof of value)

- Performance pricing --- CPM on estimated impressions (maximally
  aligned with the measurement story, but revenue varies with traffic
  and requires advertisers to trust the estimate from day one)

- Hybrid --- flat base per vehicle plus a performance bonus component

> **Proposed default:** Flat per-vehicle-per-month with impression
> reporting as value proof, moving toward hybrid once the market trusts
> the numbers.
>
> **Your decision:** ---

2\. How is advertiser money collected?

> **Why it matters:** Determines whether we build payment-gateway
> integration now or launch with invoicing.

- Prepaid: campaign is funded before it goes live (bank transfer,
  manually confirmed by ops)

- Prepaid via gateway (Paystack / Flutterwave) with automatic
  confirmation

- Postpaid invoicing (e.g. net-30) for established brands

> **Proposed default:** Prepaid by bank transfer at launch, gateway
> integration as a fast follow.
>
> **Your decision:** ---

3\. Is the driver payout budget a fixed share of what the advertiser
pays?

> **Why it matters:** Drivers earn from configurable rate cards (per-km,
> zone bonuses, caps). Whether those rates are derived from campaign
> price (e.g. drivers get 40%) or set independently changes how ops
> prices every deal --- and whether the margin is protected
> automatically or by discipline.
>
> **Proposed default:** Independent rate cards at launch, reviewed
> against margin monthly; automate a fixed-share rule later if deal
> volume grows.
>
> **Your decision:** ---

4\. VAT and invoicing details

> **Why it matters:** Invoices need to state VAT correctly from the
> first campaign.

- Prices quoted VAT-inclusive or exclusive?

- Registered entity name, TIN and invoice format requirements

> **Your decision:** ---

B. Campaign lifecycle --- who controls what goes live

5\. Should campaigns require operations approval before going live?

> **Why it matters:** Right now an advertiser can create and launch a
> campaign without review. On a marketplace that puts brands on physical
> vehicles, most operators insert an approval gate (content check,
> payment confirmed, fleet availability) before anything goes live.
>
> **Proposed default:** Yes --- advertiser submits, ops approves to
> launch. We will add the approval step.
>
> **Your decision:** ---

6\. What is the content policy --- which advertiser categories are
restricted or refused?

> **Why it matters:** Betting, alcohol, political, religious and
> pharmaceutical advertising each carry regulatory and driver-acceptance
> implications (a driver may decline to carry certain content on their
> own car --- do they get that right formally?). ARCON vetting also
> applies to outdoor creative in Nigeria.
>
> **Proposed default:** You provide the category policy; we enforce it
> in the approval step. Drivers get an explicit right to decline a
> campaign at offer stage (already how the offer/accept flow works).
>
> **Your decision:** ---

7\. What happens when a campaign hits its budget?

> **Why it matters:** Budgets are recorded today but nothing stops
> delivery when spend reaches the cap --- enforcement is a policy
> choice: hard stop, alert-and-continue, or ops discretion.
>
> **Proposed default:** Auto-pause at 100% of budget with alerts to
> advertiser and ops at 80%.
>
> **Your decision:** ---

8\. Can a live campaign be edited (zones, budget, dates) --- and by
whom?

> **Why it matters:** Mid-flight changes affect driver earnings
> expectations and reporting continuity.
>
> **Proposed default:** Zones and budget increases allowed while live;
> decreases and date changes require ops approval.
>
> **Your decision:** ---

C. Creative and physical production

9\. Who produces and installs the physical vehicle branding?

> **Why it matters:** The platform tracks campaigns digitally, but
> someone has to print and fit wraps/panels. This is an operations
> business in itself --- and it determines campaign lead times and
> pricing.

- Platform-managed: you contract printers/installers, cost built into
  campaign price (full control of quality and timing)

- Advertiser-supplied: they arrange production; platform only verifies
  installation

> **Proposed default:** Platform-managed, with installation photo
> evidence uploaded before a vehicle is activated on a campaign.
>
> **Your decision:** ---

10\. Should campaign activation on each vehicle require photo
verification of the installed creative?

> **Why it matters:** This is the strongest trust signal you can offer
> advertisers ("here is your brand on each car"), and the cheapest fraud
> control on the physical side.
>
> **Proposed default:** Yes --- ops verifies an installation photo per
> vehicle before that vehicle starts earning.
>
> **Your decision:** ---

11\. Do advertisers need to upload creative files into the platform at
launch?

> **Why it matters:** Today creatives are registered with a name, type,
> placement and a link. Direct file upload (with storage and virus
> scanning) is a build item --- worth it if advertisers self-serve,
> unnecessary if ops handles files by email during the pilot.
>
> **Proposed default:** Pilot without in-app upload; add it with the
> self-serve tier.
>
> **Your decision:** ---

D. Drivers and fleet

12\. What does driver onboarding require before a driver can carry
campaigns?

> **Why it matters:** The system currently records licence number, city
> and vehicle details. The depth of KYC is your risk decision.

- Documents: driver's licence, vehicle registration, proof of insurance,
  passport photo --- which are mandatory?

- Identity: NIN and/or BVN verification (BVN also unlocks smoother
  payouts)

- Vehicle inspection: physical or photo-based, once or recurring?

> **Proposed default:** Licence + vehicle registration + NIN + photo set
> at signup; quarterly photo re-verification of vehicle condition.
>
> **Your decision:** ---

13\. What is the drivers' legal relationship to the platform?

> **Why it matters:** Independent contractor vs anything resembling
> employment has tax, insurance and liability consequences. The driver
> agreement (who insures the vehicle and wrap, liability for accidents
> while carrying branding) needs a lawyer's pass before the first real
> campaign.
>
> **Proposed default:** Independent contractors under a signed digital
> agreement; your counsel drafts, we implement acceptance in onboarding.
>
> **Your decision:** ---

14\. Which vehicles qualify?

> **Why it matters:** Types (private cars, ride-hail only, kekys/buses
> later?), maximum vehicle age, condition standards --- this defines the
> supply side and what advertisers are promised.
>
> **Proposed default:** Pilot with cars affiliated to ride-hail
> platforms (predictable daily mileage), expand categories later.
>
> **Your decision:** ---

15\. Can a vehicle carry more than one campaign at once --- and how is
competitor separation handled?

> **Why it matters:** One car, one brand is simple and premium. Multiple
> placements per vehicle (e.g. doors vs rear screen) raise revenue per
> vehicle but need clear rules --- and two competing brands (e.g. two
> telecoms) must never share a car. This decision shapes assignment
> logic.
>
> **Proposed default:** One campaign per vehicle at a time for the
> pilot; competitor-category separation enforced by ops at assignment.
>
> **Your decision:** ---

16\. What activity is required of a driver on a campaign?

> **Why it matters:** Advertisers pay for presence on the road. Without
> a floor (minimum tracked km or hours per week), a wrapped car can sit
> parked. The floor also defines when ops should deactivate an inactive
> assignment.
>
> **Proposed default:** Minimum 100 tracked km/week per active campaign;
> auto-flag to ops after 7 idle days.
>
> **Your decision:** ---

17\. How does the platform talk to drivers?

> **Why it matters:** Offers, payment confirmations and trip issues need
> a channel drivers actually see. In this market that usually means
> WhatsApp/SMS alongside the app --- notification infrastructure is a
> build item, so channel choice affects scope.
>
> **Proposed default:** Launch: in-app + WhatsApp broadcast run by ops.
> Automated SMS/WhatsApp notifications as a fast follow.
>
> **Your decision:** ---

E. Tracking and data

18\. Is foreground app tracking acceptable for the pilot, with the
native app as phase two?

> **Why it matters:** The driver app tracks while it is open on screen
> (like a navigation app in a phone mount). True background tracking
> requires the native mobile app --- a separate build the brief
> anticipates (Flutter/React Native). This is a sequencing and budget
> decision, not a technical blocker: the backend is identical for both.
>
> **Proposed default:** Pilot on the current app with mount-and-track
> behaviour; commission the native app once the pilot proves unit
> economics.
>
> **Your decision:** ---

19\. How long is raw GPS data retained?

> **Why it matters:** Location traces are personal data under the NDPR.
> Raw pings are only needed until analytics are computed and disputes
> are settled; aggregated statistics carry the business value long-term.
>
> **Proposed default:** Raw pings retained 12 months, then deleted;
> aggregated analytics retained indefinitely.
>
> **Your decision:** ---

20\. Confirm: drivers are tracked only during trips they explicitly
start.

> **Why it matters:** This is how it is built --- tracking begins when
> the driver taps Start and ends when they tap End. We recommend keeping
> it that way and stating it prominently in driver terms; it is both an
> NDPR posture and a driver-trust selling point. Flagging it so it is a
> decision on record, not an accident of implementation.
>
> **Proposed default:** Confirmed --- trip-scoped tracking only.
>
> **Your decision:** ---

F. Fraud and trust policy

*The detection engine already catches GPS spoofing, impossible speeds,
route looping, stationary trips and exclusion-zone farming, and
automatically discounts pay on flagged trips. What needs your decision
is the human policy around it.*

21\. What are the consequences of fraud beyond discounted pay?

> **Why it matters:** Today a flagged trip earns less (configurable
> multipliers by severity). A repeat offender currently faces no
> escalation. A strikes policy needs your sign-off because it removes
> people's income.
>
> **Proposed default:** Three high-severity flags in 30 days → automatic
> suspension pending ops review; documented appeal channel. (Requires a
> small backend addition for flag review workflow --- scoped and ready.)
>
> **Your decision:** ---

22\. Should the minimum-payout-per-trip floor apply even to heavily
flagged trips?

> **Why it matters:** In live testing we confirmed an edge case: a trip
> whose movement was fully discounted by the fraud engine still received
> the campaign's minimum payout. That may be intended generosity
> (drivers never earn zero for showing up) --- or a loophole someone
> will farm with fake trips. It is exactly the kind of rule that is
> cheap to change now.
>
> **Proposed default:** Minimum floor applies only to trips with no open
> fraud flags.
>
> **Your decision:** ---

23\. Confirm the fraud-discount multipliers and speed thresholds.

> **Why it matters:** Current defaults: low-severity flags pay 90%,
> medium 70%, high 25%; movement above 198 km/h sustained is treated as
> impossible. These are all tunable per campaign --- we need your
> baseline.
>
> **Proposed default:** Keep current defaults for the pilot; revisit
> with real data after month one.
>
> **Your decision:** ---

G. Driver payouts --- money out

24\. When does a driver's pending balance become withdrawable?

> **Why it matters:** Earnings post as "pending" the moment a trip is
> processed. The release rule (instant, weekly batch, after campaign
> week ends, T+7 to allow fraud review) is a cash-flow and trust
> decision.
>
> **Proposed default:** Weekly release, 7 days after the trip (leaves
> room for fraud review), paid every Friday.
>
> **Your decision:** ---

25\. How does cash physically reach drivers?

> **Why it matters:** There is no disbursement integration yet --- it is
> a scoped build item. Options: Paystack/Flutterwave transfer APIs
> (automated, needs driver bank details + BVN), OPay/PalmPay wallets, or
> manual bank transfers by ops at pilot scale. Also: minimum withdrawal
> amount, and who absorbs transfer fees.
>
> **Proposed default:** Pilot: ops-run weekly bank transfers from the
> ledger report. Automate via Paystack Transfers as volume grows. Fees
> borne by platform; no minimum at pilot.
>
> **Your decision:** ---

26\. Who can adjust a driver's ledger, and what is the dispute process?

> **Why it matters:** The ledger supports adjustments and reversals with
> a full audit trail. Policy needed: who has adjustment rights, what the
> driver-facing dispute channel is, and the response SLA.
>
> **Proposed default:** Adjustments restricted to named ops admins;
> disputes via WhatsApp support line, 48-hour response target.
>
> **Your decision:** ---

H. Brand, compliance and launch

27\. Product name and brand

> **Why it matters:** "Vantage" is our working name throughout the
> build. The real name affects the domain, the driver app's install name
> and icon, and every advertiser-facing report. Cheap to change today;
> annoying after drivers have the app installed.
>
> **Your decision:** ---

28\. Launch city and pilot shape

> **Why it matters:** One city focus determines traffic-model
> calibration, installer logistics and permits. Useful pilot targets:
> number of vehicles, number of paying advertisers, duration before
> scale decision.
>
> **Proposed default:** Single-city pilot (your call --- Abuja or
> Lagos), 25--50 vehicles, 2--3 anchor advertisers, 8--12 weeks.
>
> **Your decision:** ---

29\. Outdoor-advertising permits: who owns them?

> **Why it matters:** Vehicle branding in Nigeria falls under state
> signage regulators (LASAA in Lagos, the FCT outdoor agency in Abuja,
> equivalents elsewhere). Mobile advert permits are typically
> per-vehicle, annual. Someone must own acquisition and cost ---
> platform (built into pricing) or advertiser. This can gate the launch
> date, so it is worth starting early.
>
> **Proposed default:** Platform obtains permits, cost passed through in
> campaign pricing.
>
> **Your decision:** ---

30\. NDPR compliance ownership

> **Why it matters:** The platform processes drivers' location data and
> advertisers' business data. Needed from your side: privacy policy and
> driver-consent wording (your counsel), a named data-protection
> contact, and confirmation of the retention rule from section E. We
> implement the consent screens and enforce the retention automatically.
>
> **Your decision:** ---

31\. Infrastructure ownership and budget

> **Why it matters:** Cloud account (recommended: opened in your
> company's name, we operate it), domain, and two small recurring
> choices: map-tile provider (from \~free tiers to \~\$50+/month
> depending on traffic) and hosting budget ceiling. Everything is
> containerised and cloud-agnostic (AWS/GCP per the brief) --- we need
> the account and the ceiling.
>
> **Proposed default:** Client-owned cloud account with our team as
> operators; MapTiler for map tiles at launch.
>
> **Your decision:** ---

32\. Who runs day-to-day operations at launch?

> **Why it matters:** The ops console handles onboarding, approvals,
> fraud review and payouts --- but someone has to staff it. Options:
> your team (we train them), or OJ Solutions operates it under a support
> retainer for the pilot.
>
> **Proposed default:** We operate through the pilot and train your ops
> hire in parallel.
>
> **Your decision:** ---

Where this goes next

None of these questions block current work --- we continue hardening and
preparing launch infrastructure while you consider them. But every
answer above either changes what we build next or locks in a rule that
money will flow through, so the sooner they are settled, the less we
ever build twice.

Suggested next step: a working session to walk through this list
together --- most questions take a minute each once discussed. We will
circulate the decisions log afterwards so there is one written source of
truth for how the product behaves.
