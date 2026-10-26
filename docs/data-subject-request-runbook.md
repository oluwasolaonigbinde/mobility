# Interim manual personal-data requests

D110 / REQ-211. Pending the lawyer's **EXT-LEGAL-PRIVACY** approval. This is
a staff procedure, not a new case-management workflow or approval for live use.

1. Record a private case reference, receipt date and requested access, correction
   or deletion. Verify the person through their signed-in account or a callback
   to an already verified contact. Resolve mismatches before releasing anything.
   Do not put identity documents, passwords or bank details in audit notes.
2. Aim to acknowledge within one working day and respond promptly once verified.
   The lawyer must confirm the response deadline and any retention exception;
   no numerical legal deadline has been approved in Cardvert. Escalate missing
   answers immediately and tell the requester about delays.
3. An active administrator checks the account and company membership; the driver
   record and KYC submissions/files; vehicles and installation evidence; trips,
   GPS pings and derived checks; payee/bank versions, payouts and ledger; invoices,
   receipts/refunds where relevant; notifications and audit records. Include
   processors, backups and the driver's unsent device queue in the scope check.
4. Use existing staff detail screens and authorised, virus-cleared file downloads.
   For a data export, a trusted database operator can use a **read-only** SQL
   transaction with a verified UUID. Start with the queries below and review the
   related records in the table list. Export to protected operations storage,
   inspect for other people's data and secrets, and deliver only to the verified
   requester. Never attach the export to a public ticket or ordinary audit note.
5. Correct fields through existing admin tools, which record their own audit.
   Disable access/stop collection where appropriate. There is **no verified
   general-purpose safe erasure/anonymisation tool**: do not run cascading deletes,
   edit GPS/payment evidence, or claim erasure is complete. Escalate the exact
   requested scope to the owner and lawyer. Existing 12-month GPS retention and
   six-month terminal KYC-file purge still run with their safety checks; they
   do not establish that every copy of a person's data has been erased.
6. Keep money and audit history, original payment/Paystack confirmations,
   refunds, held-pay decisions and immutable issued files. The lawyer decides
   what can be redacted, retained or released and for how long. Do not rewrite
   these records to satisfy an erasure request. Check processor, backup and
   device copies separately; an unverified location remains outstanding.
7. Record what was verified, supplied, corrected, retained or still outstanding
   in the protected case record. Append a short audit entry with the staff ID,
   subject ID, case reference, action, time and non-sensitive outcome. The
   existing audit helper can be used by a trusted operator; the SQL below is
   an alternative. Do not mark unresolved deletion work complete.

The following psql queries use separately supplied UUID variables
`subject_user_id`, `staff_user_id` and a non-sensitive `case_reference`.
Use an authorised connection; no credentials belong in this document.

```sql
BEGIN READ ONLY;
SELECT id, email, full_name, phone, role, status, created_at
  FROM users WHERE id = :'subject_user_id'::uuid;
SELECT * FROM organization_memberships WHERE user_id = :'subject_user_id'::uuid;
SELECT * FROM driver_profiles WHERE user_id = :'subject_user_id'::uuid;
SELECT t.* FROM trip_sessions t JOIN driver_profiles d ON d.id=t.driver_profile_id
  WHERE d.user_id = :'subject_user_id'::uuid;
SELECT p.* FROM location_pings p JOIN trip_sessions t ON t.id=p.trip_session_id
  JOIN driver_profiles d ON d.id=t.driver_profile_id
  WHERE d.user_id = :'subject_user_id'::uuid;
SELECT * FROM notifications WHERE recipient_user_id = :'subject_user_id'::uuid;
COMMIT;
```

Follow `driver_profiles.id` into `driver_kyc_submissions`, `vehicles`,
`campaign_assignments`, `trip_analytics`, `fraud_flags`, `payout_calculations`
and `earnings_ledger_entries`; follow submission/document and `stored_files`
IDs for private file downloads. Check `vehicle_evidence_submissions` and
`vehicle_evidence_documents`, `payees`, `payee_versions`, bank-account versions,
and the linked company billing records. These are an inventory map, **not**
permission to export entire joined tables or reveal other subjects.

```sql
BEGIN;
INSERT INTO audit_events (actor_user_id, action, entity_type, entity_id, metadata)
SELECT id, 'privacy.manual_request.reviewed', 'user', :'subject_user_id',
       jsonb_build_object('case_reference', :'case_reference',
                          'outcome', 'Manual review recorded; see protected case')
FROM users WHERE id=:'staff_user_id'::uuid AND role='admin' AND status='active';
-- Require exactly one inserted row; otherwise roll back and escalate.
COMMIT;
```
