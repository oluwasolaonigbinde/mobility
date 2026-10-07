# Cardvert development data and go-live decisions

1. Restore legal/privacy protections for GPS, ID collection and advertiser results before real users
2. Restore overlap/differencing protection for advertiser analytics

Identical repeat views reveal nothing new. Narrowly differing date windows are the risk to address when restoring protection. Query history and all aggregation limits remain recorded/enforced; no history reset enables ordinary navigation.

Removed controls: legal display/collection authorization and synthetic switches, disclosure/configuration/history approval references, live measurement authorization and report-method approval setting; dynamic advertiser report fallback; legal approval for aggregate CSV export. Reports display a frozen measurement snapshot; CSV/PDF publication uses that same snapshot.

Retained controls: organization membership and roles; aggregation vehicle/trip/day floors, contributor caps and resolution limits; disclosure query recording; report reproducibility, file integrity and conditional ROI inputs/method authority; person-level export rejection; storage/scanning/encryption; payment, payout and email provider controls; blocked live Meta/Google activation. `PRIVACY_LEGAL_APPROVAL_REFERENCE` remains only for actual ad-platform approval and DSR retention exceptions. `MEASUREMENT_ROI_METHOD_REFERENCE` remains for financial ROI, and the calculation method revision stays recorded on each run. Synthetic lineage fields remain where they describe source provenance and protect provider activation, without legal display authority switches.

