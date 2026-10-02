# Cardvert development data and go-live decisions

1. Restore legal/privacy protections for GPS, ID collection and advertiser results before real users
2. Restore overlap/differencing protection for advertiser analytics

Identical repeat views reveal nothing new. Narrowly differing date windows are the risk to address when restoring protection. Query history and all aggregation limits remain recorded/enforced; no history reset enables ordinary navigation.

Removed controls: legal display/collection authorization and synthetic switches, disclosure/configuration/history approval references, live measurement authorization and report-method approval setting; dynamic advertiser report fallback; legal approval for aggregate CSV export. Reports display a frozen measurement snapshot; CSV/PDF publication uses that same snapshot.

Retained controls: organization membership and roles; aggregation vehicle/trip/day floors, contributor caps and resolution limits; disclosure query recording; report reproducibility, file integrity and conditional ROI inputs/method authority; person-level export rejection; storage/scanning/encryption; payment, payout and email provider controls; blocked live Meta/Google activation. `PRIVACY_LEGAL_APPROVAL_REFERENCE` remains only for actual ad-platform approval and DSR retention exceptions. `MEASUREMENT_ROI_METHOD_REFERENCE` remains for financial ROI, and the calculation method revision stays recorded on each run. Synthetic lineage fields remain where they describe source provenance and protect provider activation, without legal display authority switches.

## Client inputs to replace

The second batch will list the exact seeded values, locations and replacing client answers here. No missing client answer is recorded as approved.

## Seeded content inventory

The second batch will list every seeded person, company, campaign and human-written field here for owner review.

Synthetic ROI inputs remain restricted to local/test calculation and publication; real ROI still needs the approved method reference.
