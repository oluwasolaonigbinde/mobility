# ruff: noqa: E501
"""Single development baseline (D83 / REQ-169).

Generated from the full PostgreSQL schema after the approved Waves 3/4 chain.
No live data exists. The owning role is the migration connection's role.
Partition names/bounds follow the frozen three-prior/four-future-month horizon;
all table, constraint, trigger, function and privilege definitions are retained.
"""

import hashlib
import re
import secrets

import sqlalchemy as sa
from argon2 import PasswordHasher

from alembic import op

revision = "0106_development_baseline"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA_DDL = (
    r"""
SET statement_timeout = 0;
""",
    r"""
SET lock_timeout = 0;
""",
    r"""
SET idle_in_transaction_session_timeout = 0;
""",
    r"""
SET client_encoding = 'UTF8';
""",
    r"""
SET standard_conforming_strings = on;
""",
    r"""
SELECT pg_catalog.set_config('search_path', '', false);
""",
    r"""
SET check_function_bodies = false;
""",
    r"""
SET xmloption = content;
""",
    r"""
SET client_min_messages = warning;
""",
    r"""
SET row_security = off;
""",
    r"""
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;
""",
    r"""
COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';
""",
    r"""
CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public;
""",
    r"""
COMMENT ON EXTENSION postgis IS 'PostGIS geometry and geography spatial types and functions';
""",
    r"""
CREATE FUNCTION public.enforce_liability_reservation_transition() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'liability reservation is durable';
          END IF;
          IF OLD.status = 'released' THEN
            RAISE EXCEPTION 'released liability is immutable';
          END IF;
          IF OLD.id IS DISTINCT FROM NEW.id
             OR OLD.campaign_id IS DISTINCT FROM NEW.campaign_id
             OR OLD.assignment_id IS DISTINCT FROM NEW.assignment_id
             OR OLD.assignment_rule_binding_id IS DISTINCT FROM NEW.assignment_rule_binding_id
             OR OLD.covered_vehicle_days IS DISTINCT FROM NEW.covered_vehicle_days
             OR OLD.hourly_rate IS DISTINCT FROM NEW.hourly_rate
             OR OLD.daily_hours_cap IS DISTINCT FROM NEW.daily_hours_cap
             OR OLD.requested_amount IS DISTINCT FROM NEW.requested_amount
             OR OLD.requested_at IS DISTINCT FROM NEW.requested_at
             OR OLD.formula_version IS DISTINCT FROM NEW.formula_version THEN
            RAISE EXCEPTION 'invalid liability reservation transition';
          END IF;
          IF OLD.status = 'pending_funding' AND NEW.status = 'reserved'
             AND NEW.authorization_id IS NOT NULL
             AND NEW.reserved_amount = NEW.requested_amount
             AND NEW.reserved_at IS NOT NULL
             AND NEW.released_at IS NULL
             AND NEW.release_cancellation_id IS NULL THEN
            RETURN NEW;
          END IF;
          IF OLD.status IN ('pending_funding', 'reserved') AND NEW.status = 'released'
             AND NEW.authorization_id IS NOT DISTINCT FROM OLD.authorization_id
             AND NEW.reserved_amount IS NOT DISTINCT FROM OLD.reserved_amount
             AND NEW.reserved_at IS NOT DISTINCT FROM OLD.reserved_at
             AND NEW.released_at IS NOT NULL
             AND NEW.release_cancellation_id IS NOT NULL THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'invalid liability reservation transition';
        END;
        $$;
""",
    r"""
CREATE FUNCTION public.guard_campaign_change_request_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'campaign change request is append-only'; END IF; IF NEW.id IS DISTINCT FROM OLD.id OR NEW.campaign_id IS DISTINCT FROM OLD.campaign_id OR NEW.organization_id IS DISTINCT FROM OLD.organization_id OR NEW.requested_by_user_id IS DISTINCT FROM OLD.requested_by_user_id OR NEW.client_request_id IS DISTINCT FROM OLD.client_request_id OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint OR NEW.proposed_changes::jsonb IS DISTINCT FROM OLD.proposed_changes::jsonb OR NEW.classifications::jsonb IS DISTINCT FROM OLD.classifications::jsonb OR NEW.impact_preview::jsonb IS DISTINCT FROM OLD.impact_preview::jsonb OR NEW.requested_liability_amount IS DISTINCT FROM OLD.requested_liability_amount OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN RAISE EXCEPTION 'campaign change request is append-only'; END IF; IF OLD.reviewed_by_user_id IS NOT NULL AND (NEW.reviewed_by_user_id IS DISTINCT FROM OLD.reviewed_by_user_id OR NEW.reviewed_at IS DISTINCT FROM OLD.reviewed_at OR NEW.review_reason IS DISTINCT FROM OLD.review_reason) THEN RAISE EXCEPTION 'campaign change review evidence is immutable'; END IF; IF OLD.status IN ('applied', 'rejected') OR NOT ((OLD.status = 'pending_admin' AND NEW.status IN ('pending_admin', 'pending_funding', 'applied', 'rejected')) OR (OLD.status = 'pending_funding' AND NEW.status IN ('pending_funding', 'applied', 'rejected'))) THEN RAISE EXCEPTION 'campaign change transition is invalid'; END IF; RETURN NEW; END $$;
""",
    r"""
CREATE FUNCTION public.guard_display_proof_challenge_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN IF TG_OP = 'DELETE' OR NEW.id IS DISTINCT FROM OLD.id OR NEW.assignment_id IS DISTINCT FROM OLD.assignment_id OR NEW.evidence_submission_id IS DISTINCT FROM OLD.evidence_submission_id OR NEW.driver_profile_id IS DISTINCT FROM OLD.driver_profile_id OR NEW.vehicle_id IS DISTINCT FROM OLD.vehicle_id OR NEW.device_id IS DISTINCT FROM OLD.device_id OR NEW.nonce_sha256 IS DISTINCT FROM OLD.nonce_sha256 OR NEW.expires_at IS DISTINCT FROM OLD.expires_at OR NEW.created_at IS DISTINCT FROM OLD.created_at OR OLD.consumed_at IS NOT NULL OR NEW.consumed_at IS NULL THEN RAISE EXCEPTION 'display proof challenge is append-only'; END IF; RETURN NEW; END $$;
""",
    r"""
CREATE FUNCTION public.guard_earnings_ledger_entry_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
            BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION USING ERRCODE = '55000',
                  MESSAGE = 'earnings ledger entries cannot be deleted';
              END IF;

              IF (
                NEW.id,
                NEW.payout_calculation_id,
                NEW.driver_profile_id,
                NEW.driver_user_id,
                NEW.campaign_id,
                NEW.trip_session_id,
                NEW.vehicle_id,
                NEW.entry_type,
                NEW.amount,
                NEW.currency,
                NEW.description,
                NEW.occurred_at,
                NEW.release_at,
                NEW.source_fraud_flag_id,
                NEW.metadata,
                NEW.created_at
              ) IS DISTINCT FROM (
                OLD.id,
                OLD.payout_calculation_id,
                OLD.driver_profile_id,
                OLD.driver_user_id,
                OLD.campaign_id,
                OLD.trip_session_id,
                OLD.vehicle_id,
                OLD.entry_type,
                OLD.amount,
                OLD.currency,
                OLD.description,
                OLD.occurred_at,
                OLD.release_at,
                OLD.source_fraud_flag_id,
                OLD.metadata,
                OLD.created_at
              ) THEN
                RAISE EXCEPTION USING ERRCODE = '55000',
                  MESSAGE = 'earnings ledger economic identity is immutable';
              END IF;

              IF NEW.status = OLD.status
                 OR (OLD.status = 'pending' AND NEW.status = 'available')
                 OR (OLD.status = 'available' AND NEW.status IN ('paid', 'reversed')) THEN
                RETURN NEW;
              END IF;
              RAISE EXCEPTION USING ERRCODE = '55000',
                MESSAGE = 'unsupported earnings ledger status transition';
            END;
            $$;
""",
    r"""
CREATE FUNCTION public.guard_installation_evidence_submission_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'installation evidence is append-only'; END IF; IF NEW.id IS DISTINCT FROM OLD.id OR NEW.assignment_id IS DISTINCT FROM OLD.assignment_id OR NEW.campaign_id IS DISTINCT FROM OLD.campaign_id OR NEW.driver_profile_id IS DISTINCT FROM OLD.driver_profile_id OR NEW.vehicle_id IS DISTINCT FROM OLD.vehicle_id OR NEW.submitted_by_user_id IS DISTINCT FROM OLD.submitted_by_user_id OR NEW.revision IS DISTINCT FROM OLD.revision OR NEW.client_request_id IS DISTINCT FROM OLD.client_request_id OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint OR NEW.device_id IS DISTINCT FROM OLD.device_id OR NEW.captured_at IS DISTINCT FROM OLD.captured_at OR NEW.required_views IS DISTINCT FROM OLD.required_views OR NEW.metadata IS DISTINCT FROM OLD.metadata OR NEW.submitted_at IS DISTINCT FROM OLD.submitted_at THEN RAISE EXCEPTION 'installation evidence is append-only'; END IF; RETURN NEW; END $$;
""",
    r"""
CREATE FUNCTION public.guard_kyc_document_retention() RETURNS trigger
    LANGUAGE plpgsql
    AS $_$
        DECLARE retired_at timestamptz;
        BEGIN
          EXECUTE format('SELECT purged_at FROM %I WHERE id=$1 FOR UPDATE', TG_ARGV[0])
            INTO retired_at USING NEW.submission_id;
          IF retired_at IS NOT NULL THEN
            RAISE EXCEPTION 'purged KYC submission cannot accept documents';
          END IF;
          RETURN NEW;
        END $_$;
""",
    r"""
CREATE FUNCTION public.guard_kyc_payload_retention() RETURNS trigger
    LANGUAGE plpgsql
    AS $_$
        DECLARE has_documents boolean;
        BEGIN
          IF TG_OP = 'DELETE' THEN
            IF OLD.purged_at IS NOT NULL THEN
              RAISE EXCEPTION 'purged KYC review identity is immutable';
            END IF;
            RETURN OLD;
          END IF;
          IF OLD.purged_at IS NOT NULL AND to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
            RAISE EXCEPTION 'purged KYC review identity is immutable';
          END IF;
          IF OLD.purged_at IS NULL AND NEW.purged_at IS NOT NULL THEN
            IF OLD.status NOT IN ('rejected', 'expired') OR
              (to_jsonb(NEW) - string_to_array(TG_ARGV[2], ',')) IS DISTINCT FROM
              (to_jsonb(OLD) - string_to_array(TG_ARGV[2], ',')) THEN
              RAISE EXCEPTION 'KYC purge may only clear an eligible terminal payload';
            END IF;
            EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I WHERE submission_id=$1)', TG_ARGV[0])
              INTO has_documents USING NEW.id;
            IF has_documents OR NOT EXISTS (
              SELECT 1 FROM audit_events WHERE entity_type=TG_ARGV[1] AND entity_id=NEW.id::text
                AND action=TG_ARGV[1] || '.payload_purge_authorized'
            ) THEN
              RAISE EXCEPTION 'KYC purge requires detached documents and durable audit authority';
            END IF;
          END IF;
          RETURN NEW;
        END $_$;
""",
    r"""
CREATE FUNCTION public.guard_payout_batch_line_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
            BEGIN
              IF ROW(
                NEW.batch_id, NEW.ledger_entry_id, NEW.predecessor_line_id,
                NEW.payee_version_id, NEW.bank_account_version_id,
                NEW.amount, NEW.currency, NEW.instruction,
                NEW.instruction_fingerprint, NEW.idempotency_key, NEW.created_at
              ) IS DISTINCT FROM ROW(
                OLD.batch_id, OLD.ledger_entry_id, OLD.predecessor_line_id,
                OLD.payee_version_id, OLD.bank_account_version_id,
                OLD.amount, OLD.currency, OLD.instruction,
                OLD.instruction_fingerprint, OLD.idempotency_key, OLD.created_at
              ) THEN
                RAISE EXCEPTION 'payout batch line identity is immutable';
              END IF;
              IF NOT (
                OLD.status = NEW.status
                OR (OLD.status = 'reserved' AND NEW.status IN ('submitted', 'void'))
                OR (OLD.status = 'submitted' AND NEW.status IN ('succeeded', 'failed'))
                OR (OLD.status = 'failed' AND NEW.status = 'succeeded')
              ) THEN
                RAISE EXCEPTION 'payout batch line state transition is invalid';
              END IF;
              IF OLD.provider_transfer_reference IS DISTINCT FROM
                   NEW.provider_transfer_reference
                 AND NOT (
                   OLD.provider_transfer_reference IS NULL
                   AND NEW.provider_transfer_reference IS NOT NULL
                   AND OLD.status = 'reserved' AND NEW.status = 'submitted'
                 ) THEN
                RAISE EXCEPTION 'payout provider transfer reference is immutable';
              END IF;
              IF OLD.reservation_active IS DISTINCT FROM NEW.reservation_active
                 AND NOT (
                   OLD.reservation_active = true
                   AND NEW.reservation_active = false
                   AND NEW.status IN ('succeeded', 'failed', 'void')
                 ) THEN
                RAISE EXCEPTION 'payout reservation release is invalid';
              END IF;
              RETURN NEW;
            END;
            $$;
""",
    r"""
CREATE FUNCTION public.guard_payout_recovery_incident_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
            BEGIN
              IF ROW(
                NEW.ledger_entry_id, NEW.chain_root_line_id, NEW.exposure_line_id,
                NEW.source_fraud_flag_id, NEW.source_reversal_entry_id,
                NEW.created_by_user_id, NEW.kind, NEW.amount, NEW.currency,
                NEW.dedupe_key, NEW.created_at
              ) IS DISTINCT FROM ROW(
                OLD.ledger_entry_id, OLD.chain_root_line_id, OLD.exposure_line_id,
                OLD.source_fraud_flag_id, OLD.source_reversal_entry_id,
                OLD.created_by_user_id, OLD.kind, OLD.amount, OLD.currency,
                OLD.dedupe_key, OLD.created_at
              ) THEN
                RAISE EXCEPTION 'payout recovery incident identity is immutable';
              END IF;
              IF NOT (
                OLD.status = NEW.status
                OR (OLD.status = 'contingent' AND NEW.status IN ('debt_activated', 'closed'))
                OR (OLD.status = 'debt_activated' AND NEW.status = 'closed')
                OR (OLD.status = 'closed' AND NEW.status = 'debt_activated')
              ) THEN
                RAISE EXCEPTION 'payout recovery incident state transition is invalid';
              END IF;
              RETURN NEW;
            END;
            $$;
""",
    r"""
CREATE FUNCTION public.guard_payout_submission_intent_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
            BEGIN
              IF ROW(
                NEW.payout_batch_line_id,
                NEW.provider_name,
                NEW.idempotency_key,
                NEW.instruction,
                NEW.instruction_fingerprint,
                NEW.requested_by_user_id,
                NEW.created_at
              ) IS DISTINCT FROM ROW(
                OLD.payout_batch_line_id,
                OLD.provider_name,
                OLD.idempotency_key,
                OLD.instruction,
                OLD.instruction_fingerprint,
                OLD.requested_by_user_id,
                OLD.created_at
              ) THEN
                RAISE EXCEPTION 'payout submission intent identity is immutable';
              END IF;
              IF NOT (
                (OLD.state IN ('pending', 'query_only')
                  AND NEW.state = 'claimed' AND NEW.generation = OLD.generation + 1)
                OR (OLD.state = 'claimed' AND NEW.state = 'claimed'
                  AND NEW.generation = OLD.generation + 1)
                OR (OLD.state = 'claimed'
                  AND NEW.state IN ('pending', 'query_only', 'resolved')
                  AND NEW.generation = OLD.generation)
                OR (OLD.state = 'pending' AND NEW.state = 'cancelled' AND NEW.generation = OLD.generation)
              ) THEN
                RAISE EXCEPTION 'payout submission intent state transition is invalid';
              END IF;
              RETURN NEW;
            END;
            $$;
""",
    r"""
CREATE FUNCTION public.guard_quarantined_trip_batch_receipt() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          IF OLD.receipt_signature IS NOT NULL AND (
            NEW.trip_session_id IS DISTINCT FROM OLD.trip_session_id OR
            NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key OR
            NEW.batch_sequence IS DISTINCT FROM OLD.batch_sequence OR
            NEW.payload_hash_version IS DISTINCT FROM OLD.payload_hash_version OR
            NEW.payload_hash IS DISTINCT FROM OLD.payload_hash OR
            NEW.pings_submitted IS DISTINCT FROM OLD.pings_submitted OR
            NEW.pings_rejected IS DISTINCT FROM OLD.pings_rejected OR
            NEW.receipt_format_version IS DISTINCT FROM OLD.receipt_format_version OR
            NEW.receipt_key_version IS DISTINCT FROM OLD.receipt_key_version OR
            NEW.receipt_signature IS DISTINCT FROM OLD.receipt_signature OR
            NEW.receipt_outcome IS DISTINCT FROM OLD.receipt_outcome OR
            NEW.payload::jsonb IS DISTINCT FROM OLD.payload::jsonb OR
            NEW.ping_count IS DISTINCT FROM OLD.ping_count OR
            NEW.received_at IS DISTINCT FROM OLD.received_at
          ) THEN RAISE EXCEPTION 'quarantined trip batch receipt is immutable'; END IF;
          RETURN NEW;
        END; $$;
""",
    r"""
CREATE FUNCTION public.guard_report_publication_settlement() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          IF TG_OP='INSERT' THEN
            IF NEW.write_protocol IS DISTINCT FROM 1 THEN
              RAISE EXCEPTION 'report publication requires write_protocol 1';
            END IF;
            RETURN NEW;
          END IF;
          IF OLD.write_protocol <> NEW.write_protocol THEN
            RAISE EXCEPTION 'report publication write protocol is immutable';
          END IF;
          IF NEW.state IN ('cleaning', 'cleaned', 'complete') AND OLD.state <> NEW.state THEN
            IF EXISTS (SELECT 1 FROM report_publication_writes
              WHERE publication_intent_id=NEW.id AND state <> 'settled') THEN
              RAISE EXCEPTION 'unsettled report write blocks terminal publication or cleanup';
            END IF;
            IF NEW.state='complete' AND (SELECT count(*) FROM report_publication_writes
              WHERE publication_intent_id=NEW.id AND state='settled') <> 2 THEN
              RAISE EXCEPTION 'report publication requires both write receipts';
            END IF;
          END IF;
          RETURN NEW;
        END $$;
""",
    r"""
CREATE FUNCTION public.guard_report_publication_write() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE publication_state text; publication_protocol integer;
        BEGIN
          IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
            RAISE EXCEPTION 'report publication write receipts are append-only';
          END IF;
          IF TG_OP='INSERT' THEN
            SELECT state,write_protocol INTO publication_state,publication_protocol
              FROM report_publication_intents
              WHERE id=NEW.publication_intent_id FOR UPDATE;
            IF publication_state IS DISTINCT FROM 'publishing' OR
              publication_protocol IS DISTINCT FROM 1 OR NEW.state <> 'registered' THEN
              RAISE EXCEPTION 'report write requires a live publishing generation';
            END IF;
          ELSE
            IF OLD.state <> 'registered' OR NEW.state NOT IN ('settled', 'uncertain') OR
              (to_jsonb(NEW)-ARRAY['state','settled_at','error_code']) IS DISTINCT FROM
              (to_jsonb(OLD)-ARRAY['state','settled_at','error_code']) THEN
              RAISE EXCEPTION 'report publication write receipts cannot be restated';
            END IF;
          END IF;
          RETURN NEW;
        END $$;
""",
    r"""
CREATE FUNCTION public.guard_signed_location_ping() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          IF TG_OP = 'INSERT' THEN
            IF EXISTS (
              SELECT 1 FROM location_ping_batches
              WHERE id = NEW.batch_id AND receipt_signature IS NOT NULL
            ) THEN RAISE EXCEPTION 'signed trip ping evidence is immutable'; END IF;
            RETURN NEW;
          ELSIF TG_OP = 'DELETE' THEN
            IF EXISTS (
              SELECT 1 FROM location_ping_batches
              WHERE id = OLD.batch_id AND receipt_signature IS NOT NULL
            ) THEN RAISE EXCEPTION 'signed trip ping evidence is immutable'; END IF;
            RETURN OLD;
          END IF;
          IF EXISTS (
            SELECT 1 FROM location_ping_batches
            WHERE id IN (OLD.batch_id, NEW.batch_id) AND receipt_signature IS NOT NULL
          ) THEN RAISE EXCEPTION 'signed trip ping evidence is immutable'; END IF;
          RETURN NEW;
        END; $$;
""",
    r"""
CREATE FUNCTION public.guard_stored_object_deletion_receipt() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'stored-object deletion receipts are append-only';
          END IF;
          IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
             OR NEW.subject_user_id IS DISTINCT FROM OLD.subject_user_id
             OR NEW.owner_type IS DISTINCT FROM OLD.owner_type
             OR NEW.owner_id IS DISTINCT FROM OLD.owner_id
             OR NEW.storage_key IS DISTINCT FROM OLD.storage_key
             OR NEW.storage_key_sha256 IS DISTINCT FROM OLD.storage_key_sha256
             OR NEW.object_checksum_sha256 IS DISTINCT FROM OLD.object_checksum_sha256
             OR NEW.reason IS DISTINCT FROM OLD.reason
             OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint
             OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'stored-object deletion identity is immutable';
          END IF;
          IF NEW.state IS DISTINCT FROM OLD.state
             AND NOT (
               (OLD.state = 'pending' AND NEW.state = 'provider_deleted')
               OR (OLD.state = 'provider_deleted' AND NEW.state = 'completed')
             ) THEN
            RAISE EXCEPTION 'stored-object deletion state transition is invalid';
          END IF;
          IF NEW.state IS NOT DISTINCT FROM OLD.state
             AND (NEW.provider_deleted_at IS DISTINCT FROM OLD.provider_deleted_at
                  OR NEW.completed_at IS DISTINCT FROM OLD.completed_at) THEN
            RAISE EXCEPTION 'stored-object deletion receipt timestamps are write-once';
          END IF;
          IF OLD.state = 'pending' AND NEW.state = 'provider_deleted'
             AND (OLD.provider_deleted_at IS NOT NULL
                  OR NEW.provider_deleted_at IS NULL
                  OR NEW.completed_at IS DISTINCT FROM OLD.completed_at) THEN
            RAISE EXCEPTION 'stored-object deletion receipt timestamps are write-once';
          END IF;
          IF OLD.state = 'provider_deleted' AND NEW.state = 'completed'
             AND (OLD.completed_at IS NOT NULL
                  OR NEW.completed_at IS NULL
                  OR NEW.provider_deleted_at IS DISTINCT FROM OLD.provider_deleted_at) THEN
            RAISE EXCEPTION 'stored-object deletion receipt timestamps are write-once';
          END IF;
          RETURN NEW;
        END;
        $$;
""",
    r"""
CREATE FUNCTION public.guard_trip_batch_receipt() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            IF OLD.receipt_signature IS NOT NULL AND (
              EXISTS (SELECT 1 FROM location_pings WHERE batch_id = OLD.id) OR
              NOT EXISTS (
                SELECT 1 FROM data_purge_audit
                WHERE event = 'dropped'
                  AND range_from IS NOT NULL
                  AND range_to IS NOT NULL
                  AND OLD.received_at >= range_from
                  AND OLD.received_at < range_to
              )
            )
            THEN RAISE EXCEPTION 'trip batch receipt is immutable'; END IF;
            RETURN OLD;
          END IF;
          IF OLD.receipt_signature IS NOT NULL AND (
            NEW.trip_session_id IS DISTINCT FROM OLD.trip_session_id OR
            NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key OR
            NEW.batch_sequence IS DISTINCT FROM OLD.batch_sequence OR
            NEW.payload_hash_version IS DISTINCT FROM OLD.payload_hash_version OR
            NEW.payload_hash IS DISTINCT FROM OLD.payload_hash OR
            NEW.pings_submitted IS DISTINCT FROM OLD.pings_submitted OR
            NEW.pings_accepted IS DISTINCT FROM OLD.pings_accepted OR
            NEW.pings_rejected IS DISTINCT FROM OLD.pings_rejected OR
            NEW.evidence_scope IS DISTINCT FROM OLD.evidence_scope OR
            NEW.receipt_format_version IS DISTINCT FROM OLD.receipt_format_version OR
            NEW.receipt_key_version IS DISTINCT FROM OLD.receipt_key_version OR
            NEW.receipt_signature IS DISTINCT FROM OLD.receipt_signature OR
            NEW.receipt_outcome IS DISTINCT FROM OLD.receipt_outcome OR
            NEW.received_at IS DISTINCT FROM OLD.received_at OR
            NEW.metadata IS DISTINCT FROM OLD.metadata
          ) THEN RAISE EXCEPTION 'trip batch receipt is immutable'; END IF;
          RETURN NEW;
        END; $$;
""",
    r"""
CREATE FUNCTION public.guard_trip_evidence_manifest() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          IF OLD.evidence_manifest_root_sha256 IS NOT NULL AND (
            NEW.evidence_manifest_version IS DISTINCT FROM OLD.evidence_manifest_version OR
            NEW.evidence_manifest_root_sha256 IS DISTINCT FROM OLD.evidence_manifest_root_sha256 OR
            NEW.evidence_manifest_batch_count IS DISTINCT FROM OLD.evidence_manifest_batch_count OR
            NEW.evidence_manifest_ping_count IS DISTINCT FROM OLD.evidence_manifest_ping_count OR
            NEW.evidence_manifest_committed_at IS DISTINCT FROM OLD.evidence_manifest_committed_at
          ) THEN RAISE EXCEPTION 'trip evidence manifest header is immutable'; END IF;
          IF OLD.evidence_manifest_complete AND NOT NEW.evidence_manifest_complete
          THEN RAISE EXCEPTION 'trip evidence completeness is one-way'; END IF;
          IF OLD.evidence_manifest_verified_at IS NOT NULL AND (
            NEW.evidence_manifest_verified_at IS DISTINCT FROM OLD.evidence_manifest_verified_at OR
            NEW.evidence_manifest_receipt_format_version IS DISTINCT FROM
              OLD.evidence_manifest_receipt_format_version OR
            NEW.evidence_manifest_receipt_key_version IS DISTINCT FROM
              OLD.evidence_manifest_receipt_key_version OR
            NEW.evidence_manifest_receipt_signature IS DISTINCT FROM
              OLD.evidence_manifest_receipt_signature
          ) THEN RAISE EXCEPTION 'trip evidence verification receipt is immutable'; END IF;
          IF OLD.grace_expired_at IS NOT NULL AND
             NEW.grace_expired_at IS DISTINCT FROM OLD.grace_expired_at
          THEN RAISE EXCEPTION 'trip evidence grace marker is immutable'; END IF;
          RETURN NEW;
        END; $$;
""",
    r"""
CREATE FUNCTION public.prevent_assignment_activity_flag_event_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'assignment activity flag evidence is append-only'; END; $$;
""",
    r"""
CREATE FUNCTION public.prevent_assignment_rule_binding_evidence_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            IF to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
                RAISE EXCEPTION 'assignment rule binding evidence is immutable';
            END IF;
            RETURN NEW;
        END;
        $$;
""",
    r"""
CREATE FUNCTION public.prevent_campaign_activation_event_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'campaign activation events are append-only'; END; $$;
""",
    r"""
CREATE FUNCTION public.prevent_campaign_assignment_offer_evidence_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN IF OLD.offer_terms::text IS DISTINCT FROM NEW.offer_terms::text OR OLD.offer_terms_sha256 IS DISTINCT FROM NEW.offer_terms_sha256 OR OLD.expires_at IS DISTINCT FROM NEW.expires_at OR (OLD.status IN ('accepted', 'declined', 'expired', 'active', 'deactivated', 'cancelled', 'completed') AND (OLD.accepted_at IS DISTINCT FROM NEW.accepted_at OR OLD.declined_at IS DISTINCT FROM NEW.declined_at OR OLD.expired_at IS DISTINCT FROM NEW.expired_at)) THEN RAISE EXCEPTION 'campaign assignment offer evidence is immutable'; END IF; RETURN NEW; END; $$;
""",
    r"""
CREATE FUNCTION public.prevent_retargeting_source_event_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            RAISE EXCEPTION 'retargeting_source_events are append-only';
        END;
        $$;
""",
    r"""
CREATE FUNCTION public.prevent_retargeting_source_link_event_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'retargeting_source_link_events are append-only'; END; $$;
""",
    r"""
CREATE FUNCTION public.protect_issued_invoice() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          IF TG_OP = 'DELETE' OR OLD.issued_at IS NOT NULL THEN
            RAISE EXCEPTION 'issued invoice is immutable';
          END IF;
          RETURN NEW;
        END;
        $$;
""",
    r"""
CREATE FUNCTION public.reject_audience_delivery_approval_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'audience delivery approvals are append-only'; END; $$;
""",
    r"""
CREATE FUNCTION public.reject_audience_delivery_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'audience delivery receipts are append-only'; END; $$;
""",
    r"""
CREATE FUNCTION public.reject_audit_subject_resolution_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN
          RAISE EXCEPTION 'audit subject resolutions are append-only';
        END $$;
""",
    r"""
CREATE FUNCTION public.reject_commercial_authority_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          RAISE EXCEPTION 'commercial quotation authority is append-only';
        END;
        $$;
""",
    r"""
CREATE FUNCTION public.reject_data_purge_audit_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
            BEGIN
                RAISE EXCEPTION 'data purge audit is immutable' USING ERRCODE = '55000';
                RETURN NULL;
            END;
            $$;
""",
    r"""
CREATE FUNCTION public.reject_data_subject_assessment_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          RAISE EXCEPTION 'data subject location assessments are append-only';
        END;
        $$;
""",
    r"""
CREATE FUNCTION public.reject_driver_kyc_review_decision_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'driver KYC review decisions are append-only'; END; $$;
""",
    r"""
CREATE FUNCTION public.reject_exposure_score_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'exposure scores are append-only'; END; $$;
""",
    r"""
CREATE FUNCTION public.reject_exposure_segment_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'exposure segment evidence is append-only'; END; $$;
""",
    r"""
CREATE FUNCTION public.reject_location_ping_batch_disposition_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
            BEGIN
              IF (OLD.receipt_signature IS NOT NULL OR OLD.rejection_digest IS NOT NULL)
                 AND (NEW.rejection_digest, NEW.rejection_manifest)
                     IS DISTINCT FROM (OLD.rejection_digest, OLD.rejection_manifest) THEN
                RAISE EXCEPTION USING ERRCODE = '55000',
                  MESSAGE = 'location ping batch dispositions are immutable';
              END IF;
              RETURN NEW;
            END;
            $$;
""",
    r"""
CREATE FUNCTION public.reject_measurement_evidence_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          RAISE EXCEPTION 'measurement evidence is append-only';
        END;
        $$;
""",
    r"""
CREATE FUNCTION public.reject_notification_delivery_receipt_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          RAISE EXCEPTION 'notification delivery receipts are append-only';
        END;
        $$;
""",
    r"""
CREATE FUNCTION public.reject_notification_evidence_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'notification evidence is append-only';
          END IF;
          IF NEW.recipient_user_id IS DISTINCT FROM OLD.recipient_user_id
             OR NEW.type_key IS DISTINCT FROM OLD.type_key
             OR NEW.template_version IS DISTINCT FROM OLD.template_version
             OR NEW.channel IS DISTINCT FROM OLD.channel
             OR NEW.payload IS DISTINCT FROM OLD.payload
             OR NEW.dedupe_key IS DISTINCT FROM OLD.dedupe_key
             OR NEW.dedupe_fingerprint IS DISTINCT FROM OLD.dedupe_fingerprint
             OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'notification evidence fields are immutable';
          END IF;
          RETURN NEW;
        END;
        $$;
""",
    r"""
CREATE FUNCTION public.reject_payee_payout_verification_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'payout bank-account verifications are append-only'; END; $$;
""",
    r"""
CREATE FUNCTION public.reject_payout_authority_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
            BEGIN
              RAISE EXCEPTION USING ERRCODE = '55000',
                MESSAGE = TG_TABLE_NAME || ' is immutable payout authority';
            END;
            $$;
""",
    r"""
CREATE FUNCTION public.reject_payout_submission_history_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
            BEGIN
              RAISE EXCEPTION 'payout submission history is append-only';
            END;
            $$;
""",
    r"""
CREATE FUNCTION public.reject_receipt_authority_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          RAISE EXCEPTION 'receipt authority is append-only';
        END;
        $$;
""",
    r"""
CREATE FUNCTION public.reject_reference_to_deleting_stored_object() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          PERFORM id FROM stored_files WHERE id = NEW.stored_file_id FOR UPDATE;
          IF EXISTS (
            SELECT 1 FROM stored_object_deletions
            WHERE stored_file_id = NEW.stored_file_id AND state <> 'completed'
          ) THEN
            RAISE EXCEPTION 'stored object has an active deletion intent';
          END IF;
          RETURN NEW;
        END;
        $$;
""",
    r"""
CREATE FUNCTION public.reject_report_artifact_file_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN IF EXISTS (SELECT 1 FROM report_artifacts WHERE stored_file_id = OLD.id) THEN RAISE EXCEPTION 'report artifact stored file is immutable'; END IF; IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; RETURN NEW; END; $$;
""",
    r"""
CREATE FUNCTION public.reject_report_artifact_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'report artifacts are immutable'; END; $$;
""",
    r"""
CREATE FUNCTION public.reject_report_issuance_delete() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'report issuances are append-only'; END; $$;
""",
    r"""
CREATE FUNCTION public.reject_report_issuance_frozen_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN IF ROW(NEW.organization_id, NEW.campaign_id, NEW.measurement_run_id, NEW.requested_by_user_id, NEW.client_request_id, NEW.request_fingerprint, NEW.reissue_of_id, NEW.version, NEW.snapshot, NEW.snapshot_sha256, NEW.authority_fingerprint, NEW.input_manifest_sha256, NEW.result_manifest_sha256, NEW.proof_manifest_sha256, NEW.report_snapshot_sha256, NEW.schema_version, NEW.renderer_version, NEW.method_revision, NEW.roi_decision, NEW.synthetic, NEW.created_at) IS DISTINCT FROM ROW(OLD.organization_id, OLD.campaign_id, OLD.measurement_run_id, OLD.requested_by_user_id, OLD.client_request_id, OLD.request_fingerprint, OLD.reissue_of_id, OLD.version, OLD.snapshot, OLD.snapshot_sha256, OLD.authority_fingerprint, OLD.input_manifest_sha256, OLD.result_manifest_sha256, OLD.proof_manifest_sha256, OLD.report_snapshot_sha256, OLD.schema_version, OLD.renderer_version, OLD.method_revision, OLD.roi_decision, OLD.synthetic, OLD.created_at) THEN RAISE EXCEPTION 'report issuance frozen authority is immutable'; END IF; RETURN NEW; END; $$;
""",
    r"""
CREATE FUNCTION public.reject_report_publication_delete() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'report publication generations are append-only'; END; $$;
""",
    r"""
CREATE FUNCTION public.reject_report_publication_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN IF ROW(NEW.report_issuance_id, NEW.generation, NEW.csv_object_key, NEW.pdf_object_key, NEW.created_at) IS DISTINCT FROM ROW(OLD.report_issuance_id, OLD.generation, OLD.csv_object_key, OLD.pdf_object_key, OLD.created_at) THEN RAISE EXCEPTION 'report publication generation identity is immutable'; END IF; IF NEW.state IS DISTINCT FROM OLD.state AND NOT ( (OLD.state = 'prepared' AND NEW.state = 'publishing') OR (OLD.state = 'prepared' AND NEW.state = 'abandoned') OR (OLD.state = 'publishing' AND NEW.state = 'complete') OR (OLD.state = 'publishing' AND NEW.state = 'abandoned') OR (OLD.state = 'abandoned' AND NEW.state = 'cleaning') OR (OLD.state = 'cleaning' AND NEW.state = 'cleaned') OR (OLD.state = 'cleaning' AND NEW.state = 'abandoned') ) THEN RAISE EXCEPTION 'report publication state transition is invalid'; END IF; RETURN NEW; END; $$;
""",
    r"""
CREATE FUNCTION public.reject_traffic_density_profile_revision_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
            BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION USING ERRCODE = '55000',
                  MESSAGE = 'traffic density profile revisions cannot be deleted';
              END IF;
              IF ROW(NEW.id, NEW.lineage_id, NEW.revision, NEW.effective_from, NEW.supersedes_id, NEW.value_fingerprint, NEW.name, NEW.description, NEW.profile_type, NEW.traffic_density_per_km, NEW.dwell_impressions_per_minute, NEW.road_category_weight, NEW.morning_weight, NEW.midday_weight, NEW.evening_weight, NEW.night_weight, NEW.target_zone_weight, NEW.bonus_zone_weight, NEW.exclusion_zone_weight, NEW.metadata)
                 IS DISTINCT FROM ROW(OLD.id, OLD.lineage_id, OLD.revision, OLD.effective_from, OLD.supersedes_id, OLD.value_fingerprint, OLD.name, OLD.description, OLD.profile_type, OLD.traffic_density_per_km, OLD.dwell_impressions_per_minute, OLD.road_category_weight, OLD.morning_weight, OLD.midday_weight, OLD.evening_weight, OLD.night_weight, OLD.target_zone_weight, OLD.bonus_zone_weight, OLD.exclusion_zone_weight, OLD.metadata) THEN
                RAISE EXCEPTION USING ERRCODE = '55000',
                  MESSAGE = 'traffic density profile revision values are immutable';
              END IF;
              RETURN NEW;
            END;
            $$;
""",
    r"""
CREATE FUNCTION public.reject_trip_evidence_adjudication_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
            BEGIN
              IF OLD.evidence_adjudicated_at IS NOT NULL
                 AND (
                   NEW.evidence_adjudicated_at,
                   NEW.evidence_adjudication_outcome,
                   NEW.evidence_adjudication_receipt_format_version,
                   NEW.evidence_adjudication_receipt_key_version,
                   NEW.evidence_adjudication_receipt_signature
                 ) IS DISTINCT FROM (
                   OLD.evidence_adjudicated_at,
                   OLD.evidence_adjudication_outcome,
                   OLD.evidence_adjudication_receipt_format_version,
                   OLD.evidence_adjudication_receipt_key_version,
                   OLD.evidence_adjudication_receipt_signature
                 ) THEN
                RAISE EXCEPTION USING ERRCODE = '55000',
                  MESSAGE = 'trip evidence adjudications are immutable';
              END IF;
              RETURN NEW;
            END;
            $$;
""",
    r"""
CREATE FUNCTION public.reject_trip_manifest_entry_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        DECLARE
          committed_at_value timestamptz;
        BEGIN
          IF TG_OP = 'INSERT' THEN
            SELECT evidence_manifest_committed_at INTO committed_at_value
            FROM trip_sessions
            WHERE id = NEW.trip_session_id
            FOR UPDATE;
            IF committed_at_value IS NOT NULL
            THEN RAISE EXCEPTION 'trip evidence manifest entries are immutable'; END IF;
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'trip evidence manifest entries are immutable';
        END;
        $$;
""",
    r"""
CREATE FUNCTION public.reject_vehicle_evidence_document_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'vehicle evidence documents are immutable'; END; $$;
""",
    r"""
CREATE FUNCTION public.reject_vehicle_evidence_snapshot_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN IF OLD.purged_at IS NULL AND NEW.purged_at IS NOT NULL THEN RETURN NEW; END IF; IF ROW(NEW.vehicle_id, NEW.version, NEW.client_request_id, NEW.created_by_user_id, NEW.snapshot_trusted, NEW.plate_number_snapshot, NEW.plate_number_normalized_snapshot, NEW.plate_country_code_snapshot, NEW.vehicle_type_snapshot, NEW.make_snapshot, NEW.model_snapshot, NEW.year_snapshot, NEW.color_snapshot) IS DISTINCT FROM ROW(OLD.vehicle_id, OLD.version, OLD.client_request_id, OLD.created_by_user_id, OLD.snapshot_trusted, OLD.plate_number_snapshot, OLD.plate_number_normalized_snapshot, OLD.plate_country_code_snapshot, OLD.vehicle_type_snapshot, OLD.make_snapshot, OLD.model_snapshot, OLD.year_snapshot, OLD.color_snapshot) THEN RAISE EXCEPTION 'vehicle evidence snapshots are immutable'; END IF; RETURN NEW; END; $$;
""",
    r"""
CREATE FUNCTION public.reject_vehicle_review_decision_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$ BEGIN RAISE EXCEPTION 'vehicle review decisions are append-only'; END; $$;
""",
    r"""
CREATE FUNCTION public.validate_data_subject_request_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'data subject requests are append-only evidence';
          END IF;
          IF NEW.id IS DISTINCT FROM OLD.id
             OR NEW.subject_user_id IS DISTINCT FROM OLD.subject_user_id
             OR NEW.request_type IS DISTINCT FROM OLD.request_type
             OR NEW.opened_by_user_id IS DISTINCT FROM OLD.opened_by_user_id
             OR NEW.client_request_id IS DISTINCT FROM OLD.client_request_id
             OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint
             OR NEW.requested_at IS DISTINCT FROM OLD.requested_at
             OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'data subject request identity is immutable';
          END IF;
          IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
            (OLD.status = 'open' AND NEW.status = 'identity_verified') OR
            (OLD.status = 'identity_verified' AND NEW.status = 'completed')
          ) THEN
            RAISE EXCEPTION 'invalid data subject request status transition';
          END IF;
          IF OLD.identity_verified_at IS NOT NULL AND (
             NEW.identity_verified_at IS DISTINCT FROM OLD.identity_verified_at OR
             NEW.identity_verified_by_user_id IS DISTINCT FROM OLD.identity_verified_by_user_id
          ) THEN
            RAISE EXCEPTION 'identity verification evidence is immutable';
          END IF;
          IF OLD.completed_at IS NOT NULL AND (
             NEW.completed_at IS DISTINCT FROM OLD.completed_at OR
             NEW.completed_by_user_id IS DISTINCT FROM OLD.completed_by_user_id
          ) THEN
            RAISE EXCEPTION 'completion evidence is immutable';
          END IF;
          RETURN NEW;
        END;
        $$;
""",
    r"""
CREATE FUNCTION public.validate_traffic_density_profile_revision() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
            DECLARE predecessor traffic_density_profiles%ROWTYPE;
            BEGIN
              IF NEW.revision = 1 THEN
                IF NEW.supersedes_id IS NOT NULL OR NEW.lineage_id <> NEW.id THEN
                  RAISE EXCEPTION USING ERRCODE = '23514',
                    CONSTRAINT = 'ck_traffic_density_profiles_revision_lineage',
                    MESSAGE = 'revision 1 must begin its own lineage';
                END IF;
                RETURN NEW;
              END IF;

              IF NEW.supersedes_id IS NULL THEN
                RAISE EXCEPTION USING ERRCODE = '23514',
                  CONSTRAINT = 'ck_traffic_density_profiles_revision_lineage',
                  MESSAGE = 'successor revision requires a predecessor';
              END IF;
              SELECT * INTO predecessor
              FROM traffic_density_profiles
              WHERE id = NEW.supersedes_id
              FOR UPDATE;
              IF NOT FOUND
                 OR predecessor.lineage_id <> NEW.lineage_id
                 OR NEW.revision <> predecessor.revision + 1
                 OR NEW.effective_from <= predecessor.effective_from THEN
                RAISE EXCEPTION USING ERRCODE = '23514',
                  CONSTRAINT = 'ck_traffic_density_profiles_revision_lineage',
                  MESSAGE = 'successor revision must be monotonic in its lineage';
              END IF;
              RETURN NEW;
            END;
            $$;
""",
    r"""
SET default_tablespace = '';
""",
    r"""
SET default_table_access_method = heap;
""",
    r"""
CREATE TABLE public.advertiser_organization_notification_preferences (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    advertiser_organization_id uuid NOT NULL,
    transactional_email_enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
""",
    r"""
CREATE TABLE public.advertiser_organizations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(255) NOT NULL,
    billing_email character varying(255),
    country_code character varying(2),
    currency character varying(3) DEFAULT 'NGN'::character varying NOT NULL,
    status character varying(32) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    address_line_1 character varying(255),
    address_line_2 character varying(255),
    address_city character varying(128),
    address_region character varying(128),
    address_postal_code character varying(32),
    address_country_code character varying(2),
    industry character varying(128),
    operational_contact_name character varying(255),
    operational_contact_email character varying(255),
    operational_contact_phone character varying(32),
    billing_contact_name character varying(255),
    billing_contact_phone character varying(32),
    profile_notes text,
    CONSTRAINT ck_advertiser_organizations_status CHECK (status IN ('active', 'suspended', 'disabled'))
);
""",
    r"""
CREATE TABLE public.assignment_activity_flag_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    flag_id uuid NOT NULL,
    assignment_id uuid NOT NULL,
    sequence_number integer NOT NULL,
    event_type character varying(16) NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    observed_seconds integer NOT NULL,
    evidence json DEFAULT '{}'::json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_assignment_activity_flag_events_observed CHECK ((observed_seconds >= 0)),
    CONSTRAINT ck_assignment_activity_flag_events_sequence CHECK ((sequence_number > 0)),
    CONSTRAINT ck_assignment_activity_flag_events_type CHECK (event_type IN ('opened', 'recovered'))
);
""",
    r"""
CREATE TABLE public.assignment_activity_flags (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    assignment_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    driver_profile_id uuid NOT NULL,
    vehicle_id uuid NOT NULL,
    flag_type character varying(32) NOT NULL,
    status character varying(16) DEFAULT 'open'::character varying NOT NULL,
    window_start timestamp with time zone NOT NULL,
    window_end timestamp with time zone NOT NULL,
    threshold_seconds integer,
    observed_seconds integer DEFAULT 0 NOT NULL,
    last_verified_activity_at timestamp with time zone,
    first_detected_at timestamp with time zone NOT NULL,
    last_evaluated_at timestamp with time zone NOT NULL,
    recovered_at timestamp with time zone,
    evidence json DEFAULT '{}'::json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_assignment_activity_flags_observed CHECK ((observed_seconds >= 0)),
    CONSTRAINT ck_assignment_activity_flags_recovery_coherence CHECK (((((status)::text = 'open'::text) AND (recovered_at IS NULL)) OR (((status)::text = 'recovered'::text) AND (recovered_at IS NOT NULL)))),
    CONSTRAINT ck_assignment_activity_flags_status CHECK (status IN ('open', 'recovered')),
    CONSTRAINT ck_assignment_activity_flags_threshold CHECK (((threshold_seconds IS NULL) OR (threshold_seconds > 0))),
    CONSTRAINT ck_assignment_activity_flags_type CHECK (flag_type IN ('verified_hours_floor', 'inactivity')),
    CONSTRAINT ck_assignment_activity_flags_window CHECK ((window_end > window_start))
);
""",
    r"""
CREATE TABLE public.assignment_rule_bindings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    assignment_id uuid NOT NULL,
    revision_id uuid NOT NULL,
    eligibility_params jsonb DEFAULT '{}'::jsonb NOT NULL,
    formula_version text NOT NULL,
    premium_zone_ids jsonb DEFAULT '[]'::jsonb NOT NULL,
    premium_zone_geometry_hash text NOT NULL,
    stationary_policy_marker text DEFAULT 'ext-rm2-fail-closed'::text NOT NULL,
    bound_at timestamp with time zone DEFAULT now() NOT NULL,
    resolved_eligibility_params jsonb,
    premium_zone_geometry_wkts jsonb DEFAULT '[]'::jsonb NOT NULL,
    exclusion_zone_ids jsonb DEFAULT '[]'::jsonb NOT NULL,
    exclusion_zone_geometry_hash text DEFAULT 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'::text NOT NULL,
    exclusion_zone_geometry_wkts jsonb DEFAULT '[]'::jsonb NOT NULL,
    campaign_window_start_at timestamp with time zone,
    campaign_window_end_at timestamp with time zone,
    campaign_window_frozen boolean DEFAULT false NOT NULL,
    offer_terms_sha256 character varying(64),
    currency character varying(3) NOT NULL,
    daily_rate_naira numeric(14,2),
    daily_target_miles numeric(10,3),
    shortfall_strategy text,
    deduction_per_mile_naira numeric(14,2),
    minimum_miles numeric(10,3),
    outside_area_weight numeric(5,4),
    CONSTRAINT ck_assignment_rule_bindings_currency CHECK (((length((currency)::text) = 3) AND ((currency)::text = upper((currency)::text)) AND (substr((currency)::text, 1, 1) = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text, 'F'::text, 'G'::text, 'H'::text, 'I'::text, 'J'::text, 'K'::text, 'L'::text, 'M'::text, 'N'::text, 'O'::text, 'P'::text, 'Q'::text, 'R'::text, 'S'::text, 'T'::text, 'U'::text, 'V'::text, 'W'::text, 'X'::text, 'Y'::text, 'Z'::text])) AND (substr((currency)::text, 2, 1) = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text, 'F'::text, 'G'::text, 'H'::text, 'I'::text, 'J'::text, 'K'::text, 'L'::text, 'M'::text, 'N'::text, 'O'::text, 'P'::text, 'Q'::text, 'R'::text, 'S'::text, 'T'::text, 'U'::text, 'V'::text, 'W'::text, 'X'::text, 'Y'::text, 'Z'::text])) AND (substr((currency)::text, 3, 1) = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text, 'F'::text, 'G'::text, 'H'::text, 'I'::text, 'J'::text, 'K'::text, 'L'::text, 'M'::text, 'N'::text, 'O'::text, 'P'::text, 'Q'::text, 'R'::text, 'S'::text, 'T'::text, 'U'::text, 'V'::text, 'W'::text, 'X'::text, 'Y'::text, 'Z'::text])))),
    CONSTRAINT ck_assignment_rule_bindings_terms_shape CHECK (((formula_version = 'payout_v4'::text) AND (daily_rate_naira IS NOT NULL) AND (daily_target_miles IS NOT NULL) AND (minimum_miles IS NOT NULL) AND (outside_area_weight IS NOT NULL) AND (shortfall_strategy IS NOT NULL) AND (daily_rate_naira > (0)::numeric) AND (daily_target_miles > (0)::numeric) AND (minimum_miles >= (0)::numeric) AND (minimum_miles <= daily_target_miles) AND (outside_area_weight >= (0)::numeric) AND (outside_area_weight <= (1)::numeric) AND (((shortfall_strategy = 'proportional'::text) AND (deduction_per_mile_naira IS NULL)) OR ((shortfall_strategy = 'per_mile_deduction'::text) AND (deduction_per_mile_naira IS NOT NULL) AND (deduction_per_mile_naira > (0)::numeric)))))
);
""",
    r"""
CREATE TABLE public.audience_deliveries (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    segment_id uuid NOT NULL,
    actor_user_id uuid NOT NULL,
    operation character varying(32) NOT NULL,
    idempotency_key character varying(255) NOT NULL,
    request_fingerprint character varying(64) NOT NULL,
    payload jsonb NOT NULL,
    payload_sha256 character varying(64) NOT NULL,
    result jsonb NOT NULL,
    result_sha256 character varying(64) NOT NULL,
    adapter_name character varying(64) NOT NULL,
    synthetic boolean DEFAULT false NOT NULL,
    status character varying(16) DEFAULT 'completed'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    approval_id uuid,
    approval_snapshot_sha256 character varying(64),
    purpose_code character varying(64),
    CONSTRAINT ck_audience_deliveries_approval_cluster CHECK ((((approval_id IS NULL) AND (approval_snapshot_sha256 IS NULL) AND (purpose_code IS NULL)) OR ((approval_id IS NOT NULL) AND (approval_snapshot_sha256 IS NOT NULL) AND (purpose_code IS NOT NULL) AND (length((approval_snapshot_sha256)::text) = 64) AND (length(TRIM(BOTH FROM purpose_code)) > 0)))),
    CONSTRAINT ck_audience_deliveries_fingerprints CHECK (((length((request_fingerprint)::text) = 64) AND (length((payload_sha256)::text) = 64) AND (length((result_sha256)::text) = 64))),
    CONSTRAINT ck_audience_deliveries_operation CHECK (operation IN ('csv_export', 'ad_platform_activation')),
    CONSTRAINT ck_audience_deliveries_status CHECK (((status)::text = 'completed'::text))
);
""",
    r"""
CREATE TABLE public.audience_delivery_approvals (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    segment_id uuid NOT NULL,
    approved_by_user_id uuid NOT NULL,
    operation character varying(32) NOT NULL,
    purpose_code character varying(64) NOT NULL,
    provider character varying(64) NOT NULL,
    provider_account_reference character varying(255),
    budget_ceiling numeric(20,2),
    legal_approval_reference character varying(255) NOT NULL,
    idempotency_key character varying(255) NOT NULL,
    request_fingerprint character varying(64) NOT NULL,
    snapshot jsonb NOT NULL,
    snapshot_sha256 character varying(64) NOT NULL,
    synthetic boolean DEFAULT false NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_until timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_audience_delivery_approvals_fingerprints CHECK (((length((request_fingerprint)::text) = 64) AND (length((snapshot_sha256)::text) = 64))),
    CONSTRAINT ck_audience_delivery_approvals_operation CHECK (operation IN ('csv_export', 'ad_platform_activation')),
    CONSTRAINT ck_audience_delivery_approvals_operation_fields CHECK (((((operation)::text = 'csv_export'::text) AND ((purpose_code)::text = 'aggregate_campaign_planning'::text) AND ((provider)::text = 'controlled-csv-v1'::text) AND (provider_account_reference IS NULL) AND (budget_ceiling IS NULL)) OR (((operation)::text = 'ad_platform_activation'::text) AND ((purpose_code)::text = 'aggregate_contextual_activation'::text) AND (provider_account_reference IS NOT NULL) AND (budget_ceiling >= (0)::numeric)))),
    CONSTRAINT ck_audience_delivery_approvals_window CHECK ((valid_from < valid_until))
);
""",
    r"""
CREATE TABLE public.audit_event_subject_resolutions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    audit_event_id uuid NOT NULL,
    role character varying(8) NOT NULL,
    subject_user_id uuid,
    outcome character varying(16) NOT NULL,
    CONSTRAINT ck_audit_subject_resolution_outcome CHECK (((((outcome)::text = 'resolved'::text) AND (subject_user_id IS NOT NULL)) OR (((outcome)::text = 'not_recorded'::text) AND ((role)::text = 'actor'::text) AND (subject_user_id IS NULL)) OR (((outcome)::text = 'unresolved'::text) AND ((role)::text = 'target'::text) AND (subject_user_id IS NULL)))),
    CONSTRAINT ck_audit_subject_resolution_role CHECK (role IN ('actor', 'target'))
);
""",
    r"""
CREATE TABLE public.audit_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    actor_user_id uuid,
    action character varying(255) NOT NULL,
    entity_type character varying(255) NOT NULL,
    entity_id text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
""",
    r"""
CREATE TABLE public.budget_campaign_transitions (
    id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    evaluation_id uuid NOT NULL,
    action character varying(16) NOT NULL,
    prior_status character varying(32) NOT NULL,
    new_status character varying(32) NOT NULL,
    actor_user_id uuid,
    reason text,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_budget_transitions_action CHECK (action IN ('pause', 'resume')),
    CONSTRAINT ck_budget_transitions_authority CHECK (((((action)::text = 'pause'::text) AND (actor_user_id IS NULL) AND ((new_status)::text = 'paused'::text)) OR (((action)::text = 'resume'::text) AND (actor_user_id IS NOT NULL) AND ((prior_status)::text = 'paused'::text) AND (length(TRIM(BOTH FROM reason)) > 0)))),
    CONSTRAINT ck_budget_transitions_statuses CHECK (prior_status IN ('scheduled', 'active', 'paused') AND new_status IN ('scheduled', 'active', 'paused') AND prior_status <> new_status)
);
""",
    r"""
CREATE TABLE public.budget_policy_evaluations (
    id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    evaluation_key character varying(64) NOT NULL,
    state character varying(40) NOT NULL,
    external_gate character varying(64),
    campaign_budget_amount numeric(14,2),
    campaign_daily_budget_amount numeric(14,2),
    currency character varying(3) NOT NULL,
    policy_revision character varying(128),
    billing_spend_amount numeric(14,2),
    alert_threshold_amount numeric(14,2),
    pause_threshold_amount numeric(14,2),
    pause_applied boolean NOT NULL,
    evaluated_at timestamp with time zone NOT NULL,
    policy_id character varying(128),
    policy_source character varying(32),
    budget_basis character varying(16),
    billing_fact_source character varying(32),
    resume_threshold_amount numeric(14,2),
    alert_applied boolean DEFAULT false NOT NULL,
    resume_allowed boolean DEFAULT false NOT NULL,
    urgent_threshold_amount numeric(14,2),
    CONSTRAINT ck_budget_policy_evaluations_authority_fields CHECK ((state = 'blocked_external_policy' AND policy_id IS NULL AND policy_revision IS NULL AND policy_source IS NULL AND budget_basis IS NULL AND billing_fact_source IS NULL AND billing_spend_amount IS NULL AND alert_threshold_amount IS NULL AND pause_threshold_amount IS NULL AND resume_threshold_amount IS NULL AND alert_applied = false AND pause_applied = false AND resume_allowed = false) OR (state <> 'blocked_external_policy' AND policy_id IS NOT NULL AND policy_revision IS NOT NULL AND policy_source IN ('external_approved', 'synthetic_test') AND budget_basis IN ('total', 'daily') AND billing_fact_source IN ('confirmed_funding', 'production_obligation') AND billing_spend_amount >= 0 AND alert_threshold_amount >= 0 AND pause_threshold_amount > alert_threshold_amount AND resume_threshold_amount <= alert_threshold_amount)),
    CONSTRAINT ck_budget_policy_evaluations_campaign_budget CHECK ((((campaign_budget_amount IS NOT NULL) OR (campaign_daily_budget_amount IS NOT NULL)) AND ((campaign_budget_amount IS NULL) OR (campaign_budget_amount >= (0)::numeric)) AND ((campaign_daily_budget_amount IS NULL) OR (campaign_daily_budget_amount >= (0)::numeric)))),
    CONSTRAINT ck_budget_policy_evaluations_currency CHECK ((length((currency)::text) = 3)),
    CONSTRAINT ck_budget_policy_evaluations_external_gate CHECK (((((state)::text = 'blocked_external_policy'::text) AND ((external_gate)::text = 'EXT-BUDGET-POLICY'::text)) OR (((state)::text <> 'blocked_external_policy'::text) AND (external_gate IS NULL)))),
    CONSTRAINT ck_budget_policy_evaluations_state CHECK (state IN ('blocked_external_policy', 'within_budget', 'alert_threshold', 'urgent_threshold', 'pause_threshold')),
    CONSTRAINT ck_budget_policy_evaluations_urgent CHECK ((state = 'blocked_external_policy' AND urgent_threshold_amount IS NULL) OR (state NOT IN ('blocked_external_policy', 'urgent_threshold') AND urgent_threshold_amount IS NULL) OR (state <> 'blocked_external_policy' AND urgent_threshold_amount IS NOT NULL AND urgent_threshold_amount > alert_threshold_amount AND urgent_threshold_amount < pause_threshold_amount))
);
""",
    r"""
CREATE TABLE public.campaign_activation_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    assignment_id uuid NOT NULL,
    actor_user_id uuid,
    event_type character varying(32) NOT NULL,
    previous_status character varying(32),
    new_status character varying(32) NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    offer_terms_sha256 character varying(64),
    CONSTRAINT ck_campaign_activation_events_accepted_status CHECK (event_type != 'accepted' OR new_status = 'accepted' OR (offer_terms_sha256 IS NULL AND new_status IN ('active', 'deactivated', 'cancelled', 'completed'))),
    CONSTRAINT ck_campaign_activation_events_declined_status CHECK ((((event_type)::text <> 'declined'::text) OR ((new_status)::text = 'declined'::text))),
    CONSTRAINT ck_campaign_activation_events_event_type CHECK (event_type IN ('assigned', 'accepted', 'declined', 'expired', 'activated', 'deactivated', 'cancelled', 'completed')),
    CONSTRAINT ck_campaign_activation_events_expired_status CHECK ((((event_type)::text <> 'expired'::text) OR ((new_status)::text = 'expired'::text)))
);
""",
    r"""
CREATE TABLE public.campaign_assignments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    campaign_id uuid NOT NULL,
    driver_profile_id uuid NOT NULL,
    vehicle_id uuid NOT NULL,
    assigned_by_user_id uuid NOT NULL,
    status character varying(32) NOT NULL,
    offered_at timestamp with time zone NOT NULL,
    accepted_at timestamp with time zone,
    activated_at timestamp with time zone,
    deactivated_at timestamp with time zone,
    cancelled_at timestamp with time zone,
    completed_at timestamp with time zone,
    notes text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone,
    declined_at timestamp with time zone,
    expired_at timestamp with time zone,
    offer_terms json,
    offer_terms_sha256 character varying(64),
    CONSTRAINT ck_campaign_assignments_accepted_status_coherence CHECK (accepted_at IS NULL OR status IN ('accepted', 'active', 'deactivated', 'cancelled', 'completed')),
    CONSTRAINT ck_campaign_assignments_accepted_timestamp CHECK ((((status)::text <> 'accepted'::text) OR (accepted_at IS NOT NULL) OR (offer_terms IS NULL))),
    CONSTRAINT ck_campaign_assignments_declined_status_coherence CHECK (((declined_at IS NULL) OR ((status)::text = 'declined'::text))),
    CONSTRAINT ck_campaign_assignments_declined_timestamp CHECK ((((status)::text <> 'declined'::text) OR (declined_at IS NOT NULL))),
    CONSTRAINT ck_campaign_assignments_expired_status_coherence CHECK (((expired_at IS NULL) OR ((status)::text = 'expired'::text))),
    CONSTRAINT ck_campaign_assignments_expired_timestamp CHECK ((((status)::text <> 'expired'::text) OR (expired_at IS NOT NULL))),
    CONSTRAINT ck_campaign_assignments_offer_snapshot_pair CHECK ((((status)::text <> 'offered'::text) OR ((offer_terms IS NULL) AND (offer_terms_sha256 IS NULL)) OR ((offer_terms IS NOT NULL) AND (offer_terms_sha256 IS NOT NULL)))),
    CONSTRAINT ck_campaign_assignments_status CHECK (status IN ('offered', 'accepted', 'declined', 'expired', 'active', 'deactivated', 'cancelled', 'completed'))
);
""",
    r"""
CREATE TABLE public.campaign_cancellation_settlement_revisions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    cancellation_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    revision_number integer NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    snapshot json NOT NULL,
    snapshot_sha256 character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_campaign_cancellation_settlement_revisions_digest CHECK ((length((snapshot_sha256)::text) = 64)),
    CONSTRAINT ck_campaign_cancellation_settlement_revisions_number CHECK ((revision_number > 0))
);
""",
    r"""
CREATE TABLE public.campaign_cancellations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    campaign_id uuid NOT NULL,
    organization_id uuid NOT NULL,
    requested_by_user_id uuid NOT NULL,
    client_request_id uuid NOT NULL,
    request_fingerprint character varying(64) NOT NULL,
    reason text NOT NULL,
    prior_status character varying(32) NOT NULL,
    cutoff_at timestamp with time zone NOT NULL,
    commercial_terms_id uuid,
    production_start_id uuid,
    funding_authorized_at timestamp with time zone,
    refund_eligibility_ends_at timestamp with time zone,
    disposition character varying(40) NOT NULL,
    refundable_amount numeric(14,2) NOT NULL,
    currency character varying(3) NOT NULL,
    released_liability_amount numeric(14,2) NOT NULL,
    cancelled_assignment_count integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_campaign_cancellations_amounts CHECK (((length((currency)::text) = 3) AND (refundable_amount >= (0)::numeric) AND (released_liability_amount >= (0)::numeric))),
    CONSTRAINT ck_campaign_cancellations_disposition CHECK (disposition IN ('cash_refund_due', 'cash_refund_not_due', 'credit_settlement_due', 'no_settlement')),
    CONSTRAINT ck_campaign_cancellations_prior_status CHECK (prior_status IN ('approved', 'scheduled', 'active', 'paused')),
    CONSTRAINT ck_campaign_cancellations_settlement_evidence CHECK (((((disposition)::text = 'cash_refund_due'::text) AND (commercial_terms_id IS NOT NULL) AND (funding_authorized_at IS NOT NULL) AND (refund_eligibility_ends_at IS NOT NULL) AND (cutoff_at < refund_eligibility_ends_at) AND (refundable_amount > (0)::numeric)) OR (((disposition)::text <> 'cash_refund_due'::text) AND (refundable_amount = (0)::numeric))))
);
""",
    r"""
CREATE TABLE public.campaign_change_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    campaign_id uuid NOT NULL,
    organization_id uuid NOT NULL,
    requested_by_user_id uuid NOT NULL,
    client_request_id uuid NOT NULL,
    request_fingerprint character varying(64) NOT NULL,
    proposed_changes json NOT NULL,
    classifications json NOT NULL,
    impact_preview json NOT NULL,
    status character varying(32) NOT NULL,
    requested_liability_amount numeric(14,2) NOT NULL,
    reserved_liability_amount numeric(14,2),
    authorization_id uuid,
    reviewed_by_user_id uuid,
    reviewed_at timestamp with time zone,
    review_reason text,
    applied_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_campaign_change_requests_applied_state CHECK (((((status)::text = 'applied'::text) AND (applied_at IS NOT NULL) AND (reserved_liability_amount IS NOT NULL)) OR (((status)::text <> 'applied'::text) AND (applied_at IS NULL)))),
    CONSTRAINT ck_campaign_change_requests_liability CHECK (((requested_liability_amount >= (0)::numeric) AND ((reserved_liability_amount IS NULL) OR (reserved_liability_amount >= (0)::numeric)))),
    CONSTRAINT ck_campaign_change_requests_rejected_state CHECK (((((status)::text = 'rejected'::text) AND (reviewed_by_user_id IS NOT NULL) AND (reviewed_at IS NOT NULL) AND (review_reason IS NOT NULL)) OR ((status)::text <> 'rejected'::text))),
    CONSTRAINT ck_campaign_change_requests_review_state CHECK ((((reviewed_by_user_id IS NULL) AND (reviewed_at IS NULL) AND (review_reason IS NULL)) OR ((reviewed_by_user_id IS NOT NULL) AND (reviewed_at IS NOT NULL) AND (review_reason IS NOT NULL) AND (length(TRIM(BOTH FROM review_reason)) > 0)))),
    CONSTRAINT ck_campaign_change_requests_status CHECK (status IN ('pending_admin', 'pending_funding', 'applied', 'rejected'))
);
""",
    r"""
CREATE TABLE public.campaign_change_revisions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    campaign_id uuid NOT NULL,
    request_id uuid NOT NULL,
    revision_number integer NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    snapshot json NOT NULL,
    snapshot_sha256 character varying(64) NOT NULL,
    applied_by_user_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_campaign_change_revisions_digest CHECK ((length((snapshot_sha256)::text) = 64)),
    CONSTRAINT ck_campaign_change_revisions_number CHECK ((revision_number > 0))
);
""",
    r"""
CREATE TABLE public.campaign_creatives (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    campaign_id uuid NOT NULL,
    name text NOT NULL,
    creative_type character varying(32) NOT NULL,
    placement character varying(32) NOT NULL,
    asset_url text,
    mime_type character varying(255),
    width_px integer,
    height_px integer,
    duration_seconds integer,
    checksum text,
    status character varying(32) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    stored_file_id uuid,
    CONSTRAINT ck_campaign_creatives_creative_type CHECK (creative_type IN ('image', 'video', 'html', 'text', 'other')),
    CONSTRAINT ck_campaign_creatives_duration_positive CHECK (((duration_seconds IS NULL) OR (duration_seconds > 0))),
    CONSTRAINT ck_campaign_creatives_height_positive CHECK (((height_px IS NULL) OR (height_px > 0))),
    CONSTRAINT ck_campaign_creatives_managed_asset_url CHECK (((stored_file_id IS NULL) OR (asset_url IS NULL))),
    CONSTRAINT ck_campaign_creatives_placement CHECK (placement IN ('vehicle_exterior', 'vehicle_interior', 'digital_screen', 'print', 'other')),
    CONSTRAINT ck_campaign_creatives_status CHECK (status IN ('draft', 'pending_review', 'approved', 'rejected', 'ready', 'archived')),
    CONSTRAINT ck_campaign_creatives_width_positive CHECK (((width_px IS NULL) OR (width_px > 0)))
);
""",
    r"""
CREATE TABLE public.campaign_financial_authorizations (
    id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    commercial_terms_id uuid NOT NULL,
    revision_number integer NOT NULL,
    authority_type character varying(32) NOT NULL,
    currency character varying(3) NOT NULL,
    authorized_amount numeric(14,2) NOT NULL,
    funded_cash_amount numeric(14,2) DEFAULT '0'::numeric NOT NULL,
    max_driver_liability numeric(14,2) NOT NULL,
    credit_limit numeric(14,2),
    credit_due_at timestamp with time zone,
    credit_approved_by_user_id uuid,
    credit_terms json,
    subsidy_reference text,
    effective_from timestamp with time zone NOT NULL,
    created_by_user_id uuid NOT NULL,
    reason text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_campaign_financial_authorizations_amounts CHECK (((authorized_amount > (0)::numeric) AND (max_driver_liability > (0)::numeric) AND (max_driver_liability <= authorized_amount))),
    CONSTRAINT ck_campaign_financial_authorizations_currency CHECK ((length((currency)::text) = 3)),
    CONSTRAINT ck_campaign_financial_authorizations_evidence CHECK (((((authority_type)::text = 'prepaid_cash'::text) AND (funded_cash_amount = authorized_amount) AND (credit_limit IS NULL) AND (credit_due_at IS NULL) AND (credit_approved_by_user_id IS NULL) AND (credit_terms IS NULL) AND (subsidy_reference IS NULL)) OR (((authority_type)::text = 'approved_credit'::text) AND (funded_cash_amount = (0)::numeric) AND (credit_limit = authorized_amount) AND (credit_due_at IS NOT NULL) AND (credit_approved_by_user_id IS NOT NULL) AND (credit_terms IS NOT NULL) AND (subsidy_reference IS NULL)) OR (((authority_type)::text = 'subsidy'::text) AND (funded_cash_amount = (0)::numeric) AND (credit_limit IS NULL) AND (credit_due_at IS NULL) AND (credit_approved_by_user_id IS NULL) AND (credit_terms IS NULL) AND (subsidy_reference IS NOT NULL)))),
    CONSTRAINT ck_campaign_financial_authorizations_revision CHECK ((revision_number > 0)),
    CONSTRAINT ck_campaign_financial_authorizations_type CHECK (authority_type IN ('prepaid_cash', 'approved_credit', 'subsidy'))
);
""",
    r"""
CREATE TABLE public.campaign_liability_reservations (
    id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    assignment_id uuid NOT NULL,
    assignment_rule_binding_id uuid NOT NULL,
    authorization_id uuid,
    status character varying(32) NOT NULL,
    covered_vehicle_days integer NOT NULL,
    hourly_rate numeric(14,2) NOT NULL,
    daily_hours_cap numeric(4,2) NOT NULL,
    requested_amount numeric(14,2) NOT NULL,
    reserved_amount numeric(14,2),
    requested_at timestamp with time zone NOT NULL,
    reserved_at timestamp with time zone,
    formula_version character varying(64) NOT NULL,
    released_at timestamp with time zone,
    release_cancellation_id uuid,
    CONSTRAINT ck_campaign_liability_reservations_formula CHECK (((covered_vehicle_days > 0) AND (hourly_rate >= (0)::numeric) AND (daily_hours_cap > (0)::numeric) AND (requested_amount > (0)::numeric) AND ((formula_version)::text <> ''::text))),
    CONSTRAINT ck_campaign_liability_reservations_state CHECK (((((status)::text = 'pending_funding'::text) AND (authorization_id IS NULL) AND (reserved_amount IS NULL) AND (reserved_at IS NULL) AND (released_at IS NULL) AND (release_cancellation_id IS NULL)) OR (((status)::text = 'reserved'::text) AND (authorization_id IS NOT NULL) AND (reserved_amount = requested_amount) AND (reserved_at IS NOT NULL) AND (released_at IS NULL) AND (release_cancellation_id IS NULL)) OR (((status)::text = 'released'::text) AND (released_at IS NOT NULL) AND (release_cancellation_id IS NOT NULL) AND (((authorization_id IS NULL) AND (reserved_amount IS NULL) AND (reserved_at IS NULL)) OR ((authorization_id IS NOT NULL) AND (reserved_amount = requested_amount) AND (reserved_at IS NOT NULL)))))),
    CONSTRAINT ck_campaign_liability_reservations_status CHECK (status IN ('pending_funding', 'reserved', 'released'))
);
""",
    r"""
CREATE TABLE public.campaign_payout_rule_revisions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    campaign_id uuid NOT NULL,
    payout_rule_id uuid NOT NULL,
    revision_number integer NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    eligibility_params jsonb DEFAULT '{}'::jsonb NOT NULL,
    formula_version text NOT NULL,
    reason text NOT NULL,
    created_by_user_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    currency character varying(3) NOT NULL,
    daily_rate_naira numeric(14,2),
    daily_target_miles numeric(10,3),
    shortfall_strategy text,
    deduction_per_mile_naira numeric(14,2),
    minimum_miles numeric(10,3),
    outside_area_weight numeric(5,4),
    CONSTRAINT ck_campaign_payout_rule_revisions_currency CHECK (((length((currency)::text) = 3) AND ((currency)::text = upper((currency)::text)) AND (substr((currency)::text, 1, 1) = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text, 'F'::text, 'G'::text, 'H'::text, 'I'::text, 'J'::text, 'K'::text, 'L'::text, 'M'::text, 'N'::text, 'O'::text, 'P'::text, 'Q'::text, 'R'::text, 'S'::text, 'T'::text, 'U'::text, 'V'::text, 'W'::text, 'X'::text, 'Y'::text, 'Z'::text])) AND (substr((currency)::text, 2, 1) = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text, 'F'::text, 'G'::text, 'H'::text, 'I'::text, 'J'::text, 'K'::text, 'L'::text, 'M'::text, 'N'::text, 'O'::text, 'P'::text, 'Q'::text, 'R'::text, 'S'::text, 'T'::text, 'U'::text, 'V'::text, 'W'::text, 'X'::text, 'Y'::text, 'Z'::text])) AND (substr((currency)::text, 3, 1) = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text, 'F'::text, 'G'::text, 'H'::text, 'I'::text, 'J'::text, 'K'::text, 'L'::text, 'M'::text, 'N'::text, 'O'::text, 'P'::text, 'Q'::text, 'R'::text, 'S'::text, 'T'::text, 'U'::text, 'V'::text, 'W'::text, 'X'::text, 'Y'::text, 'Z'::text])))),
    CONSTRAINT ck_campaign_payout_rule_revisions_number_ge_1 CHECK ((revision_number >= 1)),
    CONSTRAINT ck_campaign_payout_rule_revisions_terms_shape CHECK (((formula_version = 'payout_v4'::text) AND (daily_rate_naira IS NOT NULL) AND (daily_target_miles IS NOT NULL) AND (minimum_miles IS NOT NULL) AND (outside_area_weight IS NOT NULL) AND (shortfall_strategy IS NOT NULL) AND (daily_rate_naira > (0)::numeric) AND (daily_target_miles > (0)::numeric) AND (minimum_miles >= (0)::numeric) AND (minimum_miles <= daily_target_miles) AND (outside_area_weight >= (0)::numeric) AND (outside_area_weight <= (1)::numeric) AND (((shortfall_strategy = 'proportional'::text) AND (deduction_per_mile_naira IS NULL)) OR ((shortfall_strategy = 'per_mile_deduction'::text) AND (deduction_per_mile_naira IS NOT NULL) AND (deduction_per_mile_naira > (0)::numeric)))))
);
""",
    r"""
CREATE TABLE public.campaign_payout_rules (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    campaign_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL,
    updated_by_user_id uuid,
    formula_version text DEFAULT 'payout_v4'::text NOT NULL,
    status character varying(16) NOT NULL,
    currency character varying(3) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_campaign_payout_rules_currency CHECK (((length((currency)::text) = 3) AND ((currency)::text = upper((currency)::text)) AND (substr((currency)::text, 1, 1) = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text, 'F'::text, 'G'::text, 'H'::text, 'I'::text, 'J'::text, 'K'::text, 'L'::text, 'M'::text, 'N'::text, 'O'::text, 'P'::text, 'Q'::text, 'R'::text, 'S'::text, 'T'::text, 'U'::text, 'V'::text, 'W'::text, 'X'::text, 'Y'::text, 'Z'::text])) AND (substr((currency)::text, 2, 1) = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text, 'F'::text, 'G'::text, 'H'::text, 'I'::text, 'J'::text, 'K'::text, 'L'::text, 'M'::text, 'N'::text, 'O'::text, 'P'::text, 'Q'::text, 'R'::text, 'S'::text, 'T'::text, 'U'::text, 'V'::text, 'W'::text, 'X'::text, 'Y'::text, 'Z'::text])) AND (substr((currency)::text, 3, 1) = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text, 'F'::text, 'G'::text, 'H'::text, 'I'::text, 'J'::text, 'K'::text, 'L'::text, 'M'::text, 'N'::text, 'O'::text, 'P'::text, 'Q'::text, 'R'::text, 'S'::text, 'T'::text, 'U'::text, 'V'::text, 'W'::text, 'X'::text, 'Y'::text, 'Z'::text])))),
    CONSTRAINT ck_campaign_payout_rules_model_xor CHECK ((formula_version = 'payout_v4'::text)),
    CONSTRAINT ck_campaign_payout_rules_status CHECK (status IN ('active', 'inactive'))
);
""",
    r"""
CREATE TABLE public.campaign_review_events (
    id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    actor_user_id uuid NOT NULL,
    prior_status character varying(32) NOT NULL,
    new_status character varying(32) NOT NULL,
    rejection_reason text,
    reviewed_snapshot json,
    reviewed_snapshot_sha256 character varying(64),
    submission_event_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_campaign_review_events_new_status CHECK (new_status IN ('pending_review', 'approved', 'rejected')),
    CONSTRAINT ck_campaign_review_events_prior_status CHECK (prior_status IN ('draft', 'pending_review', 'approved', 'rejected', 'scheduled', 'active', 'paused', 'completed', 'cancelled')),
    CONSTRAINT ck_campaign_review_events_rejection_reason CHECK (((((new_status)::text = 'rejected'::text) AND (rejection_reason IS NOT NULL) AND (length(TRIM(BOTH FROM rejection_reason)) > 0)) OR (((new_status)::text <> 'rejected'::text) AND (rejection_reason IS NULL)))),
    CONSTRAINT ck_campaign_review_events_submission_binding CHECK ((new_status = 'pending_review' AND reviewed_snapshot IS NOT NULL AND reviewed_snapshot_sha256 IS NOT NULL AND submission_event_id IS NULL) OR (new_status IN ('approved', 'rejected') AND reviewed_snapshot IS NULL AND reviewed_snapshot_sha256 IS NULL AND submission_event_id IS NOT NULL))
);
""",
    r"""
CREATE TABLE public.campaign_zones (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    campaign_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL,
    name text NOT NULL,
    description text,
    zone_type text NOT NULL,
    geom public.geometry(MultiPolygon,4326) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_campaign_zones_zone_type CHECK ((zone_type = ANY (ARRAY['target'::text, 'exclusion'::text, 'bonus'::text])))
);
""",
    r"""
CREATE TABLE public.campaigns (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL,
    name text NOT NULL,
    description text,
    status character varying(32) NOT NULL,
    start_at timestamp with time zone,
    end_at timestamp with time zone,
    budget_amount numeric(14,2),
    daily_budget_amount numeric(14,2),
    currency character varying(3) DEFAULT 'NGN'::character varying NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_campaigns_budget_amount_non_negative CHECK (((budget_amount IS NULL) OR (budget_amount >= (0)::numeric))),
    CONSTRAINT ck_campaigns_currency_length CHECK ((char_length((currency)::text) = 3)),
    CONSTRAINT ck_campaigns_daily_budget_amount_non_negative CHECK (((daily_budget_amount IS NULL) OR (daily_budget_amount >= (0)::numeric))),
    CONSTRAINT ck_campaigns_daily_budget_not_exceed_budget CHECK (((budget_amount IS NULL) OR (daily_budget_amount IS NULL) OR (daily_budget_amount <= budget_amount))),
    CONSTRAINT ck_campaigns_date_range CHECK (((start_at IS NULL) OR (end_at IS NULL) OR (start_at < end_at))),
    CONSTRAINT ck_campaigns_status CHECK (status IN ('draft', 'pending_review', 'approved', 'rejected', 'scheduled', 'active', 'paused', 'completed', 'cancelled'))
);
""",
    r"""
CREATE TABLE public.commercial_quotation_revisions (
    id uuid NOT NULL,
    quote_request_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    organization_id uuid NOT NULL,
    revision_number integer NOT NULL,
    quote_reference character varying(128) NOT NULL,
    currency character varying(3) NOT NULL,
    line_items jsonb NOT NULL,
    production_scope jsonb NOT NULL,
    production_cost_amount numeric(14,2) NOT NULL,
    payment_class character varying(40) NOT NULL,
    payment_terms jsonb DEFAULT '{}'::jsonb NOT NULL,
    standard_production_wait_hours integer DEFAULT 24 NOT NULL,
    net_amount numeric(14,2) NOT NULL,
    tax_rate numeric(7,6) NOT NULL,
    tax_amount numeric(14,2) NOT NULL,
    gross_amount numeric(14,2) NOT NULL,
    created_by_user_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_commercial_quote_amounts_non_negative CHECK (((net_amount >= (0)::numeric) AND (tax_rate >= (0)::numeric) AND (tax_rate <= (1)::numeric) AND (tax_amount >= (0)::numeric) AND (gross_amount >= (0)::numeric) AND (production_cost_amount >= (0)::numeric))),
    CONSTRAINT ck_commercial_quote_currency CHECK ((length((currency)::text) = 3)),
    CONSTRAINT ck_commercial_quote_payment_class CHECK (payment_class IN ('standard_prepaid', 'approved_corporate_credit')),
    CONSTRAINT ck_commercial_quote_revision_positive CHECK ((revision_number > 0)),
    CONSTRAINT ck_commercial_quote_standard_wait CHECK ((standard_production_wait_hours = 24)),
    CONSTRAINT ck_commercial_quote_total_conservation CHECK ((gross_amount = (net_amount + tax_amount)))
);
""",
    r"""
CREATE TABLE public.commercial_quote_requests (
    id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    organization_id uuid NOT NULL,
    source character varying(32) NOT NULL,
    request_details jsonb DEFAULT '{}'::jsonb NOT NULL,
    requested_by_user_id uuid NOT NULL,
    requested_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_commercial_quote_requests_source CHECK (source IN ('in_platform', 'external_recorded'))
);
""",
    r"""
CREATE TABLE public.commercial_terms (
    id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    organization_id uuid NOT NULL,
    quotation_revision_id uuid NOT NULL,
    quote_reference character varying(128) NOT NULL,
    quotation_revision_number integer NOT NULL,
    currency character varying(3) NOT NULL,
    line_items jsonb NOT NULL,
    production_scope jsonb NOT NULL,
    production_cost_amount numeric(14,2) NOT NULL,
    payment_class character varying(40) NOT NULL,
    payment_terms jsonb NOT NULL,
    standard_production_wait_hours integer NOT NULL,
    net_amount numeric(14,2) NOT NULL,
    tax_rate numeric(7,6) NOT NULL,
    tax_amount numeric(14,2) NOT NULL,
    gross_amount numeric(14,2) NOT NULL,
    acceptance_method character varying(32) NOT NULL,
    accepted_by_user_id uuid,
    recorded_by_user_id uuid NOT NULL,
    external_acceptance_reference text,
    accepted_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_commercial_terms_acceptance_evidence CHECK (((((acceptance_method)::text = 'in_platform'::text) AND (accepted_by_user_id IS NOT NULL) AND (external_acceptance_reference IS NULL)) OR (((acceptance_method)::text = 'external_recorded'::text) AND (accepted_by_user_id IS NULL) AND (external_acceptance_reference IS NOT NULL)))),
    CONSTRAINT ck_commercial_terms_acceptance_method CHECK (acceptance_method IN ('in_platform', 'external_recorded')),
    CONSTRAINT ck_commercial_terms_amounts_non_negative CHECK (((net_amount >= (0)::numeric) AND (tax_rate >= (0)::numeric) AND (tax_rate <= (1)::numeric) AND (tax_amount >= (0)::numeric) AND (gross_amount >= (0)::numeric) AND (production_cost_amount >= (0)::numeric))),
    CONSTRAINT ck_commercial_terms_currency CHECK ((length((currency)::text) = 3)),
    CONSTRAINT ck_commercial_terms_payment_class CHECK (payment_class IN ('standard_prepaid', 'approved_corporate_credit')),
    CONSTRAINT ck_commercial_terms_standard_wait CHECK ((standard_production_wait_hours = 24)),
    CONSTRAINT ck_commercial_terms_total_conservation CHECK ((gross_amount = (net_amount + tax_amount)))
);
""",
    r"""
CREATE TABLE public.complaint_messages (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    complaint_id uuid NOT NULL,
    author_user_id uuid NOT NULL,
    author_side character varying(16) NOT NULL,
    body text NOT NULL,
    status_after character varying(16) NOT NULL,
    client_request_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_complaint_messages_author_side CHECK (author_side IN ('complainant', 'staff')),
    CONSTRAINT ck_complaint_messages_body CHECK (((length(TRIM(BOTH FROM body)) >= 1) AND (length(TRIM(BOTH FROM body)) <= 2000))),
    CONSTRAINT ck_complaint_messages_status_after CHECK (status_after IN ('open', 'answered', 'resolved'))
);
""",
    r"""
CREATE TABLE public.complaints (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    party character varying(16) NOT NULL,
    raised_by_user_id uuid NOT NULL,
    driver_profile_id uuid,
    advertiser_organization_id uuid,
    category character varying(32) NOT NULL,
    reference_type character varying(16),
    campaign_id uuid,
    trip_session_id uuid,
    earnings_ledger_entry_id uuid,
    status character varying(16) DEFAULT 'open'::character varying NOT NULL,
    assigned_to_user_id uuid,
    revision integer DEFAULT 1 NOT NULL,
    client_request_id uuid NOT NULL,
    resolved_at timestamp with time zone,
    resolved_by_user_id uuid,
    last_message_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_complaints_category CHECK (length(category) BETWEEN 1 AND 32 AND category = lower(trim(category)) AND category = replace(category, ' ', '')),
    CONSTRAINT ck_complaints_party CHECK (party IN ('driver', 'advertiser')),
    CONSTRAINT ck_complaints_party_owner CHECK (((((party)::text = 'driver'::text) AND (driver_profile_id IS NOT NULL) AND (advertiser_organization_id IS NULL)) OR (((party)::text = 'advertiser'::text) AND (advertiser_organization_id IS NOT NULL) AND (driver_profile_id IS NULL)))),
    CONSTRAINT ck_complaints_reference CHECK ((((reference_type IS NULL) AND (campaign_id IS NULL) AND (trip_session_id IS NULL) AND (earnings_ledger_entry_id IS NULL)) OR (((reference_type)::text = 'campaign'::text) AND (campaign_id IS NOT NULL) AND (trip_session_id IS NULL) AND (earnings_ledger_entry_id IS NULL)) OR (((reference_type)::text = 'trip'::text) AND ((party)::text = 'driver'::text) AND (trip_session_id IS NOT NULL) AND (campaign_id IS NULL) AND (earnings_ledger_entry_id IS NULL)) OR (((reference_type)::text = 'payout'::text) AND ((party)::text = 'driver'::text) AND (earnings_ledger_entry_id IS NOT NULL) AND (campaign_id IS NULL) AND (trip_session_id IS NULL)))),
    CONSTRAINT ck_complaints_resolution CHECK (((((status)::text = 'resolved'::text) AND (resolved_at IS NOT NULL) AND (resolved_by_user_id IS NOT NULL)) OR (((status)::text <> 'resolved'::text) AND (resolved_at IS NULL) AND (resolved_by_user_id IS NULL)))),
    CONSTRAINT ck_complaints_revision CHECK ((revision >= 1)),
    CONSTRAINT ck_complaints_status CHECK (status IN ('open', 'answered', 'resolved'))
);
""",
    r"""
CREATE TABLE public.creative_review_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    creative_id uuid NOT NULL,
    actor_user_id uuid NOT NULL,
    prior_status character varying(32) NOT NULL,
    new_status character varying(32) NOT NULL,
    rejection_reason text,
    reviewed_snapshot json,
    reviewed_snapshot_sha256 character varying(64),
    submission_event_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_creative_review_events_new_status CHECK (new_status IN ('pending_review', 'approved', 'rejected')),
    CONSTRAINT ck_creative_review_events_prior_status CHECK (prior_status IN ('draft', 'pending_review', 'approved', 'rejected', 'ready', 'archived')),
    CONSTRAINT ck_creative_review_events_rejection_reason CHECK (((((new_status)::text = 'rejected'::text) AND (rejection_reason IS NOT NULL) AND (length(TRIM(BOTH FROM rejection_reason)) > 0)) OR (((new_status)::text <> 'rejected'::text) AND (rejection_reason IS NULL)))),
    CONSTRAINT ck_creative_review_events_submission_binding CHECK ((new_status = 'pending_review' AND reviewed_snapshot IS NOT NULL AND reviewed_snapshot_sha256 IS NOT NULL AND submission_event_id IS NULL) OR (new_status IN ('approved', 'rejected') AND reviewed_snapshot IS NULL AND reviewed_snapshot_sha256 IS NULL AND submission_event_id IS NOT NULL))
);
""",
    r"""
CREATE TABLE public.data_purge_audit (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    partition_name text,
    range_from timestamp with time zone,
    range_to timestamp with time zone,
    event text NOT NULL,
    row_count bigint,
    retention_months integer NOT NULL,
    initiated_by text DEFAULT 'system'::text NOT NULL,
    job_run_id text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_data_purge_audit_event CHECK ((event = ANY (ARRAY['purge_started'::text, 'detach_finalized'::text, 'dropped'::text, 'batches_purged'::text, 'quarantined_batches_purged'::text]))),
    CONSTRAINT ck_data_purge_audit_partition_name_required CHECK (((partition_name IS NOT NULL) OR (event = ANY (ARRAY['batches_purged'::text, 'quarantined_batches_purged'::text]))))
);
""",
    r"""
CREATE TABLE public.data_subject_location_assessments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    request_id uuid NOT NULL,
    location character varying(32) NOT NULL,
    disposition character varying(32) NOT NULL,
    record_count integer NOT NULL,
    data_class_counts jsonb NOT NULL,
    evidence_reference character varying(255) NOT NULL,
    exception_reference character varying(255),
    assessed_by_user_id uuid NOT NULL,
    client_request_id uuid NOT NULL,
    request_fingerprint character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_data_subject_assessments_count CHECK ((record_count >= 0)),
    CONSTRAINT ck_data_subject_assessments_evidence CHECK ((length(TRIM(BOTH FROM evidence_reference)) > 0)),
    CONSTRAINT ck_data_subject_assessments_exception CHECK (((((disposition)::text = 'retained_exception'::text) AND (exception_reference IS NOT NULL) AND (length(TRIM(BOTH FROM exception_reference)) > 0)) OR (((disposition)::text <> 'retained_exception'::text) AND (exception_reference IS NULL)))),
    CONSTRAINT ck_data_subject_assessments_fingerprint CHECK ((length((request_fingerprint)::text) = 64)),
    CONSTRAINT ck_data_subject_assessments_zero_claim CHECK (disposition NOT IN ('erased', 'not_found') OR record_count = 0),
    CONSTRAINT ck_data_subject_location_assessments_disposition CHECK (disposition IN ('provided', 'rectified', 'erased', 'not_found', 'retained_exception')),
    CONSTRAINT ck_data_subject_location_assessments_location CHECK (location IN ('database', 'object_storage', 'device_queue', 'operational_logs', 'backups', 'processors'))
);
""",
    r"""
CREATE TABLE public.data_subject_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    subject_user_id uuid NOT NULL,
    request_type character varying(32) NOT NULL,
    status character varying(32) DEFAULT 'open'::character varying NOT NULL,
    opened_by_user_id uuid NOT NULL,
    client_request_id uuid NOT NULL,
    request_fingerprint character varying(64) NOT NULL,
    requested_at timestamp with time zone NOT NULL,
    identity_verified_at timestamp with time zone,
    identity_verified_by_user_id uuid,
    completed_at timestamp with time zone,
    completed_by_user_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_data_subject_requests_fingerprint CHECK ((length((request_fingerprint)::text) = 64)),
    CONSTRAINT ck_data_subject_requests_lifecycle CHECK (((((status)::text = 'open'::text) AND (identity_verified_at IS NULL) AND (identity_verified_by_user_id IS NULL) AND (completed_at IS NULL) AND (completed_by_user_id IS NULL)) OR (((status)::text = 'identity_verified'::text) AND (identity_verified_at IS NOT NULL) AND (identity_verified_by_user_id IS NOT NULL) AND (completed_at IS NULL) AND (completed_by_user_id IS NULL)) OR (((status)::text = 'completed'::text) AND (identity_verified_at IS NOT NULL) AND (identity_verified_by_user_id IS NOT NULL) AND (completed_at IS NOT NULL) AND (completed_by_user_id IS NOT NULL)))),
    CONSTRAINT ck_data_subject_requests_status CHECK (status IN ('open', 'identity_verified', 'completed')),
    CONSTRAINT ck_data_subject_requests_type CHECK (request_type IN ('access', 'rectification', 'erasure'))
);
""",
    r"""
CREATE TABLE public.disclosure_query_decisions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    principal_hash character varying(64) NOT NULL,
    scope_hash character varying(64) NOT NULL,
    query_hash character varying(64) NOT NULL,
    result_hash character varying(64) NOT NULL,
    tenant_id uuid,
    campaign_id uuid,
    output_class character varying(64) NOT NULL,
    decision character varying(16) NOT NULL,
    reason character varying(64) NOT NULL,
    window_start timestamp with time zone NOT NULL,
    window_end timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone,
    CONSTRAINT ck_disclosure_query_decisions_decision CHECK (decision IN ('served', 'suppressed'))
);
""",
    r"""
CREATE TABLE public.display_proof_challenges (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    assignment_id uuid NOT NULL,
    evidence_submission_id uuid NOT NULL,
    driver_profile_id uuid NOT NULL,
    vehicle_id uuid NOT NULL,
    device_id uuid NOT NULL,
    nonce_sha256 character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    consumed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_display_proof_challenge_expiry CHECK ((expires_at > created_at))
);
""",
    r"""
CREATE TABLE public.display_proofs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    challenge_id uuid NOT NULL,
    assignment_id uuid NOT NULL,
    evidence_submission_id uuid NOT NULL,
    driver_profile_id uuid NOT NULL,
    vehicle_id uuid NOT NULL,
    device_id uuid NOT NULL,
    stored_file_id uuid NOT NULL,
    verified_at timestamp with time zone NOT NULL,
    valid_until timestamp with time zone NOT NULL,
    metadata json DEFAULT '{}'::json NOT NULL,
    CONSTRAINT ck_display_proof_validity CHECK ((valid_until > verified_at))
);
""",
    r"""
CREATE TABLE public.driver_account_setup_tokens (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    application_id uuid NOT NULL,
    user_id uuid NOT NULL,
    issued_by_user_id uuid NOT NULL,
    client_request_id uuid NOT NULL,
    request_fingerprint character varying(64) NOT NULL,
    token_sha256 character varying(64) NOT NULL,
    evidence_sha256 character varying(64) NOT NULL,
    session_version integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    superseded_at timestamp with time zone,
    used_at timestamp with time zone,
    CONSTRAINT ck_driver_setup_tokens_evidence_hash CHECK ((length((evidence_sha256)::text) = 64)),
    CONSTRAINT ck_driver_setup_tokens_expiry CHECK ((expires_at > created_at)),
    CONSTRAINT ck_driver_setup_tokens_hash CHECK ((length((token_sha256)::text) = 64)),
    CONSTRAINT ck_driver_setup_tokens_request_hash CHECK ((length((request_fingerprint)::text) = 64)),
    CONSTRAINT ck_driver_setup_tokens_session_version CHECK ((session_version > 0))
);
""",
    r"""
CREATE TABLE public.driver_application_access_tokens (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    application_id uuid NOT NULL,
    token_sha256 character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    invalidated_at timestamp with time zone,
    CONSTRAINT ck_driver_application_access_tokens_hash CHECK ((length((token_sha256)::text) = 64))
);
""",
    r"""
CREATE TABLE public.driver_applications (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    driver_profile_id uuid NOT NULL,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    status_reference_sha256 character varying(64) NOT NULL,
    email character varying(255) NOT NULL,
    full_name character varying(255) NOT NULL,
    phone character varying(32),
    service_city character varying(128),
    country_code character varying(2),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    agreement_version character varying(32),
    agreement_accepted_at timestamp with time zone,
    CONSTRAINT ck_driver_applications_status CHECK (status IN ('pending', 'approved', 'rejected'))
);
""",
    r"""
CREATE TABLE public.driver_currency_debt_accounts (
    id uuid NOT NULL,
    driver_profile_id uuid NOT NULL,
    driver_user_id uuid NOT NULL,
    currency character varying(3) NOT NULL,
    outstanding_amount numeric(14,2) NOT NULL,
    lifetime_incurred_amount numeric(14,2) NOT NULL,
    lifetime_allocated_amount numeric(14,2) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_driver_debt_accounts_amounts_non_negative CHECK (((outstanding_amount >= (0)::numeric) AND (lifetime_incurred_amount >= (0)::numeric) AND (lifetime_allocated_amount >= (0)::numeric))),
    CONSTRAINT ck_driver_debt_accounts_conservation CHECK ((lifetime_incurred_amount = (outstanding_amount + lifetime_allocated_amount))),
    CONSTRAINT ck_driver_debt_accounts_currency CHECK ((length((currency)::text) = 3))
);
""",
    r"""
CREATE TABLE public.driver_kyc_documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    submission_id uuid NOT NULL,
    stored_file_id uuid NOT NULL,
    document_type character varying(32) NOT NULL,
    CONSTRAINT ck_driver_kyc_documents_type CHECK (document_type IN ('driver_license', 'driver_photo'))
);
""",
    r"""
CREATE TABLE public.driver_kyc_review_decisions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    submission_id uuid NOT NULL,
    client_request_id uuid NOT NULL,
    request_fingerprint character varying(64) NOT NULL,
    decision character varying(32) NOT NULL,
    reason_code character varying(64) NOT NULL,
    identity_match_confirmed boolean NOT NULL,
    bank_account_match_confirmed boolean NOT NULL,
    documents_readable_confirmed boolean NOT NULL,
    decided_by_user_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    document_reviews json DEFAULT '{}'::json NOT NULL,
    CONSTRAINT ck_driver_kyc_review_decisions_decision CHECK (decision IN ('approved', 'rejected', 'expired')),
    CONSTRAINT ck_driver_kyc_review_decisions_facts CHECK ((decision = 'approved' AND reason_code = 'complete_current_evidence' AND identity_match_confirmed AND bank_account_match_confirmed AND documents_readable_confirmed) OR (decision IN ('rejected', 'expired') AND reason_code <> 'complete_current_evidence')),
    CONSTRAINT ck_driver_kyc_review_decisions_fingerprint CHECK ((length((request_fingerprint)::text) = 64)),
    CONSTRAINT ck_driver_kyc_review_decisions_reason CHECK (reason_code IN ('complete_current_evidence', 'missing_evidence', 'rejected_evidence', 'expired_evidence', 'unsafe_evidence', 'identity_mismatch', 'bank_account_mismatch', 'unreadable_evidence'))
);
""",
    r"""
CREATE TABLE public.driver_kyc_submissions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    driver_profile_id uuid NOT NULL,
    nin_record_id uuid NOT NULL,
    version integer NOT NULL,
    client_request_id uuid NOT NULL,
    status character varying(32) NOT NULL,
    encrypted_nin json,
    encryption_algorithm character varying(32),
    encryption_key_version integer,
    nin_last_four character varying(4),
    bank_account_version_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    purged_at timestamp with time zone,
    agreement_version character varying(32),
    agreement_accepted_at timestamp with time zone,
    bank_check_receipt_sha256 character varying(64),
    bank_name_confirmed boolean,
    agreement_acceptance_requested boolean,
    CONSTRAINT ck_driver_kyc_submissions_algorithm CHECK (((encryption_algorithm)::text = 'AES-256-GCM'::text)),
    CONSTRAINT ck_driver_kyc_submissions_key_version CHECK ((encryption_key_version > 0)),
    CONSTRAINT ck_driver_kyc_submissions_nin_last_four CHECK ((length((nin_last_four)::text) = 4)),
    CONSTRAINT ck_driver_kyc_submissions_payload_retention CHECK ((purged_at IS NULL AND encrypted_nin IS NOT NULL AND encryption_algorithm IS NOT NULL AND encryption_key_version IS NOT NULL AND nin_last_four IS NOT NULL) OR (purged_at IS NOT NULL AND status IN ('rejected', 'expired') AND encrypted_nin IS NULL AND encryption_algorithm IS NULL AND encryption_key_version IS NULL AND nin_last_four IS NULL)),
    CONSTRAINT ck_driver_kyc_submissions_status CHECK (status IN ('pending_review', 'approved', 'rejected', 'expired')),
    CONSTRAINT ck_driver_kyc_submissions_version CHECK ((version > 0))
);
""",
    r"""
CREATE TABLE public.driver_phone_versions (
    id uuid NOT NULL,
    driver_profile_id uuid NOT NULL,
    version integer NOT NULL,
    phone_fingerprint character varying(64) NOT NULL,
    masked_phone character varying(32) NOT NULL,
    recorded_by_user_id uuid NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    verified_at timestamp with time zone,
    CONSTRAINT ck_driver_phone_versions_hash CHECK ((length((phone_fingerprint)::text) = 64)),
    CONSTRAINT ck_driver_phone_versions_mask CHECK ((length((masked_phone)::text) > 0)),
    CONSTRAINT ck_driver_phone_versions_version CHECK ((version > 0))
);
""",
    r"""
CREATE TABLE public.driver_profiles (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    onboarding_status character varying(32) NOT NULL,
    license_number character varying(128),
    service_city character varying(128),
    country_code character varying(2),
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_driver_profiles_onboarding_status CHECK (onboarding_status IN ('pending', 'active', 'suspended', 'rejected'))
);
""",
    r"""
CREATE TABLE public.earnings_ledger_entries (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    payout_calculation_id uuid,
    driver_profile_id uuid NOT NULL,
    driver_user_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    trip_session_id uuid,
    vehicle_id uuid,
    entry_type character varying(32) NOT NULL,
    status character varying(16) NOT NULL,
    amount numeric(14,2) NOT NULL,
    currency character varying(3) NOT NULL,
    description text,
    occurred_at timestamp with time zone NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    release_at timestamp with time zone,
    source_fraud_flag_id uuid,
    CONSTRAINT ck_earnings_ledger_entries_amount_non_negative CHECK ((amount >= (0)::numeric)),
    CONSTRAINT ck_earnings_ledger_entries_currency CHECK (((length((currency)::text) = 3) AND ((currency)::text = upper((currency)::text)) AND (substr((currency)::text, 1, 1) = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text, 'F'::text, 'G'::text, 'H'::text, 'I'::text, 'J'::text, 'K'::text, 'L'::text, 'M'::text, 'N'::text, 'O'::text, 'P'::text, 'Q'::text, 'R'::text, 'S'::text, 'T'::text, 'U'::text, 'V'::text, 'W'::text, 'X'::text, 'Y'::text, 'Z'::text])) AND (substr((currency)::text, 2, 1) = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text, 'F'::text, 'G'::text, 'H'::text, 'I'::text, 'J'::text, 'K'::text, 'L'::text, 'M'::text, 'N'::text, 'O'::text, 'P'::text, 'Q'::text, 'R'::text, 'S'::text, 'T'::text, 'U'::text, 'V'::text, 'W'::text, 'X'::text, 'Y'::text, 'Z'::text])) AND (substr((currency)::text, 3, 1) = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text, 'F'::text, 'G'::text, 'H'::text, 'I'::text, 'J'::text, 'K'::text, 'L'::text, 'M'::text, 'N'::text, 'O'::text, 'P'::text, 'Q'::text, 'R'::text, 'S'::text, 'T'::text, 'U'::text, 'V'::text, 'W'::text, 'X'::text, 'Y'::text, 'Z'::text])))),
    CONSTRAINT ck_earnings_ledger_entries_entry_type CHECK (entry_type IN ('trip_payout', 'adjustment', 'reversal', 'debt_remainder')),
    CONSTRAINT ck_earnings_ledger_entries_status CHECK (status IN ('pending', 'available', 'voided', 'reversed', 'paid'))
);
""",
    r"""
CREATE TABLE public.evidence_verifications (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    assignment_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    driver_profile_id uuid NOT NULL,
    vehicle_id uuid NOT NULL,
    source_trip_session_id uuid NOT NULL,
    verification_type character varying(40) NOT NULL,
    status character varying(16) NOT NULL,
    issued_by_user_id uuid,
    resolved_by_user_id uuid,
    client_request_id uuid,
    request_fingerprint character varying(64),
    result_fingerprint character varying(64),
    due_at timestamp with time zone,
    display_proof_id uuid,
    fraud_flag_id uuid,
    result_note text,
    metadata json DEFAULT '{}'::json NOT NULL,
    issued_at timestamp with time zone NOT NULL,
    resolved_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_evidence_verifications_due_at CHECK (((((verification_type)::text = 'high_earner_renewal'::text) AND (due_at IS NOT NULL)) OR (((verification_type)::text <> 'high_earner_renewal'::text) AND (due_at IS NULL)))),
    CONSTRAINT ck_evidence_verifications_request_authority CHECK (((((verification_type)::text = 'physical_spot_check'::text) AND (issued_by_user_id IS NOT NULL) AND (client_request_id IS NOT NULL) AND (request_fingerprint IS NOT NULL)) OR (((verification_type)::text <> 'physical_spot_check'::text) AND (client_request_id IS NULL) AND (request_fingerprint IS NULL)))),
    CONSTRAINT ck_evidence_verifications_resolution CHECK (((((status)::text = 'pending'::text) AND (resolved_at IS NULL) AND (resolved_by_user_id IS NULL) AND (display_proof_id IS NULL) AND (fraud_flag_id IS NULL)) OR (((status)::text = 'satisfied'::text) AND (resolved_at IS NOT NULL) AND (display_proof_id IS NOT NULL) AND (fraud_flag_id IS NULL)) OR (((status)::text = 'missed'::text) AND (resolved_at IS NOT NULL) AND (display_proof_id IS NULL) AND (fraud_flag_id IS NOT NULL)) OR (((status)::text = 'passed'::text) AND (resolved_at IS NOT NULL) AND (resolved_by_user_id IS NOT NULL) AND (display_proof_id IS NULL) AND (fraud_flag_id IS NULL)) OR (((status)::text = 'failed'::text) AND (resolved_at IS NOT NULL) AND (display_proof_id IS NULL) AND (fraud_flag_id IS NOT NULL)))),
    CONSTRAINT ck_evidence_verifications_status CHECK (status IN ('pending', 'satisfied', 'missed', 'passed', 'failed')),
    CONSTRAINT ck_evidence_verifications_type CHECK (verification_type IN ('high_earner_renewal', 'concurrent_session', 'physical_spot_check'))
);
""",
    r"""
CREATE TABLE public.expedited_production_waivers (
    id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    commercial_terms_id uuid NOT NULL,
    requested_by_user_id uuid NOT NULL,
    requested_at timestamp with time zone NOT NULL,
    accepted_by_user_id uuid NOT NULL,
    accepted_at timestamp with time zone NOT NULL,
    wording_version character varying(128) NOT NULL,
    accepted_wording_hash character varying(64) NOT NULL,
    CONSTRAINT ck_expedited_production_waivers_timeline CHECK ((accepted_at >= requested_at)),
    CONSTRAINT ck_expedited_production_waivers_wording CHECK (((length((accepted_wording_hash)::text) = 64) AND ((wording_version)::text <> ''::text)))
);
""",
    r"""
CREATE TABLE public.exposure_scores (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    measurement_run_id uuid NOT NULL,
    issued_by_user_id uuid NOT NULL,
    formula_version character varying(32) NOT NULL,
    formula_fingerprint character varying(64) NOT NULL,
    input_snapshot jsonb NOT NULL,
    input_fingerprint character varying(64) NOT NULL,
    result_snapshot jsonb NOT NULL,
    result_fingerprint character varying(64) NOT NULL,
    measurement_input_sha256 character varying(64) NOT NULL,
    measurement_result_sha256 character varying(64) NOT NULL,
    measurement_proof_sha256 character varying(64) NOT NULL,
    reissue_of_score_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_exposure_scores_fingerprints CHECK (((length((formula_fingerprint)::text) = 64) AND (length((input_fingerprint)::text) = 64) AND (length((result_fingerprint)::text) = 64) AND (length((measurement_input_sha256)::text) = 64) AND (length((measurement_result_sha256)::text) = 64) AND (length((measurement_proof_sha256)::text) = 64)))
);
""",
    r"""
CREATE TABLE public.exposure_segment_cells (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    segment_id uuid NOT NULL,
    coverage_cell character varying(64) NOT NULL,
    window_start_at timestamp with time zone NOT NULL,
    window_end_at timestamp with time zone NOT NULL,
    context character varying(32) NOT NULL,
    distinct_vehicle_count integer NOT NULL,
    trip_count integer NOT NULL,
    modelled_potential_contacts numeric(20,4) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    resolution_m integer,
    distinct_day_count integer,
    max_contributor_share numeric(8,7),
    CONSTRAINT ck_exposure_segment_cells_context CHECK (((context)::text = 'vehicle_transit'::text)),
    CONSTRAINT ck_exposure_segment_cells_counts CHECK (((distinct_vehicle_count >= 0) AND (trip_count >= 0) AND (modelled_potential_contacts >= (0)::numeric))),
    CONSTRAINT ck_exposure_segment_cells_governance CHECK ((((resolution_m IS NULL) AND (distinct_day_count IS NULL) AND (max_contributor_share IS NULL)) OR ((resolution_m IS NOT NULL) AND (distinct_day_count IS NOT NULL) AND (max_contributor_share IS NOT NULL) AND (resolution_m >= 50) AND (distinct_day_count >= 0) AND (max_contributor_share >= (0)::numeric) AND (max_contributor_share <= (1)::numeric)))),
    CONSTRAINT ck_exposure_segment_cells_window CHECK ((window_start_at < window_end_at))
);
""",
    r"""
CREATE TABLE public.exposure_segments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    zone_id uuid NOT NULL,
    source_id uuid NOT NULL,
    source_link_id uuid NOT NULL,
    measurement_run_id uuid NOT NULL,
    version integer NOT NULL,
    facts_fingerprint character varying(64) NOT NULL,
    source_link_snapshot_sha256 character varying(64) NOT NULL,
    measurement_input_sha256 character varying(64) NOT NULL,
    measurement_result_sha256 character varying(64) NOT NULL,
    measurement_proof_sha256 character varying(64) NOT NULL,
    snapshot jsonb NOT NULL,
    snapshot_sha256 character varying(64) NOT NULL,
    releasable_cell_count integer NOT NULL,
    suppressed_cell_count integer NOT NULL,
    reissue_of_segment_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    aggregate_formula_version character varying(64),
    aggregate_authority_sha256 character varying(64),
    disclosure_policy_sha256 character varying(64),
    synthetic boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_exposure_segments_cell_counts CHECK (((releasable_cell_count >= 0) AND (suppressed_cell_count >= 0))),
    CONSTRAINT ck_exposure_segments_fingerprints CHECK (((length((facts_fingerprint)::text) = 64) AND (length((snapshot_sha256)::text) = 64) AND (length((source_link_snapshot_sha256)::text) = 64) AND (length((measurement_input_sha256)::text) = 64) AND (length((measurement_result_sha256)::text) = 64) AND (length((measurement_proof_sha256)::text) = 64))),
    CONSTRAINT ck_exposure_segments_governance CHECK ((((aggregate_formula_version IS NULL) AND (aggregate_authority_sha256 IS NULL) AND (disclosure_policy_sha256 IS NULL)) OR ((aggregate_formula_version IS NOT NULL) AND (aggregate_authority_sha256 IS NOT NULL) AND (disclosure_policy_sha256 IS NOT NULL) AND (length(TRIM(BOTH FROM aggregate_formula_version)) > 0) AND (length((aggregate_authority_sha256)::text) = 64) AND (length((disclosure_policy_sha256)::text) = 64)))),
    CONSTRAINT ck_exposure_segments_version CHECK ((version > 0))
);
""",
    r"""
CREATE TABLE public.file_upload_intents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid,
    uploader_user_id uuid NOT NULL,
    client_request_id uuid NOT NULL,
    request_fingerprint character varying(64) NOT NULL,
    purpose character varying(32) NOT NULL,
    original_filename character varying(255) NOT NULL,
    declared_content_type character varying(255) NOT NULL,
    declared_size_bytes bigint NOT NULL,
    declared_sha256 character varying(64) NOT NULL,
    object_key character varying(1024) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    subject_user_id uuid,
    CONSTRAINT ck_file_upload_intents_purpose CHECK (purpose IN ('creative', 'driver_kyc', 'vehicle_evidence', 'installation_evidence')),
    CONSTRAINT ck_file_upload_intents_scope CHECK ((purpose = 'creative' AND organization_id IS NOT NULL AND subject_user_id IS NULL) OR (purpose IN ('driver_kyc', 'vehicle_evidence', 'installation_evidence') AND organization_id IS NULL AND subject_user_id IS NOT NULL)),
    CONSTRAINT ck_file_upload_intents_sha256_length CHECK ((length((declared_sha256)::text) = 64)),
    CONSTRAINT ck_file_upload_intents_size_positive CHECK ((declared_size_bytes > 0)),
    CONSTRAINT ck_file_upload_intents_status CHECK (status IN ('pending', 'confirmed', 'expired'))
);
""",
    r"""
CREATE TABLE public.financial_authorization_allocations (
    id uuid NOT NULL,
    authorization_id uuid NOT NULL,
    receipt_allocation_id uuid NOT NULL,
    amount numeric(14,2) NOT NULL,
    CONSTRAINT ck_financial_authorization_allocations_amount CHECK ((amount > (0)::numeric))
);
""",
    r"""
CREATE TABLE public.fraud_assessments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trip_session_id uuid NOT NULL,
    trip_analytics_id uuid NOT NULL,
    status character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    formula_version text NOT NULL,
    source_analytics_fingerprint character varying(64) NOT NULL,
    inputs_fingerprint character varying(64) NOT NULL,
    flags_count integer DEFAULT 0 NOT NULL,
    flags_updated_through timestamp with time zone,
    error_code character varying(64),
    assessed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_fraud_assessments_flags_count_non_negative CHECK ((flags_count >= 0)),
    CONSTRAINT ck_fraud_assessments_status CHECK (status IN ('pending', 'clean', 'flagged', 'error'))
);
""",
    r"""
CREATE TABLE public.fraud_disputes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    fraud_flag_id uuid NOT NULL,
    driver_profile_id uuid NOT NULL,
    submitted_by_user_id uuid NOT NULL,
    message text NOT NULL,
    status character varying(16) DEFAULT 'open'::character varying NOT NULL,
    replied_by_user_id uuid,
    replied_at timestamp with time zone,
    reply_text text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_fraud_disputes_message CHECK (((length(TRIM(BOTH FROM message)) >= 1) AND (length(TRIM(BOTH FROM message)) <= 2000))),
    CONSTRAINT ck_fraud_disputes_reply_evidence CHECK (((((status)::text = 'open'::text) AND (replied_by_user_id IS NULL) AND (replied_at IS NULL) AND (reply_text IS NULL)) OR (((status)::text = 'replied'::text) AND (replied_by_user_id IS NOT NULL) AND (replied_at IS NOT NULL) AND (reply_text IS NOT NULL) AND ((length(TRIM(BOTH FROM reply_text)) >= 1) AND (length(TRIM(BOTH FROM reply_text)) <= 2000))))),
    CONSTRAINT ck_fraud_disputes_status CHECK (status IN ('open', 'replied'))
);
""",
    r"""
CREATE TABLE public.fraud_flags (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trip_session_id uuid NOT NULL,
    trip_analytics_id uuid,
    assignment_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    driver_profile_id uuid NOT NULL,
    vehicle_id uuid NOT NULL,
    flag_type character varying(64) NOT NULL,
    severity character varying(16) NOT NULL,
    status character varying(16) DEFAULT 'open'::character varying NOT NULL,
    description text NOT NULL,
    evidence jsonb DEFAULT '{}'::jsonb NOT NULL,
    detected_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    reviewed_by_user_id uuid,
    reviewed_at timestamp with time zone,
    resolution_note text,
    escalated_at timestamp with time zone,
    CONSTRAINT ck_fraud_flags_flag_type CHECK (flag_type IN ('insufficient_pings', 'impossible_speed', 'poor_accuracy', 'stationary_trip', 'excessive_ping_gap', 'future_timestamp', 'route_looping', 'route_replay', 'exclusion_zone_presence', 'missed_display_challenge', 'concurrent_session_day', 'physical_spot_check_failed')),
    CONSTRAINT ck_fraud_flags_review_evidence CHECK ((status = 'open' AND reviewed_by_user_id IS NULL AND reviewed_at IS NULL AND resolution_note IS NULL) OR (status = 'acknowledged' AND reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL AND resolution_note IS NULL) OR (status IN ('confirmed', 'dismissed') AND reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL AND resolution_note IS NOT NULL AND length(trim(resolution_note)) BETWEEN 1 AND 2000)),
    CONSTRAINT ck_fraud_flags_severity CHECK (severity IN ('low', 'medium', 'high')),
    CONSTRAINT ck_fraud_flags_status CHECK (status IN ('open', 'acknowledged', 'confirmed', 'dismissed'))
);
""",
    r"""
CREATE TABLE public.impression_estimates (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trip_session_id uuid NOT NULL,
    trip_analytics_id uuid NOT NULL,
    assignment_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    driver_profile_id uuid NOT NULL,
    vehicle_id uuid NOT NULL,
    traffic_density_profile_id uuid NOT NULL,
    formula_version text DEFAULT 'impressions_v1'::text NOT NULL,
    status character varying(32) NOT NULL,
    estimated_impressions numeric(16,2) DEFAULT 0 NOT NULL,
    base_distance_impressions numeric(16,2) DEFAULT 0 NOT NULL,
    dwell_impressions numeric(16,2) DEFAULT 0 NOT NULL,
    target_zone_impressions numeric(16,2) DEFAULT 0 NOT NULL,
    bonus_zone_impressions numeric(16,2) DEFAULT 0 NOT NULL,
    exclusion_zone_adjustment numeric(16,2) DEFAULT 0 NOT NULL,
    quality_multiplier numeric(5,4) NOT NULL,
    fraud_adjustment_multiplier numeric(5,4) NOT NULL,
    confidence_score numeric(5,4) NOT NULL,
    started_at timestamp with time zone,
    ended_at timestamp with time zone,
    estimated_at timestamp with time zone NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_authoritative boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_impression_estimates_base_non_negative CHECK ((base_distance_impressions >= (0)::numeric)),
    CONSTRAINT ck_impression_estimates_bonus_non_negative CHECK ((bonus_zone_impressions >= (0)::numeric)),
    CONSTRAINT ck_impression_estimates_confidence_score_range CHECK (((confidence_score >= (0)::numeric) AND (confidence_score <= (1)::numeric))),
    CONSTRAINT ck_impression_estimates_dwell_non_negative CHECK ((dwell_impressions >= (0)::numeric)),
    CONSTRAINT ck_impression_estimates_estimated_non_negative CHECK ((estimated_impressions >= (0)::numeric)),
    CONSTRAINT ck_impression_estimates_exclusion_non_negative CHECK ((exclusion_zone_adjustment >= (0)::numeric)),
    CONSTRAINT ck_impression_estimates_fraud_multiplier_range CHECK (((fraud_adjustment_multiplier >= (0)::numeric) AND (fraud_adjustment_multiplier <= (1)::numeric))),
    CONSTRAINT ck_impression_estimates_quality_multiplier_range CHECK (((quality_multiplier >= (0)::numeric) AND (quality_multiplier <= (1)::numeric))),
    CONSTRAINT ck_impression_estimates_status CHECK (status IN ('estimated', 'insufficient_data', 'excluded')),
    CONSTRAINT ck_impression_estimates_target_non_negative CHECK ((target_zone_impressions >= (0)::numeric))
);
""",
    r"""
CREATE TABLE public.installation_evidence_photos (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    submission_id uuid NOT NULL,
    view_code character varying(64) NOT NULL,
    stored_file_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
""",
    r"""
CREATE TABLE public.installation_evidence_submissions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    assignment_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    driver_profile_id uuid NOT NULL,
    vehicle_id uuid NOT NULL,
    submitted_by_user_id uuid NOT NULL,
    reviewed_by_user_id uuid,
    revision integer NOT NULL,
    client_request_id uuid NOT NULL,
    request_fingerprint character varying(64) NOT NULL,
    device_id uuid NOT NULL,
    captured_at timestamp with time zone NOT NULL,
    required_views json NOT NULL,
    status character varying(32) NOT NULL,
    rejection_reason text,
    reviewed_at timestamp with time zone,
    approved_until timestamp with time zone,
    metadata json DEFAULT '{}'::json NOT NULL,
    submitted_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_installation_evidence_review_coherence CHECK (((((status)::text = 'pending_review'::text) AND (reviewed_by_user_id IS NULL) AND (reviewed_at IS NULL) AND (rejection_reason IS NULL) AND (approved_until IS NULL)) OR (((status)::text = 'approved'::text) AND (reviewed_by_user_id IS NOT NULL) AND (reviewed_at IS NOT NULL) AND (rejection_reason IS NULL) AND (approved_until IS NOT NULL)) OR (((status)::text = 'rejected'::text) AND (reviewed_by_user_id IS NOT NULL) AND (reviewed_at IS NOT NULL) AND (rejection_reason IS NOT NULL) AND (length(TRIM(BOTH FROM rejection_reason)) > 0) AND (approved_until IS NULL)) OR (((status)::text = 'expired'::text) AND (reviewed_by_user_id IS NOT NULL) AND (reviewed_at IS NOT NULL) AND (rejection_reason IS NULL) AND (approved_until IS NOT NULL)))),
    CONSTRAINT ck_installation_evidence_revision_positive CHECK ((revision > 0)),
    CONSTRAINT ck_installation_evidence_status CHECK (status IN ('pending_review', 'approved', 'rejected', 'expired'))
);
""",
    r"""
CREATE TABLE public.invoice_corrections (
    id uuid NOT NULL,
    invoice_id uuid NOT NULL,
    sequence_number integer NOT NULL,
    correction_number character varying(96) NOT NULL,
    correction_type character varying(32) NOT NULL,
    currency character varying(3) NOT NULL,
    net_amount numeric(14,2) NOT NULL,
    tax_amount numeric(14,2) NOT NULL,
    gross_amount numeric(14,2) NOT NULL,
    reason text NOT NULL,
    created_by_user_id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    correction_reference character varying(128) NOT NULL,
    request_fingerprint character varying(64) NOT NULL,
    CONSTRAINT ck_invoice_corrections_amounts CHECK (((net_amount >= (0)::numeric) AND (tax_amount >= (0)::numeric) AND (gross_amount > (0)::numeric) AND (gross_amount = (net_amount + tax_amount)))),
    CONSTRAINT ck_invoice_corrections_currency CHECK ((length((currency)::text) = 3)),
    CONSTRAINT ck_invoice_corrections_sequence CHECK ((sequence_number > 0)),
    CONSTRAINT ck_invoice_corrections_type CHECK (correction_type IN ('credit_note', 'debit_note'))
);
""",
    r"""
CREATE TABLE public.invoice_issuer_profiles (
    id uuid NOT NULL,
    legal_name character varying(255) NOT NULL,
    tax_identification_number character varying(128) NOT NULL,
    registered_address text NOT NULL,
    country_code character varying(2) NOT NULL,
    invoice_wording text NOT NULL,
    numbering_prefix character varying(32) NOT NULL,
    verification_status character varying(32) NOT NULL,
    external_input_reference character varying(255) NOT NULL,
    recorded_by_user_id uuid NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    company_registration_number character varying(128),
    contact_phone character varying(64),
    contact_email character varying(320),
    bank_name character varying(255),
    bank_account_name character varying(255),
    bank_account_number character varying(64),
    CONSTRAINT ck_invoice_issuer_profiles_country CHECK ((length((country_code)::text) = 2)),
    CONSTRAINT ck_invoice_issuer_profiles_verification CHECK (verification_status IN ('synthetic', 'verified'))
);
""",
    r"""
CREATE TABLE public.invoice_number_sequences (
    id uuid NOT NULL,
    calendar_year integer NOT NULL,
    next_number integer NOT NULL,
    number_prefix character varying(64) NOT NULL,
    CONSTRAINT ck_invoice_number_sequences_next CHECK ((next_number > 0)),
    CONSTRAINT ck_invoice_number_sequences_year CHECK ((calendar_year >= 2020))
);
""",
    r"""
CREATE TABLE public.invoices (
    id uuid NOT NULL,
    commercial_terms_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    organization_id uuid NOT NULL,
    issuer_profile_id uuid,
    invoice_number character varying(64),
    status character varying(32) NOT NULL,
    customer_snapshot jsonb NOT NULL,
    issuer_snapshot jsonb,
    line_items jsonb NOT NULL,
    currency character varying(3) NOT NULL,
    net_amount numeric(14,2) NOT NULL,
    tax_rate numeric(7,6) NOT NULL,
    tax_amount numeric(14,2) NOT NULL,
    gross_amount numeric(14,2) NOT NULL,
    created_by_user_id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    issued_by_user_id uuid,
    issued_at timestamp with time zone,
    CONSTRAINT ck_invoices_amounts_non_negative CHECK (((net_amount >= (0)::numeric) AND (tax_rate >= (0)::numeric) AND (tax_rate <= (1)::numeric) AND (tax_amount >= (0)::numeric) AND (gross_amount >= (0)::numeric))),
    CONSTRAINT ck_invoices_currency CHECK ((length((currency)::text) = 3)),
    CONSTRAINT ck_invoices_issuance_state CHECK ((status = 'draft' AND invoice_number IS NULL AND issued_at IS NULL AND issuer_profile_id IS NULL AND issuer_snapshot IS NULL AND issued_by_user_id IS NULL) OR (status IN ('issued', 'void') AND invoice_number IS NOT NULL AND issued_at IS NOT NULL AND issuer_profile_id IS NOT NULL AND issuer_snapshot IS NOT NULL AND issued_by_user_id IS NOT NULL)),
    CONSTRAINT ck_invoices_status CHECK (status IN ('draft', 'issued', 'void')),
    CONSTRAINT ck_invoices_total_conservation CHECK ((gross_amount = (net_amount + tax_amount)))
);
""",
    r"""
CREATE TABLE public.location_ping_batches (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trip_session_id uuid NOT NULL,
    idempotency_key text NOT NULL,
    payload_hash text NOT NULL,
    pings_accepted integer NOT NULL,
    received_at timestamp with time zone NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    batch_sequence integer,
    payload_hash_version integer DEFAULT 2 NOT NULL,
    pings_submitted integer NOT NULL,
    pings_rejected integer DEFAULT 0 NOT NULL,
    evidence_scope character varying(32) DEFAULT 'manifest'::character varying NOT NULL,
    receipt_format_version integer,
    receipt_key_version integer,
    receipt_signature text,
    receipt_outcome character varying(32),
    rejection_manifest jsonb,
    rejection_digest character varying(64),
    CONSTRAINT ck_location_ping_batches_evidence_scope CHECK (evidence_scope IN ('manifest', 'postseal_applied')),
    CONSTRAINT ck_location_ping_batches_ping_conservation CHECK (((pings_submitted >= 0) AND (pings_rejected >= 0) AND (pings_submitted = (pings_accepted + pings_rejected)))),
    CONSTRAINT ck_location_ping_batches_pings_accepted_non_negative CHECK ((pings_accepted >= 0)),
    CONSTRAINT ck_location_ping_batches_receipt_cluster CHECK ((((receipt_format_version IS NULL) AND (receipt_key_version IS NULL) AND (receipt_signature IS NULL) AND (receipt_outcome IS NULL)) OR ((receipt_format_version = 2) AND (receipt_key_version IS NOT NULL) AND (receipt_signature IS NOT NULL) AND (receipt_outcome IS NOT NULL)))),
    CONSTRAINT ck_location_ping_batches_rejection_cluster CHECK (((rejection_manifest IS NULL) = (rejection_digest IS NULL))),
    CONSTRAINT ck_location_ping_batches_rejection_digest_length CHECK (((rejection_digest IS NULL) OR (length((rejection_digest)::text) = 64)))
);
""",
    r"""
CREATE TABLE public.location_pings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trip_session_id uuid NOT NULL,
    batch_id uuid NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    received_at timestamp with time zone NOT NULL,
    sequence_number integer,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    accuracy_m double precision,
    speed_mps double precision,
    heading_degrees double precision,
    altitude_m double precision,
    geom public.geometry(Point,4326) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_location_pings_accuracy_non_negative CHECK (((accuracy_m IS NULL) OR (accuracy_m >= (0)::double precision))),
    CONSTRAINT ck_location_pings_altitude_m CHECK (((altitude_m IS NULL) OR ((altitude_m >= ('-500'::integer)::double precision) AND (altitude_m <= (10000)::double precision)))),
    CONSTRAINT ck_location_pings_heading_degrees CHECK (((heading_degrees IS NULL) OR ((heading_degrees >= (0)::double precision) AND (heading_degrees < (360)::double precision)))),
    CONSTRAINT ck_location_pings_latitude CHECK (((latitude >= ('-90'::integer)::double precision) AND (latitude <= (90)::double precision))),
    CONSTRAINT ck_location_pings_longitude CHECK (((longitude >= ('-180'::integer)::double precision) AND (longitude <= (180)::double precision))),
    CONSTRAINT ck_location_pings_sequence_number_non_negative CHECK (((sequence_number IS NULL) OR (sequence_number >= 0))),
    CONSTRAINT ck_location_pings_speed_non_negative CHECK (((speed_mps IS NULL) OR (speed_mps >= (0)::double precision)))
)
PARTITION BY RANGE (recorded_at);
""",
    r"""
CREATE TABLE public.location_pings_p2026_07 (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trip_session_id uuid NOT NULL,
    batch_id uuid NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    received_at timestamp with time zone NOT NULL,
    sequence_number integer,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    accuracy_m double precision,
    speed_mps double precision,
    heading_degrees double precision,
    altitude_m double precision,
    geom public.geometry(Point,4326) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_location_pings_accuracy_non_negative CHECK (((accuracy_m IS NULL) OR (accuracy_m >= (0)::double precision))),
    CONSTRAINT ck_location_pings_altitude_m CHECK (((altitude_m IS NULL) OR ((altitude_m >= ('-500'::integer)::double precision) AND (altitude_m <= (10000)::double precision)))),
    CONSTRAINT ck_location_pings_heading_degrees CHECK (((heading_degrees IS NULL) OR ((heading_degrees >= (0)::double precision) AND (heading_degrees < (360)::double precision)))),
    CONSTRAINT ck_location_pings_latitude CHECK (((latitude >= ('-90'::integer)::double precision) AND (latitude <= (90)::double precision))),
    CONSTRAINT ck_location_pings_longitude CHECK (((longitude >= ('-180'::integer)::double precision) AND (longitude <= (180)::double precision))),
    CONSTRAINT ck_location_pings_sequence_number_non_negative CHECK (((sequence_number IS NULL) OR (sequence_number >= 0))),
    CONSTRAINT ck_location_pings_speed_non_negative CHECK (((speed_mps IS NULL) OR (speed_mps >= (0)::double precision)))
);
""",
    r"""
CREATE TABLE public.location_pings_p2026_08 (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trip_session_id uuid NOT NULL,
    batch_id uuid NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    received_at timestamp with time zone NOT NULL,
    sequence_number integer,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    accuracy_m double precision,
    speed_mps double precision,
    heading_degrees double precision,
    altitude_m double precision,
    geom public.geometry(Point,4326) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_location_pings_accuracy_non_negative CHECK (((accuracy_m IS NULL) OR (accuracy_m >= (0)::double precision))),
    CONSTRAINT ck_location_pings_altitude_m CHECK (((altitude_m IS NULL) OR ((altitude_m >= ('-500'::integer)::double precision) AND (altitude_m <= (10000)::double precision)))),
    CONSTRAINT ck_location_pings_heading_degrees CHECK (((heading_degrees IS NULL) OR ((heading_degrees >= (0)::double precision) AND (heading_degrees < (360)::double precision)))),
    CONSTRAINT ck_location_pings_latitude CHECK (((latitude >= ('-90'::integer)::double precision) AND (latitude <= (90)::double precision))),
    CONSTRAINT ck_location_pings_longitude CHECK (((longitude >= ('-180'::integer)::double precision) AND (longitude <= (180)::double precision))),
    CONSTRAINT ck_location_pings_sequence_number_non_negative CHECK (((sequence_number IS NULL) OR (sequence_number >= 0))),
    CONSTRAINT ck_location_pings_speed_non_negative CHECK (((speed_mps IS NULL) OR (speed_mps >= (0)::double precision)))
);
""",
    r"""
CREATE TABLE public.location_pings_p2026_09 (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trip_session_id uuid NOT NULL,
    batch_id uuid NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    received_at timestamp with time zone NOT NULL,
    sequence_number integer,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    accuracy_m double precision,
    speed_mps double precision,
    heading_degrees double precision,
    altitude_m double precision,
    geom public.geometry(Point,4326) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_location_pings_accuracy_non_negative CHECK (((accuracy_m IS NULL) OR (accuracy_m >= (0)::double precision))),
    CONSTRAINT ck_location_pings_altitude_m CHECK (((altitude_m IS NULL) OR ((altitude_m >= ('-500'::integer)::double precision) AND (altitude_m <= (10000)::double precision)))),
    CONSTRAINT ck_location_pings_heading_degrees CHECK (((heading_degrees IS NULL) OR ((heading_degrees >= (0)::double precision) AND (heading_degrees < (360)::double precision)))),
    CONSTRAINT ck_location_pings_latitude CHECK (((latitude >= ('-90'::integer)::double precision) AND (latitude <= (90)::double precision))),
    CONSTRAINT ck_location_pings_longitude CHECK (((longitude >= ('-180'::integer)::double precision) AND (longitude <= (180)::double precision))),
    CONSTRAINT ck_location_pings_sequence_number_non_negative CHECK (((sequence_number IS NULL) OR (sequence_number >= 0))),
    CONSTRAINT ck_location_pings_speed_non_negative CHECK (((speed_mps IS NULL) OR (speed_mps >= (0)::double precision)))
);
""",
    r"""
CREATE TABLE public.location_pings_p2026_10 (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trip_session_id uuid NOT NULL,
    batch_id uuid NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    received_at timestamp with time zone NOT NULL,
    sequence_number integer,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    accuracy_m double precision,
    speed_mps double precision,
    heading_degrees double precision,
    altitude_m double precision,
    geom public.geometry(Point,4326) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_location_pings_accuracy_non_negative CHECK (((accuracy_m IS NULL) OR (accuracy_m >= (0)::double precision))),
    CONSTRAINT ck_location_pings_altitude_m CHECK (((altitude_m IS NULL) OR ((altitude_m >= ('-500'::integer)::double precision) AND (altitude_m <= (10000)::double precision)))),
    CONSTRAINT ck_location_pings_heading_degrees CHECK (((heading_degrees IS NULL) OR ((heading_degrees >= (0)::double precision) AND (heading_degrees < (360)::double precision)))),
    CONSTRAINT ck_location_pings_latitude CHECK (((latitude >= ('-90'::integer)::double precision) AND (latitude <= (90)::double precision))),
    CONSTRAINT ck_location_pings_longitude CHECK (((longitude >= ('-180'::integer)::double precision) AND (longitude <= (180)::double precision))),
    CONSTRAINT ck_location_pings_sequence_number_non_negative CHECK (((sequence_number IS NULL) OR (sequence_number >= 0))),
    CONSTRAINT ck_location_pings_speed_non_negative CHECK (((speed_mps IS NULL) OR (speed_mps >= (0)::double precision)))
);
""",
    r"""
CREATE TABLE public.location_pings_p2026_11 (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trip_session_id uuid NOT NULL,
    batch_id uuid NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    received_at timestamp with time zone NOT NULL,
    sequence_number integer,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    accuracy_m double precision,
    speed_mps double precision,
    heading_degrees double precision,
    altitude_m double precision,
    geom public.geometry(Point,4326) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_location_pings_accuracy_non_negative CHECK (((accuracy_m IS NULL) OR (accuracy_m >= (0)::double precision))),
    CONSTRAINT ck_location_pings_altitude_m CHECK (((altitude_m IS NULL) OR ((altitude_m >= ('-500'::integer)::double precision) AND (altitude_m <= (10000)::double precision)))),
    CONSTRAINT ck_location_pings_heading_degrees CHECK (((heading_degrees IS NULL) OR ((heading_degrees >= (0)::double precision) AND (heading_degrees < (360)::double precision)))),
    CONSTRAINT ck_location_pings_latitude CHECK (((latitude >= ('-90'::integer)::double precision) AND (latitude <= (90)::double precision))),
    CONSTRAINT ck_location_pings_longitude CHECK (((longitude >= ('-180'::integer)::double precision) AND (longitude <= (180)::double precision))),
    CONSTRAINT ck_location_pings_sequence_number_non_negative CHECK (((sequence_number IS NULL) OR (sequence_number >= 0))),
    CONSTRAINT ck_location_pings_speed_non_negative CHECK (((speed_mps IS NULL) OR (speed_mps >= (0)::double precision)))
);
""",
    r"""
CREATE TABLE public.location_pings_p2026_12 (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trip_session_id uuid NOT NULL,
    batch_id uuid NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    received_at timestamp with time zone NOT NULL,
    sequence_number integer,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    accuracy_m double precision,
    speed_mps double precision,
    heading_degrees double precision,
    altitude_m double precision,
    geom public.geometry(Point,4326) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_location_pings_accuracy_non_negative CHECK (((accuracy_m IS NULL) OR (accuracy_m >= (0)::double precision))),
    CONSTRAINT ck_location_pings_altitude_m CHECK (((altitude_m IS NULL) OR ((altitude_m >= ('-500'::integer)::double precision) AND (altitude_m <= (10000)::double precision)))),
    CONSTRAINT ck_location_pings_heading_degrees CHECK (((heading_degrees IS NULL) OR ((heading_degrees >= (0)::double precision) AND (heading_degrees < (360)::double precision)))),
    CONSTRAINT ck_location_pings_latitude CHECK (((latitude >= ('-90'::integer)::double precision) AND (latitude <= (90)::double precision))),
    CONSTRAINT ck_location_pings_longitude CHECK (((longitude >= ('-180'::integer)::double precision) AND (longitude <= (180)::double precision))),
    CONSTRAINT ck_location_pings_sequence_number_non_negative CHECK (((sequence_number IS NULL) OR (sequence_number >= 0))),
    CONSTRAINT ck_location_pings_speed_non_negative CHECK (((speed_mps IS NULL) OR (speed_mps >= (0)::double precision)))
);
""",
    r"""
CREATE TABLE public.location_pings_p2027_01 (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trip_session_id uuid NOT NULL,
    batch_id uuid NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    received_at timestamp with time zone NOT NULL,
    sequence_number integer,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    accuracy_m double precision,
    speed_mps double precision,
    heading_degrees double precision,
    altitude_m double precision,
    geom public.geometry(Point,4326) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_location_pings_accuracy_non_negative CHECK (((accuracy_m IS NULL) OR (accuracy_m >= (0)::double precision))),
    CONSTRAINT ck_location_pings_altitude_m CHECK (((altitude_m IS NULL) OR ((altitude_m >= ('-500'::integer)::double precision) AND (altitude_m <= (10000)::double precision)))),
    CONSTRAINT ck_location_pings_heading_degrees CHECK (((heading_degrees IS NULL) OR ((heading_degrees >= (0)::double precision) AND (heading_degrees < (360)::double precision)))),
    CONSTRAINT ck_location_pings_latitude CHECK (((latitude >= ('-90'::integer)::double precision) AND (latitude <= (90)::double precision))),
    CONSTRAINT ck_location_pings_longitude CHECK (((longitude >= ('-180'::integer)::double precision) AND (longitude <= (180)::double precision))),
    CONSTRAINT ck_location_pings_sequence_number_non_negative CHECK (((sequence_number IS NULL) OR (sequence_number >= 0))),
    CONSTRAINT ck_location_pings_speed_non_negative CHECK (((speed_mps IS NULL) OR (speed_mps >= (0)::double precision)))
);
""",
    r"""
CREATE TABLE public.location_pings_p2027_02 (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trip_session_id uuid NOT NULL,
    batch_id uuid NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    received_at timestamp with time zone NOT NULL,
    sequence_number integer,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    accuracy_m double precision,
    speed_mps double precision,
    heading_degrees double precision,
    altitude_m double precision,
    geom public.geometry(Point,4326) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_location_pings_accuracy_non_negative CHECK (((accuracy_m IS NULL) OR (accuracy_m >= (0)::double precision))),
    CONSTRAINT ck_location_pings_altitude_m CHECK (((altitude_m IS NULL) OR ((altitude_m >= ('-500'::integer)::double precision) AND (altitude_m <= (10000)::double precision)))),
    CONSTRAINT ck_location_pings_heading_degrees CHECK (((heading_degrees IS NULL) OR ((heading_degrees >= (0)::double precision) AND (heading_degrees < (360)::double precision)))),
    CONSTRAINT ck_location_pings_latitude CHECK (((latitude >= ('-90'::integer)::double precision) AND (latitude <= (90)::double precision))),
    CONSTRAINT ck_location_pings_longitude CHECK (((longitude >= ('-180'::integer)::double precision) AND (longitude <= (180)::double precision))),
    CONSTRAINT ck_location_pings_sequence_number_non_negative CHECK (((sequence_number IS NULL) OR (sequence_number >= 0))),
    CONSTRAINT ck_location_pings_speed_non_negative CHECK (((speed_mps IS NULL) OR (speed_mps >= (0)::double precision)))
);
""",
    r"""
CREATE TABLE public.manual_driver_contact_tasks (
    id uuid NOT NULL,
    driver_profile_id uuid NOT NULL,
    phone_version_id uuid NOT NULL,
    consent_id uuid NOT NULL,
    event_key character varying(255) NOT NULL,
    purpose character varying(128) NOT NULL,
    status character varying(16) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    completed_by_user_id uuid,
    completed_at timestamp with time zone,
    completion_outcome character varying(16),
    completion_note text,
    CONSTRAINT ck_manual_contact_completion CHECK ((status = 'open' AND completed_by_user_id IS NULL AND completed_at IS NULL AND completion_outcome IS NULL AND completion_note IS NULL) OR (status = 'completed' AND completed_by_user_id IS NOT NULL AND completed_at IS NOT NULL AND completion_outcome IN ('attempted', 'reached', 'failed') AND length(trim(completion_note)) > 0)),
    CONSTRAINT ck_manual_contact_event_key CHECK ((length(TRIM(BOTH FROM event_key)) > 0)),
    CONSTRAINT ck_manual_contact_purpose CHECK ((length(TRIM(BOTH FROM purpose)) > 0)),
    CONSTRAINT ck_manual_contact_status CHECK (status IN ('open', 'completed'))
);
""",
    r"""
CREATE TABLE public.measurement_run_proof_bindings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    measurement_run_id uuid NOT NULL,
    assignment_id uuid NOT NULL,
    activation_event_id uuid NOT NULL,
    creative_id uuid NOT NULL,
    installation_evidence_submission_id uuid NOT NULL,
    activation_snapshot_sha256 character varying(64) NOT NULL,
    binding_fingerprint character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_measurement_run_proof_binding_fingerprints CHECK (((length((activation_snapshot_sha256)::text) = 64) AND (length((binding_fingerprint)::text) = 64)))
);
""",
    r"""
CREATE TABLE public.measurement_runs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL,
    client_request_id uuid NOT NULL,
    request_fingerprint character varying(64) NOT NULL,
    mode character varying(32) NOT NULL,
    test_only boolean DEFAULT false NOT NULL,
    formula_version character varying(64) NOT NULL,
    method_revision character varying(255) NOT NULL,
    roi_method_revision character varying(255),
    period_start_at timestamp with time zone NOT NULL,
    period_end_at timestamp with time zone NOT NULL,
    input_manifest jsonb NOT NULL,
    input_manifest_sha256 character varying(64) NOT NULL,
    result_manifest jsonb NOT NULL,
    result_manifest_sha256 character varying(64) NOT NULL,
    proof_manifest jsonb NOT NULL,
    proof_manifest_sha256 character varying(64) NOT NULL,
    report_snapshot jsonb NOT NULL,
    report_snapshot_sha256 character varying(64) NOT NULL,
    reissue_of_run_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_measurement_runs_fingerprints CHECK (((length((input_manifest_sha256)::text) = 64) AND (length((result_manifest_sha256)::text) = 64) AND (length((proof_manifest_sha256)::text) = 64) AND (length((report_snapshot_sha256)::text) = 64) AND (length((request_fingerprint)::text) = 64))),
    CONSTRAINT ck_measurement_runs_mode CHECK (mode IN ('performance_only', 'roi_enabled')),
    CONSTRAINT ck_measurement_runs_period CHECK ((period_start_at < period_end_at)),
    CONSTRAINT ck_measurement_runs_roi_method CHECK (((((mode)::text = 'performance_only'::text) AND (roi_method_revision IS NULL)) OR (((mode)::text = 'roi_enabled'::text) AND (roi_method_revision IS NOT NULL) AND (length(TRIM(BOTH FROM roi_method_revision)) > 0))))
);
""",
    r"""
CREATE TABLE public.notification_delivery_receipts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    notification_id uuid NOT NULL,
    provider_event_id character varying(255) NOT NULL,
    provider_message_id character varying(255) NOT NULL,
    outcome character varying(32) NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    evidence_fingerprint character varying(64) NOT NULL,
    signing_key_id character varying(64) NOT NULL,
    verified_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_notification_delivery_receipts_outcome CHECK (outcome IN ('delivered', 'failed'))
);
""",
    r"""
CREATE TABLE public.notifications (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    recipient_user_id uuid NOT NULL,
    type_key character varying(64) NOT NULL,
    template_version character varying(16) DEFAULT 'v1'::character varying NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    dedupe_key character varying(255),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    channel character varying(32) DEFAULT 'in_app'::character varying NOT NULL,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    provider_message_id character varying(255),
    dedupe_fingerprint character varying(64) NOT NULL,
    sent_at timestamp with time zone,
    delivered_at timestamp with time zone,
    read_at timestamp with time zone,
    next_attempt_at timestamp with time zone,
    delivery_claim_token uuid,
    delivery_claim_expires_at timestamp with time zone,
    last_error_code character varying(64),
    failed_at timestamp with time zone,
    CONSTRAINT ck_notifications_attempt_count CHECK ((attempt_count >= 0)),
    CONSTRAINT ck_notifications_channel CHECK (channel IN ('in_app', 'transactional_email')),
    CONSTRAINT ck_notifications_status CHECK (status IN ('pending', 'sent', 'delivered', 'failed')),
    CONSTRAINT ck_notifications_template_version CHECK ((length(TRIM(BOTH FROM template_version)) > 0)),
    CONSTRAINT ck_notifications_type_key CHECK ((length(TRIM(BOTH FROM type_key)) > 0))
);
""",
    r"""
CREATE TABLE public.organization_memberships (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role character varying(32) NOT NULL,
    status character varying(32) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_organization_memberships_role CHECK (role IN ('owner', 'manager', 'viewer')),
    CONSTRAINT ck_organization_memberships_status CHECK (status IN ('active', 'invited', 'disabled'))
);
""",
    r"""
CREATE TABLE public.password_reset_attempts (
    id uuid NOT NULL,
    email_digest character varying(64) NOT NULL,
    ip_digest character varying(64) NOT NULL,
    issued_user_id uuid,
    requested_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_password_reset_attempt_email_hash CHECK ((length((email_digest)::text) = 64)),
    CONSTRAINT ck_password_reset_attempt_ip_hash CHECK ((length((ip_digest)::text) = 64))
);
""",
    r"""
CREATE TABLE public.password_reset_tokens (
    id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    user_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    session_version integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    CONSTRAINT ck_password_reset_tokens_expiry CHECK ((expires_at > created_at)),
    CONSTRAINT ck_password_reset_tokens_hash CHECK ((length((token_hash)::text) = 64)),
    CONSTRAINT ck_password_reset_tokens_session_version CHECK ((session_version > 0))
);
""",
    r"""
CREATE TABLE public.payee_bank_account_payout_verifications (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    bank_account_version_id uuid NOT NULL,
    verification_reference_sha256 character varying(64) NOT NULL,
    verified_by_user_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_payee_bank_account_payout_verifications_hash CHECK ((length((verification_reference_sha256)::text) = 64))
);
""",
    r"""
CREATE TABLE public.payee_bank_account_versions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    bank_account_id uuid NOT NULL,
    payee_version_id uuid NOT NULL,
    version integer NOT NULL,
    encrypted_details jsonb NOT NULL,
    encryption_algorithm character varying(32) NOT NULL,
    encryption_key_version integer NOT NULL,
    verification_reference_sha256 character varying(64) NOT NULL,
    verified_at timestamp with time zone DEFAULT now() NOT NULL,
    verified_by_user_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_payee_bank_account_versions_algorithm CHECK (((encryption_algorithm)::text = 'AES-256-GCM'::text)),
    CONSTRAINT ck_payee_bank_account_versions_positive_key_version CHECK ((encryption_key_version > 0)),
    CONSTRAINT ck_payee_bank_account_versions_positive_version CHECK ((version > 0)),
    CONSTRAINT ck_payee_bank_account_versions_verification_hash CHECK ((length((verification_reference_sha256)::text) = 64))
);
""",
    r"""
CREATE TABLE public.payee_bank_accounts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    payee_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
""",
    r"""
CREATE TABLE public.payee_versions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    payee_id uuid NOT NULL,
    version integer NOT NULL,
    payee_type character varying(32) NOT NULL,
    subject_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_payee_versions_positive_version CHECK ((version > 0)),
    CONSTRAINT ck_payee_versions_type CHECK (((payee_type)::text = 'driver'::text))
);
""",
    r"""
CREATE TABLE public.payees (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    payee_type character varying(32) NOT NULL,
    subject_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_payees_type CHECK (((payee_type)::text = 'driver'::text))
);
""",
    r"""
CREATE TABLE public.payment_checkout_intents (
    id uuid NOT NULL,
    reference character varying(100) NOT NULL,
    provider character varying(64) NOT NULL,
    organization_id uuid NOT NULL,
    commercial_terms_id uuid NOT NULL,
    invoice_id uuid NOT NULL,
    requested_by_user_id uuid NOT NULL,
    customer_email character varying(255) NOT NULL,
    amount numeric(14,2) NOT NULL,
    currency character varying(3) NOT NULL,
    status character varying(32) NOT NULL,
    checkout_url text,
    provider_checkout_id character varying(255),
    failure_code character varying(128),
    created_at timestamp with time zone NOT NULL,
    initialized_at timestamp with time zone,
    verified_at timestamp with time zone,
    CONSTRAINT ck_payment_checkout_intents_amount CHECK ((amount > (0)::numeric)),
    CONSTRAINT ck_payment_checkout_intents_currency CHECK ((length((currency)::text) = 3)),
    CONSTRAINT ck_payment_checkout_intents_initialized CHECK (((((status)::text = 'initialized'::text) AND (checkout_url IS NOT NULL) AND (initialized_at IS NOT NULL)) OR ((status)::text <> 'initialized'::text))),
    CONSTRAINT ck_payment_checkout_intents_status CHECK (status IN ('pending', 'initialized', 'initialization_unknown', 'failed', 'confirmed'))
);
""",
    r"""
CREATE TABLE public.payment_gateway_events (
    id uuid NOT NULL,
    provider character varying(64) NOT NULL,
    provider_event_id character varying(255) NOT NULL,
    external_transaction_id character varying(255) NOT NULL,
    event_type character varying(32) NOT NULL,
    commercial_terms_reference character varying(64) NOT NULL,
    amount numeric(14,2) NOT NULL,
    currency character varying(3) NOT NULL,
    payer_name character varying(255) NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    evidence_fingerprint character varying(64) NOT NULL,
    payload jsonb NOT NULL,
    received_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_payment_gateway_events_amount CHECK ((amount > (0)::numeric)),
    CONSTRAINT ck_payment_gateway_events_currency CHECK ((length((currency)::text) = 3)),
    CONSTRAINT ck_payment_gateway_events_fingerprint CHECK ((length((evidence_fingerprint)::text) = 64)),
    CONSTRAINT ck_payment_gateway_events_type CHECK (event_type IN ('payment_confirmed', 'payment_failed'))
);
""",
    r"""
CREATE TABLE public.payment_gateway_processing_attempts (
    id uuid NOT NULL,
    gateway_event_id uuid NOT NULL,
    attempt_number integer NOT NULL,
    outcome character varying(32) NOT NULL,
    error_code character varying(128),
    receipt_id uuid,
    allocation_id uuid,
    processed_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_payment_gateway_attempts_number CHECK ((attempt_number > 0)),
    CONSTRAINT ck_payment_gateway_attempts_outcome CHECK (outcome IN ('confirmed', 'confirmed_unallocated', 'ignored_failed', 'failed')),
    CONSTRAINT ck_payment_gateway_attempts_result CHECK (((((outcome)::text = 'confirmed'::text) AND (receipt_id IS NOT NULL) AND (allocation_id IS NOT NULL) AND (error_code IS NULL)) OR (((outcome)::text = 'confirmed_unallocated'::text) AND (receipt_id IS NOT NULL) AND (allocation_id IS NULL) AND (error_code IS NULL)) OR (((outcome)::text = 'ignored_failed'::text) AND (receipt_id IS NULL) AND (allocation_id IS NULL) AND (error_code IS NULL)) OR (((outcome)::text = 'failed'::text) AND (receipt_id IS NULL) AND (allocation_id IS NULL) AND (error_code IS NOT NULL))))
);
""",
    r"""
CREATE TABLE public.payment_receipts (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    method character varying(32) NOT NULL,
    provider character varying(64) NOT NULL,
    external_transaction_id character varying(255) NOT NULL,
    amount numeric(14,2) NOT NULL,
    currency character varying(3) NOT NULL,
    payer_name character varying(255) NOT NULL,
    evidence_reference character varying(255) NOT NULL,
    observed_by_user_id uuid,
    observed_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_payment_receipts_amount_positive CHECK ((amount > (0)::numeric)),
    CONSTRAINT ck_payment_receipts_currency CHECK ((length((currency)::text) = 3)),
    CONSTRAINT ck_payment_receipts_method CHECK (method IN ('manual_transfer', 'gateway'))
);
""",
    r"""
CREATE TABLE public.payout_automatic_alerts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    kind character varying(24) NOT NULL,
    dedupe_key character varying(64) NOT NULL,
    run_id uuid,
    batch_id uuid,
    line_id uuid,
    ledger_entry_id uuid,
    driver_profile_id uuid,
    lagos_day date,
    amount numeric(14,2),
    currency character varying(3),
    detail jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    resolved_by_user_id uuid,
    resolved_at timestamp with time zone,
    resolution_note text,
    CONSTRAINT ck_payout_automatic_alerts_kind CHECK (kind IN ('failed_payment', 'duplicate_payment', 'daily_limit', 'batch_limit', 'run_failed', 'submission_blocked', 'business_health')),
    CONSTRAINT ck_payout_automatic_alerts_resolution CHECK ((((resolved_by_user_id IS NULL) AND (resolved_at IS NULL) AND (resolution_note IS NULL)) OR ((resolved_by_user_id IS NOT NULL) AND (resolved_at IS NOT NULL) AND (resolution_note IS NOT NULL) AND ((length(TRIM(BOTH FROM resolution_note)) >= 3) AND (length(TRIM(BOTH FROM resolution_note)) <= 500)))))
);
""",
    r"""
CREATE TABLE public.payout_automatic_controls (
    id integer NOT NULL,
    paused boolean NOT NULL,
    reason text,
    changed_by_user_id uuid,
    changed_at timestamp with time zone,
    actor_password_fingerprint character varying(64) NOT NULL,
    candidate_cursor_at timestamp with time zone,
    candidate_cursor_id uuid,
    CONSTRAINT ck_payout_automatic_controls_actor_fingerprint CHECK ((length((actor_password_fingerprint)::text) = 64)),
    CONSTRAINT ck_payout_automatic_controls_change_evidence CHECK ((((changed_by_user_id IS NULL) AND (changed_at IS NULL) AND (reason IS NULL) AND (paused = false)) OR ((changed_by_user_id IS NOT NULL) AND (changed_at IS NOT NULL) AND (reason IS NOT NULL) AND ((length(TRIM(BOTH FROM reason)) >= 3) AND (length(TRIM(BOTH FROM reason)) <= 500))))),
    CONSTRAINT ck_payout_automatic_controls_cursor_pair CHECK (((candidate_cursor_at IS NULL) = (candidate_cursor_id IS NULL))),
    CONSTRAINT ck_payout_automatic_controls_singleton CHECK ((id = 1))
);
""",
    r"""
CREATE TABLE public.payout_automatic_runs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    period_key character varying(16) NOT NULL,
    frequency character varying(8) NOT NULL,
    currency character varying(3) NOT NULL,
    batch_limit numeric(14,2) NOT NULL,
    total_amount numeric(14,2) NOT NULL,
    batch_count integer NOT NULL,
    line_count integer NOT NULL,
    exclusions jsonb NOT NULL,
    settings_fingerprint character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_payout_automatic_runs_counts CHECK (((batch_count >= 0) AND (line_count >= batch_count))),
    CONSTRAINT ck_payout_automatic_runs_currency CHECK ((length((currency)::text) = 3)),
    CONSTRAINT ck_payout_automatic_runs_freq CHECK (frequency IN ('daily', 'weekly')),
    CONSTRAINT ck_payout_automatic_runs_limit_positive CHECK ((batch_limit > (0)::numeric)),
    CONSTRAINT ck_payout_automatic_runs_total_within_limit CHECK (((total_amount >= (0)::numeric) AND (total_amount <= batch_limit)))
);
""",
    r"""
CREATE TABLE public.payout_batch_lines (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    batch_id uuid NOT NULL,
    ledger_entry_id uuid NOT NULL,
    payee_version_id uuid NOT NULL,
    bank_account_version_id uuid NOT NULL,
    amount numeric(14,2) NOT NULL,
    currency character varying(3) NOT NULL,
    instruction jsonb NOT NULL,
    instruction_fingerprint character varying(64) NOT NULL,
    idempotency_key character varying(64) NOT NULL,
    reservation_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    status character varying(16) DEFAULT 'reserved'::character varying NOT NULL,
    provider_transfer_reference text,
    reconciled_by_user_id uuid,
    reconciled_at timestamp with time zone,
    last_provider_evidence_at timestamp with time zone,
    predecessor_line_id uuid,
    CONSTRAINT ck_payout_batch_lines_active_state CHECK ((status IN ('reserved', 'submitted') AND reservation_active = true) OR (status IN ('succeeded', 'failed', 'void') AND reservation_active = false)),
    CONSTRAINT ck_payout_batch_lines_amount_positive CHECK ((amount > (0)::numeric)),
    CONSTRAINT ck_payout_batch_lines_currency CHECK ((length((currency)::text) = 3)),
    CONSTRAINT ck_payout_batch_lines_instruction_fingerprint CHECK ((length((instruction_fingerprint)::text) = 64)),
    CONSTRAINT ck_payout_batch_lines_predecessor_not_self CHECK (((predecessor_line_id IS NULL) OR (predecessor_line_id <> id))),
    CONSTRAINT ck_payout_batch_lines_provider_state CHECK ((status IN ('reserved', 'void') AND provider_transfer_reference IS NULL) OR (status IN ('submitted', 'succeeded', 'failed') AND provider_transfer_reference IS NOT NULL)),
    CONSTRAINT ck_payout_batch_lines_status CHECK (status IN ('reserved', 'submitted', 'succeeded', 'failed', 'void'))
);
""",
    r"""
CREATE TABLE public.payout_batches (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    status character varying(16) NOT NULL,
    currency character varying(3) NOT NULL,
    total_amount numeric(14,2) DEFAULT 0 NOT NULL,
    instruction_set_fingerprint character varying(64),
    provider_submission_reference text,
    created_by_user_id uuid NOT NULL,
    approved_by_user_id uuid,
    approved_at timestamp with time zone,
    submitted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    approval_mode character varying(16) DEFAULT 'maker_checker'::character varying NOT NULL,
    automatic_run_id uuid,
    CONSTRAINT ck_payout_batches_approval_mode CHECK (((((approval_mode)::text = 'maker_checker'::text) AND (automatic_run_id IS NULL) AND (created_by_user_id <> '6c0de000-0000-4000-8000-000000000001'::uuid)) OR (((approval_mode)::text = 'automatic'::text) AND (automatic_run_id IS NOT NULL) AND (created_by_user_id = '6c0de000-0000-4000-8000-000000000001'::uuid) AND (approved_by_user_id IS NULL) AND (approved_at IS NOT NULL) AND ((status)::text <> 'draft'::text)))),
    CONSTRAINT ck_payout_batches_currency CHECK ((length((currency)::text) = 3)),
    CONSTRAINT ck_payout_batches_maker_checker CHECK (((approved_by_user_id IS NULL) OR (approved_by_user_id <> created_by_user_id))),
    CONSTRAINT ck_payout_batches_reserved_fingerprint CHECK (((((status)::text = 'draft'::text) AND (instruction_set_fingerprint IS NULL)) OR (((status)::text <> 'draft'::text) AND (instruction_set_fingerprint IS NOT NULL)))),
    CONSTRAINT ck_payout_batches_status CHECK (status IN ('draft', 'reserved', 'submitted', 'reconciled', 'completed', 'failed', 'void')),
    CONSTRAINT ck_payout_batches_total_non_negative CHECK ((total_amount >= (0)::numeric))
);
""",
    r"""
CREATE TABLE public.payout_calculations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trip_session_id uuid NOT NULL,
    trip_analytics_id uuid NOT NULL,
    impression_estimate_id uuid NOT NULL,
    payout_rule_id uuid NOT NULL,
    assignment_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    driver_profile_id uuid NOT NULL,
    vehicle_id uuid NOT NULL,
    formula_version text DEFAULT 'payout_v4'::text NOT NULL,
    status character varying(32) NOT NULL,
    currency character varying(3) NOT NULL,
    gross_payout numeric(14,2) DEFAULT 0 NOT NULL,
    final_payout numeric(14,2) DEFAULT 0 NOT NULL,
    calculated_at timestamp with time zone NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    eligible_seconds integer,
    excluded_seconds_by_reason jsonb,
    inputs_fingerprint text,
    distance_m_by_day json,
    amount_by_day json,
    CONSTRAINT ck_payout_calculations_currency CHECK (((length((currency)::text) = 3) AND ((currency)::text = upper((currency)::text)) AND (substr((currency)::text, 1, 1) = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text, 'F'::text, 'G'::text, 'H'::text, 'I'::text, 'J'::text, 'K'::text, 'L'::text, 'M'::text, 'N'::text, 'O'::text, 'P'::text, 'Q'::text, 'R'::text, 'S'::text, 'T'::text, 'U'::text, 'V'::text, 'W'::text, 'X'::text, 'Y'::text, 'Z'::text])) AND (substr((currency)::text, 2, 1) = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text, 'F'::text, 'G'::text, 'H'::text, 'I'::text, 'J'::text, 'K'::text, 'L'::text, 'M'::text, 'N'::text, 'O'::text, 'P'::text, 'Q'::text, 'R'::text, 'S'::text, 'T'::text, 'U'::text, 'V'::text, 'W'::text, 'X'::text, 'Y'::text, 'Z'::text])) AND (substr((currency)::text, 3, 1) = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text, 'F'::text, 'G'::text, 'H'::text, 'I'::text, 'J'::text, 'K'::text, 'L'::text, 'M'::text, 'N'::text, 'O'::text, 'P'::text, 'Q'::text, 'R'::text, 'S'::text, 'T'::text, 'U'::text, 'V'::text, 'W'::text, 'X'::text, 'Y'::text, 'Z'::text])))),
    CONSTRAINT ck_payout_calculations_daily_rate_fields CHECK (((formula_version = 'payout_v4'::text) AND (eligible_seconds IS NOT NULL) AND (excluded_seconds_by_reason IS NOT NULL) AND (inputs_fingerprint IS NOT NULL) AND (distance_m_by_day IS NOT NULL) AND (amount_by_day IS NOT NULL))),
    CONSTRAINT ck_payout_calculations_eligible_seconds_non_negative CHECK (((eligible_seconds IS NULL) OR (eligible_seconds >= 0))),
    CONSTRAINT ck_payout_calculations_final_non_negative CHECK ((final_payout >= (0)::numeric)),
    CONSTRAINT ck_payout_calculations_gross_non_negative CHECK ((gross_payout >= (0)::numeric)),
    CONSTRAINT ck_payout_calculations_status CHECK (status IN ('calculated', 'insufficient_data', 'blocked'))
);
""",
    r"""
CREATE TABLE public.payout_correction_orders (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    campaign_id uuid NOT NULL,
    lagos_day date NOT NULL,
    status character varying(32) NOT NULL,
    created_by_user_id uuid NOT NULL,
    approved_by_user_id uuid,
    executed_by_user_id uuid,
    reason text NOT NULL,
    projected_delta jsonb,
    projection_fingerprint text,
    projected_at timestamp with time zone,
    decided_at timestamp with time zone,
    executed_at timestamp with time zone,
    execution_result jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_payout_correction_orders_approver_not_creator CHECK (((approved_by_user_id IS NULL) OR (approved_by_user_id <> created_by_user_id))),
    CONSTRAINT ck_payout_correction_orders_status CHECK (status IN ('draft', 'pending_approval', 'approved', 'rejected', 'executed', 'stale'))
);
""",
    r"""
CREATE TABLE public.payout_debt_allocations (
    id uuid NOT NULL,
    settlement_id uuid NOT NULL,
    debt_obligation_id uuid NOT NULL,
    amount numeric(14,2) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_payout_debt_allocations_amount_positive CHECK ((amount > (0)::numeric))
);
""",
    r"""
CREATE TABLE public.payout_debt_obligations (
    id uuid NOT NULL,
    debt_account_id uuid NOT NULL,
    source_reversal_entry_id uuid,
    correction_order_id uuid,
    currency character varying(3) NOT NULL,
    original_amount numeric(14,2) NOT NULL,
    outstanding_amount numeric(14,2) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    recovery_incident_id uuid,
    CONSTRAINT ck_payout_debt_obligations_amounts CHECK (((original_amount > (0)::numeric) AND (outstanding_amount >= (0)::numeric) AND (outstanding_amount <= original_amount))),
    CONSTRAINT ck_payout_debt_obligations_currency CHECK ((length((currency)::text) = 3)),
    CONSTRAINT ck_payout_debt_obligations_source CHECK (((source_reversal_entry_id IS NOT NULL) OR (recovery_incident_id IS NOT NULL)))
);
""",
    r"""
CREATE TABLE public.payout_debt_paid_sources (
    id uuid NOT NULL,
    debt_obligation_id uuid NOT NULL,
    paid_ledger_entry_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
""",
    r"""
CREATE TABLE public.payout_debt_settlements (
    id uuid NOT NULL,
    source_credit_entry_id uuid NOT NULL,
    remainder_entry_id uuid,
    original_credit_amount numeric(14,2) NOT NULL,
    allocated_amount numeric(14,2) NOT NULL,
    idempotency_key character varying(64) NOT NULL,
    created_by_user_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_payout_debt_settlements_amounts CHECK (((original_credit_amount > (0)::numeric) AND (allocated_amount > (0)::numeric) AND (allocated_amount <= original_credit_amount))),
    CONSTRAINT ck_payout_debt_settlements_remainder CHECK ((((allocated_amount = original_credit_amount) AND (remainder_entry_id IS NULL)) OR ((allocated_amount < original_credit_amount) AND (remainder_entry_id IS NOT NULL))))
);
""",
    r"""
CREATE TABLE public.payout_line_reconciliation_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    line_id uuid NOT NULL,
    provider_event_id text NOT NULL,
    source character varying(16) NOT NULL,
    outcome character varying(16) NOT NULL,
    evidence_fingerprint character varying(64) NOT NULL,
    provider_occurred_at timestamp with time zone NOT NULL,
    applied boolean NOT NULL,
    reconciled_by_user_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_payout_line_events_evidence_fingerprint CHECK ((length((evidence_fingerprint)::text) = 64)),
    CONSTRAINT ck_payout_line_events_outcome CHECK (outcome IN ('succeeded', 'failed')),
    CONSTRAINT ck_payout_line_events_source CHECK (source IN ('webhook', 'poll'))
);
""",
    r"""
CREATE TABLE public.payout_provider_event_processing_attempts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    provider_event_id uuid NOT NULL,
    attempt_number integer NOT NULL,
    outcome character varying(16) NOT NULL,
    error_code character varying(128),
    reconciliation_event_id uuid,
    processed_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_payout_provider_attempts_number CHECK ((attempt_number > 0)),
    CONSTRAINT ck_payout_provider_attempts_outcome CHECK (outcome IN ('processed', 'failed')),
    CONSTRAINT ck_payout_provider_attempts_result CHECK (((((outcome)::text = 'processed'::text) AND (reconciliation_event_id IS NOT NULL) AND (error_code IS NULL)) OR (((outcome)::text = 'failed'::text) AND (reconciliation_event_id IS NULL) AND (error_code IS NOT NULL))))
);
""",
    r"""
CREATE TABLE public.payout_provider_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    provider character varying(64) NOT NULL,
    provider_event_id character varying(255) NOT NULL,
    provider_transfer_reference character varying(255) NOT NULL,
    provider_reference character varying(100) NOT NULL,
    amount numeric(14,2) NOT NULL,
    currency character varying(3) NOT NULL,
    outcome character varying(16) NOT NULL,
    provider_occurred_at timestamp with time zone NOT NULL,
    evidence_fingerprint character varying(64) NOT NULL,
    received_at timestamp with time zone NOT NULL,
    provider_event_type character varying(64) NOT NULL,
    CONSTRAINT ck_payout_provider_events_amount CHECK ((amount > (0)::numeric)),
    CONSTRAINT ck_payout_provider_events_currency CHECK ((length((currency)::text) = 3)),
    CONSTRAINT ck_payout_provider_events_fingerprint CHECK ((length((evidence_fingerprint)::text) = 64)),
    CONSTRAINT ck_payout_provider_events_outcome CHECK (outcome IN ('succeeded', 'failed'))
);
""",
    r"""
CREATE TABLE public.payout_recovery_incidents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    ledger_entry_id uuid NOT NULL,
    chain_root_line_id uuid NOT NULL,
    exposure_line_id uuid NOT NULL,
    source_fraud_flag_id uuid,
    source_reversal_entry_id uuid,
    created_by_user_id uuid NOT NULL,
    kind character varying(24) NOT NULL,
    status character varying(24) NOT NULL,
    amount numeric(14,2) NOT NULL,
    currency character varying(3) NOT NULL,
    dedupe_key character varying(64) NOT NULL,
    resolved_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_payout_recovery_incidents_amount_positive CHECK ((amount > (0)::numeric)),
    CONSTRAINT ck_payout_recovery_incidents_currency CHECK ((length((currency)::text) = 3)),
    CONSTRAINT ck_payout_recovery_incidents_dedupe_key CHECK ((length((dedupe_key)::text) = 64)),
    CONSTRAINT ck_payout_recovery_incidents_kind CHECK (kind IN ('confirmed_fraud', 'duplicate_cash')),
    CONSTRAINT ck_payout_recovery_incidents_resolution CHECK ((status = 'contingent' AND exposure_line_id IS NOT NULL AND resolved_at IS NULL) OR (status IN ('debt_activated', 'closed') AND resolved_at IS NOT NULL)),
    CONSTRAINT ck_payout_recovery_incidents_source CHECK (((((kind)::text = 'confirmed_fraud'::text) AND (source_fraud_flag_id IS NOT NULL) AND (source_reversal_entry_id IS NOT NULL)) OR (((kind)::text = 'duplicate_cash'::text) AND (source_fraud_flag_id IS NULL) AND (source_reversal_entry_id IS NULL)))),
    CONSTRAINT ck_payout_recovery_incidents_status CHECK (status IN ('contingent', 'debt_activated', 'closed'))
);
""",
    r"""
CREATE TABLE public.payout_submission_attempts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    intent_id uuid NOT NULL,
    generation integer NOT NULL,
    claim_token uuid NOT NULL,
    action character varying(16) NOT NULL,
    idempotency_key character varying(64) NOT NULL,
    instruction_fingerprint character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_payout_submission_attempts_action CHECK (action IN ('submit', 'query')),
    CONSTRAINT ck_payout_submission_attempts_generation CHECK ((generation > 0)),
    CONSTRAINT ck_payout_submission_attempts_idempotency_key CHECK ((length((idempotency_key)::text) = 64)),
    CONSTRAINT ck_payout_submission_attempts_instruction_fingerprint CHECK ((length((instruction_fingerprint)::text) = 64))
);
""",
    r"""
CREATE TABLE public.payout_submission_intents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    payout_batch_line_id uuid NOT NULL,
    provider_name character varying(64) NOT NULL,
    idempotency_key character varying(64) NOT NULL,
    instruction jsonb NOT NULL,
    instruction_fingerprint character varying(64) NOT NULL,
    requested_by_user_id uuid NOT NULL,
    state character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    generation integer DEFAULT 0 NOT NULL,
    claim_token uuid,
    claim_action character varying(16),
    claim_expires_at timestamp with time zone,
    provider_submission_reference text,
    provider_transfer_reference text,
    resolved_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_payout_submission_intents_claim_action CHECK (claim_action IS NULL OR claim_action IN ('submit', 'query')),
    CONSTRAINT ck_payout_submission_intents_generation CHECK ((generation >= 0)),
    CONSTRAINT ck_payout_submission_intents_idempotency_key CHECK ((length((idempotency_key)::text) = 64)),
    CONSTRAINT ck_payout_submission_intents_instruction_fingerprint CHECK ((length((instruction_fingerprint)::text) = 64)),
    CONSTRAINT ck_payout_submission_intents_state CHECK (state IN ('pending', 'claimed', 'query_only', 'resolved', 'cancelled')),
    CONSTRAINT ck_payout_submission_intents_state_fields CHECK ((state IN ('pending', 'query_only') AND claim_token IS NULL AND claim_action IS NULL AND claim_expires_at IS NULL AND provider_transfer_reference IS NULL AND resolved_at IS NULL) OR (state = 'claimed' AND generation > 0 AND claim_token IS NOT NULL AND claim_action IS NOT NULL AND claim_expires_at IS NOT NULL AND provider_transfer_reference IS NULL AND resolved_at IS NULL) OR (state = 'resolved' AND claim_token IS NULL AND claim_action IS NULL AND claim_expires_at IS NULL AND provider_transfer_reference IS NOT NULL AND resolved_at IS NOT NULL) OR (state = 'cancelled' AND claim_token IS NULL AND claim_action IS NULL AND claim_expires_at IS NULL AND provider_transfer_reference IS NULL AND resolved_at IS NOT NULL))
);
""",
    r"""
CREATE TABLE public.payout_submission_observations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    attempt_id uuid NOT NULL,
    intent_id uuid NOT NULL,
    generation integer NOT NULL,
    idempotency_key character varying(64) NOT NULL,
    instruction_fingerprint character varying(64) NOT NULL,
    outcome character varying(16) NOT NULL,
    provider_submission_reference text,
    provider_transfer_reference text,
    evidence_fingerprint character varying(64) NOT NULL,
    error_code character varying(64),
    observed_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_payout_submission_observations_evidence_fingerprint CHECK ((length((evidence_fingerprint)::text) = 64)),
    CONSTRAINT ck_payout_submission_observations_generation CHECK ((generation > 0)),
    CONSTRAINT ck_payout_submission_observations_idempotency_key CHECK ((length((idempotency_key)::text) = 64)),
    CONSTRAINT ck_payout_submission_observations_instruction_fingerprint CHECK ((length((instruction_fingerprint)::text) = 64)),
    CONSTRAINT ck_payout_submission_observations_outcome CHECK (outcome IN ('submitted', 'found', 'not_found', 'unknown')),
    CONSTRAINT ck_payout_submission_observations_provider_reference CHECK ((outcome IN ('submitted', 'found') AND provider_transfer_reference IS NOT NULL) OR (outcome IN ('not_found', 'unknown') AND provider_transfer_reference IS NULL))
);
""",
    r"""
CREATE TABLE public.phone_verification_challenges (
    id uuid NOT NULL,
    phone_version_id uuid NOT NULL,
    code_hash character varying(64) NOT NULL,
    status character varying(32) NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    max_attempts integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    verified_at timestamp with time zone,
    verified_by_user_id uuid,
    CONSTRAINT ck_phone_challenges_attempt_count CHECK (((attempt_count >= 0) AND (attempt_count <= max_attempts))),
    CONSTRAINT ck_phone_challenges_expiry CHECK ((expires_at > created_at)),
    CONSTRAINT ck_phone_challenges_hash CHECK ((length((code_hash)::text) = 64)),
    CONSTRAINT ck_phone_challenges_max_attempts CHECK ((max_attempts > 0)),
    CONSTRAINT ck_phone_challenges_status CHECK (status IN ('pending', 'verified', 'expired', 'exhausted'))
);
""",
    r"""
CREATE TABLE public.production_starts (
    id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    authorization_id uuid NOT NULL,
    authority_basis character varying(40) NOT NULL,
    waiver_id uuid,
    fully_funded_at timestamp with time zone,
    started_by_user_id uuid NOT NULL,
    started_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_production_starts_authority_basis CHECK (authority_basis IN ('standard_window_elapsed', 'advertiser_expedited_waiver', 'approved_credit')),
    CONSTRAINT ck_production_starts_funding_basis CHECK ((authority_basis IN ('standard_window_elapsed', 'advertiser_expedited_waiver') AND fully_funded_at IS NOT NULL) OR (authority_basis = 'approved_credit' AND fully_funded_at IS NULL)),
    CONSTRAINT ck_production_starts_timeline CHECK (((fully_funded_at IS NULL) OR (started_at >= fully_funded_at))),
    CONSTRAINT ck_production_starts_waiver_basis CHECK (((((authority_basis)::text = 'advertiser_expedited_waiver'::text) AND (waiver_id IS NOT NULL)) OR (((authority_basis)::text <> 'advertiser_expedited_waiver'::text) AND (waiver_id IS NULL))))
);
""",
    r"""
CREATE TABLE public.quarantined_ping_batches (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trip_session_id uuid NOT NULL,
    idempotency_key text NOT NULL,
    payload_hash text NOT NULL,
    payload json NOT NULL,
    ping_count integer NOT NULL,
    received_at timestamp with time zone NOT NULL,
    status character varying(32) DEFAULT 'quarantined'::character varying NOT NULL,
    resolved_at timestamp with time zone,
    resolved_by_user_id uuid,
    resolution_note text,
    applied_batch_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    batch_sequence integer,
    payload_hash_version integer DEFAULT 2 NOT NULL,
    pings_submitted integer NOT NULL,
    pings_rejected integer DEFAULT 0 NOT NULL,
    receipt_format_version integer,
    receipt_key_version integer,
    receipt_signature text,
    receipt_outcome character varying(32),
    CONSTRAINT ck_quarantined_ping_batches_applied_batch CHECK (((applied_batch_id IS NULL) OR ((status)::text = 'applied'::text))),
    CONSTRAINT ck_quarantined_ping_batches_ping_counts CHECK (((pings_submitted >= 0) AND (pings_rejected >= 0))),
    CONSTRAINT ck_quarantined_ping_batches_receipt_cluster CHECK ((((receipt_format_version IS NULL) AND (receipt_key_version IS NULL) AND (receipt_signature IS NULL) AND (receipt_outcome IS NULL)) OR ((receipt_format_version = 2) AND (receipt_key_version IS NOT NULL) AND (receipt_signature IS NOT NULL) AND (receipt_outcome IS NOT NULL)))),
    CONSTRAINT ck_quarantined_ping_batches_resolution CHECK ((((status)::text = 'quarantined'::text) = (resolved_at IS NULL))),
    CONSTRAINT ck_quarantined_ping_batches_resolution_actor CHECK ((((status)::text = 'quarantined'::text) = ((resolved_by_user_id IS NULL) AND (resolution_note IS NULL)))),
    CONSTRAINT ck_quarantined_ping_batches_status CHECK (status IN ('quarantined', 'applied', 'discarded'))
);
""",
    r"""
CREATE TABLE public.receipt_allocations (
    id uuid NOT NULL,
    receipt_id uuid NOT NULL,
    commercial_terms_id uuid NOT NULL,
    amount numeric(14,2) NOT NULL,
    currency character varying(3) NOT NULL,
    allocated_by_user_id uuid,
    allocated_at timestamp with time zone NOT NULL,
    allocation_source character varying(32) DEFAULT 'manual'::character varying NOT NULL,
    provider_event_id uuid,
    CONSTRAINT ck_receipt_allocations_amount_positive CHECK ((amount > (0)::numeric)),
    CONSTRAINT ck_receipt_allocations_currency CHECK ((length((currency)::text) = 3)),
    CONSTRAINT ck_receipt_allocations_source CHECK (((((allocation_source)::text = 'manual'::text) AND (allocated_by_user_id IS NOT NULL) AND (provider_event_id IS NULL)) OR (((allocation_source)::text = 'provider'::text) AND (allocated_by_user_id IS NULL) AND (provider_event_id IS NOT NULL))))
);
""",
    r"""
CREATE TABLE public.receipt_lifecycle_events (
    id uuid NOT NULL,
    receipt_id uuid NOT NULL,
    status character varying(32) NOT NULL,
    sequence_number integer NOT NULL,
    actor_user_id uuid,
    reason text,
    occurred_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_receipt_lifecycle_events_status CHECK (status IN ('observed', 'reconciled', 'confirmed', 'reversed')),
    CONSTRAINT ck_receipt_lifecycle_sequence CHECK (((sequence_number >= 1) AND (sequence_number <= 4))),
    CONSTRAINT ck_receipt_lifecycle_status_sequence CHECK (((((status)::text = 'observed'::text) AND (sequence_number = 1)) OR (((status)::text = 'reconciled'::text) AND (sequence_number = 2)) OR (((status)::text = 'confirmed'::text) AND (sequence_number = 3)) OR (((status)::text = 'reversed'::text) AND (sequence_number = 4))))
);
""",
    r"""
CREATE TABLE public.receipt_reconciliations (
    id uuid NOT NULL,
    receipt_id uuid NOT NULL,
    expected_amount numeric(14,2) NOT NULL,
    expected_currency character varying(3) NOT NULL,
    matched boolean NOT NULL,
    reconciled_by_user_id uuid,
    reconciled_at timestamp with time zone NOT NULL,
    verification_source character varying(32) DEFAULT 'manual'::character varying NOT NULL,
    provider_event_id uuid,
    CONSTRAINT ck_receipt_reconciliations_amount_positive CHECK ((expected_amount > (0)::numeric)),
    CONSTRAINT ck_receipt_reconciliations_currency CHECK ((length((expected_currency)::text) = 3)),
    CONSTRAINT ck_receipt_reconciliations_verification_source CHECK (((((verification_source)::text = 'manual'::text) AND (reconciled_by_user_id IS NOT NULL) AND (provider_event_id IS NULL)) OR (((verification_source)::text = 'provider'::text) AND (reconciled_by_user_id IS NULL) AND (provider_event_id IS NOT NULL))))
);
""",
    r"""
CREATE TABLE public.refund_settlements (
    id uuid NOT NULL,
    commercial_terms_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    receipt_id uuid,
    production_start_id uuid,
    waiver_id uuid,
    disposition character varying(40) NOT NULL,
    amount numeric(14,2) NOT NULL,
    currency character varying(3) NOT NULL,
    funding_authorized_at timestamp with time zone,
    eligibility_ends_at timestamp with time zone,
    settlement_provider character varying(64) NOT NULL,
    external_reference character varying(255) NOT NULL,
    reason text NOT NULL,
    recorded_by_user_id uuid NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    cancellation_id uuid,
    eligibility_evaluated_at timestamp with time zone,
    CONSTRAINT ck_refund_settlements_authority CHECK (((((disposition)::text = 'refund_recorded'::text) AND (receipt_id IS NOT NULL) AND (amount > (0)::numeric) AND (funding_authorized_at IS NOT NULL) AND (eligibility_ends_at IS NOT NULL)) OR (((disposition)::text = 'credit_settlement_recorded'::text) AND (receipt_id IS NULL) AND (amount = (0)::numeric) AND (funding_authorized_at IS NULL) AND (eligibility_ends_at IS NULL) AND (cancellation_id IS NULL) AND (eligibility_evaluated_at IS NULL)))),
    CONSTRAINT ck_refund_settlements_currency CHECK ((length((currency)::text) = 3)),
    CONSTRAINT ck_refund_settlements_disposition CHECK (disposition IN ('refund_recorded', 'credit_settlement_recorded')),
    CONSTRAINT ck_refund_settlements_eligibility_window CHECK (((eligibility_evaluated_at IS NULL) OR (eligibility_evaluated_at < eligibility_ends_at))),
    CONSTRAINT ck_refund_settlements_frozen_provenance CHECK ((((cancellation_id IS NULL) AND (eligibility_evaluated_at IS NULL)) OR ((cancellation_id IS NOT NULL) AND (eligibility_evaluated_at IS NOT NULL))))
);
""",
    r"""
CREATE TABLE public.report_artifacts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    report_issuance_id uuid NOT NULL,
    stored_file_id uuid NOT NULL,
    format character varying(8) NOT NULL,
    content_type character varying(64) NOT NULL,
    size_bytes integer NOT NULL,
    checksum_sha256 character varying(64) NOT NULL,
    renderer_version character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_report_artifacts_format CHECK (format IN ('csv', 'pdf')),
    CONSTRAINT ck_report_artifacts_sha256 CHECK ((length((checksum_sha256)::text) = 64)),
    CONSTRAINT ck_report_artifacts_size_positive CHECK ((size_bytes > 0))
);
""",
    r"""
CREATE TABLE public.report_issuances (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    measurement_run_id uuid NOT NULL,
    requested_by_user_id uuid NOT NULL,
    client_request_id uuid NOT NULL,
    request_fingerprint character varying(64) NOT NULL,
    reissue_of_id uuid,
    version integer NOT NULL,
    snapshot jsonb NOT NULL,
    snapshot_sha256 character varying(64) NOT NULL,
    authority_fingerprint character varying(64) NOT NULL,
    input_manifest_sha256 character varying(64) NOT NULL,
    result_manifest_sha256 character varying(64) NOT NULL,
    proof_manifest_sha256 character varying(64) NOT NULL,
    report_snapshot_sha256 character varying(64) NOT NULL,
    schema_version character varying(64) NOT NULL,
    renderer_version character varying(64) NOT NULL,
    method_revision character varying(255) NOT NULL,
    roi_decision character varying(16) NOT NULL,
    synthetic boolean NOT NULL,
    status character varying(16) DEFAULT 'queued'::character varying NOT NULL,
    worker_attempts integer DEFAULT 0 NOT NULL,
    processing_token uuid,
    lease_expires_at timestamp with time zone,
    next_attempt_at timestamp with time zone,
    last_error_code character varying(64),
    ready_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_report_issuances_attempts_nonnegative CHECK ((worker_attempts >= 0)),
    CONSTRAINT ck_report_issuances_fingerprints CHECK (((length((request_fingerprint)::text) = 64) AND (length((snapshot_sha256)::text) = 64) AND (length((authority_fingerprint)::text) = 64) AND (length((input_manifest_sha256)::text) = 64) AND (length((result_manifest_sha256)::text) = 64) AND (length((proof_manifest_sha256)::text) = 64) AND (length((report_snapshot_sha256)::text) = 64))),
    CONSTRAINT ck_report_issuances_roi_decision CHECK (roi_decision IN ('OMIT', 'INCLUDE')),
    CONSTRAINT ck_report_issuances_status CHECK (status IN ('queued', 'processing', 'ready', 'failed')),
    CONSTRAINT ck_report_issuances_status_fields CHECK (((((status)::text = 'processing'::text) AND (processing_token IS NOT NULL) AND (lease_expires_at IS NOT NULL) AND (ready_at IS NULL)) OR (((status)::text = 'ready'::text) AND (processing_token IS NULL) AND (lease_expires_at IS NULL) AND (ready_at IS NOT NULL) AND (last_error_code IS NULL)) OR (((status)::text = 'failed'::text) AND (processing_token IS NULL) AND (lease_expires_at IS NULL) AND (ready_at IS NULL) AND (last_error_code IS NOT NULL)) OR (((status)::text = 'queued'::text) AND (processing_token IS NULL) AND (lease_expires_at IS NULL) AND (ready_at IS NULL)))),
    CONSTRAINT ck_report_issuances_version_positive CHECK ((version > 0))
);
""",
    r"""
CREATE TABLE public.report_publication_intents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    report_issuance_id uuid NOT NULL,
    generation integer NOT NULL,
    state character varying(16) DEFAULT 'prepared'::character varying NOT NULL,
    csv_object_key character varying(1024) NOT NULL,
    pdf_object_key character varying(1024) NOT NULL,
    publisher_token uuid,
    lease_expires_at timestamp with time zone,
    last_error_code character varying(64),
    completed_at timestamp with time zone,
    abandoned_at timestamp with time zone,
    cleaned_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    write_protocol integer NOT NULL,
    CONSTRAINT ck_report_publication_intents_distinct_keys CHECK (((csv_object_key)::text <> (pdf_object_key)::text)),
    CONSTRAINT ck_report_publication_intents_generation CHECK ((generation > 0)),
    CONSTRAINT ck_report_publication_intents_state CHECK (state IN ('prepared', 'publishing', 'complete', 'abandoned', 'cleaning', 'cleaned')),
    CONSTRAINT ck_report_publication_intents_state_fields CHECK (((((state)::text = 'prepared'::text) AND (publisher_token IS NULL) AND (lease_expires_at IS NOT NULL) AND (completed_at IS NULL) AND (abandoned_at IS NULL) AND (cleaned_at IS NULL)) OR (((state)::text = 'publishing'::text) AND (publisher_token IS NOT NULL) AND (lease_expires_at IS NOT NULL) AND (completed_at IS NULL) AND (abandoned_at IS NULL) AND (cleaned_at IS NULL)) OR (((state)::text = 'complete'::text) AND (publisher_token IS NULL) AND (lease_expires_at IS NULL) AND (completed_at IS NOT NULL) AND (abandoned_at IS NULL) AND (cleaned_at IS NULL)) OR (((state)::text = 'abandoned'::text) AND (publisher_token IS NULL) AND (lease_expires_at IS NULL) AND (completed_at IS NULL) AND (abandoned_at IS NOT NULL) AND (cleaned_at IS NULL)) OR (((state)::text = 'cleaning'::text) AND (publisher_token IS NOT NULL) AND (lease_expires_at IS NOT NULL) AND (completed_at IS NULL) AND (abandoned_at IS NOT NULL) AND (cleaned_at IS NULL)) OR (((state)::text = 'cleaned'::text) AND (publisher_token IS NULL) AND (lease_expires_at IS NULL) AND (completed_at IS NULL) AND (abandoned_at IS NOT NULL) AND (cleaned_at IS NOT NULL)))),
    CONSTRAINT ck_report_publication_write_protocol CHECK ((write_protocol = ANY (ARRAY[0, 1])))
);
""",
    r"""
CREATE TABLE public.report_publication_writes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    publication_intent_id uuid NOT NULL,
    format character varying(8) NOT NULL,
    state character varying(16) DEFAULT 'registered'::character varying NOT NULL,
    error_code character varying(64),
    registered_at timestamp with time zone DEFAULT now() NOT NULL,
    settled_at timestamp with time zone,
    CONSTRAINT ck_report_publication_write_format CHECK (format IN ('csv', 'pdf')),
    CONSTRAINT ck_report_publication_write_state CHECK (((((state)::text = 'registered'::text) AND (settled_at IS NULL) AND (error_code IS NULL)) OR (((state)::text = 'settled'::text) AND (settled_at IS NOT NULL)) OR (((state)::text = 'uncertain'::text) AND (settled_at IS NULL) AND (error_code IS NOT NULL))))
);
""",
    r"""
CREATE TABLE public.retargeting_source_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    source_id uuid NOT NULL,
    sequence_number integer NOT NULL,
    event_type character varying(16) NOT NULL,
    snapshot jsonb NOT NULL,
    snapshot_sha256 character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_retargeting_source_events_event_type CHECK (event_type IN ('created', 'deactivated'))
);
""",
    r"""
CREATE TABLE public.retargeting_source_idempotency (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    actor_user_id uuid NOT NULL,
    operation character varying(16) NOT NULL,
    idempotency_key character varying(255) NOT NULL,
    request_fingerprint character varying(64) NOT NULL,
    source_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
""",
    r"""
CREATE TABLE public.retargeting_source_link_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    link_id uuid NOT NULL,
    sequence_number integer NOT NULL,
    event_type character varying(16) NOT NULL,
    snapshot jsonb NOT NULL,
    snapshot_sha256 character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_retargeting_source_link_events_event_type CHECK (event_type IN ('created', 'removed'))
);
""",
    r"""
CREATE TABLE public.retargeting_source_link_idempotency (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    actor_user_id uuid NOT NULL,
    operation character varying(16) NOT NULL,
    idempotency_key character varying(255) NOT NULL,
    request_fingerprint character varying(64) NOT NULL,
    link_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
""",
    r"""
CREATE TABLE public.retargeting_source_links (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    source_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    zone_id uuid NOT NULL,
    start_at timestamp with time zone NOT NULL,
    end_at timestamp with time zone NOT NULL,
    source_fingerprint character varying(64) NOT NULL,
    campaign_fingerprint character varying(64) NOT NULL,
    zone_fingerprint character varying(64) NOT NULL,
    snapshot jsonb NOT NULL,
    snapshot_sha256 character varying(64) NOT NULL,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    removed_at timestamp with time zone,
    CONSTRAINT ck_retargeting_source_links_status CHECK (status IN ('active', 'removed'))
);
""",
    r"""
CREATE TABLE public.retargeting_sources (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    source_type character varying(48) NOT NULL,
    snapshot jsonb NOT NULL,
    snapshot_sha256 character varying(64) NOT NULL,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    deactivated_at timestamp with time zone,
    CONSTRAINT ck_retargeting_sources_source_type CHECK (source_type IN ('website-traffic', 'digital-campaign-audience', 'CRM-upload-reference', 'UTM-source', 'manual-insight')),
    CONSTRAINT ck_retargeting_sources_status CHECK (status IN ('active', 'deactivated'))
);
""",
    r"""
CREATE TABLE public.route_replay_signatures (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trip_session_id uuid NOT NULL,
    trip_analytics_id uuid NOT NULL,
    status character varying(32) NOT NULL,
    detector_version text NOT NULL,
    detector_config_fingerprint character varying(64) NOT NULL,
    source_analytics_fingerprint character varying(64) NOT NULL,
    payload_fingerprint character varying(64),
    normalized_fingerprint character varying(64),
    point_count integer DEFAULT 0 NOT NULL,
    error_code character varying(64),
    computed_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_route_replay_signatures_outcome_fields CHECK (((((status)::text = 'computed'::text) AND (payload_fingerprint IS NOT NULL) AND (normalized_fingerprint IS NOT NULL) AND (error_code IS NULL)) OR (((status)::text = 'insufficient_data'::text) AND (payload_fingerprint IS NULL) AND (normalized_fingerprint IS NULL) AND (error_code IS NULL)) OR (((status)::text = 'error'::text) AND (payload_fingerprint IS NULL) AND (normalized_fingerprint IS NULL) AND (error_code IS NOT NULL)))),
    CONSTRAINT ck_route_replay_signatures_point_count_non_negative CHECK ((point_count >= 0)),
    CONSTRAINT ck_route_replay_signatures_status CHECK (status IN ('computed', 'insufficient_data', 'error'))
);
""",
    r"""
CREATE TABLE public.stored_files (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    upload_intent_id uuid,
    organization_id uuid,
    uploader_user_id uuid NOT NULL,
    purpose character varying(32) NOT NULL,
    original_filename character varying(255) NOT NULL,
    storage_key character varying(1024) NOT NULL,
    content_type character varying(255) NOT NULL,
    size_bytes bigint NOT NULL,
    checksum_sha256 character varying(64) NOT NULL,
    scan_status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    actual_content_type character varying(255),
    scan_attempts integer DEFAULT 0 NOT NULL,
    scan_error_code character varying(64),
    malware_signature character varying(255),
    next_scan_at timestamp with time zone,
    scanned_at timestamp with time zone,
    subject_user_id uuid,
    CONSTRAINT ck_stored_files_generated_source CHECK (((((purpose)::text = 'report_export'::text) AND (upload_intent_id IS NULL)) OR (((purpose)::text <> 'report_export'::text) AND (upload_intent_id IS NOT NULL)))),
    CONSTRAINT ck_stored_files_purpose CHECK (purpose IN ('creative', 'driver_kyc', 'vehicle_evidence', 'installation_evidence', 'report_export')),
    CONSTRAINT ck_stored_files_scan_status CHECK (scan_status IN ('pending', 'clean', 'infected', 'rejected', 'error')),
    CONSTRAINT ck_stored_files_scope CHECK ((purpose IN ('creative', 'report_export') AND organization_id IS NOT NULL AND subject_user_id IS NULL) OR (purpose IN ('driver_kyc', 'vehicle_evidence', 'installation_evidence') AND organization_id IS NULL AND subject_user_id IS NOT NULL)),
    CONSTRAINT ck_stored_files_sha256_length CHECK ((length((checksum_sha256)::text) = 64)),
    CONSTRAINT ck_stored_files_size_positive CHECK ((size_bytes > 0))
);
""",
    r"""
CREATE TABLE public.stored_object_deletions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    stored_file_id uuid,
    upload_intent_id uuid,
    organization_id uuid,
    subject_user_id uuid,
    owner_type character varying(64) NOT NULL,
    owner_id uuid NOT NULL,
    storage_key character varying(1024) NOT NULL,
    storage_key_sha256 character varying(64) NOT NULL,
    object_checksum_sha256 character varying(64) NOT NULL,
    reason character varying(64) NOT NULL,
    request_fingerprint character varying(64) NOT NULL,
    state character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    last_error_code character varying(64),
    provider_deleted_at timestamp with time zone,
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_stored_object_deletions_fingerprint CHECK ((length((request_fingerprint)::text) = 64)),
    CONSTRAINT ck_stored_object_deletions_key_hash CHECK ((length((storage_key_sha256)::text) = 64)),
    CONSTRAINT ck_stored_object_deletions_object_checksum CHECK ((length((object_checksum_sha256)::text) = 64)),
    CONSTRAINT ck_stored_object_deletions_scope CHECK (((organization_id IS NOT NULL) <> (subject_user_id IS NOT NULL))),
    CONSTRAINT ck_stored_object_deletions_state CHECK (state IN ('pending', 'provider_deleted', 'completed')),
    CONSTRAINT ck_stored_object_deletions_timeline CHECK (((((state)::text = 'pending'::text) AND (provider_deleted_at IS NULL) AND (completed_at IS NULL)) OR (((state)::text = 'provider_deleted'::text) AND (provider_deleted_at IS NOT NULL) AND (completed_at IS NULL)) OR (((state)::text = 'completed'::text) AND (provider_deleted_at IS NOT NULL) AND (completed_at IS NOT NULL))))
);
""",
    r"""
CREATE TABLE public.traffic_density_profiles (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    description text,
    profile_type character varying(32) NOT NULL,
    traffic_density_per_km numeric(12,4) NOT NULL,
    dwell_impressions_per_minute numeric(12,4) NOT NULL,
    road_category_weight numeric(8,4) DEFAULT 1.0 NOT NULL,
    morning_weight numeric(8,4) DEFAULT 1.0 NOT NULL,
    midday_weight numeric(8,4) DEFAULT 1.0 NOT NULL,
    evening_weight numeric(8,4) DEFAULT 1.0 NOT NULL,
    night_weight numeric(8,4) DEFAULT 0.7 NOT NULL,
    target_zone_weight numeric(8,4) DEFAULT 1.0 NOT NULL,
    bonus_zone_weight numeric(8,4) DEFAULT 1.25 NOT NULL,
    exclusion_zone_weight numeric(8,4) DEFAULT 0.0 NOT NULL,
    is_default boolean DEFAULT false NOT NULL,
    status character varying(16) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    lineage_id uuid NOT NULL,
    revision integer NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    supersedes_id uuid,
    value_fingerprint character varying(64) NOT NULL,
    CONSTRAINT ck_traffic_density_profiles_bonus_weight_non_negative CHECK ((bonus_zone_weight >= (0)::numeric)),
    CONSTRAINT ck_traffic_density_profiles_density_non_negative CHECK ((traffic_density_per_km >= (0)::numeric)),
    CONSTRAINT ck_traffic_density_profiles_dwell_non_negative CHECK ((dwell_impressions_per_minute >= (0)::numeric)),
    CONSTRAINT ck_traffic_density_profiles_evening_weight_non_negative CHECK ((evening_weight >= (0)::numeric)),
    CONSTRAINT ck_traffic_density_profiles_exclusion_weight_non_negative CHECK ((exclusion_zone_weight >= (0)::numeric)),
    CONSTRAINT ck_traffic_density_profiles_midday_weight_non_negative CHECK ((midday_weight >= (0)::numeric)),
    CONSTRAINT ck_traffic_density_profiles_morning_weight_non_negative CHECK ((morning_weight >= (0)::numeric)),
    CONSTRAINT ck_traffic_density_profiles_night_weight_non_negative CHECK ((night_weight >= (0)::numeric)),
    CONSTRAINT ck_traffic_density_profiles_profile_type CHECK (profile_type IN ('default', 'urban', 'suburban', 'highway', 'custom')),
    CONSTRAINT ck_traffic_density_profiles_revision_positive CHECK ((revision >= 1)),
    CONSTRAINT ck_traffic_density_profiles_road_weight_non_negative CHECK ((road_category_weight >= (0)::numeric)),
    CONSTRAINT ck_traffic_density_profiles_status CHECK (status IN ('active', 'inactive')),
    CONSTRAINT ck_traffic_density_profiles_target_weight_non_negative CHECK ((target_zone_weight >= (0)::numeric)),
    CONSTRAINT ck_traffic_density_profiles_value_fingerprint_length CHECK ((length((value_fingerprint)::text) = 64))
);
""",
    r"""
CREATE TABLE public.trip_analytics (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trip_session_id uuid NOT NULL,
    assignment_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    driver_profile_id uuid NOT NULL,
    vehicle_id uuid NOT NULL,
    formula_version text DEFAULT 'route_analytics_v1'::text NOT NULL,
    status character varying(32) NOT NULL,
    ping_count integer NOT NULL,
    valid_ping_count integer NOT NULL,
    invalid_ping_count integer NOT NULL,
    started_at timestamp with time zone,
    ended_at timestamp with time zone,
    first_ping_at timestamp with time zone,
    last_ping_at timestamp with time zone,
    duration_seconds integer DEFAULT 0 NOT NULL,
    active_tracking_seconds integer DEFAULT 0 NOT NULL,
    moving_seconds integer DEFAULT 0 NOT NULL,
    stationary_seconds integer DEFAULT 0 NOT NULL,
    distance_m numeric(14,2) DEFAULT 0 NOT NULL,
    avg_speed_mps numeric(12,4),
    max_observed_speed_mps numeric(12,4),
    avg_accuracy_m numeric(10,2),
    poor_accuracy_ping_count integer DEFAULT 0 NOT NULL,
    target_zone_distance_m numeric(14,2) DEFAULT 0 NOT NULL,
    bonus_zone_distance_m numeric(14,2) DEFAULT 0 NOT NULL,
    exclusion_zone_distance_m numeric(14,2) DEFAULT 0 NOT NULL,
    target_zone_seconds integer DEFAULT 0 NOT NULL,
    bonus_zone_seconds integer DEFAULT 0 NOT NULL,
    exclusion_zone_seconds integer DEFAULT 0 NOT NULL,
    quality_score numeric(5,4) NOT NULL,
    computed_at timestamp with time zone NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_trip_analytics_active_tracking_seconds_non_negative CHECK ((active_tracking_seconds >= 0)),
    CONSTRAINT ck_trip_analytics_bonus_zone_distance_m_non_negative CHECK ((bonus_zone_distance_m >= (0)::numeric)),
    CONSTRAINT ck_trip_analytics_bonus_zone_seconds_non_negative CHECK ((bonus_zone_seconds >= 0)),
    CONSTRAINT ck_trip_analytics_distance_m_non_negative CHECK ((distance_m >= (0)::numeric)),
    CONSTRAINT ck_trip_analytics_duration_seconds_non_negative CHECK ((duration_seconds >= 0)),
    CONSTRAINT ck_trip_analytics_exclusion_zone_distance_m_non_negative CHECK ((exclusion_zone_distance_m >= (0)::numeric)),
    CONSTRAINT ck_trip_analytics_exclusion_zone_seconds_non_negative CHECK ((exclusion_zone_seconds >= 0)),
    CONSTRAINT ck_trip_analytics_invalid_ping_count_non_negative CHECK ((invalid_ping_count >= 0)),
    CONSTRAINT ck_trip_analytics_moving_seconds_non_negative CHECK ((moving_seconds >= 0)),
    CONSTRAINT ck_trip_analytics_ping_count_non_negative CHECK ((ping_count >= 0)),
    CONSTRAINT ck_trip_analytics_poor_accuracy_ping_count_non_negative CHECK ((poor_accuracy_ping_count >= 0)),
    CONSTRAINT ck_trip_analytics_quality_score_range CHECK (((quality_score >= (0)::numeric) AND (quality_score <= (1)::numeric))),
    CONSTRAINT ck_trip_analytics_stationary_seconds_non_negative CHECK ((stationary_seconds >= 0)),
    CONSTRAINT ck_trip_analytics_status CHECK (status IN ('computed', 'insufficient_data', 'blocked')),
    CONSTRAINT ck_trip_analytics_target_zone_distance_m_non_negative CHECK ((target_zone_distance_m >= (0)::numeric)),
    CONSTRAINT ck_trip_analytics_target_zone_seconds_non_negative CHECK ((target_zone_seconds >= 0)),
    CONSTRAINT ck_trip_analytics_valid_ping_count_non_negative CHECK ((valid_ping_count >= 0))
);
""",
    r"""
CREATE TABLE public.trip_evidence_manifest_entries (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    trip_session_id uuid NOT NULL,
    batch_sequence integer NOT NULL,
    idempotency_key text NOT NULL,
    payload_hash_version integer NOT NULL,
    payload_hash character varying(64) NOT NULL,
    submitted_count integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_trip_manifest_entries_hash_version CHECK ((payload_hash_version = 2)),
    CONSTRAINT ck_trip_manifest_entries_sequence CHECK ((batch_sequence >= 0)),
    CONSTRAINT ck_trip_manifest_entries_submitted_count CHECK ((submitted_count >= 0))
);
""",
    r"""
CREATE TABLE public.trip_sessions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    assignment_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    driver_profile_id uuid NOT NULL,
    vehicle_id uuid NOT NULL,
    started_by_user_id uuid NOT NULL,
    status character varying(32) NOT NULL,
    started_at timestamp with time zone NOT NULL,
    ended_at timestamp with time zone,
    end_reason text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    sealed_at timestamp with time zone,
    seal_reason text,
    display_proof_id uuid,
    evidence_protocol_version integer DEFAULT 2 NOT NULL,
    evidence_manifest_version integer,
    evidence_manifest_root_sha256 character varying(64),
    evidence_manifest_batch_count integer,
    evidence_manifest_ping_count integer,
    evidence_manifest_committed_at timestamp with time zone,
    evidence_manifest_complete boolean DEFAULT false NOT NULL,
    evidence_manifest_verified_at timestamp with time zone,
    evidence_manifest_receipt_format_version integer,
    evidence_manifest_receipt_key_version integer,
    evidence_manifest_receipt_signature text,
    grace_expired_at timestamp with time zone,
    evidence_adjudicated_at timestamp with time zone,
    evidence_adjudication_outcome character varying(32),
    evidence_adjudication_receipt_format_version integer,
    evidence_adjudication_receipt_key_version integer,
    evidence_adjudication_receipt_signature text,
    CONSTRAINT ck_trip_sessions_adjudication_cluster CHECK ((((evidence_adjudicated_at IS NULL) AND (evidence_adjudication_outcome IS NULL) AND (evidence_adjudication_receipt_format_version IS NULL) AND (evidence_adjudication_receipt_key_version IS NULL) AND (evidence_adjudication_receipt_signature IS NULL)) OR ((evidence_adjudicated_at IS NOT NULL) AND ((evidence_adjudication_outcome)::text = 'incomplete_grace_expired'::text) AND (evidence_adjudication_receipt_format_version = 2) AND (evidence_adjudication_receipt_key_version IS NOT NULL) AND (evidence_adjudication_receipt_signature IS NOT NULL)))),
    CONSTRAINT ck_trip_sessions_adjudication_excludes_verification CHECK (((evidence_adjudicated_at IS NULL) OR (evidence_manifest_verified_at IS NULL))),
    CONSTRAINT ck_trip_sessions_evidence_protocol_version CHECK ((evidence_protocol_version = 2)),
    CONSTRAINT ck_trip_sessions_manifest_batch_count_non_negative CHECK (((evidence_manifest_batch_count IS NULL) OR (evidence_manifest_batch_count >= 0))),
    CONSTRAINT ck_trip_sessions_manifest_header_cluster CHECK ((((evidence_manifest_version IS NULL) AND (evidence_manifest_root_sha256 IS NULL) AND (evidence_manifest_batch_count IS NULL) AND (evidence_manifest_ping_count IS NULL) AND (evidence_manifest_committed_at IS NULL)) OR ((evidence_manifest_version = 2) AND (evidence_manifest_root_sha256 IS NOT NULL) AND (evidence_manifest_batch_count IS NOT NULL) AND (evidence_manifest_ping_count IS NOT NULL) AND (evidence_manifest_committed_at IS NOT NULL)))),
    CONSTRAINT ck_trip_sessions_manifest_ping_count_non_negative CHECK (((evidence_manifest_ping_count IS NULL) OR (evidence_manifest_ping_count >= 0))),
    CONSTRAINT ck_trip_sessions_manifest_receipt_cluster CHECK ((((evidence_manifest_verified_at IS NULL) AND (evidence_manifest_receipt_format_version IS NULL) AND (evidence_manifest_receipt_key_version IS NULL) AND (evidence_manifest_receipt_signature IS NULL)) OR (evidence_manifest_complete AND (evidence_manifest_verified_at IS NOT NULL) AND (evidence_manifest_receipt_format_version = 2) AND (evidence_manifest_receipt_key_version IS NOT NULL) AND (evidence_manifest_receipt_signature IS NOT NULL)))),
    CONSTRAINT ck_trip_sessions_seal_reason CHECK (((seal_reason IS NULL) OR (seal_reason = ANY (ARRAY['client_complete'::text, 'late_data_complete'::text])))),
    CONSTRAINT ck_trip_sessions_sealed_fields CHECK ((((status)::text = 'sealed'::text) = ((sealed_at IS NOT NULL) AND (seal_reason IS NOT NULL)))),
    CONSTRAINT ck_trip_sessions_status CHECK (status IN ('active', 'ended', 'sealed')),
    CONSTRAINT ck_trip_sessions_v2_sealed_manifest_verified CHECK ((((status)::text <> 'sealed'::text) OR (evidence_manifest_verified_at IS NOT NULL)))
);
""",
    r"""
CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    full_name character varying(255) NOT NULL,
    phone character varying(32),
    role character varying(32) NOT NULL,
    status character varying(32) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    must_change_password boolean DEFAULT false NOT NULL,
    session_version integer DEFAULT 1 NOT NULL,
    CONSTRAINT ck_users_role CHECK (role IN ('admin', 'advertiser', 'driver')),
    CONSTRAINT ck_users_status CHECK (status IN ('active', 'invited', 'suspended', 'disabled'))
);
""",
    r"""
CREATE TABLE public.vehicle_evidence_documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    submission_id uuid NOT NULL,
    stored_file_id uuid NOT NULL,
    document_type character varying(32) NOT NULL,
    CONSTRAINT ck_vehicle_evidence_documents_type CHECK (document_type IN ('registration', 'insurance', 'vehicle_photo'))
);
""",
    r"""
CREATE TABLE public.vehicle_evidence_review_decisions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    submission_id uuid NOT NULL,
    sequence integer NOT NULL,
    client_request_id uuid NOT NULL,
    request_fingerprint character varying(64) NOT NULL,
    decision character varying(32) NOT NULL,
    reason_code character varying(64) NOT NULL,
    owner_match_confirmed boolean NOT NULL,
    vehicle_identity_confirmed boolean NOT NULL,
    roadworthy_confirmed boolean NOT NULL,
    pilot_car_confirmed boolean NOT NULL,
    documents_readable_confirmed boolean NOT NULL,
    valid_until timestamp with time zone,
    decided_by_user_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    document_reviews json DEFAULT '{}'::json NOT NULL,
    CONSTRAINT ck_vehicle_review_decisions_admin_actor CHECK ((((decision)::text = 'expired'::text) OR (decided_by_user_id IS NOT NULL))),
    CONSTRAINT ck_vehicle_review_decisions_decision CHECK (decision IN ('approved', 'rejected', 'expired')),
    CONSTRAINT ck_vehicle_review_decisions_facts CHECK ((decision = 'approved' AND reason_code = 'complete_current_evidence' AND owner_match_confirmed AND vehicle_identity_confirmed AND roadworthy_confirmed AND pilot_car_confirmed AND documents_readable_confirmed AND valid_until IS NOT NULL) OR (decision IN ('rejected', 'expired') AND reason_code <> 'complete_current_evidence')),
    CONSTRAINT ck_vehicle_review_decisions_fingerprint CHECK ((length((request_fingerprint)::text) = 64)),
    CONSTRAINT ck_vehicle_review_decisions_reason CHECK (reason_code IN ('complete_current_evidence', 'missing_evidence', 'unsafe_evidence', 'expired_evidence', 'owner_mismatch', 'vehicle_identity_mismatch', 'not_roadworthy', 'not_pilot_eligible', 'unreadable_evidence')),
    CONSTRAINT ck_vehicle_review_decisions_sequence CHECK ((sequence > 0))
);
""",
    r"""
CREATE TABLE public.vehicle_evidence_submissions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    vehicle_id uuid NOT NULL,
    version integer NOT NULL,
    client_request_id uuid NOT NULL,
    status character varying(32) NOT NULL,
    created_by_user_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    plate_number_snapshot character varying(32),
    plate_number_normalized_snapshot character varying(32),
    plate_country_code_snapshot character varying(2),
    vehicle_type_snapshot character varying(32),
    make_snapshot character varying(128),
    model_snapshot character varying(128),
    year_snapshot integer,
    color_snapshot character varying(64),
    snapshot_trusted boolean DEFAULT false NOT NULL,
    purged_at timestamp with time zone,
    CONSTRAINT ck_vehicle_evidence_submissions_payload_retention CHECK ((purged_at IS NULL AND plate_number_snapshot IS NOT NULL AND plate_number_normalized_snapshot IS NOT NULL AND plate_country_code_snapshot IS NOT NULL AND vehicle_type_snapshot IS NOT NULL) OR (purged_at IS NOT NULL AND status IN ('rejected', 'expired') AND plate_number_snapshot IS NULL AND plate_number_normalized_snapshot IS NULL AND plate_country_code_snapshot IS NULL AND vehicle_type_snapshot IS NULL AND make_snapshot IS NULL AND model_snapshot IS NULL AND year_snapshot IS NULL AND color_snapshot IS NULL)),
    CONSTRAINT ck_vehicle_evidence_submissions_status CHECK (status IN ('pending_review', 'approved', 'rejected', 'expired')),
    CONSTRAINT ck_vehicle_evidence_submissions_version CHECK ((version > 0))
);
""",
    r"""
CREATE TABLE public.vehicles (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    driver_profile_id uuid NOT NULL,
    plate_number character varying(32) NOT NULL,
    plate_number_normalized character varying(32) NOT NULL,
    plate_country_code character varying(2) NOT NULL,
    vehicle_type character varying(32) NOT NULL,
    make character varying(128),
    model character varying(128),
    year integer,
    color character varying(64),
    status character varying(32) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_vehicles_status CHECK (status IN ('pending', 'active', 'inactive', 'suspended')),
    CONSTRAINT ck_vehicles_vehicle_type CHECK (vehicle_type IN ('car', 'van', 'minibus', 'bus', 'motorcycle', 'tricycle', 'other'))
);
""",
    r"""
CREATE TABLE public.whatsapp_consents (
    id uuid NOT NULL,
    driver_profile_id uuid NOT NULL,
    phone_version_id uuid NOT NULL,
    version integer NOT NULL,
    purpose character varying(128) NOT NULL,
    notice_version character varying(64) NOT NULL,
    granted_by_user_id uuid NOT NULL,
    granted_at timestamp with time zone NOT NULL,
    withdrawn_by_user_id uuid,
    withdrawn_at timestamp with time zone,
    CONSTRAINT ck_whatsapp_consents_notice_version CHECK ((length(TRIM(BOTH FROM notice_version)) > 0)),
    CONSTRAINT ck_whatsapp_consents_purpose CHECK ((length(TRIM(BOTH FROM purpose)) > 0)),
    CONSTRAINT ck_whatsapp_consents_timeline CHECK (((withdrawn_at IS NULL) OR (withdrawn_at >= granted_at))),
    CONSTRAINT ck_whatsapp_consents_version CHECK ((version > 0))
);
""",
    r"""
ALTER TABLE ONLY public.location_pings ATTACH PARTITION public.location_pings_p2026_07 FOR VALUES FROM ('2026-07-01 00:00:00+00') TO ('2026-08-01 00:00:00+00');
""",
    r"""
ALTER TABLE ONLY public.location_pings ATTACH PARTITION public.location_pings_p2026_08 FOR VALUES FROM ('2026-08-01 00:00:00+00') TO ('2026-09-01 00:00:00+00');
""",
    r"""
ALTER TABLE ONLY public.location_pings ATTACH PARTITION public.location_pings_p2026_09 FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00');
""",
    r"""
ALTER TABLE ONLY public.location_pings ATTACH PARTITION public.location_pings_p2026_10 FOR VALUES FROM ('2026-10-01 00:00:00+00') TO ('2026-11-01 00:00:00+00');
""",
    r"""
ALTER TABLE ONLY public.location_pings ATTACH PARTITION public.location_pings_p2026_11 FOR VALUES FROM ('2026-11-01 00:00:00+00') TO ('2026-12-01 00:00:00+00');
""",
    r"""
ALTER TABLE ONLY public.location_pings ATTACH PARTITION public.location_pings_p2026_12 FOR VALUES FROM ('2026-12-01 00:00:00+00') TO ('2027-01-01 00:00:00+00');
""",
    r"""
ALTER TABLE ONLY public.location_pings ATTACH PARTITION public.location_pings_p2027_01 FOR VALUES FROM ('2027-01-01 00:00:00+00') TO ('2027-02-01 00:00:00+00');
""",
    r"""
ALTER TABLE ONLY public.location_pings ATTACH PARTITION public.location_pings_p2027_02 FOR VALUES FROM ('2027-02-01 00:00:00+00') TO ('2027-03-01 00:00:00+00');
""",
    r"""
ALTER TABLE ONLY public.advertiser_organization_notification_preferences
    ADD CONSTRAINT advertiser_organization_notification_preferences_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.advertiser_organizations
    ADD CONSTRAINT advertiser_organizations_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.assignment_activity_flag_events
    ADD CONSTRAINT assignment_activity_flag_events_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.assignment_activity_flags
    ADD CONSTRAINT assignment_activity_flags_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.assignment_rule_bindings
    ADD CONSTRAINT assignment_rule_bindings_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.audience_deliveries
    ADD CONSTRAINT audience_deliveries_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.audience_delivery_approvals
    ADD CONSTRAINT audience_delivery_approvals_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.audit_event_subject_resolutions
    ADD CONSTRAINT audit_event_subject_resolutions_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT audit_events_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.budget_campaign_transitions
    ADD CONSTRAINT budget_campaign_transitions_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.budget_policy_evaluations
    ADD CONSTRAINT budget_policy_evaluations_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.campaign_activation_events
    ADD CONSTRAINT campaign_activation_events_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.campaign_assignments
    ADD CONSTRAINT campaign_assignments_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.campaign_cancellation_settlement_revisions
    ADD CONSTRAINT campaign_cancellation_settlement_revisions_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.campaign_cancellations
    ADD CONSTRAINT campaign_cancellations_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.campaign_change_requests
    ADD CONSTRAINT campaign_change_requests_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.campaign_change_revisions
    ADD CONSTRAINT campaign_change_revisions_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.campaign_creatives
    ADD CONSTRAINT campaign_creatives_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.campaign_financial_authorizations
    ADD CONSTRAINT campaign_financial_authorizations_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.campaign_liability_reservations
    ADD CONSTRAINT campaign_liability_reservations_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.campaign_payout_rule_revisions
    ADD CONSTRAINT campaign_payout_rule_revisions_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.campaign_payout_rules
    ADD CONSTRAINT campaign_payout_rules_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.campaign_review_events
    ADD CONSTRAINT campaign_review_events_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.campaign_zones
    ADD CONSTRAINT campaign_zones_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT campaigns_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.commercial_quotation_revisions
    ADD CONSTRAINT commercial_quotation_revisions_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.commercial_quote_requests
    ADD CONSTRAINT commercial_quote_requests_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.commercial_terms
    ADD CONSTRAINT commercial_terms_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.complaint_messages
    ADD CONSTRAINT complaint_messages_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.complaints
    ADD CONSTRAINT complaints_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.creative_review_events
    ADD CONSTRAINT creative_review_events_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.data_purge_audit
    ADD CONSTRAINT data_purge_audit_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.data_subject_location_assessments
    ADD CONSTRAINT data_subject_location_assessments_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.data_subject_requests
    ADD CONSTRAINT data_subject_requests_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.disclosure_query_decisions
    ADD CONSTRAINT disclosure_query_decisions_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.display_proof_challenges
    ADD CONSTRAINT display_proof_challenges_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.display_proofs
    ADD CONSTRAINT display_proofs_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.driver_account_setup_tokens
    ADD CONSTRAINT driver_account_setup_tokens_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.driver_application_access_tokens
    ADD CONSTRAINT driver_application_access_tokens_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.driver_applications
    ADD CONSTRAINT driver_applications_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.driver_currency_debt_accounts
    ADD CONSTRAINT driver_currency_debt_accounts_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.driver_kyc_documents
    ADD CONSTRAINT driver_kyc_documents_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.driver_kyc_review_decisions
    ADD CONSTRAINT driver_kyc_review_decisions_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.driver_kyc_submissions
    ADD CONSTRAINT driver_kyc_submissions_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.driver_phone_versions
    ADD CONSTRAINT driver_phone_versions_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.driver_profiles
    ADD CONSTRAINT driver_profiles_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.earnings_ledger_entries
    ADD CONSTRAINT earnings_ledger_entries_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.evidence_verifications
    ADD CONSTRAINT evidence_verifications_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.expedited_production_waivers
    ADD CONSTRAINT expedited_production_waivers_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.exposure_scores
    ADD CONSTRAINT exposure_scores_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.exposure_segment_cells
    ADD CONSTRAINT exposure_segment_cells_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.exposure_segments
    ADD CONSTRAINT exposure_segments_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.file_upload_intents
    ADD CONSTRAINT file_upload_intents_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.financial_authorization_allocations
    ADD CONSTRAINT financial_authorization_allocations_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.fraud_assessments
    ADD CONSTRAINT fraud_assessments_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.fraud_disputes
    ADD CONSTRAINT fraud_disputes_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.fraud_flags
    ADD CONSTRAINT fraud_flags_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.impression_estimates
    ADD CONSTRAINT impression_estimates_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.installation_evidence_photos
    ADD CONSTRAINT installation_evidence_photos_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.installation_evidence_submissions
    ADD CONSTRAINT installation_evidence_submissions_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.invoice_corrections
    ADD CONSTRAINT invoice_corrections_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.invoice_issuer_profiles
    ADD CONSTRAINT invoice_issuer_profiles_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.invoice_number_sequences
    ADD CONSTRAINT invoice_number_sequences_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.location_ping_batches
    ADD CONSTRAINT location_ping_batches_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.location_pings
    ADD CONSTRAINT location_pings_pkey PRIMARY KEY (id, recorded_at);
""",
    r"""
ALTER TABLE ONLY public.location_pings_p2026_07
    ADD CONSTRAINT location_pings_p2026_07_pkey PRIMARY KEY (id, recorded_at);
""",
    r"""
ALTER TABLE ONLY public.location_pings_p2026_08
    ADD CONSTRAINT location_pings_p2026_08_pkey PRIMARY KEY (id, recorded_at);
""",
    r"""
ALTER TABLE ONLY public.location_pings_p2026_09
    ADD CONSTRAINT location_pings_p2026_09_pkey PRIMARY KEY (id, recorded_at);
""",
    r"""
ALTER TABLE ONLY public.location_pings_p2026_10
    ADD CONSTRAINT location_pings_p2026_10_pkey PRIMARY KEY (id, recorded_at);
""",
    r"""
ALTER TABLE ONLY public.location_pings_p2026_11
    ADD CONSTRAINT location_pings_p2026_11_pkey PRIMARY KEY (id, recorded_at);
""",
    r"""
ALTER TABLE ONLY public.location_pings_p2026_12
    ADD CONSTRAINT location_pings_p2026_12_pkey PRIMARY KEY (id, recorded_at);
""",
    r"""
ALTER TABLE ONLY public.location_pings_p2027_01
    ADD CONSTRAINT location_pings_p2027_01_pkey PRIMARY KEY (id, recorded_at);
""",
    r"""
ALTER TABLE ONLY public.location_pings_p2027_02
    ADD CONSTRAINT location_pings_p2027_02_pkey PRIMARY KEY (id, recorded_at);
""",
    r"""
ALTER TABLE ONLY public.manual_driver_contact_tasks
    ADD CONSTRAINT manual_driver_contact_tasks_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.measurement_run_proof_bindings
    ADD CONSTRAINT measurement_run_proof_bindings_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.measurement_runs
    ADD CONSTRAINT measurement_runs_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.notification_delivery_receipts
    ADD CONSTRAINT notification_delivery_receipts_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.organization_memberships
    ADD CONSTRAINT organization_memberships_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.password_reset_attempts
    ADD CONSTRAINT password_reset_attempts_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payee_bank_account_payout_verifications
    ADD CONSTRAINT payee_bank_account_payout_verifications_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payee_bank_account_versions
    ADD CONSTRAINT payee_bank_account_versions_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payee_bank_accounts
    ADD CONSTRAINT payee_bank_accounts_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payee_versions
    ADD CONSTRAINT payee_versions_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payees
    ADD CONSTRAINT payees_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payment_checkout_intents
    ADD CONSTRAINT payment_checkout_intents_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payment_gateway_events
    ADD CONSTRAINT payment_gateway_events_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payment_gateway_processing_attempts
    ADD CONSTRAINT payment_gateway_processing_attempts_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payment_receipts
    ADD CONSTRAINT payment_receipts_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payout_automatic_alerts
    ADD CONSTRAINT payout_automatic_alerts_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payout_automatic_controls
    ADD CONSTRAINT payout_automatic_controls_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payout_automatic_runs
    ADD CONSTRAINT payout_automatic_runs_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payout_batch_lines
    ADD CONSTRAINT payout_batch_lines_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payout_batches
    ADD CONSTRAINT payout_batches_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payout_calculations
    ADD CONSTRAINT payout_calculations_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payout_correction_orders
    ADD CONSTRAINT payout_correction_orders_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payout_debt_allocations
    ADD CONSTRAINT payout_debt_allocations_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payout_debt_obligations
    ADD CONSTRAINT payout_debt_obligations_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payout_debt_paid_sources
    ADD CONSTRAINT payout_debt_paid_sources_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payout_debt_settlements
    ADD CONSTRAINT payout_debt_settlements_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payout_line_reconciliation_events
    ADD CONSTRAINT payout_line_reconciliation_events_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payout_provider_event_processing_attempts
    ADD CONSTRAINT payout_provider_event_processing_attempts_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payout_provider_events
    ADD CONSTRAINT payout_provider_events_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payout_recovery_incidents
    ADD CONSTRAINT payout_recovery_incidents_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payout_submission_attempts
    ADD CONSTRAINT payout_submission_attempts_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payout_submission_intents
    ADD CONSTRAINT payout_submission_intents_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.payout_submission_observations
    ADD CONSTRAINT payout_submission_observations_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.phone_verification_challenges
    ADD CONSTRAINT phone_verification_challenges_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.production_starts
    ADD CONSTRAINT production_starts_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.quarantined_ping_batches
    ADD CONSTRAINT quarantined_ping_batches_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.receipt_allocations
    ADD CONSTRAINT receipt_allocations_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.receipt_lifecycle_events
    ADD CONSTRAINT receipt_lifecycle_events_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.receipt_reconciliations
    ADD CONSTRAINT receipt_reconciliations_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.refund_settlements
    ADD CONSTRAINT refund_settlements_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.report_artifacts
    ADD CONSTRAINT report_artifacts_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.report_issuances
    ADD CONSTRAINT report_issuances_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.report_publication_intents
    ADD CONSTRAINT report_publication_intents_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.report_publication_writes
    ADD CONSTRAINT report_publication_writes_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_events
    ADD CONSTRAINT retargeting_source_events_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_idempotency
    ADD CONSTRAINT retargeting_source_idempotency_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_link_events
    ADD CONSTRAINT retargeting_source_link_events_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_link_idempotency
    ADD CONSTRAINT retargeting_source_link_idempotency_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_links
    ADD CONSTRAINT retargeting_source_links_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.retargeting_sources
    ADD CONSTRAINT retargeting_sources_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.route_replay_signatures
    ADD CONSTRAINT route_replay_signatures_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.stored_files
    ADD CONSTRAINT stored_files_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.stored_object_deletions
    ADD CONSTRAINT stored_object_deletions_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.traffic_density_profiles
    ADD CONSTRAINT traffic_density_profiles_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.trip_analytics
    ADD CONSTRAINT trip_analytics_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.trip_evidence_manifest_entries
    ADD CONSTRAINT trip_evidence_manifest_entries_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.trip_sessions
    ADD CONSTRAINT trip_sessions_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.advertiser_organization_notification_preferences
    ADD CONSTRAINT uq_advertiser_org_notification_preferences_organization UNIQUE (advertiser_organization_id);
""",
    r"""
ALTER TABLE ONLY public.assignment_activity_flag_events
    ADD CONSTRAINT uq_assignment_activity_flag_events_sequence UNIQUE (flag_id, sequence_number);
""",
    r"""
ALTER TABLE ONLY public.assignment_activity_flags
    ADD CONSTRAINT uq_assignment_activity_flags_assignment_type_window UNIQUE (assignment_id, flag_type, window_start, window_end);
""",
    r"""
ALTER TABLE ONLY public.assignment_rule_bindings
    ADD CONSTRAINT uq_assignment_rule_bindings_assignment_id UNIQUE (assignment_id);
""",
    r"""
ALTER TABLE ONLY public.audience_deliveries
    ADD CONSTRAINT uq_audience_deliveries_actor_operation_key UNIQUE (actor_user_id, operation, idempotency_key);
""",
    r"""
ALTER TABLE ONLY public.audience_delivery_approvals
    ADD CONSTRAINT uq_audience_delivery_approvals_actor_key UNIQUE (approved_by_user_id, idempotency_key);
""",
    r"""
ALTER TABLE ONLY public.audit_event_subject_resolutions
    ADD CONSTRAINT uq_audit_subject_resolution UNIQUE (audit_event_id, role, subject_user_id);
""",
    r"""
ALTER TABLE ONLY public.budget_policy_evaluations
    ADD CONSTRAINT uq_budget_policy_evaluation_key UNIQUE (campaign_id, evaluation_key);
""",
    r"""
ALTER TABLE ONLY public.budget_campaign_transitions
    ADD CONSTRAINT uq_budget_transition_evaluation_action UNIQUE (evaluation_id, action);
""",
    r"""
ALTER TABLE ONLY public.campaign_cancellation_settlement_revisions
    ADD CONSTRAINT uq_campaign_cancellation_settlement_revisions_number UNIQUE (cancellation_id, revision_number);
""",
    r"""
ALTER TABLE ONLY public.campaign_cancellations
    ADD CONSTRAINT uq_campaign_cancellations_campaign UNIQUE (campaign_id);
""",
    r"""
ALTER TABLE ONLY public.campaign_change_requests
    ADD CONSTRAINT uq_campaign_change_requests_retry UNIQUE (campaign_id, requested_by_user_id, client_request_id);
""",
    r"""
ALTER TABLE ONLY public.campaign_change_revisions
    ADD CONSTRAINT uq_campaign_change_revisions_number UNIQUE (campaign_id, revision_number);
""",
    r"""
ALTER TABLE ONLY public.campaign_change_revisions
    ADD CONSTRAINT uq_campaign_change_revisions_request UNIQUE (request_id);
""",
    r"""
ALTER TABLE ONLY public.campaign_creatives
    ADD CONSTRAINT uq_campaign_creatives_stored_file UNIQUE (stored_file_id);
""",
    r"""
ALTER TABLE ONLY public.campaign_financial_authorizations
    ADD CONSTRAINT uq_campaign_financial_authorization_revision UNIQUE (campaign_id, revision_number);
""",
    r"""
ALTER TABLE ONLY public.campaign_liability_reservations
    ADD CONSTRAINT uq_campaign_liability_reservations_assignment UNIQUE (assignment_id);
""",
    r"""
ALTER TABLE ONLY public.campaign_payout_rule_revisions
    ADD CONSTRAINT uq_campaign_payout_rule_revisions_campaign_effective UNIQUE (campaign_id, effective_from);
""",
    r"""
ALTER TABLE ONLY public.campaign_payout_rule_revisions
    ADD CONSTRAINT uq_campaign_payout_rule_revisions_campaign_number UNIQUE (campaign_id, revision_number);
""",
    r"""
ALTER TABLE ONLY public.commercial_quotation_revisions
    ADD CONSTRAINT uq_commercial_quote_reference_revision UNIQUE (organization_id, quote_reference, revision_number);
""",
    r"""
ALTER TABLE ONLY public.commercial_quotation_revisions
    ADD CONSTRAINT uq_commercial_quote_request_revision UNIQUE (quote_request_id, revision_number);
""",
    r"""
ALTER TABLE ONLY public.commercial_quote_requests
    ADD CONSTRAINT uq_commercial_quote_requests_campaign UNIQUE (campaign_id);
""",
    r"""
ALTER TABLE ONLY public.commercial_terms
    ADD CONSTRAINT uq_commercial_terms_campaign UNIQUE (campaign_id);
""",
    r"""
ALTER TABLE ONLY public.commercial_terms
    ADD CONSTRAINT uq_commercial_terms_quote_revision UNIQUE (quotation_revision_id);
""",
    r"""
ALTER TABLE ONLY public.complaint_messages
    ADD CONSTRAINT uq_complaint_messages_author_client_request UNIQUE (complaint_id, author_user_id, client_request_id);
""",
    r"""
ALTER TABLE ONLY public.complaints
    ADD CONSTRAINT uq_complaints_raiser_client_request UNIQUE (raised_by_user_id, client_request_id);
""",
    r"""
ALTER TABLE ONLY public.data_subject_location_assessments
    ADD CONSTRAINT uq_data_subject_assessments_actor_request UNIQUE (assessed_by_user_id, client_request_id);
""",
    r"""
ALTER TABLE ONLY public.data_subject_location_assessments
    ADD CONSTRAINT uq_data_subject_assessments_request_location UNIQUE (request_id, location);
""",
    r"""
ALTER TABLE ONLY public.data_subject_requests
    ADD CONSTRAINT uq_data_subject_requests_actor_request UNIQUE (opened_by_user_id, client_request_id);
""",
    r"""
ALTER TABLE ONLY public.disclosure_query_decisions
    ADD CONSTRAINT uq_disclosure_query_decisions_retry UNIQUE (principal_hash, scope_hash, query_hash, result_hash);
""",
    r"""
ALTER TABLE ONLY public.display_proof_challenges
    ADD CONSTRAINT uq_display_proof_challenge_nonce UNIQUE (nonce_sha256);
""",
    r"""
ALTER TABLE ONLY public.display_proofs
    ADD CONSTRAINT uq_display_proofs_challenge UNIQUE (challenge_id);
""",
    r"""
ALTER TABLE ONLY public.display_proofs
    ADD CONSTRAINT uq_display_proofs_file UNIQUE (stored_file_id);
""",
    r"""
ALTER TABLE ONLY public.driver_application_access_tokens
    ADD CONSTRAINT uq_driver_application_access_tokens_hash UNIQUE (token_sha256);
""",
    r"""
ALTER TABLE ONLY public.driver_applications
    ADD CONSTRAINT uq_driver_applications_driver_profile_id UNIQUE (driver_profile_id);
""",
    r"""
ALTER TABLE ONLY public.driver_applications
    ADD CONSTRAINT uq_driver_applications_status_reference_sha256 UNIQUE (status_reference_sha256);
""",
    r"""
ALTER TABLE ONLY public.driver_applications
    ADD CONSTRAINT uq_driver_applications_user_id UNIQUE (user_id);
""",
    r"""
ALTER TABLE ONLY public.driver_currency_debt_accounts
    ADD CONSTRAINT uq_driver_debt_accounts_driver_currency UNIQUE (driver_profile_id, currency);
""",
    r"""
ALTER TABLE ONLY public.driver_kyc_documents
    ADD CONSTRAINT uq_driver_kyc_documents_submission_type UNIQUE (submission_id, document_type);
""",
    r"""
ALTER TABLE ONLY public.driver_kyc_review_decisions
    ADD CONSTRAINT uq_driver_kyc_review_decisions_client_request UNIQUE (client_request_id);
""",
    r"""
ALTER TABLE ONLY public.driver_kyc_review_decisions
    ADD CONSTRAINT uq_driver_kyc_review_decisions_submission UNIQUE (submission_id);
""",
    r"""
ALTER TABLE ONLY public.driver_kyc_submissions
    ADD CONSTRAINT uq_driver_kyc_submissions_profile_request UNIQUE (driver_profile_id, client_request_id);
""",
    r"""
ALTER TABLE ONLY public.driver_kyc_submissions
    ADD CONSTRAINT uq_driver_kyc_submissions_profile_version UNIQUE (driver_profile_id, version);
""",
    r"""
ALTER TABLE ONLY public.driver_phone_versions
    ADD CONSTRAINT uq_driver_phone_version UNIQUE (driver_profile_id, version);
""",
    r"""
ALTER TABLE ONLY public.driver_profiles
    ADD CONSTRAINT uq_driver_profiles_user_id UNIQUE (user_id);
""",
    r"""
ALTER TABLE ONLY public.driver_account_setup_tokens
    ADD CONSTRAINT uq_driver_setup_tokens_client_request UNIQUE (client_request_id);
""",
    r"""
ALTER TABLE ONLY public.driver_account_setup_tokens
    ADD CONSTRAINT uq_driver_setup_tokens_hash UNIQUE (token_sha256);
""",
    r"""
ALTER TABLE ONLY public.expedited_production_waivers
    ADD CONSTRAINT uq_expedited_production_waivers_campaign UNIQUE (campaign_id);
""",
    r"""
ALTER TABLE ONLY public.exposure_scores
    ADD CONSTRAINT uq_exposure_scores_run_formula UNIQUE (measurement_run_id, formula_version);
""",
    r"""
ALTER TABLE ONLY public.exposure_segment_cells
    ADD CONSTRAINT uq_exposure_segment_cells_identity UNIQUE (segment_id, coverage_cell, window_start_at, window_end_at, context);
""",
    r"""
ALTER TABLE ONLY public.exposure_segments
    ADD CONSTRAINT uq_exposure_segments_link_facts UNIQUE (source_link_id, facts_fingerprint);
""",
    r"""
ALTER TABLE ONLY public.exposure_segments
    ADD CONSTRAINT uq_exposure_segments_link_version UNIQUE (source_link_id, version);
""",
    r"""
ALTER TABLE ONLY public.file_upload_intents
    ADD CONSTRAINT uq_file_upload_intents_object_key UNIQUE (object_key);
""",
    r"""
ALTER TABLE ONLY public.file_upload_intents
    ADD CONSTRAINT uq_file_upload_intents_scope_request UNIQUE (organization_id, uploader_user_id, client_request_id);
""",
    r"""
ALTER TABLE ONLY public.file_upload_intents
    ADD CONSTRAINT uq_file_upload_intents_subject_request UNIQUE (subject_user_id, uploader_user_id, client_request_id);
""",
    r"""
ALTER TABLE ONLY public.financial_authorization_allocations
    ADD CONSTRAINT uq_financial_authorization_allocation_source UNIQUE (authorization_id, receipt_allocation_id);
""",
    r"""
ALTER TABLE ONLY public.fraud_assessments
    ADD CONSTRAINT uq_fraud_assessments_trip_session_id UNIQUE (trip_session_id);
""",
    r"""
ALTER TABLE ONLY public.fraud_disputes
    ADD CONSTRAINT uq_fraud_disputes_fraud_flag_id UNIQUE (fraud_flag_id);
""",
    r"""
ALTER TABLE ONLY public.impression_estimates
    ADD CONSTRAINT uq_impression_estimates_trip_formula_profile UNIQUE (trip_session_id, formula_version, traffic_density_profile_id);
""",
    r"""
ALTER TABLE ONLY public.installation_evidence_submissions
    ADD CONSTRAINT uq_installation_evidence_assignment_revision UNIQUE (assignment_id, revision);
""",
    r"""
ALTER TABLE ONLY public.installation_evidence_photos
    ADD CONSTRAINT uq_installation_evidence_photo_file UNIQUE (stored_file_id);
""",
    r"""
ALTER TABLE ONLY public.installation_evidence_photos
    ADD CONSTRAINT uq_installation_evidence_photo_view UNIQUE (submission_id, view_code);
""",
    r"""
ALTER TABLE ONLY public.installation_evidence_submissions
    ADD CONSTRAINT uq_installation_evidence_request UNIQUE (assignment_id, submitted_by_user_id, client_request_id);
""",
    r"""
ALTER TABLE ONLY public.invoice_corrections
    ADD CONSTRAINT uq_invoice_corrections_number UNIQUE (correction_number);
""",
    r"""
ALTER TABLE ONLY public.invoice_corrections
    ADD CONSTRAINT uq_invoice_corrections_reference UNIQUE (invoice_id, correction_reference);
""",
    r"""
ALTER TABLE ONLY public.invoice_corrections
    ADD CONSTRAINT uq_invoice_corrections_sequence UNIQUE (invoice_id, sequence_number);
""",
    r"""
ALTER TABLE ONLY public.invoice_issuer_profiles
    ADD CONSTRAINT uq_invoice_issuer_profiles_external_ref UNIQUE (external_input_reference);
""",
    r"""
ALTER TABLE ONLY public.invoice_number_sequences
    ADD CONSTRAINT uq_invoice_number_sequences_scope UNIQUE (number_prefix, calendar_year);
""",
    r"""
ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT uq_invoices_commercial_terms UNIQUE (commercial_terms_id);
""",
    r"""
ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT uq_invoices_number UNIQUE (invoice_number);
""",
    r"""
ALTER TABLE ONLY public.location_ping_batches
    ADD CONSTRAINT uq_location_ping_batches_trip_idempotency_key UNIQUE (trip_session_id, idempotency_key);
""",
    r"""
ALTER TABLE ONLY public.manual_driver_contact_tasks
    ADD CONSTRAINT uq_manual_contact_event UNIQUE (driver_profile_id, event_key);
""",
    r"""
ALTER TABLE ONLY public.measurement_run_proof_bindings
    ADD CONSTRAINT uq_measurement_run_proof_assignment UNIQUE (measurement_run_id, assignment_id);
""",
    r"""
ALTER TABLE ONLY public.measurement_runs
    ADD CONSTRAINT uq_measurement_runs_actor_request UNIQUE (created_by_user_id, client_request_id);
""",
    r"""
ALTER TABLE ONLY public.notification_delivery_receipts
    ADD CONSTRAINT uq_notification_receipts_notification UNIQUE (notification_id);
""",
    r"""
ALTER TABLE ONLY public.notification_delivery_receipts
    ADD CONSTRAINT uq_notification_receipts_provider_event UNIQUE (provider_event_id);
""",
    r"""
ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT uq_notifications_provider_message_id UNIQUE (provider_message_id);
""",
    r"""
ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT uq_notifications_recipient_channel_dedupe_key UNIQUE (recipient_user_id, channel, dedupe_key);
""",
    r"""
ALTER TABLE ONLY public.organization_memberships
    ADD CONSTRAINT uq_organization_memberships_org_user UNIQUE (organization_id, user_id);
""",
    r"""
ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT uq_password_reset_tokens_attempt UNIQUE (attempt_id);
""",
    r"""
ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT uq_password_reset_tokens_hash UNIQUE (token_hash);
""",
    r"""
ALTER TABLE ONLY public.payee_bank_account_payout_verifications
    ADD CONSTRAINT uq_payee_bank_account_payout_verifications_version UNIQUE (bank_account_version_id);
""",
    r"""
ALTER TABLE ONLY public.payee_bank_account_versions
    ADD CONSTRAINT uq_payee_bank_account_versions_account_version UNIQUE (bank_account_id, version);
""",
    r"""
ALTER TABLE ONLY public.payee_bank_accounts
    ADD CONSTRAINT uq_payee_bank_accounts_payee_id UNIQUE (payee_id);
""",
    r"""
ALTER TABLE ONLY public.payee_versions
    ADD CONSTRAINT uq_payee_versions_payee_version UNIQUE (payee_id, version);
""",
    r"""
ALTER TABLE ONLY public.payees
    ADD CONSTRAINT uq_payees_tenant_type_subject UNIQUE (tenant_id, payee_type, subject_id);
""",
    r"""
ALTER TABLE ONLY public.payment_checkout_intents
    ADD CONSTRAINT uq_payment_checkout_intents_reference UNIQUE (reference);
""",
    r"""
ALTER TABLE ONLY public.payment_gateway_processing_attempts
    ADD CONSTRAINT uq_payment_gateway_attempt_sequence UNIQUE (gateway_event_id, attempt_number);
""",
    r"""
ALTER TABLE ONLY public.payment_gateway_events
    ADD CONSTRAINT uq_payment_gateway_events_provider_event UNIQUE (provider, provider_event_id);
""",
    r"""
ALTER TABLE ONLY public.payment_receipts
    ADD CONSTRAINT uq_payment_receipts_external_transaction UNIQUE (external_transaction_id);
""",
    r"""
ALTER TABLE ONLY public.payout_automatic_alerts
    ADD CONSTRAINT uq_payout_automatic_alerts_dedupe_key UNIQUE (dedupe_key);
""",
    r"""
ALTER TABLE ONLY public.payout_automatic_runs
    ADD CONSTRAINT uq_payout_automatic_runs_period_key UNIQUE (period_key);
""",
    r"""
ALTER TABLE ONLY public.payout_batch_lines
    ADD CONSTRAINT uq_payout_batch_lines_idempotency_key UNIQUE (idempotency_key);
""",
    r"""
ALTER TABLE ONLY public.payout_calculations
    ADD CONSTRAINT uq_payout_calculations_trip_formula_rule UNIQUE (trip_session_id, formula_version, payout_rule_id);
""",
    r"""
ALTER TABLE ONLY public.payout_debt_allocations
    ADD CONSTRAINT uq_payout_debt_allocations_settlement_obligation UNIQUE (settlement_id, debt_obligation_id);
""",
    r"""
ALTER TABLE ONLY public.payout_debt_obligations
    ADD CONSTRAINT uq_payout_debt_obligations_recovery_incident UNIQUE (recovery_incident_id);
""",
    r"""
ALTER TABLE ONLY public.payout_debt_paid_sources
    ADD CONSTRAINT uq_payout_debt_paid_sources_obligation_entry UNIQUE (debt_obligation_id, paid_ledger_entry_id);
""",
    r"""
ALTER TABLE ONLY public.payout_debt_settlements
    ADD CONSTRAINT uq_payout_debt_settlements_idempotency UNIQUE (idempotency_key);
""",
    r"""
ALTER TABLE ONLY public.payout_debt_settlements
    ADD CONSTRAINT uq_payout_debt_settlements_remainder UNIQUE (remainder_entry_id);
""",
    r"""
ALTER TABLE ONLY public.payout_debt_settlements
    ADD CONSTRAINT uq_payout_debt_settlements_source_credit UNIQUE (source_credit_entry_id);
""",
    r"""
ALTER TABLE ONLY public.payout_line_reconciliation_events
    ADD CONSTRAINT uq_payout_line_events_provider_event_id UNIQUE (provider_event_id);
""",
    r"""
ALTER TABLE ONLY public.payout_provider_event_processing_attempts
    ADD CONSTRAINT uq_payout_provider_attempt_sequence UNIQUE (provider_event_id, attempt_number);
""",
    r"""
ALTER TABLE ONLY public.payout_provider_events
    ADD CONSTRAINT uq_payout_provider_events_identity UNIQUE (provider, provider_event_id);
""",
    r"""
ALTER TABLE ONLY public.payout_recovery_incidents
    ADD CONSTRAINT uq_payout_recovery_incidents_dedupe_key UNIQUE (dedupe_key);
""",
    r"""
ALTER TABLE ONLY public.payout_submission_attempts
    ADD CONSTRAINT uq_payout_submission_attempts_claim_token UNIQUE (claim_token);
""",
    r"""
ALTER TABLE ONLY public.payout_submission_attempts
    ADD CONSTRAINT uq_payout_submission_attempts_intent_generation UNIQUE (intent_id, generation);
""",
    r"""
ALTER TABLE ONLY public.payout_submission_attempts
    ADD CONSTRAINT uq_payout_submission_attempts_observation_binding UNIQUE (id, intent_id, generation, idempotency_key, instruction_fingerprint);
""",
    r"""
ALTER TABLE ONLY public.payout_submission_intents
    ADD CONSTRAINT uq_payout_submission_intents_claim_token UNIQUE (claim_token);
""",
    r"""
ALTER TABLE ONLY public.payout_submission_intents
    ADD CONSTRAINT uq_payout_submission_intents_key UNIQUE (idempotency_key);
""",
    r"""
ALTER TABLE ONLY public.payout_submission_intents
    ADD CONSTRAINT uq_payout_submission_intents_line UNIQUE (payout_batch_line_id);
""",
    r"""
ALTER TABLE ONLY public.payout_submission_observations
    ADD CONSTRAINT uq_payout_submission_observations_attempt UNIQUE (attempt_id);
""",
    r"""
ALTER TABLE ONLY public.payout_submission_observations
    ADD CONSTRAINT uq_payout_submission_observations_intent_generation UNIQUE (intent_id, generation);
""",
    r"""
ALTER TABLE ONLY public.production_starts
    ADD CONSTRAINT uq_production_starts_campaign UNIQUE (campaign_id);
""",
    r"""
ALTER TABLE ONLY public.quarantined_ping_batches
    ADD CONSTRAINT uq_quarantined_ping_batches_trip_idempotency_key UNIQUE (trip_session_id, idempotency_key);
""",
    r"""
ALTER TABLE ONLY public.receipt_allocations
    ADD CONSTRAINT uq_receipt_allocations_provider_event UNIQUE (provider_event_id);
""",
    r"""
ALTER TABLE ONLY public.receipt_allocations
    ADD CONSTRAINT uq_receipt_allocations_terms UNIQUE (receipt_id, commercial_terms_id);
""",
    r"""
ALTER TABLE ONLY public.receipt_lifecycle_events
    ADD CONSTRAINT uq_receipt_lifecycle_sequence UNIQUE (receipt_id, sequence_number);
""",
    r"""
ALTER TABLE ONLY public.receipt_lifecycle_events
    ADD CONSTRAINT uq_receipt_lifecycle_status UNIQUE (receipt_id, status);
""",
    r"""
ALTER TABLE ONLY public.receipt_reconciliations
    ADD CONSTRAINT uq_receipt_reconciliations_provider_event UNIQUE (provider_event_id);
""",
    r"""
ALTER TABLE ONLY public.receipt_reconciliations
    ADD CONSTRAINT uq_receipt_reconciliations_receipt UNIQUE (receipt_id);
""",
    r"""
ALTER TABLE ONLY public.refund_settlements
    ADD CONSTRAINT uq_refund_settlements_external_reference UNIQUE (settlement_provider, external_reference);
""",
    r"""
ALTER TABLE ONLY public.report_artifacts
    ADD CONSTRAINT uq_report_artifacts_issuance_format UNIQUE (report_issuance_id, format);
""",
    r"""
ALTER TABLE ONLY public.report_artifacts
    ADD CONSTRAINT uq_report_artifacts_stored_file UNIQUE (stored_file_id);
""",
    r"""
ALTER TABLE ONLY public.report_issuances
    ADD CONSTRAINT uq_report_issuances_actor_request UNIQUE (requested_by_user_id, client_request_id);
""",
    r"""
ALTER TABLE ONLY public.report_issuances
    ADD CONSTRAINT uq_report_issuances_run_version UNIQUE (measurement_run_id, version);
""",
    r"""
ALTER TABLE ONLY public.report_publication_intents
    ADD CONSTRAINT uq_report_publication_intents_csv_key UNIQUE (csv_object_key);
""",
    r"""
ALTER TABLE ONLY public.report_publication_intents
    ADD CONSTRAINT uq_report_publication_intents_generation UNIQUE (report_issuance_id, generation);
""",
    r"""
ALTER TABLE ONLY public.report_publication_intents
    ADD CONSTRAINT uq_report_publication_intents_pdf_key UNIQUE (pdf_object_key);
""",
    r"""
ALTER TABLE ONLY public.report_publication_writes
    ADD CONSTRAINT uq_report_publication_write UNIQUE (publication_intent_id, format);
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_events
    ADD CONSTRAINT uq_retargeting_source_events_sequence UNIQUE (source_id, sequence_number);
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_idempotency
    ADD CONSTRAINT uq_retargeting_source_idempotency_actor_operation_key UNIQUE (actor_user_id, operation, idempotency_key);
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_link_events
    ADD CONSTRAINT uq_retargeting_source_link_events_sequence UNIQUE (link_id, sequence_number);
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_link_idempotency
    ADD CONSTRAINT uq_retargeting_source_link_idempotency_actor_operation_key UNIQUE (actor_user_id, operation, idempotency_key);
""",
    r"""
ALTER TABLE ONLY public.stored_files
    ADD CONSTRAINT uq_stored_files_storage_key UNIQUE (storage_key);
""",
    r"""
ALTER TABLE ONLY public.stored_files
    ADD CONSTRAINT uq_stored_files_upload_intent UNIQUE (upload_intent_id);
""",
    r"""
ALTER TABLE ONLY public.stored_object_deletions
    ADD CONSTRAINT uq_stored_object_deletions_request_fingerprint UNIQUE (request_fingerprint);
""",
    r"""
ALTER TABLE ONLY public.traffic_density_profiles
    ADD CONSTRAINT uq_traffic_density_profiles_lineage_revision UNIQUE (lineage_id, revision);
""",
    r"""
ALTER TABLE ONLY public.traffic_density_profiles
    ADD CONSTRAINT uq_traffic_density_profiles_supersedes_id UNIQUE (supersedes_id);
""",
    r"""
ALTER TABLE ONLY public.trip_analytics
    ADD CONSTRAINT uq_trip_analytics_trip_session_id UNIQUE (trip_session_id);
""",
    r"""
ALTER TABLE ONLY public.trip_evidence_manifest_entries
    ADD CONSTRAINT uq_trip_manifest_entries_trip_idempotency_key UNIQUE (trip_session_id, idempotency_key);
""",
    r"""
ALTER TABLE ONLY public.trip_evidence_manifest_entries
    ADD CONSTRAINT uq_trip_manifest_entries_trip_sequence UNIQUE (trip_session_id, batch_sequence);
""",
    r"""
ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_users_email UNIQUE (email);
""",
    r"""
ALTER TABLE ONLY public.vehicle_evidence_documents
    ADD CONSTRAINT uq_vehicle_evidence_documents_submission_type UNIQUE (submission_id, document_type);
""",
    r"""
ALTER TABLE ONLY public.vehicle_evidence_submissions
    ADD CONSTRAINT uq_vehicle_evidence_submissions_owner_request UNIQUE (created_by_user_id, client_request_id);
""",
    r"""
ALTER TABLE ONLY public.vehicle_evidence_submissions
    ADD CONSTRAINT uq_vehicle_evidence_submissions_vehicle_request UNIQUE (vehicle_id, client_request_id);
""",
    r"""
ALTER TABLE ONLY public.vehicle_evidence_submissions
    ADD CONSTRAINT uq_vehicle_evidence_submissions_vehicle_version UNIQUE (vehicle_id, version);
""",
    r"""
ALTER TABLE ONLY public.vehicle_evidence_review_decisions
    ADD CONSTRAINT uq_vehicle_review_decisions_client_request UNIQUE (client_request_id);
""",
    r"""
ALTER TABLE ONLY public.vehicle_evidence_review_decisions
    ADD CONSTRAINT uq_vehicle_review_decisions_submission_sequence UNIQUE (submission_id, sequence);
""",
    r"""
ALTER TABLE ONLY public.vehicles
    ADD CONSTRAINT uq_vehicles_plate_country_normalized UNIQUE (plate_country_code, plate_number_normalized);
""",
    r"""
ALTER TABLE ONLY public.whatsapp_consents
    ADD CONSTRAINT uq_whatsapp_consent_version UNIQUE (driver_profile_id, version);
""",
    r"""
ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.vehicle_evidence_documents
    ADD CONSTRAINT vehicle_evidence_documents_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.vehicle_evidence_review_decisions
    ADD CONSTRAINT vehicle_evidence_review_decisions_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.vehicle_evidence_submissions
    ADD CONSTRAINT vehicle_evidence_submissions_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.vehicles
    ADD CONSTRAINT vehicles_pkey PRIMARY KEY (id);
""",
    r"""
ALTER TABLE ONLY public.whatsapp_consents
    ADD CONSTRAINT whatsapp_consents_pkey PRIMARY KEY (id);
""",
    r"""
CREATE INDEX ix_assignment_activity_flag_events_flag_created ON public.assignment_activity_flag_events USING btree (flag_id, occurred_at);
""",
    r"""
CREATE INDEX ix_assignment_activity_flags_assignment_status ON public.assignment_activity_flags USING btree (assignment_id, status);
""",
    r"""
CREATE INDEX ix_assignment_activity_flags_driver_status ON public.assignment_activity_flags USING btree (driver_profile_id, status);
""",
    r"""
CREATE INDEX ix_assignment_activity_flags_status ON public.assignment_activity_flags USING btree (status);
""",
    r"""
CREATE INDEX ix_assignment_activity_flags_window ON public.assignment_activity_flags USING btree (window_start, window_end);
""",
    r"""
CREATE INDEX ix_assignment_rule_bindings_revision_id ON public.assignment_rule_bindings USING btree (revision_id);
""",
    r"""
CREATE INDEX ix_audience_deliveries_scope ON public.audience_deliveries USING btree (organization_id, campaign_id, segment_id, created_at);
""",
    r"""
CREATE INDEX ix_audience_delivery_approvals_scope ON public.audience_delivery_approvals USING btree (organization_id, campaign_id, segment_id, operation, valid_until);
""",
    r"""
CREATE INDEX ix_audit_events_action ON public.audit_events USING btree (action);
""",
    r"""
CREATE INDEX ix_audit_events_actor_user_id ON public.audit_events USING btree (actor_user_id);
""",
    r"""
CREATE INDEX ix_audit_events_created_at ON public.audit_events USING btree (created_at);
""",
    r"""
CREATE INDEX ix_audit_events_entity_type_entity_id ON public.audit_events USING btree (entity_type, entity_id);
""",
    r"""
CREATE INDEX ix_audit_subject_user_event ON public.audit_event_subject_resolutions USING btree (subject_user_id, audit_event_id);
""",
    r"""
CREATE INDEX ix_budget_campaign_transitions_campaign_id ON public.budget_campaign_transitions USING btree (campaign_id, created_at);
""",
    r"""
CREATE INDEX ix_budget_policy_evaluations_campaign_id ON public.budget_policy_evaluations USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_campaign_activation_events_actor_user_id ON public.campaign_activation_events USING btree (actor_user_id);
""",
    r"""
CREATE INDEX ix_campaign_activation_events_assignment_id ON public.campaign_activation_events USING btree (assignment_id);
""",
    r"""
CREATE INDEX ix_campaign_activation_events_assignment_occurred ON public.campaign_activation_events USING btree (assignment_id, occurred_at);
""",
    r"""
CREATE INDEX ix_campaign_assignments_campaign_id ON public.campaign_assignments USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_campaign_assignments_campaign_status ON public.campaign_assignments USING btree (campaign_id, status);
""",
    r"""
CREATE INDEX ix_campaign_assignments_driver_profile_id ON public.campaign_assignments USING btree (driver_profile_id);
""",
    r"""
CREATE INDEX ix_campaign_assignments_driver_status ON public.campaign_assignments USING btree (driver_profile_id, status);
""",
    r"""
CREATE INDEX ix_campaign_assignments_vehicle_id ON public.campaign_assignments USING btree (vehicle_id);
""",
    r"""
CREATE INDEX ix_campaign_assignments_vehicle_status ON public.campaign_assignments USING btree (vehicle_id, status);
""",
    r"""
CREATE INDEX ix_campaign_cancellation_settlement_revisions_campaign_id ON public.campaign_cancellation_settlement_revisions USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_campaign_cancellation_settlement_revisions_cancellation_id ON public.campaign_cancellation_settlement_revisions USING btree (cancellation_id);
""",
    r"""
CREATE INDEX ix_campaign_cancellations_campaign_id ON public.campaign_cancellations USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_campaign_change_requests_campaign_id ON public.campaign_change_requests USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_campaign_change_requests_status_created ON public.campaign_change_requests USING btree (status, created_at);
""",
    r"""
CREATE INDEX ix_campaign_change_revisions_campaign_effective ON public.campaign_change_revisions USING btree (campaign_id, effective_from);
""",
    r"""
CREATE INDEX ix_campaign_change_revisions_campaign_id ON public.campaign_change_revisions USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_campaign_creatives_campaign_id ON public.campaign_creatives USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_campaign_creatives_campaign_status ON public.campaign_creatives USING btree (campaign_id, status);
""",
    r"""
CREATE INDEX ix_campaign_creatives_creative_type ON public.campaign_creatives USING btree (creative_type);
""",
    r"""
CREATE INDEX ix_campaign_financial_authorizations_campaign_id ON public.campaign_financial_authorizations USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_campaign_liability_reservations_campaign_id ON public.campaign_liability_reservations USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_campaign_payout_rule_revisions_campaign_id ON public.campaign_payout_rule_revisions USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_campaign_payout_rule_revisions_payout_rule_id ON public.campaign_payout_rule_revisions USING btree (payout_rule_id);
""",
    r"""
CREATE INDEX ix_campaign_payout_rules_campaign_id ON public.campaign_payout_rules USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_campaign_payout_rules_campaign_status ON public.campaign_payout_rules USING btree (campaign_id, status);
""",
    r"""
CREATE INDEX ix_campaign_review_events_actor_user_id ON public.campaign_review_events USING btree (actor_user_id);
""",
    r"""
CREATE INDEX ix_campaign_review_events_campaign_id ON public.campaign_review_events USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_campaign_review_events_submission_event_id ON public.campaign_review_events USING btree (submission_event_id);
""",
    r"""
CREATE INDEX ix_campaign_zones_campaign_id ON public.campaign_zones USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_campaign_zones_campaign_zone_type ON public.campaign_zones USING btree (campaign_id, zone_type);
""",
    r"""
CREATE INDEX ix_campaign_zones_created_by_user_id ON public.campaign_zones USING btree (created_by_user_id);
""",
    r"""
CREATE INDEX ix_campaign_zones_geom ON public.campaign_zones USING gist (geom);
""",
    r"""
CREATE INDEX ix_campaigns_created_by_user_id ON public.campaigns USING btree (created_by_user_id);
""",
    r"""
CREATE INDEX ix_campaigns_organization_id ON public.campaigns USING btree (organization_id);
""",
    r"""
CREATE INDEX ix_campaigns_organization_status ON public.campaigns USING btree (organization_id, status);
""",
    r"""
CREATE INDEX ix_campaigns_start_end ON public.campaigns USING btree (start_at, end_at);
""",
    r"""
CREATE INDEX ix_commercial_quotation_revisions_campaign_id ON public.commercial_quotation_revisions USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_commercial_quote_requests_campaign_id ON public.commercial_quote_requests USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_commercial_quote_requests_organization_id ON public.commercial_quote_requests USING btree (organization_id);
""",
    r"""
CREATE INDEX ix_commercial_terms_campaign_id ON public.commercial_terms USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_complaint_messages_author_user_id ON public.complaint_messages USING btree (author_user_id);
""",
    r"""
CREATE INDEX ix_complaint_messages_complaint_created ON public.complaint_messages USING btree (complaint_id, created_at);
""",
    r"""
CREATE INDEX ix_complaints_advertiser_organization_id ON public.complaints USING btree (advertiser_organization_id);
""",
    r"""
CREATE INDEX ix_complaints_assigned_to_user_id ON public.complaints USING btree (assigned_to_user_id);
""",
    r"""
CREATE INDEX ix_complaints_driver_profile_id ON public.complaints USING btree (driver_profile_id);
""",
    r"""
CREATE INDEX ix_complaints_status_last_message ON public.complaints USING btree (status, last_message_at);
""",
    r"""
CREATE INDEX ix_creative_review_events_actor_user_id ON public.creative_review_events USING btree (actor_user_id);
""",
    r"""
CREATE INDEX ix_creative_review_events_creative_id ON public.creative_review_events USING btree (creative_id);
""",
    r"""
CREATE INDEX ix_creative_review_events_submission_event_id ON public.creative_review_events USING btree (submission_event_id);
""",
    r"""
CREATE INDEX ix_data_purge_audit_partition_created_at ON public.data_purge_audit USING btree (partition_name, created_at);
""",
    r"""
CREATE INDEX ix_data_subject_requests_subject_user_id ON public.data_subject_requests USING btree (subject_user_id);
""",
    r"""
CREATE INDEX ix_disclosure_query_decisions_overlap ON public.disclosure_query_decisions USING btree (tenant_id, campaign_id, expires_at, window_start, window_end);
""",
    r"""
CREATE INDEX ix_disclosure_query_decisions_scope_history ON public.disclosure_query_decisions USING btree (principal_hash, scope_hash, expires_at, created_at);
""",
    r"""
CREATE INDEX ix_display_proof_challenge_assignment ON public.display_proof_challenges USING btree (assignment_id, created_at);
""",
    r"""
CREATE INDEX ix_display_proofs_assignment_verified ON public.display_proofs USING btree (assignment_id, verified_at);
""",
    r"""
CREATE INDEX ix_driver_application_access_tokens_application_created ON public.driver_application_access_tokens USING btree (application_id, created_at);
""",
    r"""
CREATE INDEX ix_driver_applications_status_created ON public.driver_applications USING btree (status, created_at);
""",
    r"""
CREATE INDEX ix_driver_kyc_documents_submission_id ON public.driver_kyc_documents USING btree (submission_id);
""",
    r"""
CREATE INDEX ix_driver_kyc_review_decisions_submission_id ON public.driver_kyc_review_decisions USING btree (submission_id);
""",
    r"""
CREATE INDEX ix_driver_kyc_submissions_driver_profile_id ON public.driver_kyc_submissions USING btree (driver_profile_id);
""",
    r"""
CREATE INDEX ix_driver_kyc_submissions_nin_record_id ON public.driver_kyc_submissions USING btree (nin_record_id);
""",
    r"""
CREATE INDEX ix_driver_phone_versions_profile ON public.driver_phone_versions USING btree (driver_profile_id, version);
""",
    r"""
CREATE INDEX ix_driver_profiles_country_city ON public.driver_profiles USING btree (country_code, service_city);
""",
    r"""
CREATE INDEX ix_driver_profiles_onboarding_status ON public.driver_profiles USING btree (onboarding_status);
""",
    r"""
CREATE INDEX ix_driver_profiles_user_id ON public.driver_profiles USING btree (user_id);
""",
    r"""
CREATE INDEX ix_driver_setup_tokens_application_created ON public.driver_account_setup_tokens USING btree (application_id, created_at);
""",
    r"""
CREATE INDEX ix_earnings_ledger_entries_campaign_id ON public.earnings_ledger_entries USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_earnings_ledger_entries_campaign_occurred_at ON public.earnings_ledger_entries USING btree (campaign_id, occurred_at);
""",
    r"""
CREATE INDEX ix_earnings_ledger_entries_driver_occurred_at ON public.earnings_ledger_entries USING btree (driver_profile_id, occurred_at);
""",
    r"""
CREATE INDEX ix_earnings_ledger_entries_driver_profile_id ON public.earnings_ledger_entries USING btree (driver_profile_id);
""",
    r"""
CREATE INDEX ix_earnings_ledger_entries_driver_status ON public.earnings_ledger_entries USING btree (driver_profile_id, status);
""",
    r"""
CREATE INDEX ix_earnings_ledger_entries_driver_user_id ON public.earnings_ledger_entries USING btree (driver_user_id);
""",
    r"""
CREATE INDEX ix_earnings_ledger_entries_trip_session_id ON public.earnings_ledger_entries USING btree (trip_session_id);
""",
    r"""
CREATE INDEX ix_earnings_ledger_entries_vehicle_id ON public.earnings_ledger_entries USING btree (vehicle_id);
""",
    r"""
CREATE INDEX ix_evidence_verifications_assignment_status ON public.evidence_verifications USING btree (assignment_id, status);
""",
    r"""
CREATE INDEX ix_evidence_verifications_driver_status ON public.evidence_verifications USING btree (driver_profile_id, status);
""",
    r"""
CREATE INDEX ix_evidence_verifications_fraud_flag ON public.evidence_verifications USING btree (fraud_flag_id);
""",
    r"""
CREATE INDEX ix_evidence_verifications_type_status ON public.evidence_verifications USING btree (verification_type, status);
""",
    r"""
CREATE INDEX ix_exposure_scores_campaign_history ON public.exposure_scores USING btree (organization_id, campaign_id, created_at);
""",
    r"""
CREATE INDEX ix_exposure_scores_reissue ON public.exposure_scores USING btree (reissue_of_score_id);
""",
    r"""
CREATE INDEX ix_exposure_segment_cells_segment ON public.exposure_segment_cells USING btree (segment_id, coverage_cell);
""",
    r"""
CREATE INDEX ix_exposure_segments_reissue ON public.exposure_segments USING btree (reissue_of_segment_id);
""",
    r"""
CREATE INDEX ix_exposure_segments_scope ON public.exposure_segments USING btree (organization_id, campaign_id, zone_id, created_at);
""",
    r"""
CREATE INDEX ix_file_upload_intents_status_expires ON public.file_upload_intents USING btree (status, expires_at);
""",
    r"""
CREATE INDEX ix_fraud_assessments_status ON public.fraud_assessments USING btree (status);
""",
    r"""
CREATE INDEX ix_fraud_assessments_trip_analytics_id ON public.fraud_assessments USING btree (trip_analytics_id);
""",
    r"""
CREATE INDEX ix_fraud_disputes_created_at ON public.fraud_disputes USING btree (created_at);
""",
    r"""
CREATE INDEX ix_fraud_disputes_driver_profile_id ON public.fraud_disputes USING btree (driver_profile_id);
""",
    r"""
CREATE INDEX ix_fraud_disputes_status ON public.fraud_disputes USING btree (status);
""",
    r"""
CREATE INDEX ix_fraud_flags_campaign_id ON public.fraud_flags USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_fraud_flags_campaign_status ON public.fraud_flags USING btree (campaign_id, status);
""",
    r"""
CREATE INDEX ix_fraud_flags_driver_profile_id ON public.fraud_flags USING btree (driver_profile_id);
""",
    r"""
CREATE INDEX ix_fraud_flags_flag_type ON public.fraud_flags USING btree (flag_type);
""",
    r"""
CREATE INDEX ix_fraud_flags_severity ON public.fraud_flags USING btree (severity);
""",
    r"""
CREATE INDEX ix_fraud_flags_status ON public.fraud_flags USING btree (status);
""",
    r"""
CREATE INDEX ix_fraud_flags_trip_analytics_id ON public.fraud_flags USING btree (trip_analytics_id);
""",
    r"""
CREATE INDEX ix_fraud_flags_trip_session_id ON public.fraud_flags USING btree (trip_session_id);
""",
    r"""
CREATE INDEX ix_fraud_flags_unresolved_sla ON public.fraud_flags USING btree (detected_at, id) WHERE status IN ('open', 'acknowledged') AND escalated_at IS NULL;
""",
    r"""
CREATE INDEX ix_fraud_flags_vehicle_id ON public.fraud_flags USING btree (vehicle_id);
""",
    r"""
CREATE INDEX ix_health_email_status_age ON public.notifications USING btree (channel, status, created_at, failed_at);
""",
    r"""
CREATE INDEX ix_health_payment_event_received ON public.payment_gateway_events USING btree (received_at);
""",
    r"""
CREATE INDEX ix_health_payout_event_received ON public.payout_provider_events USING btree (received_at);
""",
    r"""
CREATE INDEX ix_health_payout_line_progress ON public.payout_batch_lines USING btree (status, created_at);
""",
    r"""
CREATE INDEX ix_health_trip_status_activity ON public.trip_sessions USING btree (status, started_at, ended_at);
""",
    r"""
CREATE INDEX ix_impression_estimates_assignment_id ON public.impression_estimates USING btree (assignment_id);
""",
    r"""
CREATE INDEX ix_impression_estimates_campaign_estimated_at ON public.impression_estimates USING btree (campaign_id, estimated_at);
""",
    r"""
CREATE INDEX ix_impression_estimates_campaign_id ON public.impression_estimates USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_impression_estimates_campaign_status ON public.impression_estimates USING btree (campaign_id, status);
""",
    r"""
CREATE INDEX ix_impression_estimates_driver_profile_id ON public.impression_estimates USING btree (driver_profile_id);
""",
    r"""
CREATE INDEX ix_impression_estimates_traffic_density_profile_id ON public.impression_estimates USING btree (traffic_density_profile_id);
""",
    r"""
CREATE INDEX ix_impression_estimates_trip_analytics_id ON public.impression_estimates USING btree (trip_analytics_id);
""",
    r"""
CREATE INDEX ix_impression_estimates_vehicle_id ON public.impression_estimates USING btree (vehicle_id);
""",
    r"""
CREATE INDEX ix_installation_evidence_assignment_status ON public.installation_evidence_submissions USING btree (assignment_id, status);
""",
    r"""
CREATE INDEX ix_installation_evidence_photos_submission ON public.installation_evidence_photos USING btree (submission_id);
""",
    r"""
CREATE INDEX ix_invoice_corrections_invoice_id ON public.invoice_corrections USING btree (invoice_id);
""",
    r"""
CREATE INDEX ix_invoices_campaign_id ON public.invoices USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_invoices_organization_id ON public.invoices USING btree (organization_id);
""",
    r"""
CREATE INDEX ix_location_ping_batches_trip_received_at ON public.location_ping_batches USING btree (trip_session_id, received_at);
""",
    r"""
CREATE INDEX ix_location_ping_batches_trip_session_id ON public.location_ping_batches USING btree (trip_session_id);
""",
    r"""
CREATE INDEX ix_location_pings_batch_id ON ONLY public.location_pings USING btree (batch_id);
""",
    r"""
CREATE INDEX ix_location_pings_geom ON ONLY public.location_pings USING gist (geom);
""",
    r"""
CREATE INDEX ix_location_pings_trip_recorded_at ON ONLY public.location_pings USING btree (trip_session_id, recorded_at);
""",
    r"""
CREATE INDEX ix_location_pings_trip_session_id ON ONLY public.location_pings USING btree (trip_session_id);
""",
    r"""
CREATE INDEX ix_manual_contact_tasks_status ON public.manual_driver_contact_tasks USING btree (status, created_at);
""",
    r"""
CREATE INDEX ix_measurement_run_proof_activation ON public.measurement_run_proof_bindings USING btree (activation_event_id);
""",
    r"""
CREATE INDEX ix_measurement_run_proof_creative ON public.measurement_run_proof_bindings USING btree (creative_id);
""",
    r"""
CREATE INDEX ix_measurement_run_proof_evidence ON public.measurement_run_proof_bindings USING btree (installation_evidence_submission_id);
""",
    r"""
CREATE INDEX ix_measurement_runs_campaign_period ON public.measurement_runs USING btree (campaign_id, period_start_at, period_end_at, created_at);
""",
    r"""
CREATE INDEX ix_measurement_runs_organization ON public.measurement_runs USING btree (organization_id, created_at);
""",
    r"""
CREATE INDEX ix_measurement_runs_reissue ON public.measurement_runs USING btree (reissue_of_run_id);
""",
    r"""
CREATE INDEX ix_notifications_email_dispatch ON public.notifications USING btree (status, next_attempt_at, delivery_claim_expires_at) WHERE ((channel)::text = 'transactional_email'::text);
""",
    r"""
CREATE INDEX ix_notifications_recipient_created ON public.notifications USING btree (recipient_user_id, created_at);
""",
    r"""
CREATE INDEX ix_notifications_recipient_unread ON public.notifications USING btree (recipient_user_id, created_at) WHERE (read_at IS NULL);
""",
    r"""
CREATE INDEX ix_notifications_type_key ON public.notifications USING btree (type_key);
""",
    r"""
CREATE INDEX ix_organization_memberships_organization_id ON public.organization_memberships USING btree (organization_id);
""",
    r"""
CREATE INDEX ix_organization_memberships_user_id ON public.organization_memberships USING btree (user_id);
""",
    r"""
CREATE INDEX ix_password_reset_attempt_email ON public.password_reset_attempts USING btree (email_digest, requested_at);
""",
    r"""
CREATE INDEX ix_password_reset_attempt_ip ON public.password_reset_attempts USING btree (ip_digest, requested_at);
""",
    r"""
CREATE INDEX ix_password_reset_tokens_user ON public.password_reset_tokens USING btree (user_id, created_at);
""",
    r"""
CREATE INDEX ix_payee_bank_account_versions_bank_account_id ON public.payee_bank_account_versions USING btree (bank_account_id);
""",
    r"""
CREATE INDEX ix_payee_bank_account_versions_payee_version_id ON public.payee_bank_account_versions USING btree (payee_version_id);
""",
    r"""
CREATE INDEX ix_payee_bank_accounts_payee_id ON public.payee_bank_accounts USING btree (payee_id);
""",
    r"""
CREATE INDEX ix_payee_payout_verifications_version ON public.payee_bank_account_payout_verifications USING btree (bank_account_version_id);
""",
    r"""
CREATE INDEX ix_payee_versions_payee_id ON public.payee_versions USING btree (payee_id);
""",
    r"""
CREATE INDEX ix_payees_tenant_id ON public.payees USING btree (tenant_id);
""",
    r"""
CREATE INDEX ix_payment_checkout_intents_commercial_terms_id ON public.payment_checkout_intents USING btree (commercial_terms_id);
""",
    r"""
CREATE INDEX ix_payment_checkout_intents_invoice_id ON public.payment_checkout_intents USING btree (invoice_id);
""",
    r"""
CREATE INDEX ix_payment_checkout_intents_organization_id ON public.payment_checkout_intents USING btree (organization_id);
""",
    r"""
CREATE INDEX ix_payment_gateway_processing_attempts_gateway_event_id ON public.payment_gateway_processing_attempts USING btree (gateway_event_id);
""",
    r"""
CREATE INDEX ix_payment_receipts_organization_id ON public.payment_receipts USING btree (organization_id);
""",
    r"""
CREATE INDEX ix_payout_automatic_alerts_created_at ON public.payout_automatic_alerts USING btree (created_at);
""",
    r"""
CREATE INDEX ix_payout_automatic_alerts_open ON public.payout_automatic_alerts USING btree (created_at) WHERE (resolved_at IS NULL);
""",
    r"""
CREATE INDEX ix_payout_batch_lines_batch_id ON public.payout_batch_lines USING btree (batch_id);
""",
    r"""
CREATE INDEX ix_payout_batch_lines_ledger_entry_id ON public.payout_batch_lines USING btree (ledger_entry_id);
""",
    r"""
CREATE INDEX ix_payout_batches_automatic_run_id ON public.payout_batches USING btree (automatic_run_id);
""",
    r"""
CREATE INDEX ix_payout_batches_status_created ON public.payout_batches USING btree (status, created_at);
""",
    r"""
CREATE INDEX ix_payout_calculations_assignment_id ON public.payout_calculations USING btree (assignment_id);
""",
    r"""
CREATE INDEX ix_payout_calculations_campaign_calculated_at ON public.payout_calculations USING btree (campaign_id, calculated_at);
""",
    r"""
CREATE INDEX ix_payout_calculations_campaign_id ON public.payout_calculations USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_payout_calculations_campaign_status ON public.payout_calculations USING btree (campaign_id, status);
""",
    r"""
CREATE INDEX ix_payout_calculations_driver_profile_calculated_at ON public.payout_calculations USING btree (driver_profile_id, calculated_at);
""",
    r"""
CREATE INDEX ix_payout_calculations_driver_profile_id ON public.payout_calculations USING btree (driver_profile_id);
""",
    r"""
CREATE INDEX ix_payout_calculations_impression_estimate_id ON public.payout_calculations USING btree (impression_estimate_id);
""",
    r"""
CREATE INDEX ix_payout_calculations_trip_analytics_id ON public.payout_calculations USING btree (trip_analytics_id);
""",
    r"""
CREATE INDEX ix_payout_calculations_vehicle_id ON public.payout_calculations USING btree (vehicle_id);
""",
    r"""
CREATE INDEX ix_payout_correction_orders_campaign_day ON public.payout_correction_orders USING btree (campaign_id, lagos_day);
""",
    r"""
CREATE INDEX ix_payout_correction_orders_campaign_id ON public.payout_correction_orders USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_payout_debt_obligations_account ON public.payout_debt_obligations USING btree (debt_account_id, created_at);
""",
    r"""
CREATE INDEX ix_payout_line_events_line_id ON public.payout_line_reconciliation_events USING btree (line_id);
""",
    r"""
CREATE INDEX ix_payout_provider_event_processing_attempts_provider_event_id ON public.payout_provider_event_processing_attempts USING btree (provider_event_id);
""",
    r"""
CREATE INDEX ix_payout_recovery_incidents_exposure ON public.payout_recovery_incidents USING btree (exposure_line_id, status);
""",
    r"""
CREATE INDEX ix_payout_recovery_incidents_ledger ON public.payout_recovery_incidents USING btree (ledger_entry_id, created_at);
""",
    r"""
CREATE INDEX ix_payout_submission_intents_due ON public.payout_submission_intents USING btree (state, claim_expires_at, updated_at);
""",
    r"""
CREATE INDEX ix_payout_submission_observations_intent ON public.payout_submission_observations USING btree (intent_id, created_at);
""",
    r"""
CREATE INDEX ix_phone_challenges_version ON public.phone_verification_challenges USING btree (phone_version_id, created_at);
""",
    r"""
CREATE INDEX ix_quarantined_ping_batches_status ON public.quarantined_ping_batches USING btree (status);
""",
    r"""
CREATE INDEX ix_quarantined_ping_batches_trip_session_id ON public.quarantined_ping_batches USING btree (trip_session_id);
""",
    r"""
CREATE INDEX ix_receipt_allocations_commercial_terms_id ON public.receipt_allocations USING btree (commercial_terms_id);
""",
    r"""
CREATE INDEX ix_receipt_allocations_receipt_id ON public.receipt_allocations USING btree (receipt_id);
""",
    r"""
CREATE INDEX ix_receipt_lifecycle_events_receipt_id ON public.receipt_lifecycle_events USING btree (receipt_id);
""",
    r"""
CREATE INDEX ix_receipt_reconciliations_receipt_id ON public.receipt_reconciliations USING btree (receipt_id);
""",
    r"""
CREATE INDEX ix_refund_settlements_campaign_id ON public.refund_settlements USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_refund_settlements_cancellation_id ON public.refund_settlements USING btree (cancellation_id);
""",
    r"""
CREATE INDEX ix_refund_settlements_commercial_terms_id ON public.refund_settlements USING btree (commercial_terms_id);
""",
    r"""
CREATE INDEX ix_report_artifacts_issuance ON public.report_artifacts USING btree (report_issuance_id, created_at);
""",
    r"""
CREATE INDEX ix_report_issuances_due ON public.report_issuances USING btree (status, next_attempt_at, lease_expires_at, created_at);
""",
    r"""
CREATE INDEX ix_report_issuances_scope ON public.report_issuances USING btree (organization_id, campaign_id, created_at);
""",
    r"""
CREATE INDEX ix_report_publication_intents_due ON public.report_publication_intents USING btree (state, lease_expires_at, created_at);
""",
    r"""
CREATE INDEX ix_retargeting_source_events_source_created ON public.retargeting_source_events USING btree (source_id, created_at);
""",
    r"""
CREATE INDEX ix_retargeting_source_links_source_created ON public.retargeting_source_links USING btree (source_id, created_at);
""",
    r"""
CREATE INDEX ix_retargeting_sources_organization_created ON public.retargeting_sources USING btree (organization_id, created_at);
""",
    r"""
CREATE INDEX ix_route_replay_signatures_normalized_lookup ON public.route_replay_signatures USING btree (detector_version, normalized_fingerprint);
""",
    r"""
CREATE INDEX ix_route_replay_signatures_payload_lookup ON public.route_replay_signatures USING btree (detector_version, payload_fingerprint);
""",
    r"""
CREATE INDEX ix_route_replay_signatures_trip_analytics_id ON public.route_replay_signatures USING btree (trip_analytics_id);
""",
    r"""
CREATE INDEX ix_stored_files_organization_created ON public.stored_files USING btree (organization_id, created_at);
""",
    r"""
CREATE INDEX ix_stored_files_subject_created ON public.stored_files USING btree (subject_user_id, created_at);
""",
    r"""
CREATE INDEX ix_stored_object_deletions_organization_id ON public.stored_object_deletions USING btree (organization_id);
""",
    r"""
CREATE INDEX ix_stored_object_deletions_owner ON public.stored_object_deletions USING btree (owner_type, owner_id);
""",
    r"""
CREATE INDEX ix_stored_object_deletions_state_created ON public.stored_object_deletions USING btree (state, created_at);
""",
    r"""
CREATE INDEX ix_stored_object_deletions_stored_file_id ON public.stored_object_deletions USING btree (stored_file_id);
""",
    r"""
CREATE INDEX ix_stored_object_deletions_subject_user_id ON public.stored_object_deletions USING btree (subject_user_id);
""",
    r"""
CREATE INDEX ix_stored_object_deletions_upload_intent_id ON public.stored_object_deletions USING btree (upload_intent_id);
""",
    r"""
CREATE INDEX ix_traffic_density_profiles_lineage_effective ON public.traffic_density_profiles USING btree (lineage_id, effective_from);
""",
    r"""
CREATE INDEX ix_traffic_density_profiles_profile_type ON public.traffic_density_profiles USING btree (profile_type);
""",
    r"""
CREATE INDEX ix_traffic_density_profiles_status ON public.traffic_density_profiles USING btree (status);
""",
    r"""
CREATE INDEX ix_trip_analytics_assignment_id ON public.trip_analytics USING btree (assignment_id);
""",
    r"""
CREATE INDEX ix_trip_analytics_campaign_computed_at ON public.trip_analytics USING btree (campaign_id, computed_at);
""",
    r"""
CREATE INDEX ix_trip_analytics_campaign_id ON public.trip_analytics USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_trip_analytics_driver_profile_computed_at ON public.trip_analytics USING btree (driver_profile_id, computed_at);
""",
    r"""
CREATE INDEX ix_trip_analytics_driver_profile_id ON public.trip_analytics USING btree (driver_profile_id);
""",
    r"""
CREATE INDEX ix_trip_analytics_vehicle_id ON public.trip_analytics USING btree (vehicle_id);
""",
    r"""
CREATE INDEX ix_trip_manifest_entries_trip_session_id ON public.trip_evidence_manifest_entries USING btree (trip_session_id);
""",
    r"""
CREATE INDEX ix_trip_sessions_assignment_id ON public.trip_sessions USING btree (assignment_id);
""",
    r"""
CREATE INDEX ix_trip_sessions_campaign_id ON public.trip_sessions USING btree (campaign_id);
""",
    r"""
CREATE INDEX ix_trip_sessions_campaign_started_at ON public.trip_sessions USING btree (campaign_id, started_at);
""",
    r"""
CREATE INDEX ix_trip_sessions_display_proof_id ON public.trip_sessions USING btree (display_proof_id);
""",
    r"""
CREATE INDEX ix_trip_sessions_driver_profile_id ON public.trip_sessions USING btree (driver_profile_id);
""",
    r"""
CREATE INDEX ix_trip_sessions_driver_status ON public.trip_sessions USING btree (driver_profile_id, status);
""",
    r"""
CREATE INDEX ix_trip_sessions_vehicle_id ON public.trip_sessions USING btree (vehicle_id);
""",
    r"""
CREATE INDEX ix_trip_sessions_vehicle_status ON public.trip_sessions USING btree (vehicle_id, status);
""",
    r"""
CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);
""",
    r"""
CREATE INDEX ix_vehicle_evidence_documents_submission_id ON public.vehicle_evidence_documents USING btree (submission_id);
""",
    r"""
CREATE INDEX ix_vehicle_evidence_review_decisions_submission_id ON public.vehicle_evidence_review_decisions USING btree (submission_id);
""",
    r"""
CREATE INDEX ix_vehicle_evidence_submissions_vehicle_id ON public.vehicle_evidence_submissions USING btree (vehicle_id);
""",
    r"""
CREATE INDEX ix_vehicles_driver_profile_id ON public.vehicles USING btree (driver_profile_id);
""",
    r"""
CREATE INDEX ix_vehicles_plate_country_normalized ON public.vehicles USING btree (plate_country_code, plate_number_normalized);
""",
    r"""
CREATE INDEX ix_vehicles_status ON public.vehicles USING btree (status);
""",
    r"""
CREATE INDEX ix_whatsapp_consents_profile ON public.whatsapp_consents USING btree (driver_profile_id, version);
""",
    r"""
CREATE INDEX location_pings_p2026_07_batch_id_idx ON public.location_pings_p2026_07 USING btree (batch_id);
""",
    r"""
CREATE INDEX location_pings_p2026_07_geom_idx ON public.location_pings_p2026_07 USING gist (geom);
""",
    r"""
CREATE INDEX location_pings_p2026_07_trip_session_id_idx ON public.location_pings_p2026_07 USING btree (trip_session_id);
""",
    r"""
CREATE INDEX location_pings_p2026_07_trip_session_id_recorded_at_idx ON public.location_pings_p2026_07 USING btree (trip_session_id, recorded_at);
""",
    r"""
CREATE INDEX location_pings_p2026_08_batch_id_idx ON public.location_pings_p2026_08 USING btree (batch_id);
""",
    r"""
CREATE INDEX location_pings_p2026_08_geom_idx ON public.location_pings_p2026_08 USING gist (geom);
""",
    r"""
CREATE INDEX location_pings_p2026_08_trip_session_id_idx ON public.location_pings_p2026_08 USING btree (trip_session_id);
""",
    r"""
CREATE INDEX location_pings_p2026_08_trip_session_id_recorded_at_idx ON public.location_pings_p2026_08 USING btree (trip_session_id, recorded_at);
""",
    r"""
CREATE INDEX location_pings_p2026_09_batch_id_idx ON public.location_pings_p2026_09 USING btree (batch_id);
""",
    r"""
CREATE INDEX location_pings_p2026_09_geom_idx ON public.location_pings_p2026_09 USING gist (geom);
""",
    r"""
CREATE INDEX location_pings_p2026_09_trip_session_id_idx ON public.location_pings_p2026_09 USING btree (trip_session_id);
""",
    r"""
CREATE INDEX location_pings_p2026_09_trip_session_id_recorded_at_idx ON public.location_pings_p2026_09 USING btree (trip_session_id, recorded_at);
""",
    r"""
CREATE INDEX location_pings_p2026_10_batch_id_idx ON public.location_pings_p2026_10 USING btree (batch_id);
""",
    r"""
CREATE INDEX location_pings_p2026_10_geom_idx ON public.location_pings_p2026_10 USING gist (geom);
""",
    r"""
CREATE INDEX location_pings_p2026_10_trip_session_id_idx ON public.location_pings_p2026_10 USING btree (trip_session_id);
""",
    r"""
CREATE INDEX location_pings_p2026_10_trip_session_id_recorded_at_idx ON public.location_pings_p2026_10 USING btree (trip_session_id, recorded_at);
""",
    r"""
CREATE INDEX location_pings_p2026_11_batch_id_idx ON public.location_pings_p2026_11 USING btree (batch_id);
""",
    r"""
CREATE INDEX location_pings_p2026_11_geom_idx ON public.location_pings_p2026_11 USING gist (geom);
""",
    r"""
CREATE INDEX location_pings_p2026_11_trip_session_id_idx ON public.location_pings_p2026_11 USING btree (trip_session_id);
""",
    r"""
CREATE INDEX location_pings_p2026_11_trip_session_id_recorded_at_idx ON public.location_pings_p2026_11 USING btree (trip_session_id, recorded_at);
""",
    r"""
CREATE INDEX location_pings_p2026_12_batch_id_idx ON public.location_pings_p2026_12 USING btree (batch_id);
""",
    r"""
CREATE INDEX location_pings_p2026_12_geom_idx ON public.location_pings_p2026_12 USING gist (geom);
""",
    r"""
CREATE INDEX location_pings_p2026_12_trip_session_id_idx ON public.location_pings_p2026_12 USING btree (trip_session_id);
""",
    r"""
CREATE INDEX location_pings_p2026_12_trip_session_id_recorded_at_idx ON public.location_pings_p2026_12 USING btree (trip_session_id, recorded_at);
""",
    r"""
CREATE INDEX location_pings_p2027_01_batch_id_idx ON public.location_pings_p2027_01 USING btree (batch_id);
""",
    r"""
CREATE INDEX location_pings_p2027_01_geom_idx ON public.location_pings_p2027_01 USING gist (geom);
""",
    r"""
CREATE INDEX location_pings_p2027_01_trip_session_id_idx ON public.location_pings_p2027_01 USING btree (trip_session_id);
""",
    r"""
CREATE INDEX location_pings_p2027_01_trip_session_id_recorded_at_idx ON public.location_pings_p2027_01 USING btree (trip_session_id, recorded_at);
""",
    r"""
CREATE INDEX location_pings_p2027_02_batch_id_idx ON public.location_pings_p2027_02 USING btree (batch_id);
""",
    r"""
CREATE INDEX location_pings_p2027_02_geom_idx ON public.location_pings_p2027_02 USING gist (geom);
""",
    r"""
CREATE INDEX location_pings_p2027_02_trip_session_id_idx ON public.location_pings_p2027_02 USING btree (trip_session_id);
""",
    r"""
CREATE INDEX location_pings_p2027_02_trip_session_id_recorded_at_idx ON public.location_pings_p2027_02 USING btree (trip_session_id, recorded_at);
""",
    r"""
CREATE UNIQUE INDEX uq_audit_subject_unresolved ON public.audit_event_subject_resolutions USING btree (audit_event_id, role) WHERE (subject_user_id IS NULL);
""",
    r"""
CREATE UNIQUE INDEX uq_campaign_activation_events_assignment_terminal_decision ON public.campaign_activation_events USING btree (assignment_id) WHERE event_type IN ('accepted', 'declined', 'expired');
""",
    r"""
CREATE UNIQUE INDEX uq_campaign_assignments_campaign_vehicle_non_terminal ON public.campaign_assignments USING btree (campaign_id, vehicle_id) WHERE status IN ('offered', 'accepted', 'active', 'deactivated');
""",
    r"""
CREATE UNIQUE INDEX uq_campaign_assignments_driver_active ON public.campaign_assignments USING btree (driver_profile_id) WHERE ((status)::text = 'active'::text);
""",
    r"""
CREATE UNIQUE INDEX uq_campaign_assignments_vehicle_active ON public.campaign_assignments USING btree (vehicle_id) WHERE ((status)::text = 'active'::text);
""",
    r"""
CREATE UNIQUE INDEX uq_campaign_payout_rules_active_campaign ON public.campaign_payout_rules USING btree (campaign_id) WHERE ((status)::text = 'active'::text);
""",
    r"""
CREATE UNIQUE INDEX uq_data_purge_audit_dropped ON public.data_purge_audit USING btree (partition_name) WHERE (event = 'dropped'::text);
""",
    r"""
CREATE UNIQUE INDEX uq_earnings_ledger_entries_payout_calculation_id ON public.earnings_ledger_entries USING btree (payout_calculation_id) WHERE (payout_calculation_id IS NOT NULL);
""",
    r"""
CREATE UNIQUE INDEX uq_earnings_ledger_entries_source_fraud_flag_id ON public.earnings_ledger_entries USING btree (source_fraud_flag_id) WHERE (source_fraud_flag_id IS NOT NULL);
""",
    r"""
CREATE UNIQUE INDEX uq_earnings_ledger_entries_trip_payout_per_trip ON public.earnings_ledger_entries USING btree (trip_session_id) WHERE ((entry_type)::text = 'trip_payout'::text);
""",
    r"""
CREATE UNIQUE INDEX uq_evidence_verifications_admin_request ON public.evidence_verifications USING btree (issued_by_user_id, client_request_id) WHERE (client_request_id IS NOT NULL);
""",
    r"""
CREATE UNIQUE INDEX uq_evidence_verifications_automatic_source ON public.evidence_verifications USING btree (verification_type, source_trip_session_id) WHERE ((verification_type)::text <> 'physical_spot_check'::text);
""",
    r"""
CREATE UNIQUE INDEX uq_fraud_flags_trip_nonterminal_flag_type ON public.fraud_flags USING btree (trip_session_id, flag_type) WHERE status IN ('open', 'acknowledged', 'confirmed');
""",
    r"""
CREATE UNIQUE INDEX uq_impression_estimates_authoritative_trip_formula ON public.impression_estimates USING btree (trip_session_id, formula_version) WHERE (is_authoritative = true);
""",
    r"""
CREATE UNIQUE INDEX uq_installation_evidence_assignment_pending ON public.installation_evidence_submissions USING btree (assignment_id) WHERE ((status)::text = 'pending_review'::text);
""",
    r"""
CREATE UNIQUE INDEX uq_location_ping_batches_trip_sequence_manifest ON public.location_ping_batches USING btree (trip_session_id, batch_sequence) WHERE ((evidence_scope)::text = 'manifest'::text);
""",
    r"""
CREATE UNIQUE INDEX uq_organization_memberships_user_active ON public.organization_memberships USING btree (user_id) WHERE ((status)::text = 'active'::text);
""",
    r"""
CREATE UNIQUE INDEX uq_payout_batch_lines_active_ledger_entry ON public.payout_batch_lines USING btree (ledger_entry_id) WHERE (reservation_active = true);
""",
    r"""
CREATE UNIQUE INDEX uq_payout_batch_lines_predecessor ON public.payout_batch_lines USING btree (predecessor_line_id) WHERE (predecessor_line_id IS NOT NULL);
""",
    r"""
CREATE UNIQUE INDEX uq_payout_batch_lines_provider_transfer_reference ON public.payout_batch_lines USING btree (provider_transfer_reference) WHERE (provider_transfer_reference IS NOT NULL);
""",
    r"""
CREATE UNIQUE INDEX uq_payout_debt_obligations_direct_reversal ON public.payout_debt_obligations USING btree (source_reversal_entry_id) WHERE (recovery_incident_id IS NULL);
""",
    r"""
CREATE UNIQUE INDEX uq_payout_submission_intents_provider_transfer_reference ON public.payout_submission_intents USING btree (provider_transfer_reference) WHERE (provider_transfer_reference IS NOT NULL);
""",
    r"""
CREATE UNIQUE INDEX uq_report_issuances_initial_run ON public.report_issuances USING btree (measurement_run_id) WHERE (reissue_of_id IS NULL);
""",
    r"""
CREATE UNIQUE INDEX uq_report_publication_intents_live ON public.report_publication_intents USING btree (report_issuance_id) WHERE state IN ('prepared', 'publishing');
""",
    r"""
CREATE UNIQUE INDEX uq_retargeting_source_links_active_identity ON public.retargeting_source_links USING btree (source_id, campaign_id, zone_id, start_at, end_at) WHERE ((status)::text = 'active'::text);
""",
    r"""
CREATE UNIQUE INDEX uq_route_replay_signatures_trip_session_id ON public.route_replay_signatures USING btree (trip_session_id);
""",
    r"""
CREATE UNIQUE INDEX uq_traffic_density_profiles_active_default ON public.traffic_density_profiles USING btree (is_default) WHERE ((is_default = true) AND ((status)::text = 'active'::text));
""",
    r"""
CREATE UNIQUE INDEX uq_trip_sessions_driver_profile_active ON public.trip_sessions USING btree (driver_profile_id) WHERE ((status)::text = 'active'::text);
""",
    r"""
CREATE UNIQUE INDEX uq_trip_sessions_vehicle_active ON public.trip_sessions USING btree (vehicle_id) WHERE ((status)::text = 'active'::text);
""",
    r"""
ALTER INDEX public.ix_location_pings_batch_id ATTACH PARTITION public.location_pings_p2026_07_batch_id_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_geom ATTACH PARTITION public.location_pings_p2026_07_geom_idx;
""",
    r"""
ALTER INDEX public.location_pings_pkey ATTACH PARTITION public.location_pings_p2026_07_pkey;
""",
    r"""
ALTER INDEX public.ix_location_pings_trip_session_id ATTACH PARTITION public.location_pings_p2026_07_trip_session_id_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_trip_recorded_at ATTACH PARTITION public.location_pings_p2026_07_trip_session_id_recorded_at_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_batch_id ATTACH PARTITION public.location_pings_p2026_08_batch_id_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_geom ATTACH PARTITION public.location_pings_p2026_08_geom_idx;
""",
    r"""
ALTER INDEX public.location_pings_pkey ATTACH PARTITION public.location_pings_p2026_08_pkey;
""",
    r"""
ALTER INDEX public.ix_location_pings_trip_session_id ATTACH PARTITION public.location_pings_p2026_08_trip_session_id_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_trip_recorded_at ATTACH PARTITION public.location_pings_p2026_08_trip_session_id_recorded_at_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_batch_id ATTACH PARTITION public.location_pings_p2026_09_batch_id_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_geom ATTACH PARTITION public.location_pings_p2026_09_geom_idx;
""",
    r"""
ALTER INDEX public.location_pings_pkey ATTACH PARTITION public.location_pings_p2026_09_pkey;
""",
    r"""
ALTER INDEX public.ix_location_pings_trip_session_id ATTACH PARTITION public.location_pings_p2026_09_trip_session_id_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_trip_recorded_at ATTACH PARTITION public.location_pings_p2026_09_trip_session_id_recorded_at_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_batch_id ATTACH PARTITION public.location_pings_p2026_10_batch_id_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_geom ATTACH PARTITION public.location_pings_p2026_10_geom_idx;
""",
    r"""
ALTER INDEX public.location_pings_pkey ATTACH PARTITION public.location_pings_p2026_10_pkey;
""",
    r"""
ALTER INDEX public.ix_location_pings_trip_session_id ATTACH PARTITION public.location_pings_p2026_10_trip_session_id_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_trip_recorded_at ATTACH PARTITION public.location_pings_p2026_10_trip_session_id_recorded_at_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_batch_id ATTACH PARTITION public.location_pings_p2026_11_batch_id_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_geom ATTACH PARTITION public.location_pings_p2026_11_geom_idx;
""",
    r"""
ALTER INDEX public.location_pings_pkey ATTACH PARTITION public.location_pings_p2026_11_pkey;
""",
    r"""
ALTER INDEX public.ix_location_pings_trip_session_id ATTACH PARTITION public.location_pings_p2026_11_trip_session_id_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_trip_recorded_at ATTACH PARTITION public.location_pings_p2026_11_trip_session_id_recorded_at_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_batch_id ATTACH PARTITION public.location_pings_p2026_12_batch_id_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_geom ATTACH PARTITION public.location_pings_p2026_12_geom_idx;
""",
    r"""
ALTER INDEX public.location_pings_pkey ATTACH PARTITION public.location_pings_p2026_12_pkey;
""",
    r"""
ALTER INDEX public.ix_location_pings_trip_session_id ATTACH PARTITION public.location_pings_p2026_12_trip_session_id_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_trip_recorded_at ATTACH PARTITION public.location_pings_p2026_12_trip_session_id_recorded_at_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_batch_id ATTACH PARTITION public.location_pings_p2027_01_batch_id_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_geom ATTACH PARTITION public.location_pings_p2027_01_geom_idx;
""",
    r"""
ALTER INDEX public.location_pings_pkey ATTACH PARTITION public.location_pings_p2027_01_pkey;
""",
    r"""
ALTER INDEX public.ix_location_pings_trip_session_id ATTACH PARTITION public.location_pings_p2027_01_trip_session_id_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_trip_recorded_at ATTACH PARTITION public.location_pings_p2027_01_trip_session_id_recorded_at_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_batch_id ATTACH PARTITION public.location_pings_p2027_02_batch_id_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_geom ATTACH PARTITION public.location_pings_p2027_02_geom_idx;
""",
    r"""
ALTER INDEX public.location_pings_pkey ATTACH PARTITION public.location_pings_p2027_02_pkey;
""",
    r"""
ALTER INDEX public.ix_location_pings_trip_session_id ATTACH PARTITION public.location_pings_p2027_02_trip_session_id_idx;
""",
    r"""
ALTER INDEX public.ix_location_pings_trip_recorded_at ATTACH PARTITION public.location_pings_p2027_02_trip_session_id_recorded_at_idx;
""",
    r"""
CREATE TRIGGER a_driver_kyc_documents_parent_retention BEFORE INSERT OR UPDATE ON public.driver_kyc_documents FOR EACH ROW EXECUTE FUNCTION public.guard_kyc_document_retention('driver_kyc_submissions');
""",
    r"""
ALTER TABLE public.driver_kyc_documents ENABLE ALWAYS TRIGGER a_driver_kyc_documents_parent_retention;
""",
    r"""
CREATE TRIGGER a_driver_kyc_submissions_payload_retention BEFORE DELETE OR UPDATE ON public.driver_kyc_submissions FOR EACH ROW EXECUTE FUNCTION public.guard_kyc_payload_retention('driver_kyc_documents', 'driver_kyc_submission', 'encrypted_nin,encryption_algorithm,encryption_key_version,nin_last_four,purged_at');
""",
    r"""
ALTER TABLE public.driver_kyc_submissions ENABLE ALWAYS TRIGGER a_driver_kyc_submissions_payload_retention;
""",
    r"""
CREATE TRIGGER a_vehicle_evidence_documents_parent_retention BEFORE INSERT OR UPDATE ON public.vehicle_evidence_documents FOR EACH ROW EXECUTE FUNCTION public.guard_kyc_document_retention('vehicle_evidence_submissions');
""",
    r"""
ALTER TABLE public.vehicle_evidence_documents ENABLE ALWAYS TRIGGER a_vehicle_evidence_documents_parent_retention;
""",
    r"""
CREATE TRIGGER a_vehicle_evidence_submissions_payload_retention BEFORE DELETE OR UPDATE ON public.vehicle_evidence_submissions FOR EACH ROW EXECUTE FUNCTION public.guard_kyc_payload_retention('vehicle_evidence_documents', 'vehicle_evidence_submission', 'plate_number_snapshot,plate_number_normalized_snapshot,plate_country_code_snapshot,vehicle_type_snapshot,make_snapshot,model_snapshot,year_snapshot,color_snapshot,purged_at');
""",
    r"""
ALTER TABLE public.vehicle_evidence_submissions ENABLE ALWAYS TRIGGER a_vehicle_evidence_submissions_payload_retention;
""",
    r"""
CREATE TRIGGER assignment_activity_flag_events_append_only BEFORE DELETE OR UPDATE ON public.assignment_activity_flag_events FOR EACH ROW EXECUTE FUNCTION public.prevent_assignment_activity_flag_event_mutation();
""",
    r"""
CREATE TRIGGER assignment_rule_binding_offer_evidence_immutable BEFORE UPDATE ON public.assignment_rule_bindings FOR EACH ROW EXECUTE FUNCTION public.prevent_assignment_rule_binding_evidence_mutation();
""",
    r"""
CREATE TRIGGER audience_deliveries_immutable BEFORE DELETE OR UPDATE ON public.audience_deliveries FOR EACH ROW EXECUTE FUNCTION public.reject_audience_delivery_mutation();
""",
    r"""
CREATE TRIGGER audience_delivery_approvals_immutable BEFORE DELETE OR UPDATE ON public.audience_delivery_approvals FOR EACH ROW EXECUTE FUNCTION public.reject_audience_delivery_approval_mutation();
""",
    r"""
CREATE TRIGGER audit_subject_resolution_immutable BEFORE DELETE OR UPDATE ON public.audit_event_subject_resolutions FOR EACH ROW EXECUTE FUNCTION public.reject_audit_subject_resolution_mutation();
""",
    r"""
ALTER TABLE public.audit_event_subject_resolutions ENABLE ALWAYS TRIGGER audit_subject_resolution_immutable;
""",
    r"""
CREATE TRIGGER audit_subject_resolution_no_truncate BEFORE TRUNCATE ON public.audit_event_subject_resolutions FOR EACH STATEMENT EXECUTE FUNCTION public.reject_audit_subject_resolution_mutation();
""",
    r"""
ALTER TABLE public.audit_event_subject_resolutions ENABLE ALWAYS TRIGGER audit_subject_resolution_no_truncate;
""",
    r"""
CREATE TRIGGER budget_campaign_transitions_append_only BEFORE DELETE OR UPDATE ON public.budget_campaign_transitions FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER budget_policy_evaluations_append_only BEFORE DELETE OR UPDATE ON public.budget_policy_evaluations FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER campaign_activation_events_append_only BEFORE DELETE OR UPDATE ON public.campaign_activation_events FOR EACH ROW EXECUTE FUNCTION public.prevent_campaign_activation_event_mutation();
""",
    r"""
CREATE TRIGGER campaign_assignment_offer_evidence_immutable BEFORE UPDATE ON public.campaign_assignments FOR EACH ROW EXECUTE FUNCTION public.prevent_campaign_assignment_offer_evidence_mutation();
""",
    r"""
CREATE TRIGGER campaign_cancellation_settlement_revisions_append_only BEFORE DELETE OR UPDATE ON public.campaign_cancellation_settlement_revisions FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER campaign_cancellations_append_only BEFORE DELETE OR UPDATE ON public.campaign_cancellations FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER campaign_change_request_guard BEFORE DELETE OR UPDATE ON public.campaign_change_requests FOR EACH ROW EXECUTE FUNCTION public.guard_campaign_change_request_mutation();
""",
    r"""
CREATE TRIGGER campaign_change_revisions_append_only BEFORE DELETE OR UPDATE ON public.campaign_change_revisions FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER campaign_financial_authorizations_append_only BEFORE DELETE OR UPDATE ON public.campaign_financial_authorizations FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER campaign_liability_reservations_transition BEFORE DELETE OR UPDATE ON public.campaign_liability_reservations FOR EACH ROW EXECUTE FUNCTION public.enforce_liability_reservation_transition();
""",
    r"""
CREATE TRIGGER campaign_review_events_append_only BEFORE DELETE OR UPDATE ON public.campaign_review_events FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER commercial_quotation_revisions_append_only BEFORE DELETE OR UPDATE ON public.commercial_quotation_revisions FOR EACH ROW EXECUTE FUNCTION public.reject_commercial_authority_mutation();
""",
    r"""
CREATE TRIGGER commercial_terms_append_only BEFORE DELETE OR UPDATE ON public.commercial_terms FOR EACH ROW EXECUTE FUNCTION public.reject_commercial_authority_mutation();
""",
    r"""
CREATE TRIGGER creative_review_events_append_only BEFORE DELETE OR UPDATE ON public.creative_review_events FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER data_purge_audit_immutable BEFORE DELETE OR UPDATE OR TRUNCATE ON public.data_purge_audit FOR EACH STATEMENT EXECUTE FUNCTION public.reject_data_purge_audit_mutation();
""",
    r"""
ALTER TABLE public.data_purge_audit ENABLE ALWAYS TRIGGER data_purge_audit_immutable;
""",
    r"""
CREATE TRIGGER data_subject_location_assessments_immutable BEFORE DELETE OR UPDATE ON public.data_subject_location_assessments FOR EACH ROW EXECUTE FUNCTION public.reject_data_subject_assessment_mutation();
""",
    r"""
CREATE TRIGGER data_subject_requests_guard BEFORE DELETE OR UPDATE ON public.data_subject_requests FOR EACH ROW EXECUTE FUNCTION public.validate_data_subject_request_mutation();
""",
    r"""
CREATE TRIGGER display_proof_challenge_guard BEFORE DELETE OR UPDATE ON public.display_proof_challenges FOR EACH ROW EXECUTE FUNCTION public.guard_display_proof_challenge_mutation();
""",
    r"""
CREATE TRIGGER display_proofs_append_only BEFORE DELETE OR UPDATE ON public.display_proofs FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER driver_kyc_review_decisions_immutable BEFORE DELETE OR UPDATE ON public.driver_kyc_review_decisions FOR EACH ROW EXECUTE FUNCTION public.reject_driver_kyc_review_decision_mutation();
""",
    r"""
CREATE TRIGGER expedited_production_waivers_append_only BEFORE DELETE OR UPDATE ON public.expedited_production_waivers FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER exposure_scores_immutable BEFORE DELETE OR UPDATE ON public.exposure_scores FOR EACH ROW EXECUTE FUNCTION public.reject_exposure_score_mutation();
""",
    r"""
CREATE TRIGGER exposure_segment_cells_immutable BEFORE DELETE OR UPDATE ON public.exposure_segment_cells FOR EACH ROW EXECUTE FUNCTION public.reject_exposure_segment_mutation();
""",
    r"""
CREATE TRIGGER exposure_segments_immutable BEFORE DELETE OR UPDATE ON public.exposure_segments FOR EACH ROW EXECUTE FUNCTION public.reject_exposure_segment_mutation();
""",
    r"""
CREATE TRIGGER financial_authorization_allocations_append_only BEFORE DELETE OR UPDATE ON public.financial_authorization_allocations FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER installation_evidence_photos_append_only BEFORE DELETE OR UPDATE ON public.installation_evidence_photos FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER installation_evidence_submission_guard BEFORE DELETE OR UPDATE ON public.installation_evidence_submissions FOR EACH ROW EXECUTE FUNCTION public.guard_installation_evidence_submission_mutation();
""",
    r"""
CREATE TRIGGER invoice_corrections_append_only BEFORE DELETE OR UPDATE ON public.invoice_corrections FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER invoice_issuer_profiles_append_only BEFORE DELETE OR UPDATE ON public.invoice_issuer_profiles FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER invoices_issued_immutable BEFORE DELETE OR UPDATE ON public.invoices FOR EACH ROW EXECUTE FUNCTION public.protect_issued_invoice();
""",
    r"""
CREATE TRIGGER measurement_run_proof_bindings_immutable BEFORE DELETE OR UPDATE ON public.measurement_run_proof_bindings FOR EACH ROW EXECUTE FUNCTION public.reject_measurement_evidence_mutation();
""",
    r"""
CREATE TRIGGER measurement_runs_immutable BEFORE DELETE OR UPDATE ON public.measurement_runs FOR EACH ROW EXECUTE FUNCTION public.reject_measurement_evidence_mutation();
""",
    r"""
CREATE TRIGGER notification_delivery_receipts_immutable BEFORE DELETE OR UPDATE ON public.notification_delivery_receipts FOR EACH ROW EXECUTE FUNCTION public.reject_notification_delivery_receipt_mutation();
""",
    r"""
CREATE TRIGGER notifications_evidence_immutable BEFORE DELETE OR UPDATE ON public.notifications FOR EACH ROW EXECUTE FUNCTION public.reject_notification_evidence_mutation();
""",
    r"""
CREATE TRIGGER payee_bank_account_payout_verifications_immutable BEFORE DELETE OR UPDATE ON public.payee_bank_account_payout_verifications FOR EACH ROW EXECUTE FUNCTION public.reject_payee_payout_verification_mutation();
""",
    r"""
CREATE TRIGGER payment_gateway_events_append_only BEFORE DELETE OR UPDATE ON public.payment_gateway_events FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER payment_gateway_processing_attempts_append_only BEFORE DELETE OR UPDATE ON public.payment_gateway_processing_attempts FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER payment_receipts_append_only BEFORE DELETE OR UPDATE ON public.payment_receipts FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER payout_batch_lines_guarded BEFORE UPDATE ON public.payout_batch_lines FOR EACH ROW EXECUTE FUNCTION public.guard_payout_batch_line_mutation();
""",
    r"""
CREATE TRIGGER payout_batch_lines_no_delete BEFORE DELETE ON public.payout_batch_lines FOR EACH ROW EXECUTE FUNCTION public.reject_payout_submission_history_mutation();
""",
    r"""
CREATE TRIGGER payout_batch_lines_no_truncate BEFORE TRUNCATE ON public.payout_batch_lines FOR EACH STATEMENT EXECUTE FUNCTION public.reject_payout_submission_history_mutation();
""",
    r"""
CREATE TRIGGER payout_recovery_incidents_guarded BEFORE UPDATE ON public.payout_recovery_incidents FOR EACH ROW EXECUTE FUNCTION public.guard_payout_recovery_incident_mutation();
""",
    r"""
CREATE TRIGGER payout_recovery_incidents_no_delete BEFORE DELETE ON public.payout_recovery_incidents FOR EACH ROW EXECUTE FUNCTION public.reject_payout_submission_history_mutation();
""",
    r"""
CREATE TRIGGER payout_recovery_incidents_no_truncate BEFORE TRUNCATE ON public.payout_recovery_incidents FOR EACH STATEMENT EXECUTE FUNCTION public.reject_payout_submission_history_mutation();
""",
    r"""
CREATE TRIGGER payout_submission_attempts_no_delete BEFORE DELETE ON public.payout_submission_attempts FOR EACH ROW EXECUTE FUNCTION public.reject_payout_submission_history_mutation();
""",
    r"""
CREATE TRIGGER payout_submission_attempts_no_truncate BEFORE TRUNCATE ON public.payout_submission_attempts FOR EACH STATEMENT EXECUTE FUNCTION public.reject_payout_submission_history_mutation();
""",
    r"""
CREATE TRIGGER payout_submission_attempts_no_update BEFORE UPDATE ON public.payout_submission_attempts FOR EACH ROW EXECUTE FUNCTION public.reject_payout_submission_history_mutation();
""",
    r"""
CREATE TRIGGER payout_submission_intents_guarded BEFORE UPDATE ON public.payout_submission_intents FOR EACH ROW EXECUTE FUNCTION public.guard_payout_submission_intent_mutation();
""",
    r"""
CREATE TRIGGER payout_submission_intents_no_delete BEFORE DELETE ON public.payout_submission_intents FOR EACH ROW EXECUTE FUNCTION public.reject_payout_submission_history_mutation();
""",
    r"""
CREATE TRIGGER payout_submission_intents_no_truncate BEFORE TRUNCATE ON public.payout_submission_intents FOR EACH STATEMENT EXECUTE FUNCTION public.reject_payout_submission_history_mutation();
""",
    r"""
CREATE TRIGGER payout_submission_observations_no_delete BEFORE DELETE ON public.payout_submission_observations FOR EACH ROW EXECUTE FUNCTION public.reject_payout_submission_history_mutation();
""",
    r"""
CREATE TRIGGER payout_submission_observations_no_truncate BEFORE TRUNCATE ON public.payout_submission_observations FOR EACH STATEMENT EXECUTE FUNCTION public.reject_payout_submission_history_mutation();
""",
    r"""
CREATE TRIGGER payout_submission_observations_no_update BEFORE UPDATE ON public.payout_submission_observations FOR EACH ROW EXECUTE FUNCTION public.reject_payout_submission_history_mutation();
""",
    r"""
CREATE TRIGGER production_starts_append_only BEFORE DELETE OR UPDATE ON public.production_starts FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER quarantined_trip_batch_receipt_guard BEFORE UPDATE ON public.quarantined_ping_batches FOR EACH ROW EXECUTE FUNCTION public.guard_quarantined_trip_batch_receipt();
""",
    r"""
CREATE TRIGGER receipt_allocations_append_only BEFORE DELETE OR UPDATE ON public.receipt_allocations FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER receipt_lifecycle_events_append_only BEFORE DELETE OR UPDATE ON public.receipt_lifecycle_events FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER receipt_reconciliations_append_only BEFORE DELETE OR UPDATE ON public.receipt_reconciliations FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER refund_settlements_append_only BEFORE DELETE OR UPDATE ON public.refund_settlements FOR EACH ROW EXECUTE FUNCTION public.reject_receipt_authority_mutation();
""",
    r"""
CREATE TRIGGER report_artifact_files_immutable BEFORE DELETE OR UPDATE ON public.stored_files FOR EACH ROW EXECUTE FUNCTION public.reject_report_artifact_file_mutation();
""",
    r"""
CREATE TRIGGER report_artifacts_immutable BEFORE DELETE OR UPDATE ON public.report_artifacts FOR EACH ROW EXECUTE FUNCTION public.reject_report_artifact_mutation();
""",
    r"""
CREATE TRIGGER report_issuances_frozen_immutable BEFORE UPDATE ON public.report_issuances FOR EACH ROW EXECUTE FUNCTION public.reject_report_issuance_frozen_mutation();
""",
    r"""
CREATE TRIGGER report_issuances_no_delete BEFORE DELETE ON public.report_issuances FOR EACH ROW EXECUTE FUNCTION public.reject_report_issuance_delete();
""",
    r"""
CREATE TRIGGER report_publication_intents_guarded BEFORE UPDATE ON public.report_publication_intents FOR EACH ROW EXECUTE FUNCTION public.reject_report_publication_mutation();
""",
    r"""
CREATE TRIGGER report_publication_intents_no_delete BEFORE DELETE ON public.report_publication_intents FOR EACH ROW EXECUTE FUNCTION public.reject_report_publication_delete();
""",
    r"""
CREATE TRIGGER report_publication_settlement_guard BEFORE INSERT OR UPDATE ON public.report_publication_intents FOR EACH ROW EXECUTE FUNCTION public.guard_report_publication_settlement();
""",
    r"""
ALTER TABLE public.report_publication_intents ENABLE ALWAYS TRIGGER report_publication_settlement_guard;
""",
    r"""
CREATE TRIGGER report_publication_write_guard BEFORE INSERT OR DELETE OR UPDATE ON public.report_publication_writes FOR EACH ROW EXECUTE FUNCTION public.guard_report_publication_write();
""",
    r"""
ALTER TABLE public.report_publication_writes ENABLE ALWAYS TRIGGER report_publication_write_guard;
""",
    r"""
CREATE TRIGGER report_publication_write_truncate BEFORE TRUNCATE ON public.report_publication_writes FOR EACH STATEMENT EXECUTE FUNCTION public.guard_report_publication_write();
""",
    r"""
ALTER TABLE public.report_publication_writes ENABLE ALWAYS TRIGGER report_publication_write_truncate;
""",
    r"""
CREATE TRIGGER signed_location_ping_guard BEFORE INSERT OR DELETE OR UPDATE ON public.location_pings FOR EACH ROW EXECUTE FUNCTION public.guard_signed_location_ping();
""",
    r"""
CREATE TRIGGER trg_assignment_rule_bindings_immutable BEFORE DELETE OR UPDATE ON public.assignment_rule_bindings FOR EACH STATEMENT EXECUTE FUNCTION public.reject_payout_authority_mutation();
""",
    r"""
ALTER TABLE public.assignment_rule_bindings ENABLE ALWAYS TRIGGER trg_assignment_rule_bindings_immutable;
""",
    r"""
CREATE TRIGGER trg_assignment_rule_bindings_no_truncate BEFORE TRUNCATE ON public.assignment_rule_bindings FOR EACH STATEMENT EXECUTE FUNCTION public.reject_payout_authority_mutation();
""",
    r"""
ALTER TABLE public.assignment_rule_bindings ENABLE ALWAYS TRIGGER trg_assignment_rule_bindings_no_truncate;
""",
    r"""
CREATE TRIGGER trg_campaign_creatives_deletion_fence BEFORE INSERT OR UPDATE OF stored_file_id ON public.campaign_creatives FOR EACH ROW EXECUTE FUNCTION public.reject_reference_to_deleting_stored_object();
""",
    r"""
CREATE TRIGGER trg_campaign_payout_rule_revisions_immutable BEFORE DELETE OR UPDATE ON public.campaign_payout_rule_revisions FOR EACH STATEMENT EXECUTE FUNCTION public.reject_payout_authority_mutation();
""",
    r"""
ALTER TABLE public.campaign_payout_rule_revisions ENABLE ALWAYS TRIGGER trg_campaign_payout_rule_revisions_immutable;
""",
    r"""
CREATE TRIGGER trg_campaign_payout_rule_revisions_no_truncate BEFORE TRUNCATE ON public.campaign_payout_rule_revisions FOR EACH STATEMENT EXECUTE FUNCTION public.reject_payout_authority_mutation();
""",
    r"""
ALTER TABLE public.campaign_payout_rule_revisions ENABLE ALWAYS TRIGGER trg_campaign_payout_rule_revisions_no_truncate;
""",
    r"""
CREATE TRIGGER trg_display_proofs_deletion_fence BEFORE INSERT OR UPDATE OF stored_file_id ON public.display_proofs FOR EACH ROW EXECUTE FUNCTION public.reject_reference_to_deleting_stored_object();
""",
    r"""
CREATE TRIGGER trg_driver_kyc_documents_deletion_fence BEFORE INSERT OR UPDATE OF stored_file_id ON public.driver_kyc_documents FOR EACH ROW EXECUTE FUNCTION public.reject_reference_to_deleting_stored_object();
""",
    r"""
CREATE TRIGGER trg_earnings_ledger_entries_guard BEFORE DELETE OR UPDATE ON public.earnings_ledger_entries FOR EACH ROW EXECUTE FUNCTION public.guard_earnings_ledger_entry_mutation();
""",
    r"""
ALTER TABLE public.earnings_ledger_entries ENABLE ALWAYS TRIGGER trg_earnings_ledger_entries_guard;
""",
    r"""
CREATE TRIGGER trg_earnings_ledger_entries_no_truncate BEFORE TRUNCATE ON public.earnings_ledger_entries FOR EACH STATEMENT EXECUTE FUNCTION public.reject_payout_authority_mutation();
""",
    r"""
ALTER TABLE public.earnings_ledger_entries ENABLE ALWAYS TRIGGER trg_earnings_ledger_entries_no_truncate;
""",
    r"""
CREATE TRIGGER trg_installation_evidence_photos_deletion_fence BEFORE INSERT OR UPDATE OF stored_file_id ON public.installation_evidence_photos FOR EACH ROW EXECUTE FUNCTION public.reject_reference_to_deleting_stored_object();
""",
    r"""
CREATE TRIGGER trg_location_ping_batch_disposition_immutable BEFORE UPDATE ON public.location_ping_batches FOR EACH ROW EXECUTE FUNCTION public.reject_location_ping_batch_disposition_mutation();
""",
    r"""
CREATE TRIGGER trg_payout_calculations_immutable BEFORE DELETE OR UPDATE ON public.payout_calculations FOR EACH STATEMENT EXECUTE FUNCTION public.reject_payout_authority_mutation();
""",
    r"""
ALTER TABLE public.payout_calculations ENABLE ALWAYS TRIGGER trg_payout_calculations_immutable;
""",
    r"""
CREATE TRIGGER trg_payout_calculations_no_truncate BEFORE TRUNCATE ON public.payout_calculations FOR EACH STATEMENT EXECUTE FUNCTION public.reject_payout_authority_mutation();
""",
    r"""
ALTER TABLE public.payout_calculations ENABLE ALWAYS TRIGGER trg_payout_calculations_no_truncate;
""",
    r"""
CREATE TRIGGER trg_report_artifacts_deletion_fence BEFORE INSERT OR UPDATE OF stored_file_id ON public.report_artifacts FOR EACH ROW EXECUTE FUNCTION public.reject_reference_to_deleting_stored_object();
""",
    r"""
CREATE TRIGGER trg_retargeting_source_events_append_only BEFORE DELETE OR UPDATE ON public.retargeting_source_events FOR EACH ROW EXECUTE FUNCTION public.prevent_retargeting_source_event_mutation();
""",
    r"""
CREATE TRIGGER trg_retargeting_source_link_events_append_only BEFORE DELETE OR UPDATE ON public.retargeting_source_link_events FOR EACH ROW EXECUTE FUNCTION public.prevent_retargeting_source_link_event_mutation();
""",
    r"""
CREATE TRIGGER trg_stored_object_deletion_receipt_guard BEFORE DELETE OR UPDATE ON public.stored_object_deletions FOR EACH ROW EXECUTE FUNCTION public.guard_stored_object_deletion_receipt();
""",
    r"""
CREATE TRIGGER trg_traffic_density_profile_revision_immutable BEFORE DELETE OR UPDATE ON public.traffic_density_profiles FOR EACH ROW EXECUTE FUNCTION public.reject_traffic_density_profile_revision_mutation();
""",
    r"""
CREATE TRIGGER trg_traffic_density_profile_revision_validate BEFORE INSERT ON public.traffic_density_profiles FOR EACH ROW EXECUTE FUNCTION public.validate_traffic_density_profile_revision();
""",
    r"""
CREATE TRIGGER trg_trip_evidence_adjudication_immutable BEFORE UPDATE ON public.trip_sessions FOR EACH ROW EXECUTE FUNCTION public.reject_trip_evidence_adjudication_mutation();
""",
    r"""
CREATE TRIGGER trg_vehicle_evidence_documents_deletion_fence BEFORE INSERT OR UPDATE OF stored_file_id ON public.vehicle_evidence_documents FOR EACH ROW EXECUTE FUNCTION public.reject_reference_to_deleting_stored_object();
""",
    r"""
CREATE TRIGGER trip_batch_receipt_guard BEFORE DELETE OR UPDATE ON public.location_ping_batches FOR EACH ROW EXECUTE FUNCTION public.guard_trip_batch_receipt();
""",
    r"""
CREATE TRIGGER trip_evidence_manifest_entries_immutable BEFORE INSERT OR DELETE OR UPDATE ON public.trip_evidence_manifest_entries FOR EACH ROW EXECUTE FUNCTION public.reject_trip_manifest_entry_mutation();
""",
    r"""
CREATE TRIGGER trip_evidence_manifest_guard BEFORE UPDATE ON public.trip_sessions FOR EACH ROW EXECUTE FUNCTION public.guard_trip_evidence_manifest();
""",
    r"""
CREATE TRIGGER vehicle_evidence_documents_immutable BEFORE UPDATE ON public.vehicle_evidence_documents FOR EACH ROW EXECUTE FUNCTION public.reject_vehicle_evidence_document_update();
""",
    r"""
CREATE TRIGGER vehicle_evidence_snapshots_immutable BEFORE UPDATE ON public.vehicle_evidence_submissions FOR EACH ROW EXECUTE FUNCTION public.reject_vehicle_evidence_snapshot_mutation();
""",
    r"""
CREATE TRIGGER vehicle_review_decisions_immutable BEFORE DELETE OR UPDATE ON public.vehicle_evidence_review_decisions FOR EACH ROW EXECUTE FUNCTION public.reject_vehicle_review_decision_mutation();
""",
    r"""
ALTER TABLE ONLY public.advertiser_organization_notification_preferences
    ADD CONSTRAINT advertiser_organization_notific_advertiser_organization_id_fkey FOREIGN KEY (advertiser_organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.assignment_activity_flag_events
    ADD CONSTRAINT assignment_activity_flag_events_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.campaign_assignments(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.assignment_activity_flag_events
    ADD CONSTRAINT assignment_activity_flag_events_flag_id_fkey FOREIGN KEY (flag_id) REFERENCES public.assignment_activity_flags(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.assignment_activity_flags
    ADD CONSTRAINT assignment_activity_flags_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.campaign_assignments(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.assignment_activity_flags
    ADD CONSTRAINT assignment_activity_flags_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.assignment_activity_flags
    ADD CONSTRAINT assignment_activity_flags_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.assignment_activity_flags
    ADD CONSTRAINT assignment_activity_flags_vehicle_id_fkey FOREIGN KEY (vehicle_id) REFERENCES public.vehicles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.assignment_rule_bindings
    ADD CONSTRAINT assignment_rule_bindings_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.campaign_assignments(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.assignment_rule_bindings
    ADD CONSTRAINT assignment_rule_bindings_revision_id_fkey FOREIGN KEY (revision_id) REFERENCES public.campaign_payout_rule_revisions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.audience_deliveries
    ADD CONSTRAINT audience_deliveries_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.audience_deliveries
    ADD CONSTRAINT audience_deliveries_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.audience_deliveries
    ADD CONSTRAINT audience_deliveries_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.audience_deliveries
    ADD CONSTRAINT audience_deliveries_segment_id_fkey FOREIGN KEY (segment_id) REFERENCES public.exposure_segments(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.audience_delivery_approvals
    ADD CONSTRAINT audience_delivery_approvals_approved_by_user_id_fkey FOREIGN KEY (approved_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.audience_delivery_approvals
    ADD CONSTRAINT audience_delivery_approvals_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.audience_delivery_approvals
    ADD CONSTRAINT audience_delivery_approvals_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.audience_delivery_approvals
    ADD CONSTRAINT audience_delivery_approvals_segment_id_fkey FOREIGN KEY (segment_id) REFERENCES public.exposure_segments(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.audit_event_subject_resolutions
    ADD CONSTRAINT audit_event_subject_resolutions_audit_event_id_fkey FOREIGN KEY (audit_event_id) REFERENCES public.audit_events(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT audit_events_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE SET NULL;
""",
    r"""
ALTER TABLE ONLY public.budget_campaign_transitions
    ADD CONSTRAINT budget_campaign_transitions_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.budget_campaign_transitions
    ADD CONSTRAINT budget_campaign_transitions_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.budget_campaign_transitions
    ADD CONSTRAINT budget_campaign_transitions_evaluation_id_fkey FOREIGN KEY (evaluation_id) REFERENCES public.budget_policy_evaluations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.budget_policy_evaluations
    ADD CONSTRAINT budget_policy_evaluations_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_activation_events
    ADD CONSTRAINT campaign_activation_events_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id);
""",
    r"""
ALTER TABLE ONLY public.campaign_activation_events
    ADD CONSTRAINT campaign_activation_events_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.campaign_assignments(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.campaign_assignments
    ADD CONSTRAINT campaign_assignments_assigned_by_user_id_fkey FOREIGN KEY (assigned_by_user_id) REFERENCES public.users(id);
""",
    r"""
ALTER TABLE ONLY public.campaign_assignments
    ADD CONSTRAINT campaign_assignments_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.campaign_assignments
    ADD CONSTRAINT campaign_assignments_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.campaign_assignments
    ADD CONSTRAINT campaign_assignments_vehicle_id_fkey FOREIGN KEY (vehicle_id) REFERENCES public.vehicles(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.campaign_cancellation_settlement_revisions
    ADD CONSTRAINT campaign_cancellation_settlement_revisions_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_cancellation_settlement_revisions
    ADD CONSTRAINT campaign_cancellation_settlement_revisions_cancellation_id_fkey FOREIGN KEY (cancellation_id) REFERENCES public.campaign_cancellations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_cancellations
    ADD CONSTRAINT campaign_cancellations_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_cancellations
    ADD CONSTRAINT campaign_cancellations_commercial_terms_id_fkey FOREIGN KEY (commercial_terms_id) REFERENCES public.commercial_terms(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_cancellations
    ADD CONSTRAINT campaign_cancellations_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_cancellations
    ADD CONSTRAINT campaign_cancellations_production_start_id_fkey FOREIGN KEY (production_start_id) REFERENCES public.production_starts(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_cancellations
    ADD CONSTRAINT campaign_cancellations_requested_by_user_id_fkey FOREIGN KEY (requested_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_change_requests
    ADD CONSTRAINT campaign_change_requests_authorization_id_fkey FOREIGN KEY (authorization_id) REFERENCES public.campaign_financial_authorizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_change_requests
    ADD CONSTRAINT campaign_change_requests_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_change_requests
    ADD CONSTRAINT campaign_change_requests_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_change_requests
    ADD CONSTRAINT campaign_change_requests_requested_by_user_id_fkey FOREIGN KEY (requested_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_change_requests
    ADD CONSTRAINT campaign_change_requests_reviewed_by_user_id_fkey FOREIGN KEY (reviewed_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_change_revisions
    ADD CONSTRAINT campaign_change_revisions_applied_by_user_id_fkey FOREIGN KEY (applied_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_change_revisions
    ADD CONSTRAINT campaign_change_revisions_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_change_revisions
    ADD CONSTRAINT campaign_change_revisions_request_id_fkey FOREIGN KEY (request_id) REFERENCES public.campaign_change_requests(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_creatives
    ADD CONSTRAINT campaign_creatives_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.campaign_financial_authorizations
    ADD CONSTRAINT campaign_financial_authorizatio_credit_approved_by_user_id_fkey FOREIGN KEY (credit_approved_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_financial_authorizations
    ADD CONSTRAINT campaign_financial_authorizations_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_financial_authorizations
    ADD CONSTRAINT campaign_financial_authorizations_commercial_terms_id_fkey FOREIGN KEY (commercial_terms_id) REFERENCES public.commercial_terms(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_financial_authorizations
    ADD CONSTRAINT campaign_financial_authorizations_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_liability_reservations
    ADD CONSTRAINT campaign_liability_reservations_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.campaign_assignments(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_liability_reservations
    ADD CONSTRAINT campaign_liability_reservations_assignment_rule_binding_id_fkey FOREIGN KEY (assignment_rule_binding_id) REFERENCES public.assignment_rule_bindings(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_liability_reservations
    ADD CONSTRAINT campaign_liability_reservations_authorization_id_fkey FOREIGN KEY (authorization_id) REFERENCES public.campaign_financial_authorizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_liability_reservations
    ADD CONSTRAINT campaign_liability_reservations_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_payout_rule_revisions
    ADD CONSTRAINT campaign_payout_rule_revisions_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_payout_rule_revisions
    ADD CONSTRAINT campaign_payout_rule_revisions_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);
""",
    r"""
ALTER TABLE ONLY public.campaign_payout_rule_revisions
    ADD CONSTRAINT campaign_payout_rule_revisions_payout_rule_id_fkey FOREIGN KEY (payout_rule_id) REFERENCES public.campaign_payout_rules(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_payout_rules
    ADD CONSTRAINT campaign_payout_rules_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.campaign_payout_rules
    ADD CONSTRAINT campaign_payout_rules_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);
""",
    r"""
ALTER TABLE ONLY public.campaign_payout_rules
    ADD CONSTRAINT campaign_payout_rules_updated_by_user_id_fkey FOREIGN KEY (updated_by_user_id) REFERENCES public.users(id);
""",
    r"""
ALTER TABLE ONLY public.campaign_review_events
    ADD CONSTRAINT campaign_review_events_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_review_events
    ADD CONSTRAINT campaign_review_events_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_review_events
    ADD CONSTRAINT campaign_review_events_submission_event_id_fkey FOREIGN KEY (submission_event_id) REFERENCES public.campaign_review_events(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_zones
    ADD CONSTRAINT campaign_zones_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.campaign_zones
    ADD CONSTRAINT campaign_zones_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);
""",
    r"""
ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT campaigns_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);
""",
    r"""
ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT campaigns_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.commercial_quotation_revisions
    ADD CONSTRAINT commercial_quotation_revisions_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.commercial_quotation_revisions
    ADD CONSTRAINT commercial_quotation_revisions_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.commercial_quotation_revisions
    ADD CONSTRAINT commercial_quotation_revisions_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.commercial_quotation_revisions
    ADD CONSTRAINT commercial_quotation_revisions_quote_request_id_fkey FOREIGN KEY (quote_request_id) REFERENCES public.commercial_quote_requests(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.commercial_quote_requests
    ADD CONSTRAINT commercial_quote_requests_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.commercial_quote_requests
    ADD CONSTRAINT commercial_quote_requests_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.commercial_quote_requests
    ADD CONSTRAINT commercial_quote_requests_requested_by_user_id_fkey FOREIGN KEY (requested_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.commercial_terms
    ADD CONSTRAINT commercial_terms_accepted_by_user_id_fkey FOREIGN KEY (accepted_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.commercial_terms
    ADD CONSTRAINT commercial_terms_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.commercial_terms
    ADD CONSTRAINT commercial_terms_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.commercial_terms
    ADD CONSTRAINT commercial_terms_quotation_revision_id_fkey FOREIGN KEY (quotation_revision_id) REFERENCES public.commercial_quotation_revisions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.commercial_terms
    ADD CONSTRAINT commercial_terms_recorded_by_user_id_fkey FOREIGN KEY (recorded_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.complaint_messages
    ADD CONSTRAINT complaint_messages_author_user_id_fkey FOREIGN KEY (author_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.complaint_messages
    ADD CONSTRAINT complaint_messages_complaint_id_fkey FOREIGN KEY (complaint_id) REFERENCES public.complaints(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.complaints
    ADD CONSTRAINT complaints_advertiser_organization_id_fkey FOREIGN KEY (advertiser_organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.complaints
    ADD CONSTRAINT complaints_assigned_to_user_id_fkey FOREIGN KEY (assigned_to_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.complaints
    ADD CONSTRAINT complaints_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.complaints
    ADD CONSTRAINT complaints_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.complaints
    ADD CONSTRAINT complaints_earnings_ledger_entry_id_fkey FOREIGN KEY (earnings_ledger_entry_id) REFERENCES public.earnings_ledger_entries(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.complaints
    ADD CONSTRAINT complaints_raised_by_user_id_fkey FOREIGN KEY (raised_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.complaints
    ADD CONSTRAINT complaints_resolved_by_user_id_fkey FOREIGN KEY (resolved_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.complaints
    ADD CONSTRAINT complaints_trip_session_id_fkey FOREIGN KEY (trip_session_id) REFERENCES public.trip_sessions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.data_subject_location_assessments
    ADD CONSTRAINT data_subject_location_assessments_assessed_by_user_id_fkey FOREIGN KEY (assessed_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.data_subject_location_assessments
    ADD CONSTRAINT data_subject_location_assessments_request_id_fkey FOREIGN KEY (request_id) REFERENCES public.data_subject_requests(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.data_subject_requests
    ADD CONSTRAINT data_subject_requests_completed_by_user_id_fkey FOREIGN KEY (completed_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.data_subject_requests
    ADD CONSTRAINT data_subject_requests_identity_verified_by_user_id_fkey FOREIGN KEY (identity_verified_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.data_subject_requests
    ADD CONSTRAINT data_subject_requests_opened_by_user_id_fkey FOREIGN KEY (opened_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.data_subject_requests
    ADD CONSTRAINT data_subject_requests_subject_user_id_fkey FOREIGN KEY (subject_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.display_proof_challenges
    ADD CONSTRAINT display_proof_challenges_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.campaign_assignments(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.display_proof_challenges
    ADD CONSTRAINT display_proof_challenges_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.display_proof_challenges
    ADD CONSTRAINT display_proof_challenges_evidence_submission_id_fkey FOREIGN KEY (evidence_submission_id) REFERENCES public.installation_evidence_submissions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.display_proof_challenges
    ADD CONSTRAINT display_proof_challenges_vehicle_id_fkey FOREIGN KEY (vehicle_id) REFERENCES public.vehicles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.display_proofs
    ADD CONSTRAINT display_proofs_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.campaign_assignments(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.display_proofs
    ADD CONSTRAINT display_proofs_challenge_id_fkey FOREIGN KEY (challenge_id) REFERENCES public.display_proof_challenges(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.display_proofs
    ADD CONSTRAINT display_proofs_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.display_proofs
    ADD CONSTRAINT display_proofs_evidence_submission_id_fkey FOREIGN KEY (evidence_submission_id) REFERENCES public.installation_evidence_submissions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.display_proofs
    ADD CONSTRAINT display_proofs_stored_file_id_fkey FOREIGN KEY (stored_file_id) REFERENCES public.stored_files(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.display_proofs
    ADD CONSTRAINT display_proofs_vehicle_id_fkey FOREIGN KEY (vehicle_id) REFERENCES public.vehicles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.driver_account_setup_tokens
    ADD CONSTRAINT driver_account_setup_tokens_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.driver_applications(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.driver_account_setup_tokens
    ADD CONSTRAINT driver_account_setup_tokens_issued_by_user_id_fkey FOREIGN KEY (issued_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.driver_account_setup_tokens
    ADD CONSTRAINT driver_account_setup_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.driver_application_access_tokens
    ADD CONSTRAINT driver_application_access_tokens_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.driver_applications(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.driver_currency_debt_accounts
    ADD CONSTRAINT driver_currency_debt_accounts_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.driver_currency_debt_accounts
    ADD CONSTRAINT driver_currency_debt_accounts_driver_user_id_fkey FOREIGN KEY (driver_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.driver_kyc_review_decisions
    ADD CONSTRAINT driver_kyc_review_decisions_decided_by_user_id_fkey FOREIGN KEY (decided_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.driver_kyc_review_decisions
    ADD CONSTRAINT driver_kyc_review_decisions_submission_id_fkey FOREIGN KEY (submission_id) REFERENCES public.driver_kyc_submissions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.driver_phone_versions
    ADD CONSTRAINT driver_phone_versions_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.driver_phone_versions
    ADD CONSTRAINT driver_phone_versions_recorded_by_user_id_fkey FOREIGN KEY (recorded_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.driver_profiles
    ADD CONSTRAINT driver_profiles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.earnings_ledger_entries
    ADD CONSTRAINT earnings_ledger_entries_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.earnings_ledger_entries
    ADD CONSTRAINT earnings_ledger_entries_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.earnings_ledger_entries
    ADD CONSTRAINT earnings_ledger_entries_driver_user_id_fkey FOREIGN KEY (driver_user_id) REFERENCES public.users(id);
""",
    r"""
ALTER TABLE ONLY public.earnings_ledger_entries
    ADD CONSTRAINT earnings_ledger_entries_payout_calculation_id_fkey FOREIGN KEY (payout_calculation_id) REFERENCES public.payout_calculations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.earnings_ledger_entries
    ADD CONSTRAINT earnings_ledger_entries_source_fraud_flag_id_fkey FOREIGN KEY (source_fraud_flag_id) REFERENCES public.fraud_flags(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.earnings_ledger_entries
    ADD CONSTRAINT earnings_ledger_entries_trip_session_id_fkey FOREIGN KEY (trip_session_id) REFERENCES public.trip_sessions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.earnings_ledger_entries
    ADD CONSTRAINT earnings_ledger_entries_vehicle_id_fkey FOREIGN KEY (vehicle_id) REFERENCES public.vehicles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.evidence_verifications
    ADD CONSTRAINT evidence_verifications_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.campaign_assignments(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.evidence_verifications
    ADD CONSTRAINT evidence_verifications_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.evidence_verifications
    ADD CONSTRAINT evidence_verifications_display_proof_id_fkey FOREIGN KEY (display_proof_id) REFERENCES public.display_proofs(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.evidence_verifications
    ADD CONSTRAINT evidence_verifications_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.evidence_verifications
    ADD CONSTRAINT evidence_verifications_fraud_flag_id_fkey FOREIGN KEY (fraud_flag_id) REFERENCES public.fraud_flags(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.evidence_verifications
    ADD CONSTRAINT evidence_verifications_issued_by_user_id_fkey FOREIGN KEY (issued_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.evidence_verifications
    ADD CONSTRAINT evidence_verifications_resolved_by_user_id_fkey FOREIGN KEY (resolved_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.evidence_verifications
    ADD CONSTRAINT evidence_verifications_source_trip_session_id_fkey FOREIGN KEY (source_trip_session_id) REFERENCES public.trip_sessions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.evidence_verifications
    ADD CONSTRAINT evidence_verifications_vehicle_id_fkey FOREIGN KEY (vehicle_id) REFERENCES public.vehicles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.expedited_production_waivers
    ADD CONSTRAINT expedited_production_waivers_accepted_by_user_id_fkey FOREIGN KEY (accepted_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.expedited_production_waivers
    ADD CONSTRAINT expedited_production_waivers_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.expedited_production_waivers
    ADD CONSTRAINT expedited_production_waivers_commercial_terms_id_fkey FOREIGN KEY (commercial_terms_id) REFERENCES public.commercial_terms(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.expedited_production_waivers
    ADD CONSTRAINT expedited_production_waivers_requested_by_user_id_fkey FOREIGN KEY (requested_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.exposure_scores
    ADD CONSTRAINT exposure_scores_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.exposure_scores
    ADD CONSTRAINT exposure_scores_issued_by_user_id_fkey FOREIGN KEY (issued_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.exposure_scores
    ADD CONSTRAINT exposure_scores_measurement_run_id_fkey FOREIGN KEY (measurement_run_id) REFERENCES public.measurement_runs(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.exposure_scores
    ADD CONSTRAINT exposure_scores_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.exposure_scores
    ADD CONSTRAINT exposure_scores_reissue_of_score_id_fkey FOREIGN KEY (reissue_of_score_id) REFERENCES public.exposure_scores(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.exposure_segment_cells
    ADD CONSTRAINT exposure_segment_cells_segment_id_fkey FOREIGN KEY (segment_id) REFERENCES public.exposure_segments(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.exposure_segments
    ADD CONSTRAINT exposure_segments_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.exposure_segments
    ADD CONSTRAINT exposure_segments_measurement_run_id_fkey FOREIGN KEY (measurement_run_id) REFERENCES public.measurement_runs(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.exposure_segments
    ADD CONSTRAINT exposure_segments_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.exposure_segments
    ADD CONSTRAINT exposure_segments_reissue_of_segment_id_fkey FOREIGN KEY (reissue_of_segment_id) REFERENCES public.exposure_segments(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.exposure_segments
    ADD CONSTRAINT exposure_segments_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.retargeting_sources(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.exposure_segments
    ADD CONSTRAINT exposure_segments_source_link_id_fkey FOREIGN KEY (source_link_id) REFERENCES public.retargeting_source_links(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.exposure_segments
    ADD CONSTRAINT exposure_segments_zone_id_fkey FOREIGN KEY (zone_id) REFERENCES public.campaign_zones(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.financial_authorization_allocations
    ADD CONSTRAINT financial_authorization_allocations_authorization_id_fkey FOREIGN KEY (authorization_id) REFERENCES public.campaign_financial_authorizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.financial_authorization_allocations
    ADD CONSTRAINT financial_authorization_allocations_receipt_allocation_id_fkey FOREIGN KEY (receipt_allocation_id) REFERENCES public.receipt_allocations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.audience_deliveries
    ADD CONSTRAINT fk_audience_deliveries_approval_id FOREIGN KEY (approval_id) REFERENCES public.audience_delivery_approvals(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_creatives
    ADD CONSTRAINT fk_campaign_creatives_stored_file FOREIGN KEY (stored_file_id) REFERENCES public.stored_files(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.campaign_liability_reservations
    ADD CONSTRAINT fk_campaign_liability_reservations_release_cancellation_id FOREIGN KEY (release_cancellation_id) REFERENCES public.campaign_cancellations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.creative_review_events
    ADD CONSTRAINT fk_creative_review_events_actor FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.creative_review_events
    ADD CONSTRAINT fk_creative_review_events_creative FOREIGN KEY (creative_id) REFERENCES public.campaign_creatives(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.creative_review_events
    ADD CONSTRAINT fk_creative_review_events_submission FOREIGN KEY (submission_event_id) REFERENCES public.creative_review_events(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.driver_applications
    ADD CONSTRAINT fk_driver_applications_driver_profile FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.driver_applications
    ADD CONSTRAINT fk_driver_applications_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.driver_kyc_documents
    ADD CONSTRAINT fk_driver_kyc_documents_file FOREIGN KEY (stored_file_id) REFERENCES public.stored_files(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.driver_kyc_documents
    ADD CONSTRAINT fk_driver_kyc_documents_submission FOREIGN KEY (submission_id) REFERENCES public.driver_kyc_submissions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.driver_kyc_submissions
    ADD CONSTRAINT fk_driver_kyc_submissions_bank_version FOREIGN KEY (bank_account_version_id) REFERENCES public.payee_bank_account_versions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.driver_kyc_submissions
    ADD CONSTRAINT fk_driver_kyc_submissions_creator FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.driver_kyc_submissions
    ADD CONSTRAINT fk_driver_kyc_submissions_profile FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.file_upload_intents
    ADD CONSTRAINT fk_file_upload_intents_organization FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.file_upload_intents
    ADD CONSTRAINT fk_file_upload_intents_subject_user FOREIGN KEY (subject_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.file_upload_intents
    ADD CONSTRAINT fk_file_upload_intents_uploader FOREIGN KEY (uploader_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.fraud_flags
    ADD CONSTRAINT fk_fraud_flags_reviewed_by_user_id_users FOREIGN KEY (reviewed_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_batch_lines
    ADD CONSTRAINT fk_payout_batch_lines_predecessor_line_id_payout_batch_lines FOREIGN KEY (predecessor_line_id) REFERENCES public.payout_batch_lines(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_batches
    ADD CONSTRAINT fk_payout_batches_automatic_run_id FOREIGN KEY (automatic_run_id) REFERENCES public.payout_automatic_runs(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_debt_obligations
    ADD CONSTRAINT fk_payout_debt_obligations_recovery_incident FOREIGN KEY (recovery_incident_id) REFERENCES public.payout_recovery_incidents(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_submission_observations
    ADD CONSTRAINT fk_payout_submission_observations_attempt_binding FOREIGN KEY (attempt_id, intent_id, generation, idempotency_key, instruction_fingerprint) REFERENCES public.payout_submission_attempts(id, intent_id, generation, idempotency_key, instruction_fingerprint) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.receipt_allocations
    ADD CONSTRAINT fk_receipt_allocations_provider_event_id FOREIGN KEY (provider_event_id) REFERENCES public.payment_gateway_events(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.receipt_reconciliations
    ADD CONSTRAINT fk_receipt_reconciliations_provider_event_id FOREIGN KEY (provider_event_id) REFERENCES public.payment_gateway_events(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.refund_settlements
    ADD CONSTRAINT fk_refund_settlements_cancellation_id FOREIGN KEY (cancellation_id) REFERENCES public.campaign_cancellations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.stored_files
    ADD CONSTRAINT fk_stored_files_organization FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.stored_files
    ADD CONSTRAINT fk_stored_files_subject_user FOREIGN KEY (subject_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.stored_files
    ADD CONSTRAINT fk_stored_files_upload_intent FOREIGN KEY (upload_intent_id) REFERENCES public.file_upload_intents(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.stored_files
    ADD CONSTRAINT fk_stored_files_uploader FOREIGN KEY (uploader_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.traffic_density_profiles
    ADD CONSTRAINT fk_traffic_density_profiles_supersedes_id FOREIGN KEY (supersedes_id) REFERENCES public.traffic_density_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.trip_sessions
    ADD CONSTRAINT fk_trip_sessions_display_proof FOREIGN KEY (display_proof_id) REFERENCES public.display_proofs(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.vehicle_evidence_documents
    ADD CONSTRAINT fk_vehicle_evidence_documents_file FOREIGN KEY (stored_file_id) REFERENCES public.stored_files(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.vehicle_evidence_documents
    ADD CONSTRAINT fk_vehicle_evidence_documents_submission FOREIGN KEY (submission_id) REFERENCES public.vehicle_evidence_submissions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.vehicle_evidence_submissions
    ADD CONSTRAINT fk_vehicle_evidence_submissions_creator FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.vehicle_evidence_submissions
    ADD CONSTRAINT fk_vehicle_evidence_submissions_vehicle FOREIGN KEY (vehicle_id) REFERENCES public.vehicles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.fraud_assessments
    ADD CONSTRAINT fraud_assessments_trip_analytics_id_fkey FOREIGN KEY (trip_analytics_id) REFERENCES public.trip_analytics(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.fraud_assessments
    ADD CONSTRAINT fraud_assessments_trip_session_id_fkey FOREIGN KEY (trip_session_id) REFERENCES public.trip_sessions(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.fraud_disputes
    ADD CONSTRAINT fraud_disputes_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.fraud_disputes
    ADD CONSTRAINT fraud_disputes_fraud_flag_id_fkey FOREIGN KEY (fraud_flag_id) REFERENCES public.fraud_flags(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.fraud_disputes
    ADD CONSTRAINT fraud_disputes_replied_by_user_id_fkey FOREIGN KEY (replied_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.fraud_disputes
    ADD CONSTRAINT fraud_disputes_submitted_by_user_id_fkey FOREIGN KEY (submitted_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.fraud_flags
    ADD CONSTRAINT fraud_flags_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.campaign_assignments(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.fraud_flags
    ADD CONSTRAINT fraud_flags_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.fraud_flags
    ADD CONSTRAINT fraud_flags_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.fraud_flags
    ADD CONSTRAINT fraud_flags_trip_analytics_id_fkey FOREIGN KEY (trip_analytics_id) REFERENCES public.trip_analytics(id) ON DELETE SET NULL;
""",
    r"""
ALTER TABLE ONLY public.fraud_flags
    ADD CONSTRAINT fraud_flags_trip_session_id_fkey FOREIGN KEY (trip_session_id) REFERENCES public.trip_sessions(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.fraud_flags
    ADD CONSTRAINT fraud_flags_vehicle_id_fkey FOREIGN KEY (vehicle_id) REFERENCES public.vehicles(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.impression_estimates
    ADD CONSTRAINT impression_estimates_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.campaign_assignments(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.impression_estimates
    ADD CONSTRAINT impression_estimates_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.impression_estimates
    ADD CONSTRAINT impression_estimates_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.impression_estimates
    ADD CONSTRAINT impression_estimates_traffic_density_profile_id_fkey FOREIGN KEY (traffic_density_profile_id) REFERENCES public.traffic_density_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.impression_estimates
    ADD CONSTRAINT impression_estimates_trip_analytics_id_fkey FOREIGN KEY (trip_analytics_id) REFERENCES public.trip_analytics(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.impression_estimates
    ADD CONSTRAINT impression_estimates_trip_session_id_fkey FOREIGN KEY (trip_session_id) REFERENCES public.trip_sessions(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.impression_estimates
    ADD CONSTRAINT impression_estimates_vehicle_id_fkey FOREIGN KEY (vehicle_id) REFERENCES public.vehicles(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.installation_evidence_photos
    ADD CONSTRAINT installation_evidence_photos_stored_file_id_fkey FOREIGN KEY (stored_file_id) REFERENCES public.stored_files(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.installation_evidence_photos
    ADD CONSTRAINT installation_evidence_photos_submission_id_fkey FOREIGN KEY (submission_id) REFERENCES public.installation_evidence_submissions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.installation_evidence_submissions
    ADD CONSTRAINT installation_evidence_submissions_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.campaign_assignments(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.installation_evidence_submissions
    ADD CONSTRAINT installation_evidence_submissions_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.installation_evidence_submissions
    ADD CONSTRAINT installation_evidence_submissions_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.installation_evidence_submissions
    ADD CONSTRAINT installation_evidence_submissions_reviewed_by_user_id_fkey FOREIGN KEY (reviewed_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.installation_evidence_submissions
    ADD CONSTRAINT installation_evidence_submissions_submitted_by_user_id_fkey FOREIGN KEY (submitted_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.installation_evidence_submissions
    ADD CONSTRAINT installation_evidence_submissions_vehicle_id_fkey FOREIGN KEY (vehicle_id) REFERENCES public.vehicles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.invoice_corrections
    ADD CONSTRAINT invoice_corrections_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.invoice_corrections
    ADD CONSTRAINT invoice_corrections_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.invoices(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.invoice_issuer_profiles
    ADD CONSTRAINT invoice_issuer_profiles_recorded_by_user_id_fkey FOREIGN KEY (recorded_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_commercial_terms_id_fkey FOREIGN KEY (commercial_terms_id) REFERENCES public.commercial_terms(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_issued_by_user_id_fkey FOREIGN KEY (issued_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_issuer_profile_id_fkey FOREIGN KEY (issuer_profile_id) REFERENCES public.invoice_issuer_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.location_ping_batches
    ADD CONSTRAINT location_ping_batches_trip_session_id_fkey FOREIGN KEY (trip_session_id) REFERENCES public.trip_sessions(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE public.location_pings
    ADD CONSTRAINT location_pings_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES public.location_ping_batches(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE public.location_pings
    ADD CONSTRAINT location_pings_trip_session_id_fkey FOREIGN KEY (trip_session_id) REFERENCES public.trip_sessions(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.manual_driver_contact_tasks
    ADD CONSTRAINT manual_driver_contact_tasks_completed_by_user_id_fkey FOREIGN KEY (completed_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.manual_driver_contact_tasks
    ADD CONSTRAINT manual_driver_contact_tasks_consent_id_fkey FOREIGN KEY (consent_id) REFERENCES public.whatsapp_consents(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.manual_driver_contact_tasks
    ADD CONSTRAINT manual_driver_contact_tasks_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.manual_driver_contact_tasks
    ADD CONSTRAINT manual_driver_contact_tasks_phone_version_id_fkey FOREIGN KEY (phone_version_id) REFERENCES public.driver_phone_versions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.measurement_run_proof_bindings
    ADD CONSTRAINT measurement_run_proof_binding_installation_evidence_submis_fkey FOREIGN KEY (installation_evidence_submission_id) REFERENCES public.installation_evidence_submissions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.measurement_run_proof_bindings
    ADD CONSTRAINT measurement_run_proof_bindings_activation_event_id_fkey FOREIGN KEY (activation_event_id) REFERENCES public.campaign_activation_events(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.measurement_run_proof_bindings
    ADD CONSTRAINT measurement_run_proof_bindings_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.campaign_assignments(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.measurement_run_proof_bindings
    ADD CONSTRAINT measurement_run_proof_bindings_creative_id_fkey FOREIGN KEY (creative_id) REFERENCES public.campaign_creatives(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.measurement_run_proof_bindings
    ADD CONSTRAINT measurement_run_proof_bindings_measurement_run_id_fkey FOREIGN KEY (measurement_run_id) REFERENCES public.measurement_runs(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.measurement_runs
    ADD CONSTRAINT measurement_runs_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.measurement_runs
    ADD CONSTRAINT measurement_runs_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.measurement_runs
    ADD CONSTRAINT measurement_runs_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.measurement_runs
    ADD CONSTRAINT measurement_runs_reissue_of_run_id_fkey FOREIGN KEY (reissue_of_run_id) REFERENCES public.measurement_runs(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.notification_delivery_receipts
    ADD CONSTRAINT notification_delivery_receipts_notification_id_fkey FOREIGN KEY (notification_id) REFERENCES public.notifications(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_recipient_user_id_fkey FOREIGN KEY (recipient_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.organization_memberships
    ADD CONSTRAINT organization_memberships_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.organization_memberships
    ADD CONSTRAINT organization_memberships_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.password_reset_attempts
    ADD CONSTRAINT password_reset_attempts_issued_user_id_fkey FOREIGN KEY (issued_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_attempt_id_fkey FOREIGN KEY (attempt_id) REFERENCES public.password_reset_attempts(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payee_bank_account_payout_verifications
    ADD CONSTRAINT payee_bank_account_payout_verifica_bank_account_version_id_fkey FOREIGN KEY (bank_account_version_id) REFERENCES public.payee_bank_account_versions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payee_bank_account_payout_verifications
    ADD CONSTRAINT payee_bank_account_payout_verification_verified_by_user_id_fkey FOREIGN KEY (verified_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payee_bank_account_versions
    ADD CONSTRAINT payee_bank_account_versions_bank_account_id_fkey FOREIGN KEY (bank_account_id) REFERENCES public.payee_bank_accounts(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payee_bank_account_versions
    ADD CONSTRAINT payee_bank_account_versions_payee_version_id_fkey FOREIGN KEY (payee_version_id) REFERENCES public.payee_versions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payee_bank_account_versions
    ADD CONSTRAINT payee_bank_account_versions_verified_by_user_id_fkey FOREIGN KEY (verified_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payee_bank_accounts
    ADD CONSTRAINT payee_bank_accounts_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payee_bank_accounts
    ADD CONSTRAINT payee_bank_accounts_payee_id_fkey FOREIGN KEY (payee_id) REFERENCES public.payees(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payee_versions
    ADD CONSTRAINT payee_versions_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payee_versions
    ADD CONSTRAINT payee_versions_payee_id_fkey FOREIGN KEY (payee_id) REFERENCES public.payees(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payees
    ADD CONSTRAINT payees_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payees
    ADD CONSTRAINT payees_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payment_checkout_intents
    ADD CONSTRAINT payment_checkout_intents_commercial_terms_id_fkey FOREIGN KEY (commercial_terms_id) REFERENCES public.commercial_terms(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payment_checkout_intents
    ADD CONSTRAINT payment_checkout_intents_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.invoices(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payment_checkout_intents
    ADD CONSTRAINT payment_checkout_intents_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payment_checkout_intents
    ADD CONSTRAINT payment_checkout_intents_requested_by_user_id_fkey FOREIGN KEY (requested_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payment_gateway_processing_attempts
    ADD CONSTRAINT payment_gateway_processing_attempts_allocation_id_fkey FOREIGN KEY (allocation_id) REFERENCES public.receipt_allocations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payment_gateway_processing_attempts
    ADD CONSTRAINT payment_gateway_processing_attempts_gateway_event_id_fkey FOREIGN KEY (gateway_event_id) REFERENCES public.payment_gateway_events(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payment_gateway_processing_attempts
    ADD CONSTRAINT payment_gateway_processing_attempts_receipt_id_fkey FOREIGN KEY (receipt_id) REFERENCES public.payment_receipts(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payment_receipts
    ADD CONSTRAINT payment_receipts_observed_by_user_id_fkey FOREIGN KEY (observed_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payment_receipts
    ADD CONSTRAINT payment_receipts_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_automatic_alerts
    ADD CONSTRAINT payout_automatic_alerts_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES public.payout_batches(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_automatic_alerts
    ADD CONSTRAINT payout_automatic_alerts_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_automatic_alerts
    ADD CONSTRAINT payout_automatic_alerts_ledger_entry_id_fkey FOREIGN KEY (ledger_entry_id) REFERENCES public.earnings_ledger_entries(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_automatic_alerts
    ADD CONSTRAINT payout_automatic_alerts_line_id_fkey FOREIGN KEY (line_id) REFERENCES public.payout_batch_lines(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_automatic_alerts
    ADD CONSTRAINT payout_automatic_alerts_resolved_by_user_id_fkey FOREIGN KEY (resolved_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_automatic_alerts
    ADD CONSTRAINT payout_automatic_alerts_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.payout_automatic_runs(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_automatic_controls
    ADD CONSTRAINT payout_automatic_controls_changed_by_user_id_fkey FOREIGN KEY (changed_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_batch_lines
    ADD CONSTRAINT payout_batch_lines_bank_account_version_id_fkey FOREIGN KEY (bank_account_version_id) REFERENCES public.payee_bank_account_versions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_batch_lines
    ADD CONSTRAINT payout_batch_lines_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES public.payout_batches(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_batch_lines
    ADD CONSTRAINT payout_batch_lines_ledger_entry_id_fkey FOREIGN KEY (ledger_entry_id) REFERENCES public.earnings_ledger_entries(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_batch_lines
    ADD CONSTRAINT payout_batch_lines_payee_version_id_fkey FOREIGN KEY (payee_version_id) REFERENCES public.payee_versions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_batch_lines
    ADD CONSTRAINT payout_batch_lines_reconciled_by_user_id_fkey FOREIGN KEY (reconciled_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_batches
    ADD CONSTRAINT payout_batches_approved_by_user_id_fkey FOREIGN KEY (approved_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_batches
    ADD CONSTRAINT payout_batches_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_calculations
    ADD CONSTRAINT payout_calculations_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.campaign_assignments(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_calculations
    ADD CONSTRAINT payout_calculations_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_calculations
    ADD CONSTRAINT payout_calculations_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_calculations
    ADD CONSTRAINT payout_calculations_impression_estimate_id_fkey FOREIGN KEY (impression_estimate_id) REFERENCES public.impression_estimates(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_calculations
    ADD CONSTRAINT payout_calculations_payout_rule_id_fkey FOREIGN KEY (payout_rule_id) REFERENCES public.campaign_payout_rules(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_calculations
    ADD CONSTRAINT payout_calculations_trip_analytics_id_fkey FOREIGN KEY (trip_analytics_id) REFERENCES public.trip_analytics(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_calculations
    ADD CONSTRAINT payout_calculations_trip_session_id_fkey FOREIGN KEY (trip_session_id) REFERENCES public.trip_sessions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_calculations
    ADD CONSTRAINT payout_calculations_vehicle_id_fkey FOREIGN KEY (vehicle_id) REFERENCES public.vehicles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_correction_orders
    ADD CONSTRAINT payout_correction_orders_approved_by_user_id_fkey FOREIGN KEY (approved_by_user_id) REFERENCES public.users(id);
""",
    r"""
ALTER TABLE ONLY public.payout_correction_orders
    ADD CONSTRAINT payout_correction_orders_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.payout_correction_orders
    ADD CONSTRAINT payout_correction_orders_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);
""",
    r"""
ALTER TABLE ONLY public.payout_correction_orders
    ADD CONSTRAINT payout_correction_orders_executed_by_user_id_fkey FOREIGN KEY (executed_by_user_id) REFERENCES public.users(id);
""",
    r"""
ALTER TABLE ONLY public.payout_debt_allocations
    ADD CONSTRAINT payout_debt_allocations_debt_obligation_id_fkey FOREIGN KEY (debt_obligation_id) REFERENCES public.payout_debt_obligations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_debt_allocations
    ADD CONSTRAINT payout_debt_allocations_settlement_id_fkey FOREIGN KEY (settlement_id) REFERENCES public.payout_debt_settlements(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_debt_obligations
    ADD CONSTRAINT payout_debt_obligations_correction_order_id_fkey FOREIGN KEY (correction_order_id) REFERENCES public.payout_correction_orders(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_debt_obligations
    ADD CONSTRAINT payout_debt_obligations_debt_account_id_fkey FOREIGN KEY (debt_account_id) REFERENCES public.driver_currency_debt_accounts(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_debt_obligations
    ADD CONSTRAINT payout_debt_obligations_source_reversal_entry_id_fkey FOREIGN KEY (source_reversal_entry_id) REFERENCES public.earnings_ledger_entries(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_debt_paid_sources
    ADD CONSTRAINT payout_debt_paid_sources_debt_obligation_id_fkey FOREIGN KEY (debt_obligation_id) REFERENCES public.payout_debt_obligations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_debt_paid_sources
    ADD CONSTRAINT payout_debt_paid_sources_paid_ledger_entry_id_fkey FOREIGN KEY (paid_ledger_entry_id) REFERENCES public.earnings_ledger_entries(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_debt_settlements
    ADD CONSTRAINT payout_debt_settlements_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_debt_settlements
    ADD CONSTRAINT payout_debt_settlements_remainder_entry_id_fkey FOREIGN KEY (remainder_entry_id) REFERENCES public.earnings_ledger_entries(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_debt_settlements
    ADD CONSTRAINT payout_debt_settlements_source_credit_entry_id_fkey FOREIGN KEY (source_credit_entry_id) REFERENCES public.earnings_ledger_entries(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_line_reconciliation_events
    ADD CONSTRAINT payout_line_reconciliation_events_line_id_fkey FOREIGN KEY (line_id) REFERENCES public.payout_batch_lines(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_line_reconciliation_events
    ADD CONSTRAINT payout_line_reconciliation_events_reconciled_by_user_id_fkey FOREIGN KEY (reconciled_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_provider_event_processing_attempts
    ADD CONSTRAINT payout_provider_event_processing_a_reconciliation_event_id_fkey FOREIGN KEY (reconciliation_event_id) REFERENCES public.payout_line_reconciliation_events(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_provider_event_processing_attempts
    ADD CONSTRAINT payout_provider_event_processing_attempt_provider_event_id_fkey FOREIGN KEY (provider_event_id) REFERENCES public.payout_provider_events(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_recovery_incidents
    ADD CONSTRAINT payout_recovery_incidents_chain_root_line_id_fkey FOREIGN KEY (chain_root_line_id) REFERENCES public.payout_batch_lines(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_recovery_incidents
    ADD CONSTRAINT payout_recovery_incidents_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_recovery_incidents
    ADD CONSTRAINT payout_recovery_incidents_exposure_line_id_fkey FOREIGN KEY (exposure_line_id) REFERENCES public.payout_batch_lines(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_recovery_incidents
    ADD CONSTRAINT payout_recovery_incidents_ledger_entry_id_fkey FOREIGN KEY (ledger_entry_id) REFERENCES public.earnings_ledger_entries(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_recovery_incidents
    ADD CONSTRAINT payout_recovery_incidents_source_fraud_flag_id_fkey FOREIGN KEY (source_fraud_flag_id) REFERENCES public.fraud_flags(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_recovery_incidents
    ADD CONSTRAINT payout_recovery_incidents_source_reversal_entry_id_fkey FOREIGN KEY (source_reversal_entry_id) REFERENCES public.earnings_ledger_entries(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_submission_attempts
    ADD CONSTRAINT payout_submission_attempts_intent_id_fkey FOREIGN KEY (intent_id) REFERENCES public.payout_submission_intents(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_submission_intents
    ADD CONSTRAINT payout_submission_intents_payout_batch_line_id_fkey FOREIGN KEY (payout_batch_line_id) REFERENCES public.payout_batch_lines(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.payout_submission_intents
    ADD CONSTRAINT payout_submission_intents_requested_by_user_id_fkey FOREIGN KEY (requested_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.phone_verification_challenges
    ADD CONSTRAINT phone_verification_challenges_phone_version_id_fkey FOREIGN KEY (phone_version_id) REFERENCES public.driver_phone_versions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.phone_verification_challenges
    ADD CONSTRAINT phone_verification_challenges_verified_by_user_id_fkey FOREIGN KEY (verified_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.production_starts
    ADD CONSTRAINT production_starts_authorization_id_fkey FOREIGN KEY (authorization_id) REFERENCES public.campaign_financial_authorizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.production_starts
    ADD CONSTRAINT production_starts_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.production_starts
    ADD CONSTRAINT production_starts_started_by_user_id_fkey FOREIGN KEY (started_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.production_starts
    ADD CONSTRAINT production_starts_waiver_id_fkey FOREIGN KEY (waiver_id) REFERENCES public.expedited_production_waivers(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.quarantined_ping_batches
    ADD CONSTRAINT quarantined_ping_batches_applied_batch_id_fkey FOREIGN KEY (applied_batch_id) REFERENCES public.location_ping_batches(id) ON DELETE SET NULL;
""",
    r"""
ALTER TABLE ONLY public.quarantined_ping_batches
    ADD CONSTRAINT quarantined_ping_batches_resolved_by_user_id_fkey FOREIGN KEY (resolved_by_user_id) REFERENCES public.users(id);
""",
    r"""
ALTER TABLE ONLY public.quarantined_ping_batches
    ADD CONSTRAINT quarantined_ping_batches_trip_session_id_fkey FOREIGN KEY (trip_session_id) REFERENCES public.trip_sessions(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.receipt_allocations
    ADD CONSTRAINT receipt_allocations_allocated_by_user_id_fkey FOREIGN KEY (allocated_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.receipt_allocations
    ADD CONSTRAINT receipt_allocations_commercial_terms_id_fkey FOREIGN KEY (commercial_terms_id) REFERENCES public.commercial_terms(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.receipt_allocations
    ADD CONSTRAINT receipt_allocations_receipt_id_fkey FOREIGN KEY (receipt_id) REFERENCES public.payment_receipts(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.receipt_lifecycle_events
    ADD CONSTRAINT receipt_lifecycle_events_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.receipt_lifecycle_events
    ADD CONSTRAINT receipt_lifecycle_events_receipt_id_fkey FOREIGN KEY (receipt_id) REFERENCES public.payment_receipts(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.receipt_reconciliations
    ADD CONSTRAINT receipt_reconciliations_receipt_id_fkey FOREIGN KEY (receipt_id) REFERENCES public.payment_receipts(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.receipt_reconciliations
    ADD CONSTRAINT receipt_reconciliations_reconciled_by_user_id_fkey FOREIGN KEY (reconciled_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.refund_settlements
    ADD CONSTRAINT refund_settlements_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.refund_settlements
    ADD CONSTRAINT refund_settlements_commercial_terms_id_fkey FOREIGN KEY (commercial_terms_id) REFERENCES public.commercial_terms(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.refund_settlements
    ADD CONSTRAINT refund_settlements_production_start_id_fkey FOREIGN KEY (production_start_id) REFERENCES public.production_starts(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.refund_settlements
    ADD CONSTRAINT refund_settlements_receipt_id_fkey FOREIGN KEY (receipt_id) REFERENCES public.payment_receipts(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.refund_settlements
    ADD CONSTRAINT refund_settlements_recorded_by_user_id_fkey FOREIGN KEY (recorded_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.refund_settlements
    ADD CONSTRAINT refund_settlements_waiver_id_fkey FOREIGN KEY (waiver_id) REFERENCES public.expedited_production_waivers(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.report_artifacts
    ADD CONSTRAINT report_artifacts_report_issuance_id_fkey FOREIGN KEY (report_issuance_id) REFERENCES public.report_issuances(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.report_artifacts
    ADD CONSTRAINT report_artifacts_stored_file_id_fkey FOREIGN KEY (stored_file_id) REFERENCES public.stored_files(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.report_issuances
    ADD CONSTRAINT report_issuances_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.report_issuances
    ADD CONSTRAINT report_issuances_measurement_run_id_fkey FOREIGN KEY (measurement_run_id) REFERENCES public.measurement_runs(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.report_issuances
    ADD CONSTRAINT report_issuances_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.report_issuances
    ADD CONSTRAINT report_issuances_reissue_of_id_fkey FOREIGN KEY (reissue_of_id) REFERENCES public.report_issuances(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.report_issuances
    ADD CONSTRAINT report_issuances_requested_by_user_id_fkey FOREIGN KEY (requested_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.report_publication_intents
    ADD CONSTRAINT report_publication_intents_report_issuance_id_fkey FOREIGN KEY (report_issuance_id) REFERENCES public.report_issuances(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.report_publication_writes
    ADD CONSTRAINT report_publication_writes_publication_intent_id_fkey FOREIGN KEY (publication_intent_id) REFERENCES public.report_publication_intents(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_events
    ADD CONSTRAINT retargeting_source_events_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.retargeting_sources(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_idempotency
    ADD CONSTRAINT retargeting_source_idempotency_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_idempotency
    ADD CONSTRAINT retargeting_source_idempotency_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.retargeting_sources(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_link_events
    ADD CONSTRAINT retargeting_source_link_events_link_id_fkey FOREIGN KEY (link_id) REFERENCES public.retargeting_source_links(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_link_idempotency
    ADD CONSTRAINT retargeting_source_link_idempotency_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_link_idempotency
    ADD CONSTRAINT retargeting_source_link_idempotency_link_id_fkey FOREIGN KEY (link_id) REFERENCES public.retargeting_source_links(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_links
    ADD CONSTRAINT retargeting_source_links_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_links
    ADD CONSTRAINT retargeting_source_links_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_links
    ADD CONSTRAINT retargeting_source_links_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.retargeting_sources(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.retargeting_source_links
    ADD CONSTRAINT retargeting_source_links_zone_id_fkey FOREIGN KEY (zone_id) REFERENCES public.campaign_zones(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.retargeting_sources
    ADD CONSTRAINT retargeting_sources_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.advertiser_organizations(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.route_replay_signatures
    ADD CONSTRAINT route_replay_signatures_trip_analytics_id_fkey FOREIGN KEY (trip_analytics_id) REFERENCES public.trip_analytics(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.route_replay_signatures
    ADD CONSTRAINT route_replay_signatures_trip_session_id_fkey FOREIGN KEY (trip_session_id) REFERENCES public.trip_sessions(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.stored_object_deletions
    ADD CONSTRAINT stored_object_deletions_stored_file_id_fkey FOREIGN KEY (stored_file_id) REFERENCES public.stored_files(id) ON DELETE SET NULL;
""",
    r"""
ALTER TABLE ONLY public.stored_object_deletions
    ADD CONSTRAINT stored_object_deletions_upload_intent_id_fkey FOREIGN KEY (upload_intent_id) REFERENCES public.file_upload_intents(id) ON DELETE SET NULL;
""",
    r"""
ALTER TABLE ONLY public.trip_analytics
    ADD CONSTRAINT trip_analytics_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.campaign_assignments(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.trip_analytics
    ADD CONSTRAINT trip_analytics_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.trip_analytics
    ADD CONSTRAINT trip_analytics_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.trip_analytics
    ADD CONSTRAINT trip_analytics_trip_session_id_fkey FOREIGN KEY (trip_session_id) REFERENCES public.trip_sessions(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.trip_analytics
    ADD CONSTRAINT trip_analytics_vehicle_id_fkey FOREIGN KEY (vehicle_id) REFERENCES public.vehicles(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.trip_evidence_manifest_entries
    ADD CONSTRAINT trip_evidence_manifest_entries_trip_session_id_fkey FOREIGN KEY (trip_session_id) REFERENCES public.trip_sessions(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.trip_sessions
    ADD CONSTRAINT trip_sessions_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.campaign_assignments(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.trip_sessions
    ADD CONSTRAINT trip_sessions_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.trip_sessions
    ADD CONSTRAINT trip_sessions_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.trip_sessions
    ADD CONSTRAINT trip_sessions_started_by_user_id_fkey FOREIGN KEY (started_by_user_id) REFERENCES public.users(id);
""",
    r"""
ALTER TABLE ONLY public.trip_sessions
    ADD CONSTRAINT trip_sessions_vehicle_id_fkey FOREIGN KEY (vehicle_id) REFERENCES public.vehicles(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.vehicle_evidence_review_decisions
    ADD CONSTRAINT vehicle_evidence_review_decisions_decided_by_user_id_fkey FOREIGN KEY (decided_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.vehicle_evidence_review_decisions
    ADD CONSTRAINT vehicle_evidence_review_decisions_submission_id_fkey FOREIGN KEY (submission_id) REFERENCES public.vehicle_evidence_submissions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.vehicles
    ADD CONSTRAINT vehicles_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE CASCADE;
""",
    r"""
ALTER TABLE ONLY public.whatsapp_consents
    ADD CONSTRAINT whatsapp_consents_driver_profile_id_fkey FOREIGN KEY (driver_profile_id) REFERENCES public.driver_profiles(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.whatsapp_consents
    ADD CONSTRAINT whatsapp_consents_granted_by_user_id_fkey FOREIGN KEY (granted_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.whatsapp_consents
    ADD CONSTRAINT whatsapp_consents_phone_version_id_fkey FOREIGN KEY (phone_version_id) REFERENCES public.driver_phone_versions(id) ON DELETE RESTRICT;
""",
    r"""
ALTER TABLE ONLY public.whatsapp_consents
    ADD CONSTRAINT whatsapp_consents_withdrawn_by_user_id_fkey FOREIGN KEY (withdrawn_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;
""",
)

PARTITION_MONTHS = (
    "2026_07",
    "2026_08",
    "2026_09",
    "2026_10",
    "2026_11",
    "2026_12",
    "2027_01",
    "2027_02",
)
PARTITION_BOUNDS = (
    "2026-07-01 00:00:00+00",
    "2026-08-01 00:00:00+00",
    "2026-09-01 00:00:00+00",
    "2026-10-01 00:00:00+00",
    "2026-11-01 00:00:00+00",
    "2026-12-01 00:00:00+00",
    "2027-01-01 00:00:00+00",
    "2027-02-01 00:00:00+00",
    "2027-03-01 00:00:00+00",
)


def upgrade() -> None:
    bind = op.get_bind()
    op.alter_column("alembic_version", "version_num", type_=sa.String(64))
    month = bind.execute(
        sa.text("SELECT date_trunc('month', now() AT TIME ZONE 'UTC')")
    ).scalar_one()
    base = month.year * 12 + month.month - 1
    substitutions = {}
    for offset, original in enumerate(PARTITION_MONTHS, start=-3):
        year, zero_month = divmod(base + offset, 12)
        substitutions[f"location_pings_p{original}"] = (
            f"location_pings_p{year:04d}_{zero_month + 1:02d}"
        )
    # The final upper bound is one month beyond the final named partition.
    for offset, original in enumerate(PARTITION_BOUNDS, start=-3):
        year, zero_month = divmod(base + offset, 12)
        substitutions[original] = f"{year:04d}-{zero_month + 1:02d}-01 00:00:00+00"
    pattern = re.compile("|".join(re.escape(key) for key in substitutions))
    for statement in SCHEMA_DDL:
        statement = pattern.sub(lambda match: substitutions[match.group()], statement)
        # Escape SQLAlchemy bind markers inside immutable SQL function/string bodies.
        op.execute(sa.text(statement.replace(":", r"\:")))
    op.execute("SET search_path TO public")
    password_hash = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1).hash(
        secrets.token_urlsafe(96)
    )
    bind.execute(
        sa.text(
            "INSERT INTO users (id, email, password_hash, full_name, role, status) VALUES ('6c0de000-0000-4000-8000-000000000001', 'automatic-payouts@cardvert.invalid', :password_hash, 'Cardvert (automatic payouts)', 'admin', 'disabled')"
        ),
        {"password_hash": password_hash},
    )
    bind.execute(
        sa.text(
            "INSERT INTO payout_automatic_controls (id, paused, actor_password_fingerprint) VALUES (1, false, :fingerprint)"
        ),
        {"fingerprint": hashlib.sha256(password_hash.encode()).hexdigest()},
    )


def downgrade() -> None:
    raise RuntimeError(
        "Recreate the disposable development database; the baseline has no predecessor"
    )