Owner Batch 2 seed review corrections (REQ-097–REQ-103) were committed in `6879c95` after review and integrated into master. [Full CI](https://github.com/oluwasolaonigbinde/mobility/actions/runs/37433319087) on `b77945d` passed on 6 October 2026, including production build and the controlled coverage receipt. The earlier dated seed and preview receipts below remain historical evidence; this closure includes no application deployment.

## Client inputs to replace

No missing client answer is recorded as approved. These records are fictional and must be replaced before onboarding people or accepting real campaigns.

| Temporary input | Current value and location | Replacing answer |
| --- | --- | --- |
| Installation upload roles | `driver,admin` in development compose and local/client-preview API and seed environment files | REQ-039 |
| Required installation photos | `front,back,left,right,close_up` in those files | REQ-039 |
| Installation evidence lifetime | `INSTALLATION_EVIDENCE_VALIDITY_HOURS=168` in those files | REQ-039 |
| Display challenge lifetime | `DISPLAY_PROOF_CHALLENGE_TTL_SECONDS=600` in those files | REQ-039 |
| Display proof lifetime | `DISPLAY_PROOF_VALIDITY_SECONDS=86400` in those files | REQ-039 |
| Higher-earner spot-check threshold | `EVIDENCE_HIGH_EARNER_THRESHOLD_NGN=50000` in those files | REQ-039 |
| Renewal lookback | `EVIDENCE_RENEWAL_LOOKBACK_DAYS=7` in those files | REQ-039 |
| Reply window | `EVIDENCE_CHALLENGE_RESPONSE_HOURS=24` in those files | REQ-039 |
| Invoice bank and number prefix | OPay, non-routable all-zero account `0000000000`, prefix `TXM`, held only in the seeded issuer profile and invoice snapshots | REQ-041, REQ-042 and REQ-052 |
| Reach estimates | Lagos weekday: 240 contacts/km, 5/minute, road factor 1.15; Abuja office: 180/km, 4/minute, road factor 1; Lagos weekend: 140/km, 4/minute, road factor 1; morning/midday/evening/night factors 1.2/1/1.3/0.7; target/bonus/exclusion factors 1.2/1.35/0 | EXT-REPORT-METHOD: calculation, labels and limitations |
| Report calculation inputs | Seeded traffic profiles, routes, impression estimates, exposure scores and frozen measurement snapshots; `impressions_v1` / `exposure_v1` identify the existing calculation | EXT-REPORT-METHOD; no revenue or conversion inputs are invented |
| Commercial records | Campaign budgets and quotations, including ₦1,000,000 portal campaigns, ₦3,000,000 scopes for the three additional report contributor histories, ₦1,800,000 for Ikeja Office Lunch, partial funding of ₦500,000, 7.5% VAT, five-vehicle scopes and zero production-cost components | EXT-COMMERCIAL-VALUES: approved quotation components, production prices and commissions; each real campaign's accepted quotation replaces its seeded snapshot |
| Complaint handling | Existing categories and fictional replies in the inventory below; no reply target is configured | REQ-020 and REQ-021 |
| Staff roster and contacts | The seven fictional Terrax staff in the inventory, their departmental actors and `@terraxmedia.com` addresses | Client's actual staff names, departments and sign-in details |
| Driver identity and payment details | Fictional people, plates, licence numbers and document cards; encrypted NIN `00000000000`, non-routable all-zero bank account `0000000000`, bank code `999` | Each applicant's actual documents, identity checks and verified exact bank-account version |
| Advertiser identity and contact details | Fictional business names and contact emails in the inventory | Each advertiser's actual company profile and authorized contact |
| Audience descriptions | Fictional area/time/category descriptions, website sources and aggregate CSV records | Advertiser's actual audience descriptions; legal and platform authority before any live platform delivery |

The eight installation values are an explicit owner-approved development/preview exception to the seed-only rule. They are present in `.env.example`, both API and worker sections of `docker-compose.yml`, and the local client-preview `api.env` / `seed.env`. Numeric code defaults and production/staging templates remain unset. The client preview was freshly seeded on 4 October with its existing c2ab2d9 application image preserved; no application-source deployment is claimed.

Budget warning/pause thresholds remain unset (EXT-BUDGET-POLICY). Automatic provider dispatch remains disabled; the illustrated run reserves credits but sends no transfers. The ₦10,000 / 70-mile proportional daily rate is the confirmed D43 rule, not an unanswered commercial placeholder. Terrax's legal name, address, TIN, RC, phone and email are confirmed REQ-019 facts and are retained.

Installation images are synthetic Marula Kitchens vehicle photographs reused across the fictional fleet. Applicant portraits and documents are illustrated cards. They exercise private storage, scanning and review flows; replace them with each person's own captured documents and each assigned vehicle's actual installation photos before real operations.

## Before real users

In addition to the first two restore items above: replace every unanswered input and fictional identity; confirm report and ROI methods; confirm budget and commercial rules; restore the collection/results operating policy and legal evidence; complete device, pilot and handover evidence; separately authorize provider credentials, transfers, messages and live advertising-platform delivery. None of the recorded staff reviews authorizes a real-world identity or payment.

The brief transfers ownership of the golden-path walkthrough from L2-3 to this change. No matching L2-3 golden-path row exists in the current tracked programme, so no package status was invented or advanced.

Other wording found outside the pages changed here, for owner follow-up: the coverage map's “disclosure-cleared” and “No production basemap configured”; the zone-insight method explanation; the tracker sentence about “every live safety check”; the report activity-score phrases “Synthetic provider-neutral operational index” and “Pilot calibration and live methodology approval remain absent”; and older operator readiness/closeout explanations. These are outside this batch's copy edits.

Finance: Hauwa Sani; Customer Service: Chiamaka Obi; Compliance: Olumide Fashola; Operations: Ibrahim Danjuma; CEO: Efe Okoro. These five logins are active. Temitope Ojo is the invited administrator; Aisha Garba is the suspended Operations login. Each stands in for an unnamed client staff member.

## Batch 2 verification — 2026-10-04

The integrated branch follows batch 1 (`5fdf6ec`) on the owner-selected `c2ab2d9` base. Receipts live in the sibling `batch2-review` folder outside Git. At this 4 October checkpoint, full CI, batch 2 commit, push and merge were not yet claimed. Batch 2 was subsequently committed as `6879c95`; the 6 October full-green integration and closure are recorded above and in requests.md. No new application deployment is claimed.

| Criterion | Actual evidence |
| --- | --- |
| B1 — every portal and applicable state | 261 successful visits (217 admin, 33 advertiser, 11 driver), plus 147 normalized screen/tab count checks; all linked entity details and work drawers opened. Campaigns span nine states; applications unsubmitted/pending/approved/rejected, complaints open/answered/resolved, invoices draft/issued/void, earnings held/released/paid. Three completed campaigns each have an issued report; Marula Kitchens — Wuse Lunch Rush is the only live campaign with its report in progress. WALKTHROUGH.md and its JSON receipts enumerate each screen, tab, section, count and captured state. |
| B2 — natural content and complete inventory | The single table below contains all persisted seeded names and human-written fields, frozen offer/financial text, filenames and artwork text. Eleven businesses own their campaigns and have their own contacts; Marula owns nine campaigns covering the requested states. Created/updated/submitted records span hours, days and weeks. Zone names and descriptions are specific; Apapa explains its heavy port traffic. Invented accounts/NIN use all-zero non-routable values; invented User.phone fields are unset. Confirmed Terrax contacts remain intact. The 28 unchanged images were visually inspected. |
| B3 — staff and actors | Five active departmental logins loaded nonempty work and notification panels; invited and suspended logins were refused. Reviews, complaint replies, corrections and payout actions use the corresponding staff actors. department-walk.json and auth-downloads.json retain actual access results. |
| B4 — ordinary golden path and money authority | Existing guarded services create accepted quotations, funding, reviewed artwork, payout_v4 offers/bindings, installation, activation, trips, frozen issued reports, available credit and an automatic reserved batch. Money problems/holds/earnings belong to active drivers. Specialist SQL checks find no line/ledger/calculation mismatch, payable active hold, funding overflow, tenant/actor error or provider attempt/event. All 29 final installation histories and managed-file stages follow acceptance → capture → upload/scan → submission → review → activation. v20-installation-chronology.txt and final test receipts cover the correction. |
| B5 — aggregation, integrity and reruns | Ordinary Marula overview clears unchanged floors/caps with eight vehicles, 36 trips and nine days; no over-cap metric. Coverage/heatmap and issued reports show nonempty figures. Fresh v20 FULL seed and FULL rerun retain all 18 required immutable table hashes and every business count; only legitimate audit rows grow (207→247) and subject resolutions (424→526). All 190 stored files match streamed bytes, size, SHA-256, MIME and clean scan state; six reports are ready. Final3 preview staging independently repeats those checks. |
| B6 — focused checks and real collection/downloads | All 35 selected backend seed/smoke cases passed across the initial run and corrected affected-case reruns; the final chronology/idempotence/rolling rerun passes three cases. Report scope/revocation passes; 55 unchanged copy/sparse-result tests pass. Build/types and scoped source checks pass. All 34 selected browser cases pass across the initial 28 and corrected six; the strict isolated account-setup write fixture is excluded. Eleven preview-isolation configuration cases pass. Twelve issued CSV/PDF downloads match hashes; the aggregate suggestions CSV is 1,561 bytes. Final GPS records two accepted pings and seals a complete V2 manifest; private ID upload/confirmation/clean scan/read succeeds. |

Seed verification commands: `python -m pytest tests/test_seed_demo.py tests/test_seed_smoke.py`; corrected five-case selection in seed-owner-fix-final-delta.txt; final three-case selection in seed-chronology-final-tests.txt. Other focused commands and exact results are in HANDOVER.md. The initial failures and diagnostic runs are retained and are not counted as passes.

## Client preview and browser-test isolation

The serving `cardvertpreview` database is freshly seeded from final3: 21 campaigns, 11 business organizations, six ready reports, all three completed campaigns with reports, exactly one live report in progress, 190 verified files, 29 valid installation histories and zero overlapping driver trips. Fifteen established account IDs and authentication records are preserved. The extension-preserving atomic restore was first tested on a disposable database; all recorded Tiger/Topology/PostGIS extension identities and table hashes remained unchanged. The serving API returns 21 admin campaigns, nine Marula advertiser campaigns and six driver assignments. The local preview proxy login returns HTTP 200.

The running API/frontend remain pinned to c2ab2d9. Its report endpoint still returns `503 PRIVACY_LIVE_USE_BLOCKED`; the page-unlock source has not been deployed. Browser-accessible storage routing also needs verification before an application deployment; storage/scanning and seeded bytes are verified internally. The recorded public tunnel hostname failed DNS resolution from this host during the final check, so current public reachability is not claimed.

The affected E2E suites used only `mobility_unlock_seed_v21`, a fresh v20 copy, through the owned local API/frontend at ports 3355/3356. Playwright rejects the public tunnel domains, preview service hosts, preview proxy/frontend/relay ports and preview database names/containers. Eleven guard cases pass. The serving preview still contains zero E2E campaigns after those tests; no historical claim about earlier suite targets is inferred.

## Seeded content inventory

This one table lists persisted names and human-written fields, including frozen text and media wording. The established `@demo.mobility.local` sign-ins remain working as the brief requires. The guarded automatic-payout actor and exact approval audit references are existing technical identities rather than invented human notes.

| Record / human-written field | Seeded content |
| --- | --- |
| `advertiser_organizations.billing_contact_name` | Adesola Aderemi<br>Ejiro Oghene<br>Funmilayo Ajayi<br>Halima Mohammed<br>Ijeoma Nwachukwu<br>Kabir Usman<br>Osahon Igbinosa<br>Tamuno Briggs<br>Uche Nnaji<br>Yetunde Akinyemi |
| `advertiser_organizations.billing_email` | accounts@marulakitchens.ng<br>adesola.aderemi@copperfinch.ng<br>ejiro.oghene@dovecrescent.ng<br>funmilayo.ajayi@lindenharbour.ng<br>halima.mohammed@oriolebooks.ng<br>ijeoma.nwachukwu@junipercourt.ng<br>kabir.usman@mangogrove.ng<br>osahon.igbinosa@sableridge.ng<br>tamuno.briggs@beryllane.ng<br>uche.nnaji@cedarbay.ng<br>yetunde.akinyemi@astervale.ng |
| `advertiser_organizations.name` | Aster Vale Foods<br>Beryl Lane Grocers<br>Cedar Bay Furnishings<br>Copper Finch Bakery<br>Dove Crescent Laundry<br>Juniper Court Pharmacy<br>Linden Harbour Clothing<br>Mango Grove Interiors<br>Marula Kitchens<br>Oriole Books<br>Sable Ridge Travel |
| `advertiser_organizations.operational_contact_email` | adesola.aderemi@copperfinch.ng<br>ejiro.oghene@dovecrescent.ng<br>funmilayo.ajayi@lindenharbour.ng<br>halima.mohammed@oriolebooks.ng<br>ijeoma.nwachukwu@junipercourt.ng<br>kabir.usman@mangogrove.ng<br>osahon.igbinosa@sableridge.ng<br>tamuno.briggs@beryllane.ng<br>uche.nnaji@cedarbay.ng<br>yetunde.akinyemi@astervale.ng |
| `advertiser_organizations.operational_contact_name` | Adesola Aderemi<br>Ejiro Oghene<br>Funmilayo Ajayi<br>Halima Mohammed<br>Ijeoma Nwachukwu<br>Kabir Usman<br>Osahon Igbinosa<br>Tamuno Briggs<br>Uche Nnaji<br>Yetunde Akinyemi |
| `audience_deliveries.adapter_name` | controlled-csv-v1 |
| `audit_events.metadata.after.reason` | Finance has checked the bank advice; transfers can continue.<br>Hold transfers while Finance checks today's bank advice. |
| `audit_events.metadata.before.reason` | Hold transfers while Finance checks today's bank advice. |
| `audit_events.metadata.note` | The upload matches the route recorded that morning.<br>The upload repeats a point already recorded on this route. |
| `audit_events.metadata.purpose` | person_payee_approval |
| `audit_events.metadata.reason` | Finance has checked the bank advice; transfers can continue.<br>Hold transfers while Finance checks today's bank advice.<br>Please hold deliveries while the Ikeja showroom is repainted.<br>Please hold lunch deliveries while the Ikeja kitchen is renovated.<br>Return the campaign payment after the advertiser's cancellation.<br>person_payee_approval:3641fbe3-1431-44bd-a679-e8397a5f166a<br>vehicle_approval:a6e1ba6d-0f2d-4439-a8da-a02dabea0a35 |
| `audit_events.metadata.rejection_reason` | Please enlarge the phone number before printing. |
| `audit_events.metadata.resolution_note` | The car remained at the depot during the recorded trip.<br>The driver was waiting at the market entrance; the route checks out. |
| `campaign_assignments.notes` | All agreed routes completed by Friday.<br>Collect the catering panels at the Wuse office on Friday.<br>Collect the door panels at the Ikeja office.<br>Deliver lunch orders around Yaba and Surulere.<br>Market deliveries finished on Friday. |
| `campaign_assignments.offer_terms.branding.campaign_name` | Aster Vale Foods — Mainland Deliveries<br>Beryl Lane Grocers — Market Routes<br>Cedar Bay Furnishings — Ikeja Showroom<br>Linden Harbour Clothing — Lagos Commute<br>Marula Kitchens — Ikeja Office Lunch<br>Marula Kitchens — Island Lunch Deliveries<br>Marula Kitchens — Lagos Lunch Routes<br>Marula Kitchens — Wuse Lunch Rush<br>Marula Kitchens — Wuse Weekend Catering<br>Oriole Books — Island Reading Week<br>Sable Ridge Travel — Airport Arrivals |
| `campaign_assignments.offer_terms.creative.name` | Aster Vale Foods door panel<br>Beryl Lane Grocers door panel<br>Cedar Bay Furnishings door panel<br>Door panel — teal<br>Linden Harbour Clothing door panel<br>Marula Kitchens door panel<br>Oriole Books door panel<br>Sable Ridge Travel door panel |
| `campaign_assignments.offer_terms.service_area.city` | abuja<br>lagos |
| `campaign_assignments.offer_terms.zones.bonus[].name` | Aminu Kano Crescent<br>Surulere shops<br>Yaba offices |
| `campaign_assignments.offer_terms.zones.exclusion[].name` | Apapa port access |
| `campaign_assignments.offer_terms.zones.premium[].name` | Airport Road<br>Ikeja and Maryland<br>Lagos Island<br>Lagos Mainland<br>Lagos Market Corridor<br>Wuse II offices<br>Wuse II shops |
| `campaign_assignments.offer_terms.zones.target[].name` | Airport Road<br>Ikeja and Maryland<br>Lagos Island<br>Lagos Mainland<br>Lagos Market Corridor<br>Wuse II offices<br>Wuse II shops |
| `campaign_cancellation_settlement_revisions.snapshot.reason` | Please cancel the Island launch until the new branch is ready.<br>Please cancel the collection campaign; the van delivery has been delayed. |
| `campaign_cancellations.reason` | Please cancel the Island launch until the new branch is ready.<br>Please cancel the collection campaign; the van delivery has been delayed. |
| `campaign_change_requests.impact_preview.after.campaign_name` | Aster Vale Foods — Mainland Deliveries<br>Marula Kitchens — Lagos Lunch Routes |
| `campaign_change_requests.impact_preview.before.campaign_name` | Aster Vale Foods — Mainland Deliveries<br>Marula Kitchens — Lagos Lunch Routes |
| `campaign_change_requests.impact_preview.request_reason` | Please cover the next week of office deliveries.<br>Please extend the lunch deliveries for another week. |
| `campaign_creatives.name` | Aster Vale Foods door panel<br>Beryl Lane Grocers door panel<br>Cedar Bay Furnishings door panel<br>Copper Finch Bakery door panel<br>Door panel — teal<br>Dove Crescent Laundry door panel<br>Juniper Court Pharmacy door panel<br>Linden Harbour Clothing door panel<br>Mango Grove Interiors door panel<br>Marula Kitchens door panel<br>Oriole Books door panel<br>Sable Ridge Travel door panel |
| `campaign_financial_authorizations.reason` | Full payment received for the agreed routes. |
| `campaign_payout_rule_revisions.reason` | Daily rate agreed for the scheduled routes. |
| `campaign_zones.description` | Deliver lunch orders to offices along Herbert Macaulay Way.<br>Heavy industrial traffic; avoid during campaigns.<br>Heavy port traffic; avoid during campaigns.<br>Invite readers to bookshops along Herbert Macaulay Way.<br>Promote local deliveries around Bode Thomas Street shops.<br>Promote lunch deliveries along Aminu Kano Crescent.<br>Promote the reading week around Lagos Island bookshops.<br>Promote weekend orders around Aminu Kano Crescent shops.<br>Reach furniture shoppers along Ikorodu Road and Maryland.<br>Reach households along the Maitama neighbourhood routes.<br>Reach lunch customers along the Yaba and Surulere routes.<br>Reach office workers along Aminu Kano Crescent.<br>Reach shops along the Mainland market routes.<br>Reach shops and offices along the Yaba and Surulere routes.<br>Reach travellers along Airport Road in Ikeja.<br>Reach weekday customers around Area 11 offices. |
| `campaign_zones.name` | Airport Road<br>Aminu Kano Crescent<br>Apapa port access<br>Garki offices<br>Ikeja and Maryland<br>Lagos Island<br>Lagos Mainland<br>Lagos Market Corridor<br>Maitama homes<br>Surulere shops<br>Wuse II offices<br>Wuse II shops<br>Yaba bookshops<br>Yaba offices |
| `campaigns.description` | Bring weekday lunch deliveries to offices around Garki.<br>Bring weekday lunches to offices along Allen Avenue.<br>Bring weekday lunches to offices around Maitama.<br>Deliver lunch orders around Yaba and Surulere.<br>Deliver weekday lunches around Lagos Island offices.<br>Delivery visibility around Lagos offices.<br>Introduce a lunch collection point for Lekki residents.<br>Introduce doorstep laundry collection around Victoria Island.<br>Introduce the new furniture collection around Maitama.<br>Invite readers to the weekend book fair around Yaba.<br>Lunchtime visibility around Wuse II offices.<br>Offer weekend lunch deliveries around Yaba homes.<br>Promote weekend bread orders around Wuse II.<br>Promote weekend catering orders around Wuse II.<br>Reach households along the Lekki collection route.<br>Visibility along Lagos Mainland commuter routes.<br>Visibility around Garki offices before the shop opens.<br>Visibility around Lagos markets and neighbourhood shops.<br>Visibility around shops and offices in Lagos. |
| `campaigns.name` | Aster Vale Foods — Mainland Deliveries<br>Beryl Lane Grocers — Market Routes<br>Cedar Bay Furnishings — Ikeja Showroom<br>Copper Finch Bakery — Weekend Orders<br>Dove Crescent Laundry — Home Collection<br>Dove Crescent Laundry — Island Collection<br>Juniper Court Pharmacy — Garki Opening<br>Linden Harbour Clothing — Lagos Commute<br>Mango Grove Interiors — Maitama Collection<br>Marula Kitchens — Garki Office Lunch<br>Marula Kitchens — Ikeja Office Lunch<br>Marula Kitchens — Island Lunch Deliveries<br>Marula Kitchens — Lagos Lunch Routes<br>Marula Kitchens — Lekki Lunch Collection<br>Marula Kitchens — Maitama Office Lunch<br>Marula Kitchens — Wuse Lunch Rush<br>Marula Kitchens — Wuse Weekend Catering<br>Marula Kitchens — Yaba Weekend Lunch<br>Oriole Books — Island Reading Week<br>Oriole Books — Yaba Book Fair<br>Sable Ridge Travel — Airport Arrivals |
| `commercial_quotation_revisions.line_items[].description` | Vehicle advertising on the agreed routes |
| `commercial_quotation_revisions.payment_terms.notes` | Payment before printing and installation. |
| `commercial_quote_requests.request_details.notes` | Please quote for the Yaba book fair weekend.<br>Please quote for weekday visibility around the selected areas.<br>Please quote for weekend lunch deliveries around Yaba. |
| `commercial_terms.line_items[].description` | Vehicle advertising on the agreed routes |
| `commercial_terms.payment_terms.notes` | Payment before printing and installation. |
| `complaint_messages.body` | Can the cars cover Aminu Kano Crescent before lunch?<br>Could you send the invoice with our Wuse office address?<br>My Tuesday trip ended near Yaba but the earnings are still pending.<br>Please visit the Ikeja office tomorrow morning for a replacement.<br>The app stopped recording after I left the fuel station.<br>The corrected panel is fitted and the photos are attached.<br>The lunch menu on the back panel needs the new phone number.<br>The rear sticker is lifting at the left corner.<br>Yes, the morning route includes Aminu Kano Crescent.<br>Your route has been checked and the missing section has been corrected. |
| `creative_review_events.rejection_reason` | Please enlarge the phone number before printing. |
| `creative_review_events.reviewed_snapshot.name` | Aster Vale Foods door panel<br>Beryl Lane Grocers door panel<br>Cedar Bay Furnishings door panel<br>Copper Finch Bakery door panel<br>Door panel — teal<br>Dove Crescent Laundry door panel<br>Juniper Court Pharmacy door panel<br>Linden Harbour Clothing door panel<br>Mango Grove Interiors door panel<br>Marula Kitchens door panel<br>Oriole Books door panel<br>Sable Ridge Travel door panel |
| `disclosure_query_decisions.reason` | privacy_floor_passed |
| `driver_applications.email` | abdulrahman.yusuf@mail.ng<br>ayodele.bakare@mail.ng<br>nneka.umeh@mail.ng<br>suleiman.idris@mail.ng |
| `driver_applications.full_name` | Abdulrahman Yusuf<br>Ayodele Bakare<br>Nneka Umeh<br>Suleiman Idris |
| `driver_applications.service_city` | Abuja |
| `driver_phone_versions.masked_phone` | 000••••0000 |
| `driver_profiles.license_number` | ABJ-2023-49158<br>LAG-2024-58219<br>LAG-2024-58301<br>LAG-2024-58302<br>LAG-2024-58303<br>LAG-2024-58304<br>LAG-2024-58305<br>LAG-2024-58306<br>LAG-2024-58307<br>LAG-2024-58308<br>LAG-2024-58309 |
| `driver_profiles.service_city` | Abuja<br>Lagos |
| `earnings_ledger_entries.description` | No earnings for this route<br>Trip payout |
| `evidence_verifications.result_note` | All panels are secure and the phone number is readable.<br>Meet the driver near Yaba market after the morning route.<br>Please check the rear panel at the Ikeja office.<br>The rear panel is peeling; arrange a replacement before the next route. |
| `exposure_scores.result_snapshot.label` | Exposure score |
| `file_upload_intents.original_filename` | aster-vale-foods.png<br>ayodele-bakare-driver-license.png<br>ayodele-bakare-driver-photo.png<br>ayodele-bakare-insurance.png<br>ayodele-bakare-registration.png<br>ayodele-bakare-signed-agreement.png<br>ayodele-bakare-vehicle-photo.png<br>back.png<br>beryl-lane-grocers.png<br>cedar-bay-furnishings.png<br>close_up.png<br>copper-finch-bakery.png<br>dove-crescent-laundry.png<br>front.png<br>juniper-court-pharmacy.png<br>left.png<br>linden-harbour-clothing.png<br>mango-grove-interiors.png<br>marula-kitchens.png<br>nneka-umeh-driver-license.png<br>nneka-umeh-driver-photo.png<br>nneka-umeh-signed-agreement.png<br>oriole-books.png<br>right.png<br>sable-ridge-travel.png<br>suleiman-idris-driver-license.png<br>suleiman-idris-driver-photo.png<br>suleiman-idris-signed-agreement.png |
| `file_upload_intents.purpose` | creative<br>driver_kyc<br>installation_evidence<br>vehicle_evidence |
| `fraud_flags.description` | A physical display spot check failed and requires staff review.<br>Consecutive location pings had an excessive time gap.<br>Observed speed exceeded configured threshold.<br>Poor GPS accuracy ratio exceeded configured threshold.<br>Stationary time ratio exceeded configured threshold.<br>Trip route ended close to its start after significant distance.<br>Trip route intersected an exclusion zone. |
| `fraud_flags.resolution_note` | The car remained at the depot during the recorded trip.<br>The driver was waiting at the market entrance; the route checks out. |
| `invoice_issuer_profiles.contact_email` | terraxmediacompany@gmail.com |
| `invoice_issuer_profiles.contact_phone` | 07074200080 |
| `invoice_issuer_profiles.invoice_wording` | Vehicle advertising |
| `invoice_issuer_profiles.legal_name` | Terrax Media Company Ltd |
| `invoice_issuer_profiles.registered_address` | 73 Lome Crescent, Wuse Zone 7, Abuja |
| `invoices.customer_snapshot.name` | Aster Vale Foods<br>Beryl Lane Grocers<br>Cedar Bay Furnishings<br>Copper Finch Bakery<br>Dove Crescent Laundry<br>Juniper Court Pharmacy<br>Linden Harbour Clothing<br>Mango Grove Interiors<br>Marula Kitchens<br>Oriole Books |
| `invoices.issuer_snapshot.bank_account_name` | Terrax Media Company Ltd |
| `invoices.issuer_snapshot.bank_name` | OPay |
| `invoices.issuer_snapshot.legal_name` | Terrax Media Company Ltd |
| `invoices.line_items[].description` | Vehicle advertising on the agreed routes |
| `manual_driver_contact_tasks.completion_note` | Amina can visit the Ikeja office on Thursday.<br>Chinedu was driving; call again after six. |
| `manual_driver_contact_tasks.purpose` | Arrange an installation visit |
| `notifications.payload.campaign_name` | Marula Kitchens — Lagos Lunch Routes |
| `payment_receipts.evidence_reference` | Transfer advice received by Finance. |
| `payment_receipts.payer_name` | Aster Vale Foods<br>Beryl Lane Grocers<br>Cedar Bay Furnishings<br>Copper Finch Bakery<br>Dove Crescent Laundry<br>Linden Harbour Clothing<br>Marula Kitchens<br>Oriole Books |
| `payout_automatic_alerts.detail.reason` | provider_unavailable |
| `payout_automatic_controls.reason` | Finance has checked the bank advice; transfers can continue. |
| `payout_correction_orders.reason` | Please check the Yaba distance after the route was corrected.<br>Please recheck the distance recorded near the fuel station.<br>The Surulere return leg needs a second review.<br>The route review is complete; please confirm the earnings. |
| `payout_submission_intents.provider_name` | fake |
| `quarantined_ping_batches.resolution_note` | The upload matches the route recorded that morning.<br>The upload repeats a point already recorded on this route. |
| `receipt_lifecycle_events.reason` | First instalment received; the balance is due before printing.<br>Return the campaign payment after the advertiser's cancellation.<br>Transfer amount matches the accepted quotation. |
| `refund_settlements.reason` | Returned the full payment before printing began. |
| `report_issuances.snapshot.metrics[].label` | Driver campaign cost<br>Modelled potential contacts<br>Verified vehicle movement |
| `report_issuances.snapshot.metrics[].values[].label` | Active tracking time<br>Distance<br>NGN<br>Trip count<br>Value |
| `stored_files.original_filename` | aster-vale-foods.png<br>ayodele-bakare-driver-license.png<br>ayodele-bakare-driver-photo.png<br>ayodele-bakare-insurance.png<br>ayodele-bakare-registration.png<br>ayodele-bakare-signed-agreement.png<br>ayodele-bakare-vehicle-photo.png<br>back.png<br>beryl-lane-grocers.png<br>cardvert-campaign-performance-analysis-v1.csv<br>cardvert-campaign-performance-analysis-v1.pdf<br>cedar-bay-furnishings.png<br>close_up.png<br>copper-finch-bakery.png<br>dove-crescent-laundry.png<br>front.png<br>juniper-court-pharmacy.png<br>left.png<br>linden-harbour-clothing.png<br>mango-grove-interiors.png<br>marula-kitchens.png<br>nneka-umeh-driver-license.png<br>nneka-umeh-driver-photo.png<br>nneka-umeh-signed-agreement.png<br>oriole-books.png<br>right.png<br>sable-ridge-travel.png<br>suleiman-idris-driver-license.png<br>suleiman-idris-driver-photo.png<br>suleiman-idris-signed-agreement.png |
| `stored_files.purpose` | creative<br>driver_kyc<br>installation_evidence<br>report_export<br>vehicle_evidence |
| `traffic_density_profiles.description` | Weekday traffic around Lagos offices and markets.<br>Weekday traffic around Wuse and Garki offices.<br>Weekend traffic around Lagos shopping streets. |
| `traffic_density_profiles.name` | Abuja office traffic<br>Lagos weekday traffic<br>Lagos weekend traffic |
| `trip_sessions.end_reason` | driver_finished |
| `trip_sessions.seal_reason` | client_complete |
| `users.email` | abdulrahman.yusuf@mail.ng<br>adesola.aderemi@copperfinch.ng<br>admin@demo.mobility.local<br>advertiser@demo.mobility.local<br>aisha.garba@terraxmedia.com<br>automatic-payouts@cardvert.invalid<br>ayodele.bakare@mail.ng<br>chiamaka.obi@terraxmedia.com<br>chukwudi.agu@mail.ng<br>driver.wuse@demo.mobility.local<br>driver01@demo.mobility.local<br>driver02@demo.mobility.local<br>driver03@demo.mobility.local<br>driver04@demo.mobility.local<br>driver05@demo.mobility.local<br>driver06@demo.mobility.local<br>driver07@demo.mobility.local<br>driver08@demo.mobility.local<br>driver09@demo.mobility.local<br>driver@demo.mobility.local<br>efe.okoro@terraxmedia.com<br>ejiro.oghene@dovecrescent.ng<br>fatima.adamu@mail.ng<br>funmilayo.ajayi@lindenharbour.ng<br>halima.mohammed@oriolebooks.ng<br>hauwa.sani@terraxmedia.com<br>ibrahim.danjuma@terraxmedia.com<br>ijeoma.nwachukwu@junipercourt.ng<br>kabir.usman@mangogrove.ng<br>nneka.umeh@mail.ng<br>obinna.onyekachi@mail.ng<br>olumide.fashola@terraxmedia.com<br>osahon.igbinosa@sableridge.ng<br>suleiman.idris@mail.ng<br>tamuno.briggs@beryllane.ng<br>temitope.ojo@terraxmedia.com<br>uche.nnaji@cedarbay.ng<br>viewer@demo.mobility.local<br>yetunde.akinyemi@astervale.ng<br>yewande.afolabi@mail.ng |
| `users.full_name` | Abdulrahman Yusuf<br>Adesola Aderemi<br>Aisha Garba<br>Amina Bello<br>Ayodele Bakare<br>Babatunde Lawal<br>Bola Adeyemi<br>Cardvert (automatic payouts)<br>Chiamaka Obi<br>Chinedu Okafor<br>Chukwudi Agu<br>Efe Okoro<br>Ejiro Oghene<br>Emeka Nwankwo<br>Fatima Adamu<br>Folashade Akinwale<br>Funmilayo Ajayi<br>Halima Mohammed<br>Hauwa Sani<br>Ibrahim Danjuma<br>Ifeanyi Nwosu<br>Ijeoma Nwachukwu<br>Kabir Usman<br>Kemi Balogun<br>Musa Abdullahi<br>Ngozi Eze<br>Nkiru Chukwu<br>Nneka Umeh<br>Obinna Onyekachi<br>Olumide Fashola<br>Osahon Igbinosa<br>Seyi Ogunleye<br>Suleiman Idris<br>Tamuno Briggs<br>Temitope Ojo<br>Tunde Adebayo<br>Uche Nnaji<br>Yetunde Akinyemi<br>Yewande Afolabi<br>Zainab Musa |
| `vehicles.color` | Black<br>Blue<br>Grey<br>Red<br>Silver<br>White |
| `vehicles.make` | Honda<br>Hyundai<br>Kia<br>Nissan<br>Suzuki<br>Toyota |
| `vehicles.model` | Accord<br>Camry<br>Civic<br>Corolla<br>Elantra<br>Every<br>Rio<br>Sienna<br>Urvan |
| `vehicles.plate_number` | AAA-681-WZ<br>ABJ-482-KD<br>ABJ-603-MR<br>ABJ-715-FM<br>AKD-458-PQ<br>EPE-926-KL<br>FKJ-204-NP<br>FKJ-824-CN<br>KJA-637-BD<br>KJA-916-NB<br>KRD-347-JM<br>LND-315-HG<br>LSR-219-XY<br>LSR-528-HP<br>MUS-763-RS<br>SMK-592-TV |
| `whatsapp_consents.purpose` | Installation and trip updates |
| Artwork and installation photo text | Marula Kitchens; Lunch delivered.; Good Food Brighter Days; each fictional business name above; Closer to your neighbourhood; Lagos • Abuja |
| Applicant document artwork | Driver licence; Portrait; Vehicle advertising agreement; Vehicle registration; Insurance; Vehicle photo; each applicant's full name above; Abuja; I agree to keep the panels fitted and report any damage promptly.; Signed; ABJ-2024-58219; ABJ-603-MR; Toyota Corolla White 2020 |

## Wave 2 C renewal and phone examples — 7 October 2026

Development/preview drivers use Ofcom's reserved fictional mobile range
[07700 900000–900999](https://www.ofcom.org.uk/phones-and-broadband/phone-numbers/numbers-for-drama),
which is not allocated to real customers. These UK country-code numbers are
deliberately different from a plausible routable Nigerian mobile number.
No WhatsApp/SMS is sent by the application or seed.

| Login | Fictional saved phone |
| --- | --- |
| driver@demo.mobility.local | +447700900100 |
| driver01…driver09@demo.mobility.local | +447700900101…+447700900109, respectively |
| abdulrahman.yusuf@mail.ng | +447700900110 |
| nneka.umeh@mail.ng | +447700900111 |
| ayodele.bakare@mail.ng | +447700900112 |
| suleiman.idris@mail.ng | +447700900113 |
| damilola.akinwale@demo.mobility.local | +447700900114 |
| Terrax development/preview destination | +447700900999 |

Damilola Akinwale (`LagosRoutes2026!`) has an active login, a readable
renewal example with identity documents rejected as unreadable, and vehicle
documents explicitly marked expired for ABJ-714-KM. The six clearly fictional
PNG documents are privately stored and scanned through the existing seed
pipeline. No licence/insurance expiry date or renewal period is invented.
Work remains pending until the current complete identity/bank and car revisions
pass the existing review gates. Reruns preserve submitted revisions and decisions.

Use Profile → Your documents to upload replacements; review them in the driver's
Documents section. View each current document; Show NIN and bank View remain
separate audited reads. Bank approval still requires verification authority.
For the phone demonstration, save the driver's fictional number, tap Verify my
phone, then enter the displayed code and that same sender in Phone → Record
phone verification, or Support → Driver contact. Staff never fetch the code.
Production/staging destinations remain blank; real use additionally requires
`PHONE_OPERATOR_EXTERNAL_APPROVED`, `PHONE_OPERATOR_NAME` and
`PHONE_WHATSAPP_NOTICE_APPROVAL_REFERENCE` with REQ-032 approved wording.
Preview deployment is a separate owner action; this change provides configuration
and source only.

Existing Start demo drivers retain the trusted no-application/no-KYC baseline.
The seed does not manufacture approved KYC or car snapshots without reviewed
documents. Its existing synthetic payee, encrypted zero-value bank details and
payout verification fixtures remain unchanged and are reused on rerun.
