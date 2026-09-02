"""Add immutable effective traffic-density profile revisions."""

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0079_traffic_density_profile_revisions"
down_revision: str | Sequence[str] | None = "0078_campaign_assignment_driver_active"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IMMUTABLE_TRIGGER = "trg_traffic_density_profile_revision_immutable"
VALIDATE_TRIGGER = "trg_traffic_density_profile_revision_validate"


def _fingerprint_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _fingerprint_value(item) for key, item in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [_fingerprint_value(item) for item in value]
    return value


def _fingerprint(row: sa.RowMapping) -> str:
    payload = {
        "lineage_id": row["id"],
        "revision": 1,
        "effective_from": row["created_at"],
        "name": row["name"],
        "description": row["description"],
        "profile_type": row["profile_type"],
        "traffic_density_per_km": row["traffic_density_per_km"],
        "dwell_impressions_per_minute": row["dwell_impressions_per_minute"],
        "road_category_weight": row["road_category_weight"],
        "morning_weight": row["morning_weight"],
        "midday_weight": row["midday_weight"],
        "evening_weight": row["evening_weight"],
        "night_weight": row["night_weight"],
        "target_zone_weight": row["target_zone_weight"],
        "bonus_zone_weight": row["bonus_zone_weight"],
        "exclusion_zone_weight": row["exclusion_zone_weight"],
        "profile_metadata": row["metadata"],
    }
    encoded = json.dumps(
        _fingerprint_value(payload),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def upgrade() -> None:
    op.add_column(
        "traffic_density_profiles",
        sa.Column("lineage_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "traffic_density_profiles",
        sa.Column("revision", sa.Integer(), nullable=True),
    )
    op.add_column(
        "traffic_density_profiles",
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "traffic_density_profiles",
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "traffic_density_profiles",
        sa.Column("value_fingerprint", sa.String(length=64), nullable=True),
    )

    connection = op.get_bind()
    profiles = connection.execute(
        sa.text(
            """
            SELECT id, name, description, profile_type,
                   traffic_density_per_km, dwell_impressions_per_minute,
                   road_category_weight, morning_weight, midday_weight,
                   evening_weight, night_weight, target_zone_weight,
                   bonus_zone_weight, exclusion_zone_weight, metadata, created_at
            FROM traffic_density_profiles
            ORDER BY id
            """
        )
    ).mappings()
    for profile in profiles:
        fingerprint = _fingerprint(profile)
        connection.execute(
            sa.text(
                """
                UPDATE traffic_density_profiles
                SET lineage_id = id,
                    revision = 1,
                    effective_from = created_at,
                    value_fingerprint = :fingerprint
                WHERE id = :profile_id
                """
            ),
            {"profile_id": profile["id"], "fingerprint": fingerprint},
        )
        connection.execute(
            sa.text(
                """
                UPDATE impression_estimates
                SET metadata = jsonb_set(
                    metadata,
                    '{traffic_density_profile_fingerprint}',
                    to_jsonb(CAST(:fingerprint AS text)),
                    true
                )
                WHERE traffic_density_profile_id = :profile_id
                """
            ),
            {"profile_id": profile["id"], "fingerprint": fingerprint},
        )

    op.alter_column("traffic_density_profiles", "lineage_id", nullable=False)
    op.alter_column("traffic_density_profiles", "revision", nullable=False)
    op.alter_column("traffic_density_profiles", "effective_from", nullable=False)
    op.alter_column("traffic_density_profiles", "value_fingerprint", nullable=False)
    op.create_foreign_key(
        "fk_traffic_density_profiles_supersedes_id",
        "traffic_density_profiles",
        "traffic_density_profiles",
        ["supersedes_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_traffic_density_profiles_lineage_revision",
        "traffic_density_profiles",
        ["lineage_id", "revision"],
    )
    op.create_unique_constraint(
        "uq_traffic_density_profiles_supersedes_id",
        "traffic_density_profiles",
        ["supersedes_id"],
    )
    op.create_check_constraint(
        "ck_traffic_density_profiles_revision_positive",
        "traffic_density_profiles",
        "revision >= 1",
    )
    op.create_check_constraint(
        "ck_traffic_density_profiles_value_fingerprint_length",
        "traffic_density_profiles",
        "length(value_fingerprint) = 64",
    )
    op.create_index(
        "ix_traffic_density_profiles_lineage_effective",
        "traffic_density_profiles",
        ["lineage_id", "effective_from"],
    )

    op.execute(
        sa.text(
            """
            CREATE FUNCTION validate_traffic_density_profile_revision()
            RETURNS trigger AS $$
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
            $$ LANGUAGE plpgsql
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER {VALIDATE_TRIGGER}
            BEFORE INSERT ON traffic_density_profiles
            FOR EACH ROW EXECUTE FUNCTION validate_traffic_density_profile_revision()
            """
        )
    )
    immutable_columns = (
        "id, lineage_id, revision, effective_from, supersedes_id, value_fingerprint, "
        "name, description, profile_type, traffic_density_per_km, "
        "dwell_impressions_per_minute, road_category_weight, morning_weight, "
        "midday_weight, evening_weight, night_weight, target_zone_weight, "
        "bonus_zone_weight, exclusion_zone_weight, metadata"
    )
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION reject_traffic_density_profile_revision_mutation()
            RETURNS trigger AS $$
            BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION USING ERRCODE = '55000',
                  MESSAGE = 'traffic density profile revisions cannot be deleted';
              END IF;
              IF ROW(NEW.{immutable_columns.replace(", ", ", NEW.")})
                 IS DISTINCT FROM ROW(OLD.{immutable_columns.replace(", ", ", OLD.")}) THEN
                RAISE EXCEPTION USING ERRCODE = '55000',
                  MESSAGE = 'traffic density profile revision values are immutable';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TRIGGER {IMMUTABLE_TRIGGER}
            BEFORE UPDATE OR DELETE ON traffic_density_profiles
            FOR EACH ROW EXECUTE FUNCTION reject_traffic_density_profile_revision_mutation()
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("LOCK TABLE traffic_density_profiles IN ACCESS EXCLUSIVE MODE"))
    populated_successors = (
        op.get_bind()
        .execute(
            sa.text("SELECT EXISTS (SELECT 1 FROM traffic_density_profiles WHERE revision > 1)")
        )
        .scalar_one()
    )
    if populated_successors:
        raise RuntimeError("Refusing to drop versioned traffic-density profile history")

    op.execute(sa.text(f"DROP TRIGGER {IMMUTABLE_TRIGGER} ON traffic_density_profiles"))
    op.execute(sa.text(f"DROP TRIGGER {VALIDATE_TRIGGER} ON traffic_density_profiles"))
    op.execute(sa.text("DROP FUNCTION reject_traffic_density_profile_revision_mutation()"))
    op.execute(sa.text("DROP FUNCTION validate_traffic_density_profile_revision()"))
    op.drop_index(
        "ix_traffic_density_profiles_lineage_effective",
        table_name="traffic_density_profiles",
    )
    op.drop_constraint(
        "ck_traffic_density_profiles_value_fingerprint_length",
        "traffic_density_profiles",
        type_="check",
    )
    op.drop_constraint(
        "ck_traffic_density_profiles_revision_positive",
        "traffic_density_profiles",
        type_="check",
    )
    op.drop_constraint(
        "uq_traffic_density_profiles_supersedes_id",
        "traffic_density_profiles",
        type_="unique",
    )
    op.drop_constraint(
        "uq_traffic_density_profiles_lineage_revision",
        "traffic_density_profiles",
        type_="unique",
    )
    op.drop_constraint(
        "fk_traffic_density_profiles_supersedes_id",
        "traffic_density_profiles",
        type_="foreignkey",
    )
    op.drop_column("traffic_density_profiles", "value_fingerprint")
    op.drop_column("traffic_density_profiles", "supersedes_id")
    op.drop_column("traffic_density_profiles", "effective_from")
    op.drop_column("traffic_density_profiles", "revision")
    op.drop_column("traffic_density_profiles", "lineage_id")
