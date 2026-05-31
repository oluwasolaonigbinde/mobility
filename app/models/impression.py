from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TrafficDensityProfileType(StrEnum):
    DEFAULT = "default"
    URBAN = "urban"
    SUBURBAN = "suburban"
    HIGHWAY = "highway"
    CUSTOM = "custom"


class TrafficDensityProfileStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class ImpressionEstimateStatus(StrEnum):
    ESTIMATED = "estimated"
    INSUFFICIENT_DATA = "insufficient_data"
    EXCLUDED = "excluded"


class TrafficDensityProfile(Base):
    __tablename__ = "traffic_density_profiles"
    __table_args__ = (
        CheckConstraint(
            "profile_type IN ('default', 'urban', 'suburban', 'highway', 'custom')",
            name="ck_traffic_density_profiles_profile_type",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_traffic_density_profiles_status",
        ),
        CheckConstraint(
            "traffic_density_per_km >= 0",
            name="ck_traffic_density_profiles_density_non_negative",
        ),
        CheckConstraint(
            "dwell_impressions_per_minute >= 0",
            name="ck_traffic_density_profiles_dwell_non_negative",
        ),
        CheckConstraint(
            "road_category_weight >= 0",
            name="ck_traffic_density_profiles_road_weight_non_negative",
        ),
        CheckConstraint(
            "morning_weight >= 0",
            name="ck_traffic_density_profiles_morning_weight_non_negative",
        ),
        CheckConstraint(
            "midday_weight >= 0",
            name="ck_traffic_density_profiles_midday_weight_non_negative",
        ),
        CheckConstraint(
            "evening_weight >= 0",
            name="ck_traffic_density_profiles_evening_weight_non_negative",
        ),
        CheckConstraint(
            "night_weight >= 0",
            name="ck_traffic_density_profiles_night_weight_non_negative",
        ),
        CheckConstraint(
            "target_zone_weight >= 0",
            name="ck_traffic_density_profiles_target_weight_non_negative",
        ),
        CheckConstraint(
            "bonus_zone_weight >= 0",
            name="ck_traffic_density_profiles_bonus_weight_non_negative",
        ),
        CheckConstraint(
            "exclusion_zone_weight >= 0",
            name="ck_traffic_density_profiles_exclusion_weight_non_negative",
        ),
        Index("ix_traffic_density_profiles_status", "status"),
        Index("ix_traffic_density_profiles_profile_type", "profile_type"),
        Index(
            "uq_traffic_density_profiles_active_default",
            "is_default",
            unique=True,
            sqlite_where=text("is_default = 1 AND status = 'active'"),
            postgresql_where=text("is_default = true AND status = 'active'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    profile_type: Mapped[str] = mapped_column(String(32), nullable=False)
    traffic_density_per_km: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    dwell_impressions_per_minute: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    road_category_weight: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=Decimal("1.0"),
        server_default=text("1.0"),
        nullable=False,
    )
    morning_weight: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=Decimal("1.0"),
        server_default=text("1.0"),
        nullable=False,
    )
    midday_weight: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=Decimal("1.0"),
        server_default=text("1.0"),
        nullable=False,
    )
    evening_weight: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=Decimal("1.0"),
        server_default=text("1.0"),
        nullable=False,
    )
    night_weight: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=Decimal("0.7"),
        server_default=text("0.7"),
        nullable=False,
    )
    target_zone_weight: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=Decimal("1.0"),
        server_default=text("1.0"),
        nullable=False,
    )
    bonus_zone_weight: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=Decimal("1.25"),
        server_default=text("1.25"),
        nullable=False,
    )
    exclusion_zone_weight: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        default=Decimal("0.0"),
        server_default=text("0.0"),
        nullable=False,
    )
    is_default: Mapped[bool] = mapped_column(
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    profile_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ImpressionEstimate(Base):
    __tablename__ = "impression_estimates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('estimated', 'insufficient_data', 'excluded')",
            name="ck_impression_estimates_status",
        ),
        CheckConstraint(
            "estimated_impressions >= 0",
            name="ck_impression_estimates_estimated_non_negative",
        ),
        CheckConstraint(
            "base_distance_impressions >= 0",
            name="ck_impression_estimates_base_non_negative",
        ),
        CheckConstraint(
            "dwell_impressions >= 0",
            name="ck_impression_estimates_dwell_non_negative",
        ),
        CheckConstraint(
            "target_zone_impressions >= 0",
            name="ck_impression_estimates_target_non_negative",
        ),
        CheckConstraint(
            "bonus_zone_impressions >= 0",
            name="ck_impression_estimates_bonus_non_negative",
        ),
        CheckConstraint(
            "exclusion_zone_adjustment >= 0",
            name="ck_impression_estimates_exclusion_non_negative",
        ),
        CheckConstraint(
            "quality_multiplier >= 0 AND quality_multiplier <= 1",
            name="ck_impression_estimates_quality_multiplier_range",
        ),
        CheckConstraint(
            "fraud_adjustment_multiplier >= 0 AND fraud_adjustment_multiplier <= 1",
            name="ck_impression_estimates_fraud_multiplier_range",
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="ck_impression_estimates_confidence_score_range",
        ),
        UniqueConstraint(
            "trip_session_id",
            "formula_version",
            "traffic_density_profile_id",
            name="uq_impression_estimates_trip_formula_profile",
        ),
        Index("ix_impression_estimates_trip_analytics_id", "trip_analytics_id"),
        Index("ix_impression_estimates_campaign_id", "campaign_id"),
        Index("ix_impression_estimates_assignment_id", "assignment_id"),
        Index("ix_impression_estimates_driver_profile_id", "driver_profile_id"),
        Index("ix_impression_estimates_vehicle_id", "vehicle_id"),
        Index("ix_impression_estimates_campaign_estimated_at", "campaign_id", "estimated_at"),
        Index("ix_impression_estimates_campaign_status", "campaign_id", "status"),
        Index("ix_impression_estimates_traffic_density_profile_id", "traffic_density_profile_id"),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    trip_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("trip_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    trip_analytics_id: Mapped[UUID] = mapped_column(
        ForeignKey("trip_analytics.id", ondelete="CASCADE"),
        nullable=False,
    )
    assignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaign_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    campaign_id: Mapped[UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    driver_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("driver_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    vehicle_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
    )
    traffic_density_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("traffic_density_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    formula_version: Mapped[str] = mapped_column(
        Text,
        default="impressions_v1",
        server_default=text("'impressions_v1'"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    estimated_impressions: Mapped[Decimal] = mapped_column(
        Numeric(16, 2),
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    base_distance_impressions: Mapped[Decimal] = mapped_column(
        Numeric(16, 2),
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    dwell_impressions: Mapped[Decimal] = mapped_column(
        Numeric(16, 2),
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    target_zone_impressions: Mapped[Decimal] = mapped_column(
        Numeric(16, 2),
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    bonus_zone_impressions: Mapped[Decimal] = mapped_column(
        Numeric(16, 2),
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    exclusion_zone_adjustment: Mapped[Decimal] = mapped_column(
        Numeric(16, 2),
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    quality_multiplier: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    fraud_adjustment_multiplier: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    estimate_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
